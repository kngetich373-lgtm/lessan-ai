# memory/conversation_memory.py
# Lessan AI — Conversation Memory
#
# Stores what was DISCUSSED (topics, summaries, key points per session),
# separate from long_term.json which stores distilled facts about the user.
#
# Two recall paths:
#   1. Recent context injected into the system prompt automatically.
#   2. On-demand lookup via the conversation_recall tool
#      ("what did we talk about yesterday?").

import json
import re
import sys
import time
from datetime import datetime, date, timedelta
from pathlib import Path
from threading import Lock


def get_base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


BASE_DIR          = get_base_dir()
CONVERSATIONS_DIR = BASE_DIR / "memory"
CONVERSATIONS_PATH = CONVERSATIONS_DIR / "conversation_memory.json"

_lock = Lock()

# Hard caps — keep the file small and cheap to summarize.
MAX_SESSIONS       = 60          # most recent sessions kept
MAX_TURNS_IN_MEM   = 80          # turns buffered for the live session
MAX_TURN_CHARS     = 400         # chars kept per turn for summarization
MAX_SUMMARY_CHARS  = 1400        # model-generated summary cap
MAX_RECENT_IN_PROMPT = 3         # sessions auto-injected into system prompt
MAX_RECENT_CHARS   = 1600        # total chars for the recent-context block


# ─────────────────────────────────────────────────────────────────────
# JSON helpers
# ─────────────────────────────────────────────────────────────────────
def _empty_store() -> dict:
    return {
        "sessions": [],
        "current": None,   # live in-progress session (also in sessions[-1])
    }


def load_conversations() -> dict:
    if not CONVERSATIONS_PATH.exists():
        return _empty_store()

    with _lock:
        try:
            data = json.loads(CONVERSATIONS_PATH.read_text(encoding="utf-8"))
            if isinstance(data, dict) and "sessions" in data:
                if not isinstance(data.get("sessions"), list):
                    data["sessions"] = []
                if "current" not in data:
                    data["current"] = None
                # Re-link the current session so it points to the SAME object
                # that lives in sessions[].  JSON loading creates two separate
                # dicts (one for "current", one for sessions[-1]); without
                # this, mutations to the live session (turns, summary) would
                # never reach the copy persisted in the sessions list.
                cur      = data.get("current")
                sessions = data.get("sessions", [])
                if cur and sessions:
                    for s in sessions:
                        if s.get("id") == cur.get("id") and s.get("end_time") is None:
                            data["current"] = s
                            break
                    else:
                        sessions.append(cur)
                        data["sessions"] = sessions
                return data
            return _empty_store()
        except Exception as e:
            print(f"[ConvMemory] ⚠️ Load error: {e}")
            return _empty_store()


def _save(store: dict) -> None:
    store = _prune(store)
    CONVERSATIONS_DIR.mkdir(parents=True, exist_ok=True)
    with _lock:
        CONVERSATIONS_PATH.write_text(
            json.dumps(store, indent=2, ensure_ascii=False),
            encoding="utf-8"
        )


def _prune(store: dict) -> dict:
    """Drop old sessions beyond the cap and trim nested fields."""
    sessions = store.get("sessions", [])
    live_id  = (store.get("current") or {}).get("id")

    # Trim keys/values that are too big (belt + braces).
    for s in sessions:
        s["summary"]    = (s.get("summary") or "")[:MAX_SUMMARY_CHARS]
        s["key_points"] = (s.get("key_points") or [])[:10]
        s["topics"]     = (s.get("topics") or [])[:12]

    # Keep the most recent MAX_SESSIONS (never drop the live session).
    if len(sessions) > MAX_SESSIONS:
        sessions.sort(
            key=lambda s: s.get("start_time") or s.get("date") or "",
            reverse=True,
        )
        keep = []
        for s in sessions:
            if len(keep) >= MAX_SESSIONS and s.get("id") != live_id:
                continue
            keep.append(s)
        sessions = keep

    store["sessions"] = sessions
    return store


