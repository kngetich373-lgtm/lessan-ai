# actions/reminder.py
# Lessan AI — Persistent Reminders & Alarms
#
# Standard action-module pattern:
#   - single entry-point `reminder(parameters, response, player, session_memory)`
#   - reads args from `parameters`
#   - never raises; returns a friendly result string
#   - uses `player.write_log(...)` when a player is available
#
# Capabilities:
#   - set    (default)  — 'remind me to X at Y', 'set an alarm for 6am',
#                         'remind me in 30 minutes', 'tomorrow 9am', '17:30'
#   - list   / status   — show pending reminders
#   - cancel / delete   — cancel by number (index) or message text
#   - cancel_all / clear — cancel everything pending
#
# Persistence: reminders are stored in memory/reminders.json so they survive
# restarts. A background monitor thread (started by `start_reminder_monitor`,
# or lazily on the first set) fires the local notification/alert when a
# reminder comes due.

import json
import platform
import re
import subprocess
import threading
import time
import uuid
from datetime import datetime, timedelta
from pathlib import Path


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------

def _find_project_root() -> Path:
    """Walks up until we find the directory containing the memory/ folder.
    Works whether this file lives in actions/ or actions/actions/."""
    current = Path(__file__).resolve().parent
    for _ in range(4):
        if (current / "memory").is_dir():
            return current
        if current.parent == current:
            break
        current = current.parent
    return Path(__file__).resolve().parent.parent


BASE_DIR       = _find_project_root()
REMINDER_PATH  = BASE_DIR / "memory" / "reminders.json"
_lock          = threading.Lock()


def _load_reminders() -> list:
    if not REMINDER_PATH.exists():
        return []
    with _lock:
        try:
            data = json.loads(REMINDER_PATH.read_text(encoding="utf-8"))
            return data if isinstance(data, list) else []
        except Exception as e:
            print(f"[Reminder] ⚠️ Load error: {e}")
            return []


