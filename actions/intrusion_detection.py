# actions/intrusion_detection.py
# Lessan AI — Intrusion Detection System (IDS)
#
# Monitors the user's OWN machine for suspicious activity and reports it:
#   - Active TCP/UDP connections (baseline-aware)
#   - Unusual outbound network connections
#   - New/unknown running processes
#   - Failed login attempts (Linux: /var/log/auth.log, Windows: Security log)
#   - File system changes in sensitive directories (snapshot-diff)
#
# All monitoring is local and read-only. It does NOT perform attacks;
# it defends. This is the defensive half of the cybersecurity suite.

import datetime
import json
import os
import platform
import re
import socket
import subprocess
import sys
from pathlib import Path

try:
    import psutil
    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False


def get_base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


BASE_DIR = get_base_dir()
IDS_DIR  = BASE_DIR / "reports" / "ids"
IDS_DIR.mkdir(parents=True, exist_ok=True)

STATE_FILE = IDS_DIR / "ids_state.json"

# Directories that, when changed unexpectedly, are high-signal
SENSITIVE_DIRS = [
    Path.home() / ".ssh",
    Path.home() / ".aws",
    Path.home() / ".config",
]


def _is_windows() -> bool:
    return platform.system().lower() == "windows"


def _is_linux() -> bool:
    return platform.system().lower() == "linux"


def _load_state() -> dict:
    try:
        if STATE_FILE.exists():
            return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {}


def _save_state(state: dict) -> None:
    try:
        STATE_FILE.write_text(
            json.dumps(state, indent=2, default=str),
            encoding="utf-8"
        )
    except Exception:
        pass


# ─────────────────────────────────────────────────────────────────────
# 1. Active network connections
# ─────────────────────────────────────────────────────────────────────
def _active_connections() -> list:
    """Lists active TCP/UDP connections with process info."""
    results = []
    if not HAS_PSUTIL:
        return [{"error": "psutil not installed — run: pip install psutil"}]

    for conn in psutil.net_connections(kind="inet"):
        try:
            proc_name = ""
            pid = conn.pid
            if pid:
                try:
                    proc_name = psutil.Process(pid).name()
                except Exception:
                    proc_name = "?"
            entry = {
                "fd": conn.fd,
                "family": str(conn.family),
                "type": str(conn.type),
                "laddr": f"{conn.laddr.ip}:{conn.laddr.port}" if conn.laddr else "",
                "raddr": f"{conn.raddr.ip}:{conn.raddr.port}" if conn.raddr else "",
                "status": conn.status,
                "pid": pid,
                "process": proc_name,
            }
            # Only keep connections that have a remote address (active sessions)
            if conn.raddr and conn.status in ("ESTABLISHED", "SYN_SENT"):
                results.append(entry)
        except Exception:
            continue
    return results


def _anomaly_connections(current: list) -> list:
    """Compares current connections to the saved baseline; flags new remote IPs."""
    state   = _load_state()
    baseline = state.get("connections_baseline", {})

    new_ips = {}
    for c in current:
        raddr = c.get("raddr", "")
        if not raddr:
            continue
        ip = raddr.rsplit(":", 1)[0]
        proc = c.get("process", "?")
        if ip not in baseline:
            new_ips.setdefault(ip, []).append(proc)

    result = []
    for ip, procs in new_ips.items():
        result.append({
            "remote_ip": ip,
            "processes": list(set(procs)),
            "reason": "New remote address not in baseline",
        })
    return result


# ─────────────────────────────────────────────────────────────────────
# 2. Suspicious process detection
# ─────────────────────────────────────────────────────────────────────
def _suspicious_processes() -> list:
    """Flags processes with known-malicious or unusual command lines."""
    suspicious_patterns = [
        r"powershell\s+.*-enc",          # encoded PowerShell command
        r"certutil\s+.*-urlcache",        # certutil download cradle
        r"bitsadmin\s+.*/transfer",       # BITS download
        r"rundll32\s+.*\b(?:javascript|mshtml)",  # rundll32 HTML/JS
        r"mshta\.exe",                    # MSHTA abuse
        r"regsvr32\s+.*/i:http",          # regsvr32 remote
        r"wscript\.exe\s+.*\.(?:vbs|js)", # wscript script abuse
        r"cscript\.exe\s+.*\.(?:vbs|js)",
        r"(^|\s)nc\s+.*-e",               # netcat reverse shell
        r"ncat\s+.*-e",
        r"python.*\s-s\s+c",              # python reverse shell one-liner (heuristic)
    ]
    results = []
    if not HAS_PSUTIL:
        return results

    for proc in psutil.process_iter(["pid", "name", "cmdline"]):
        try:
            cmdline = " ".join(proc.info.get("cmdline") or [])
            name    = (proc.info.get("name") or "").lower()
            for pattern in suspicious_patterns:
                if re.search(pattern, cmdline, re.IGNORECASE):
                    results.append({
                        "pid": proc.info["pid"],
                        "name": proc.info.get("name"),
                        "cmdline": cmdline[:200],
                        "reason": f"Matches suspicious pattern: {pattern}",
                    })
                    break
        except Exception:
            continue
    return results