# ─────────────────────────────────────────────────────────────────────
# Session lifecycle
# ─────────────────────────────────────────────────────────────────────
def start_session() -> None:
    """Begin a new conversation session (called once at startup)."""
    store   = load_conversations()
    now     = datetime.now()
    session = {
        "id":          now.strftime("%Y-%m-%d-%H:%M:%S"),
        "date":        now.strftime("%Y-%m-%d"),
        "start_time":  now.strftime("%H:%M"),
        "end_time":    None,
        "duration_min": None,
        "topics":      [],
        "summary":     "",
        "key_points":  [],
        "turns":       0,
        "last_updated": now.isoformat(timespec="seconds"),
        "turns_detail": [],   # raw buffered turns, only used for summarization
    }
    store["sessions"].append(session)
    store["current"] = session
    _save(store)
    print(f"[ConvMemory] 🗂️  Session started: {session['id']}")


def append_turn(user_text: str, lessan_text: str) -> None:
    """Accumulate a turn into the live session (for summarization)."""
    store = load_conversations()
    cur   = store.get("current")
    if not cur:
        cur = _ensure_current(store)

    user_text   = (user_text or "").strip()
    lessan_text = (lessan_text or "").strip()
    if not user_text and not lessan_text:
        return

    cur["turns"] = cur.get("turns", 0) + 1
    cur["last_updated"] = datetime.now().isoformat(timespec="seconds")

    detail = cur.setdefault("turns_detail", [])
    detail.append({
        "user": user_text[:MAX_TURN_CHARS],
        "lessan": lessan_text[:MAX_TURN_CHARS],
    })
    # Keep a bounded buffer of the most recent turns.
    if len(detail) > MAX_TURNS_IN_MEM:
        detail = detail[-MAX_TURNS_IN_MEM:]
        cur["turns_detail"] = detail

    _save(store)


def _ensure_current(store: dict) -> dict:
    """If no live session exists (e.g. app crashed), create one."""
    now     = datetime.now()
    session = {
        "id":           now.strftime("%Y-%m-%d-%H:%M:%S"),
        "date":         now.strftime("%Y-%m-%d"),
        "start_time":   now.strftime("%H:%M"),
        "end_time":     None,
        "duration_min": None,
        "topics":       [],
        "summary":      "",
        "key_points":   [],
        "turns":        0,
        "last_updated": now.isoformat(timespec="seconds"),
        "turns_detail": [],
    }
    store["sessions"].append(session)
    store["current"] = session
    return session


def _summarize_session(session: dict) -> dict:
    """Use the free OmniRoute model pool to distill a session summary."""
    from or_client import client

    raw_turns = session.get("turns_detail", [])
    if not raw_turns:
        return session

    # Build a compact transcript for the LLM.
    lines = []
    for i, t in enumerate(raw_turns, 1):
        if t.get("user"):
            lines.append(f"{i}. User: {t['user']}")
        if t.get("lessan"):
            lines.append(f"   Lessan: {t['lessan']}")
        if sum(len(x) for x in lines) > 6000:
            lines = lines[-40:]
            break

    transcript = "\n".join(lines)

    try:
        raw = client.chat(
            f"Summarize this conversation from an AI assistant's session.\n\n"
            f"Return ONLY valid JSON, no markdown, no extra text:\n"
            f'{{"summary": "2-4 sentence recap of what was discussed/decided",\n'
            f' "topics": ["topic1", "topic2", ...],\n'
            f' "key_points": ["key fact or outcome", ...]}}\n\n'
            f"Rules:\n"
            f"- summary ≤ 3 sentences, include any decisions or actionable outcomes.\n"
            f"- topics: 3-6 short nouns/phrases for the main themes.\n"
            f"- key_points: up to 4 short bullets of important details worth remembering later.\n"
            f"- Skip small talk and one-time commands (weather, searches) unless they're the main subject.\n\n"
            f"Conversation:\n{transcript}\n\nJSON:",
            system=(
                "You are a conversation summarizer. "
                "Return ONLY valid JSON. No markdown fences."
            ),
            max_tokens=700,
            temperature=0.2,
        )

        raw_text = (raw or "").strip()
        if not raw_text:
            print("[ConvMemory] ⚠️ Summarizer returned empty output.")
            return session

        clean = re.sub(r"```(?:json)?", "", raw_text).strip().rstrip("`").strip()
        # If fences/prose remain, pull out the first JSON object.
        obj_start = clean.find("{")
        obj_end   = clean.rfind("}")
        if obj_start != -1 and obj_end != -1:
            clean = clean[obj_start:obj_end + 1]
        data = json.loads(clean)

        if isinstance(data, dict):
            session["summary"]    = str(data.get("summary", ""))[:MAX_SUMMARY_CHARS]
            session["topics"]     = [str(t) for t in data.get("topics", [])][:12]
            session["key_points"] = [str(k) for k in data.get("key_points", [])][:10]

    except json.JSONDecodeError:
        print("[ConvMemory] ⚠️ Summary JSON parse failed — keeping raw turns.")
    except Exception as e:
        if "429" not in str(e):
            print(f"[ConvMemory] ⚠️ Summarize failed: {e}")

    return session