def _save_reminders(reminders: list) -> None:
    with _lock:
        try:
            REMINDER_PATH.parent.mkdir(parents=True, exist_ok=True)
            REMINDER_PATH.write_text(
                json.dumps(reminders, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception as e:
            print(f"[Reminder] ⚠️ Save error: {e}")


# ---------------------------------------------------------------------------
# Time parsing (no external deps)
# ---------------------------------------------------------------------------

_AM_PM_RE    = re.compile(r"^(\d{1,2})(?::(\d{2}))?\s*(am|pm)$", re.I)
_24H_RE      = re.compile(r"^(\d{1,2}):(\d{2})$")
_BARE_HOUR_RE = re.compile(r"^(\d{1,2})$")
_REL_HALF_RE = re.compile(
    r"^(half|quarter)\s+(?:of\s+)?(?:an?\s+)?(hours?|minutes?|seconds?)$", re.I
)
_REL_ONE_RE  = re.compile(r"^(an?)\s+(hour|minute|second)s?$", re.I)
_REL_NUM_RE  = re.compile(
    r"^(\d+(?:\.\d+)?)\s*(hours?|hrs?|h|minutes?|mins?|m|seconds?|secs?|s)$", re.I
)


def _time_today(text: str) -> datetime | None:
    """Parses a clock time ('5pm', '17:30', '8:00 am', 'at 7', 'noon') as a
    datetime on TODAY (no auto-shift). Returns None if unparseable."""
    t = (text or "").strip()
    if not t:
        return None
    t = re.sub(r"^\s*at\s+", "", t, flags=re.I).strip()

    now = datetime.now()
    low = t.lower()

    if low in ("noon", "12pm", "12:00pm", "12:00 pm"):
        return now.replace(hour=12, minute=0, second=0, microsecond=0)
    if low in ("midnight", "12am", "12:00am", "12:00 am"):
        return now.replace(hour=0, minute=0, second=0, microsecond=0)

    m = _AM_PM_RE.match(t)
    if m:
        hour = int(m.group(1))
        minute = int(m.group(2)) if m.group(2) else 0
        if not (1 <= hour <= 12) or minute > 59:
            return None
        if hour == 12:
            hour = 0
        if m.group(3).lower() == "pm":
            hour += 12
        return now.replace(hour=hour, minute=minute, second=0, microsecond=0)

    m = _24H_RE.match(t)
    if m:
        hour, minute = int(m.group(1)), int(m.group(2))
        if hour > 23 or minute > 59:
            return None
        return now.replace(hour=hour, minute=minute, second=0, microsecond=0)

    m = _BARE_HOUR_RE.match(t)
    if m:
        hour = int(m.group(1))
        if hour > 23:
            return None
        return now.replace(hour=hour, minute=0, second=0, microsecond=0)

    return None


def _parse_time_of_day(text: str) -> datetime | None:
    """Like _time_today but if the time already passed today, rolls to tomorrow."""
    td = _time_today(text)
    if td is None:
        return None
    if td <= datetime.now():
        td += timedelta(days=1)
    return td


def _parse_relative_delta(text: str) -> timedelta | None:
    """Parses 'in 30 minutes', '2 hours', 'half an hour', 'an hour', '10 seconds'."""
    t = (text or "").strip().lower()
    if not t:
        return None
    if t.startswith("in "):
        t = t[3:].strip()
    t = re.sub(r"^at\s+", "", t).strip()

    amount, unit = None, None

    m = _REL_HALF_RE.fullmatch(t)
    if m:
        amount = 0.5 if m.group(1) == "half" else 0.25
        unit = m.group(2)
    else:
        m = _REL_ONE_RE.fullmatch(t)
        if m:
            amount = 1.0
            unit = m.group(2)
        else:
            m = _REL_NUM_RE.fullmatch(t)
            if m:
                amount = float(m.group(1))
                unit = m.group(2)

    if amount is None or unit is None:
        return None

    u = unit.lower()
    if u.startswith("sec") or u == "s":
        return timedelta(seconds=amount)
    if u.startswith("min") or u == "m":
        return timedelta(minutes=amount)
    return timedelta(hours=amount)


_TOMORROW_RE = re.compile(r"^\s*tomorrow(?:\s+(?:at\s+)?(.*))?$", re.I)
_TODAY_RE    = re.compile(r"^\s*today(?:\s+(?:at\s+)?(.*))?$", re.I)


def _parse_when(when: str) -> datetime | None:
    """Parses free-form: 'in 30 minutes', 'tomorrow 9am', '5pm', '17:30',
    'half an hour', 'today at 5pm'..."""
    t = (when or "").strip()
    if not t:
        return None

    # Relative: "in 30 minutes", "2 hours", "half an hour"
    delta = _parse_relative_delta(t)
    if delta is not None:
        return datetime.now() + delta

    # "tomorrow [at] <time>" -> tomorrow at that time (or 9am default)
    m = _TOMORROW_RE.match(t)
    if m:
        time_part = m.group(1)
        if time_part:
            td = _time_today(time_part)
            if td is not None:
                return td + timedelta(days=1)
        return _time_today("9am") + timedelta(days=1)

    # "today [at] <time>"
    m = _TODAY_RE.match(t)
    if m:
        return _time_today(m.group(1)) if m.group(1) else None

    # Plain clock time: "5pm", "17:30", "at 7" (rolls to tomorrow if passed)
    return _parse_time_of_day(t)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def reminder(
    parameters:     dict,
    response:       None = None,
    player:         None = None,
    session_memory: None = None,
) -> str:
    """Sets / lists / cancels persistent reminders and alarms.

    parameters:
        action  : set (default) | list | status | cancel | delete | cancel_all | clear
        when    : natural time — 'in 30 minutes', '5pm', 'tomorrow 9am', '17:30'
        date    : YYYY-MM-DD, 'today', 'tomorrow' (alternative to 'when')
        time    : HH:MM or '5pm' / '8:00 am' (alternative to 'when')
        message : what the reminder/alarm should say
        index   : reminder number from 'list' — used with action 'cancel'
    """
    params = parameters or {}
    action = (params.get("action") or "set").strip().lower()

    if action in ("list", "status"):
        return _list_reminders(player)

    if action in ("cancel", "delete"):
        return _cancel_reminder(params, player)

    if action in ("cancel_all", "clear"):
        return _cancel_all(player)

    # -- set --
    message = (params.get("message") or "").strip() or "Reminder"
    when    = (params.get("when") or "").strip()
    date_str = (params.get("date") or "").strip()
    time_str = (params.get("time") or "").strip()

    target = None
    if when:
        target = _parse_when(when)
    elif time_str:
        if date_str:
            if date_str.lower() in ("today", "now"):
                base_date = datetime.now().date()
            elif date_str.lower() == "tomorrow":
                base_date = (datetime.now() + timedelta(days=1)).date()
            else:
                try:
                    base_date = datetime.strptime(date_str, "%Y-%m-%d").date()
                except ValueError:
                    return "I couldn't understand that date format, sir. Use YYYY-MM-DD, 'today', or 'tomorrow'."
        else:
            base_date = None

        td = _time_today(time_str)
        if td is None:
            return "I couldn't understand that time, sir. Try '5pm', '17:30', or 'in 30 minutes'."

        if base_date is not None:
            target = td.replace(year=base_date.year, month=base_date.month, day=base_date.day)
        else:
            target = _parse_time_of_day(time_str)

    if target is None:
        return (
            "Please tell me when, sir — for example 'in 30 minutes', "
            "'at 5pm', or 'tomorrow at 9am'."
        )

    if target <= datetime.now():
        return "That time is already in the past, sir."

    item = {
        "id":         f"rem_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:4]}",
        "message":    message[:300],
        "due_at":     target.strftime("%Y-%m-%dT%H:%M:%S"),
        "created_at": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
        "status":     "active",
    }

    reminders = _load_reminders()
    reminders.append(item)
    _save_reminders(reminders)

    start_reminder_monitor(player=player)

    human = target.strftime("%A, %B %d at %I:%M %p")
    if player:
        try:
            player.write_log(f"[reminder] set for {human} — {message}")
        except Exception:
            pass

    print(f"[Reminder] 📌 '{message}' scheduled for {human}")
    return f"Done, sir. Reminder set for {human}: {message}"


# ---------------------------------------------------------------------------
# List / cancel management
# ---------------------------------------------------------------------------

def _list_reminders(player=None) -> str:
    active = [r for r in _load_reminders() if r.get("status") == "active"]
    if not active:
        return "You have no pending reminders, sir."

    lines = []
    for i, r in enumerate(active, 1):
        try:
            due = datetime.strptime(r["due_at"], "%Y-%m-%dT%H:%M:%S")
            when_str = due.strftime("%A, %B %d at %I:%M %p")
        except (ValueError, KeyError):
            when_str = r.get("due_at", "?")
        lines.append(f"{i}. {when_str} — {r.get('message', 'Reminder')}")

    if player:
        try:
            player.write_log(f"[reminder] {len(active)} pending")
        except Exception:
            pass

    return "Pending reminders:\n" + "\n".join(lines)


def _cancel_reminder(params: dict, player=None) -> str:
    reminders  = _load_reminders()
    active     = [r for r in reminders if r.get("status") == "active"]
    if not active:
        return "There's nothing to cancel, sir — no pending reminders."

    target_id = None
    index = params.get("index")
    if index is not None:
        try:
            idx = int(index) - 1
            if idx < 0 or idx >= len(active):
                return f"I only found {len(active)} pending reminder(s), sir."
            target_id = active[idx]["id"]
        except (TypeError, ValueError):
            return "That index didn't look right, sir. Use 'list' to see reminder numbers."

    if target_id is None:
        phrase = (params.get("message") or params.get("when") or "").strip().lower()
        if not phrase:
            return "Tell me which reminder to cancel, sir — by number or by its text."
        matches = [
            r["id"] for r in active
            if phrase in (r.get("message", "") or "").lower()
        ]
        if not matches:
            return "I couldn't find a matching reminder, sir."
        target_id = matches[0]

    kept = [r for r in reminders if r["id"] != target_id]
    _save_reminders(kept)

    if player:
        try:
            player.write_log(f"[reminder] cancelled {target_id}")
        except Exception:
            pass

    return "Cancelled that reminder, sir."


def _cancel_all(player=None) -> str:
    reminders = _load_reminders()
    active    = [r for r in reminders if r.get("status") == "active"]
    if not active:
        return "There's nothing to cancel, sir — no pending reminders."

    kept = [r for r in reminders if r.get("status") != "active"]
    _save_reminders(kept)

    if player:
        try:
            player.write_log(f"[reminder] cancelled all ({len(active)})")
        except Exception:
            pass

    return f"Cancelled all {len(active)} pending reminder(s), sir."


# ---------------------------------------------------------------------------
# Background monitor + local alerts
# ---------------------------------------------------------------------------

_player_lock = threading.Lock()
_player       = None
_monitor      = None
_monitor_lock = threading.Lock()

CHECK_INTERVAL_SECONDS = 15


def start_reminder_monitor(player=None) -> None:
    """Starts the background daemon thread that fires due reminders.
    Safe to call multiple times / at app startup (persisted reminders fire
    even if no new reminder was set this session)."""
    global _player, _monitor
    with _monitor_lock:
        with _player_lock:
            if player is not None:
                _player = player
        if _monitor is None or not _monitor.is_alive():
            _monitor = threading.Thread(
                name="reminder-monitor",
                target=_monitor_loop,
                daemon=True,
            )
            _monitor.start()
            print("[Reminder] 🔔 Monitor started")


def _monitor_loop() -> None:
    while True:
        try:
            _check_due_reminders()
        except Exception as e:
            print(f"[Reminder] ⚠️ Monitor error: {e}")
        time.sleep(CHECK_INTERVAL_SECONDS)


def _check_due_reminders() -> int:
    """Fires every due reminder, marks it triggered, persists. Returns count fired."""
    now      = datetime.now()
    reminders = _load_reminders()
    changed  = False
    fired    = 0

    for r in reminders:
        if r.get("status") != "active":
            continue
        try:
            due = datetime.strptime(r["due_at"], "%Y-%m-%dT%H:%M:%S")
        except (ValueError, TypeError):
            continue
        if due <= now:
            _fire_alert(r)
            r["status"]       = "triggered"
            r["triggered_at"] = now.strftime("%Y-%m-%dT%H:%M:%S")
            changed = True
            fired   += 1

    if changed:
        _save_reminders(reminders)

    return fired


def _fire_alert(item: dict) -> None:
    message = item.get("message", "Reminder")
    print(f"[Reminder] 🔔 ALERT: {message}")

    try:
        system = platform.system()
        if system == "Windows":
            _alert_windows(message)
        elif system == "Darwin":
            _alert_macos(message)
        else:
            _alert_linux(message)
    except Exception as e:
        print(f"[Reminder] ⚠️ Alert error: {e}")

    with _player_lock:
        player = _player
    if player is not None:
        try:
            player.write_log(f"[reminder] 🔔 {message}")
        except Exception:
            pass


def _alert_linux(message: str) -> None:
    try:
        subprocess.run(["notify-send", "Lessan Reminder", message], check=False, timeout=5)
    except FileNotFoundError:
        print(f"\n🔔 [Lessan Reminder] {message}\n")
    except Exception:
        pass

    try:
        sound = "/usr/share/sounds/freedesktop/stereo/complete.oga"
        subprocess.run(["paplay", sound], check=False, timeout=10)
    except FileNotFoundError:
        pass
    except Exception:
        pass


def _alert_windows(message: str) -> None:
    try:
        import winsound
        for freq in (800, 1000, 1200):
            winsound.Beep(freq, 200)
            time.sleep(0.1)
    except Exception:
        pass

    try:
        import importlib
        win10toast = importlib.import_module("win10toast")  # type: ignore[import-not-found]  # Windows-only pkg
        win10toast.ToastNotifier().show_toast(
            "Lessan Reminder", message, duration=15, threaded=False
        )
    except Exception:
        try:
            subprocess.run(["msg", "*", "/TIME:30", message], shell=True, check=False)
        except Exception:
            pass


def _alert_macos(message: str) -> None:
    try:
        subprocess.run(
            ["osascript", "-e",
             f'display notification "{message}" with title "Lessan Reminder" sound name "Glass"'],
            check=False, timeout=10,
        )
    except Exception:
        pass