# ─────────────────────────────────────────────────────────────────────
# 3. Failed login attempts
# ─────────────────────────────────────────────────────────────────────
def _failed_logins(limit: int = 20) -> list:
    """Reads recent failed authentication attempts."""
    results = []
    try:
        if _is_linux():
            logs = ["/var/log/auth.log", "/var/log/secure"]
            for log in logs:
                path = Path(log)
                if not path.exists():
                    continue
                # Source the last 8000 lines
                lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()[-8000:]
                for line in lines:
                    if "Failed password" in line or "authentication failure" in line.lower():
                        m = re.search(r"from (\S+)", line)
                        user_m = re.search(r"for (?:invalid user )?(\S+)", line)
                        results.append({
                            "source": log,
                            "line": line[:250],
                            "ip": m.group(1) if m else "?",
                            "user": user_m.group(1) if user_m else "?",
                        })
                        if len(results) >= limit:
                            return results
        elif _is_windows():
            cmd = (
                'wevtutil qe Security "/q:*[System[(EventID=4625)]]" '
                f"/c:{limit} /f:text /rd:true"
            )
            out = subprocess.run(
                cmd, shell=True, capture_output=True, text=True, timeout=30
            ).stdout
            for block in re.split(r"\n\s*\n", out):
                if "Event ID: 4625" in block or "EventID 4625" in block:
                    ip_m = re.search(r"Source Network Address:\s*(\S+)", block)
                    user_m = re.search(r"Account Name:\s*(\S+)", block)
                    results.append({
                        "source": "Windows Security log",
                        "ip": ip_m.group(1) if ip_m else "?",
                        "user": user_m.group(1) if user_m else "?",
                        "line": block[:200].replace("\n", " | "),
                    })
    except Exception:
        pass
    return results


# ─────────────────────────────────────────────────────────────────────
# 4. Sensitive directory change detection
# ─────────────────────────────────────────────────────────────────────
def _snapshot_sensitive_dirs() -> dict:
    """Takes a snapshot of sensitive dirs to diff against later."""
    snapshot = {}
    for d in SENSITIVE_DIRS:
        if d.exists():
            items = {}
            for root, dirs, files in os.walk(d):
                for f in files:
                    p = Path(root) / f
                    try:
                        stat = p.stat()
                        items[str(p)] = f"{stat.st_size}:{stat.st_mtime:.0f}"
                    except Exception:
                        continue
            snapshot[str(d)] = items
    return snapshot


def _diff_sensitive_dirs() -> list:
    state  = _load_state()
    before = state.get("dir_snapshot", {})
    now    = _snapshot_sensitive_dirs()

    changes = []
    all_paths = set(before.keys()) | set(now.keys())
    for d in all_paths:
        old = before.get(d, {})
        new = now.get(d, {})
        for f in set(old.keys()) - set(new.keys()):
            changes.append({"path": f, "action": "DELETED"})
        for f in set(new.keys()) - set(old.keys()):
            changes.append({"path": f, "action": "NEW"})
        for f in set(old.keys()) & set(new.keys()):
            if old[f] != new[f]:
                changes.append({"path": f, "action": "MODIFIED"})
    return changes


# ─────────────────────────────────────────────────────────────────────
# 5. Login/logout/who session info
# ─────────────────────────────────────────────────────────────────────
def _session_users() -> list:
    results = []
    try:
        out = subprocess.run(
            ["who", "-a"], capture_output=True, text=True, timeout=10
        ).stdout
        for line in out.splitlines():
            if line.strip():
                results.append(line.strip())
    except Exception:
        pass
    return results