def finalize_session() -> None:
    """Summarize the live session and close it (called on shutdown)."""
    store = load_conversations()
    cur   = store.get("current")
    if not cur:
        return

    session = _summarize_session(cur)
    if (session.get("summary") or "").strip():
        session.pop("turns_detail", None)   # free memory — keep only summary
    else:
        print("[ConvMemory] ⚠️ No summary generated — keeping raw turns.")

    now = datetime.now()
    session["end_time"] = now.strftime("%H:%M")
    try:
        start = datetime.strptime(f"{session['date']} {session['start_time']}", "%Y-%m-%d %H:%M")
        session["duration_min"] = int((now - start).total_seconds() // 60)
    except Exception:
        session["duration_min"] = None

    store["current"] = None
    _save(store)
    print(f"[ConvMemory] 📦 Session finalized: {session['id']} — "
          f"{session.get('turns', 0)} turns")


# ─────────────────────────────────────────────────────────────────────
# Recall helpers
# ─────────────────────────────────────────────────────────────────────
def recent_sessions(days: int = 7, limit: int = 10) -> list[dict]:
    store = load_conversations()
    sessions = [s for s in store.get("sessions", []) if s.get("summary")]
    cutoff = None
    if days is not None:
        cutoff = (date.today() - timedelta(days=days)).isoformat()
        sessions = [s for s in sessions if (s.get("date") or "") >= cutoff]
    sessions.sort(key=lambda s: (s.get("date") or "", s.get("start_time") or ""), reverse=True)
    return _public_shape(sessions[:limit])


def sessions_on(date_str: str) -> list[dict]:
    store   = load_conversations()
    session = [s for s in store.get("sessions", []) if (s.get("date") or "") == date_str]
    session.sort(key=lambda s: (s.get("start_time") or ""), reverse=True)
    return _public_shape(session)


def search_conversations(query: str, limit: int = 8) -> list[dict]:
    store = load_conversations()
    q     = (query or "").strip().lower()
    if not q:
        return recent_sessions(days=None, limit=limit)

    results = []
    for s in store.get("sessions", []):
        if not s.get("summary"):
            continue
        haystack = " ".join([
            s.get("summary", ""),
            " ".join(s.get("topics", [])),
            " ".join(s.get("key_points", [])),
        ]).lower()
        if q in haystack:
            results.append(s)

    results.sort(key=lambda s: (s.get("date") or "", s.get("start_time") or ""), reverse=True)
    return _public_shape(results[:limit])


def forget_sessions(date_str: str | None = None, session_id: str | None = None) -> int:
    store    = load_conversations()
    sessions = store.get("sessions", [])
    removed  = 0

    if session_id:
        before = len([s for s in sessions if s.get("id") == session_id])
        sessions = [s for s in sessions if s.get("id") != session_id]
        removed = before
    elif date_str:
        before  = len(sessions)
        sessions = [s for s in sessions if s.get("date") != date_str]
        removed = before - len(sessions)
    else:
        # Forget ALL finalized sessions (keep the live one).
        before  = sum(1 for s in sessions if s.get("id") != (store.get("current") or {}).get("id"))
        sessions = [s for s in sessions if s.get("id") == (store.get("current") or {}).get("id")]
        removed = before

    store["sessions"] = sessions
    _save(store)
    return removed


# ─────────────────────────────────────────────────────────────────────
# Prompt injection
# ─────────────────────────────────────────────────────────────────────
def _public_shape(sessions: list[dict]) -> list[dict]:
    """Strip raw internal fields (turns_detail) from results."""
    out = []
    for s in sessions:
        out.append({
            "date":        s.get("date"),
            "start_time":  s.get("start_time"),
            "end_time":    s.get("end_time"),
            "duration_min": s.get("duration_min"),
            "topics":      s.get("topics", []),
            "summary":     s.get("summary", ""),
            "key_points":  s.get("key_points", []),
            "turns":       s.get("turns", 0),
        })
    return out


def format_recent_for_prompt(k: int = MAX_RECENT_IN_PROMPT) -> str:
    """Compact 'Recent conversations' block for the system prompt."""
    store = load_conversations()
    sessions = [s for s in store.get("sessions", []) if s.get("summary")]
    sessions.sort(key=lambda s: (s.get("date") or "", s.get("start_time") or ""), reverse=True)
    sessions = sessions[:k]

    if not sessions:
        return ""

    lines = ["[RECENT CONVERSATIONS — what was discussed recently. "
             "Use naturally when relevant; never recite like a list]"]
    for s in sessions:
        date_str    = s.get("date", "")
        summary     = (s.get("summary") or "").strip()
        key_points  = s.get("key_points", [])
        if not summary:
            continue
        lines.append(f"\n• {date_str}: {summary}")
        if key_points:
            lines.append("  Points: " + "; ".join(str(x) for x in key_points[:3]))

    block = "\n".join(lines)
    if len(block) > MAX_RECENT_CHARS:
        block = block[:MAX_RECENT_CHARS - 1] + "…"

    return block + "\n"


def recall_text(action: str, query: str = "", date: str = "", days: int = 7) -> str:
    """Build a human-readable answer for the conversation_recall tool."""
    action = (action or "recent").strip().lower()
    query  = (query or "").strip()
    date   = (date or "").strip()
    days   = int(days or 7)

    if action == "forget":
        removed = forget_sessions(date_str=date or None, session_id=query or None)
        if removed:
            return f"Forgot {removed} conversation session(s)."
        return "No matching conversation history to forget."

    if action == "today":
        sessions = sessions_on(datetime.now().strftime("%Y-%m-%d"))
        if not sessions:
            return "No conversation sessions recorded today yet."
    elif action == "date":
        if not re.match(r"\d{4}-\d{2}-\d{2}", date):
            return "Please provide a date in YYYY-MM-DD format."
        sessions = sessions_on(date)
        if not sessions:
            return f"No conversation sessions found for {date}."
    elif action == "search":
        if not query:
            return "Please provide a query to search for."
        sessions = search_conversations(query)
        if not sessions:
            return f"No past conversations found matching '{query}'."
    else:  # recent
        label = f"({days} days)" if days else "(all time)"
        sessions = recent_sessions(days=days if days > 0 else None)
        if not sessions:
            return f"No conversation summaries available {label}."

    return _format_sessions(sessions)


def _format_sessions(sessions: list[dict]) -> str:
    lines = []
    for s in sessions:
        date_str   = s.get("date", "") + (" " + s.get("start_time", "") if s.get("start_time") else "")
        summary    = s.get("summary", "").strip()
        topics     = s.get("topics", [])
        key_points = s.get("key_points", [])
        lines.append(f"• {date_str} — {summary}")
        if topics:
            lines.append(f"    Topics: {', '.join(str(t) for t in topics[:6])}")
        if key_points:
            lines.append(f"    Key points: {'; '.join(str(k) for k in key_points[:3])}")
    return "\n".join(lines)


if __name__ == "__main__":
    print("Conversation memory module loaded.")
    print(f"Store: {CONVERSATIONS_PATH}")
    print(f"Recent sessions: {len(recent_sessions())}")