# ─────────────────────────────────────────────────────────────────────
# 6. Main IDS entry point
# ─────────────────────────────────────────────────────────────────────
def intrusion_check(parameters: dict, player=None) -> str:
    """
    Runs an intrusion detection check on this machine.

    Parameters:
        baseline: "save" | "clear" — save/clear the connection baseline
        action: "scan" (default) | "save_baseline" | "monitor_start" | "monitor_status"
        save_report: bool — write a report file (default True)
    """
    action = (parameters.get("action") or "scan").lower()
    save   = parameters.get("save_report", True)

    state  = _load_state()

    # ── Save baseline of trusted connections ────────────────────────
    if action == "save_baseline" or parameters.get("baseline") == "save":
        current = _active_connections()
        state["connections_baseline"] = {
            c["raddr"].rsplit(":", 1)[0]: c.get("process", "?")
            for c in current if c.get("raddr")
        }
        state["dir_snapshot"] = _snapshot_sensitive_dirs()
        state["baseline_saved_at"] = datetime.datetime.now().isoformat()
        _save_state(state)
        return (
            f"✅ Baseline saved: {len(state['connections_baseline'])} remote hosts, "
            f"sensitive dirs snapshotted. Future scans will compare against this."
        )

    if action == "clear_baseline" or parameters.get("baseline") == "clear":
        state.pop("connections_baseline", None)
        state.pop("dir_snapshot", None)
        _save_state(state)
        return "🧹 Baseline cleared. Next scan has nothing to compare against."

    # ── Full scan ───────────────────────────────────────────────────
    findings = []

    # 1. Suspicious processes — always scan
    procs = _suspicious_processes()
    if procs:
        findings.append(("Suspicious Processes", procs))
    else:
        findings.append(("Suspicious Processes", ["None found. ✅"]))

    # 2. New connections (only if baseline exists)
    has_baseline = bool(state.get("connections_baseline"))
    if has_baseline:
        current = _active_connections()
        new_con = _anomaly_connections(current)
        if new_con:
            findings.append(("New Connections (not in baseline)", new_con))
        else:
            findings.append(("New Connections (not in baseline)", ["None. ✅"]))

    # 3. Sensitive dir changes (only if snapshot exists)
    has_snapshot = bool(state.get("dir_snapshot"))
    if has_snapshot:
        changes = _diff_sensitive_dirs()
        if changes:
            findings.append(("Sensitive Directory Changes", changes[:30]))
        else:
            findings.append(("Sensitive Directory Changes", ["No changes. ✅"]))

    # 4. Failed logins
    logins = _failed_logins()
    if logins:
        findings.append(("Failed Login Attempts", logins))
    else:
        findings.append(("Failed Login Attempts", ["None found (may need elevated privileges). ✅"]))

    # 5. Session info
    sessions = _session_users()
    if sessions:
        findings.append(("Current Sessions", sessions[:10]))

    # ── Build report ────────────────────────────────────────────────
    lines = []
    lines.append("# 🛡️ Lessan Intrusion Detection Report")
    lines.append(f"\n**Date:** {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append(f"**Host:** {socket.gethostname()} ({platform.system()} {platform.release()})")
    if state.get("baseline_saved_at"):
        lines.append(f"**Baseline saved:** {state['baseline_saved_at']}\n")
    else:
        lines.append("\n⚠️ **No baseline saved yet.** Run with `action: save_baseline` "
                     "to enable connection + file-change anomaly detection.\n")

    for title, content in findings:
        lines.append(f"\n## {title}")
        if isinstance(content, list):
            for item in content:
                if isinstance(item, dict):
                    lines.append("- " + ", ".join(f"{k}: {v}" for k, v in item.items()))
                else:
                    lines.append(f"- {item}")

    report = "\n".join(lines)

    # ── Save new state snapshot for next run ────────────────────────
    state["dir_snapshot"] = _snapshot_sensitive_dirs()
    _save_state(state)

    # ── Verdict ─────────────────────────────────────────────────────
    alert_count = 0
    for title, content in findings:
        if title == "Suspicious Processes" and content and content[0] != "None found. ✅":
            alert_count += len(content)
        if title == "New Connections (not in baseline)" and content and content[0] != "None. ✅":
            alert_count += len(content)
        if title == "Failed Login Attempts" and content and content[0] != "None found (may need elevated privileges). ✅":
            alert_count += len(content)
        if title == "Sensitive Directory Changes" and content and content[0] != "No changes. ✅":
            alert_count += len(content)

    if alert_count == 0:
        verdict = "✅ No intrusion indicators detected. System appears clean."
    elif alert_count <= 3:
        verdict = f"⚠️ {alert_count} potential indicator(s) — review the report."
    else:
        verdict = f"🚨 {alert_count} indicators found — possible intrusion! Review immediately."

    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    path  = IDS_DIR / f"intrusion-report-{stamp}.md"
    if save:
        path.write_text(report, encoding="utf-8")
        saved = f"\n\n📄 Report saved: {path}"
    else:
        saved = ""

    now_baseline = "Baseline saved" if has_baseline else "Run 'action: save_baseline' to enable anomaly detection"

    return f"{verdict}\n\n{report}{saved}\n\n🔄 {now_baseline}"


# CLI entry for testing
if __name__ == "__main__":
    print(intrusion_check({"action": "scan"}))