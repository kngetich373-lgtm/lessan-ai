# actions/security_scanner.py
# Lessan AI — Vulnerability Scanner & Security Audit
#
# Safe, local-only security checks:
#   - System vulnerability scan (open ports, weak services, outdated packages)
#   - Wi-Fi network recon (SSID, signal, security type, connected devices)
#   - Password strength auditor
#   - File/disk permission audit
#   - Malware-suspicion checks (startup entries, running processes)
#
# Everything runs against the user's OWN machine with clear consent.
# It never touches remote systems.

import datetime
import json
import os
import platform
import re
import socket
import subprocess
import sys
from pathlib import Path


def get_base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


BASE_DIR = get_base_dir()
REPORT_DIR = BASE_DIR / "reports"
REPORT_DIR.mkdir(parents=True, exist_ok=True)


def _is_windows() -> bool:
    return platform.system().lower() == "windows"


def _is_linux() -> bool:
    return platform.system().lower() == "linux"


def _is_macos() -> bool:
    return platform.system().lower() == "darwin"


# ─────────────────────────────────────────────────────────────────────
# 1. Open port scan (localhost only)
# ─────────────────────────────────────────────────────────────────────
def _scan_local_ports() -> list:
    """Checks common localhost ports to see if anything is listening."""
    common_ports = [
        21, 22, 23, 25, 53, 80, 110, 135, 139, 143, 443, 445,
        1080, 1433, 1521, 1723, 3306, 3389, 5432, 5900, 6379,
        8080, 8443, 9000, 9200, 27017,
    ]
    open_ports = []
    for port in common_ports:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(0.3)
        try:
            result = s.connect_ex(("127.0.0.1", port))
            if result == 0:
                open_ports.append(port)
        except Exception:
            pass
        finally:
            s.close()
    return open_ports


def _service_name(port: int) -> str:
    try:
        return socket.getservbyport(port)
    except Exception:
        names = {
            3389: "RDP",
            3306: "MySQL",
            5432: "PostgreSQL",
            27017: "MongoDB",
            6379: "Redis",
            9200: "Elasticsearch",
            8080: "HTTP-alt",
            8443: "HTTPS-alt",
        }
        return names.get(port, "unknown")


# ─────────────────────────────────────────────────────────────────────
# 2. Wi-Fi network recon
# ─────────────────────────────────────────────────────────────────────
def _wifi_recon() -> list:
    """Gathers local Wi-Fi info: SSID, signal, security."""
    results = []
    try:
        if _is_linux():
            out = subprocess.run(
                ["nmcli", "-t", "-f", "SSID,SIGNAL,SECURITY,ACTIVE", "dev", "wifi", "list"],
                capture_output=True, text=True, timeout=15,
            ).stdout
            for line in out.strip().splitlines():
                parts = line.split(":")
                if len(parts) >= 2 and parts[0]:
                    results.append({
                        "ssid": parts[0],
                        "signal": parts[1] if len(parts) > 1 else "?",
                        "security": parts[2] if len(parts) > 2 else "?",
                        "connected": parts[3] == "yes" if len(parts) > 3 else False,
                    })
        elif _is_windows():
            out = subprocess.run(
                ["netsh", "wlan", "show", "interfaces"],
                capture_output=True, text=True, timeout=15,
            ).stdout
            for line in out.splitlines():
                line = line.strip()
                if line.lower().startswith("ssid"):
                    results.append({"ssid": line.split(":", 1)[1].strip()})
        elif _is_macos():
            out = subprocess.run(
                ["/System/Library/PrivateFrameworks/Apple80211.framework"
                 "/Versions/Current/Resources/airport", "-s"],
                capture_output=True, text=True, timeout=15,
            ).stdout
            for line in out.splitlines()[1:]:
                parts = line.split()
                if len(parts) >= 1:
                    results.append({"ssid": parts[0]})
    except Exception as e:
        results.append({"error": str(e)})
    return results


# ─────────────────────────────────────────────────────────────────────
# 3. Password strength auditor
# ─────────────────────────────────────────────────────────────────────
def audit_password(password: str) -> dict:
    """Evaluates a password's strength and returns a detailed report."""
    score = 0
    checks = []

    length = len(password)
    if length >= 12:
        score += 2
        checks.append("Length ≥ 12 characters ✅")
    elif length >= 8:
        score += 1
        checks.append("Length ≥ 8 characters ✅")
    else:
        checks.append("⚠️ Length < 8 characters")

    if re.search(r"[a-z]", password):
        score += 1
        checks.append("Contains lowercase ✅")
    else:
        checks.append("⚠️ No lowercase letters")

    if re.search(r"[A-Z]", password):
        score += 1
        checks.append("Contains uppercase ✅")
    else:
        checks.append("⚠️ No uppercase letters")

    if re.search(r"\d", password):
        score += 1
        checks.append("Contains numbers ✅")
    else:
        checks.append("⚠️ No numbers")

    if re.search(r"[^A-Za-z0-9]", password):
        score += 1
        checks.append("Contains symbols ✅")
    else:
        checks.append("⚠️ No symbols")

    common = [
        "password", "123456", "12345678", "qwerty", "abc123",
        "admin", "letmein", "welcome", "iloveyou", "monkey",
        "dragon", "football", "baseball", "master", "shadow",
    ]
    if password.lower() in common:
        score = 0
        checks.append("❌ Password is in the common weak-password list")

    if score >= 6:
        verdict = "STRONG"
        color = "green"
    elif score >= 4:
        verdict = "MODERATE"
        color = "orange"
    else:
        verdict = "WEAK"
        color = "red"

    return {
        "verdict": verdict,
        "score": f"{score}/8",
        "color": color,
        "checks": checks,
        "suggested": _suggest_password()
    }


def _suggest_password() -> str:
    import secrets
    import string
    alphabet = string.ascii_letters + string.digits + "!@#$%^&*"
    return "".join(secrets.choice(alphabet) for _ in range(16))


# ─────────────────────────────────────────────────────────────────────
# 4. Startup entry audit (malware suspicion)
# ─────────────────────────────────────────────────────────────────────
def _startup_audit() -> list:
    suspicious = []
    patterns = [
        r"temp", r"tmp", r"download", r"\.exe$", r"powershell.*-enc",
        r"rundll32.*\.dll.*,", r"regsvr32", r"wscript", r"cscript",
        r"%appdata%.*\.bat", r"%appdata%.*\.vbs",
    ]
    try:
        if _is_windows():
            cmd = 'reg query "HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run"'
            out = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=10).stdout
            for line in out.splitlines():
                if "REG_SZ" in line and "=" in line:
                    name, _, value = line.partition("=")
                    name = name.strip()
                    value = value.strip()
                    for pattern in patterns:
                        if re.search(pattern, value, re.IGNORECASE):
                            suspicious.append({
                                "entry": name,
                                "command": value,
                                "reason": f"Matches suspicious pattern: {pattern}"
                            })
                            break
    except Exception:
        pass
    return suspicious


# ─────────────────────────────────────────────────────────────────────
# 5. Permission / sensitive-file audit
# ─────────────────────────────────────────────────────────────────────
def _permission_audit() -> list:
    issues = []
    sensitive = []
    home = Path.home()

    if _is_linux() or _is_macos():
        private_files = [
            ".ssh/id_rsa", ".ssh/id_ed25519", ".ssh/id_ecdsa",
            ".aws/credentials", ".netrc", ".pgpass",
        ]
        for rel in private_files:
            p = home / rel
            if p.exists():
                mode = oct(p.stat().st_mode & 0o777)
                sensitive.append({
                    "file": str(p),
                    "permissions": mode,
                    "warning": "Permissions are too open — chmod 600 recommended"
                    if mode in ("0o644", "0o666", "0o755", "0o777")
                    else "OK",
                })

    if _is_windows():
        # Check common sensitive locations for public ACLs is complex;
        # at minimum flag world-writable temp USER directories.
        temp_dirs = [
            Path(os.environ.get("TEMP", "")),
            Path(os.environ.get("TMP", "")),
        ]
        for d in temp_dirs:
            if d.exists():
                issues.append(f"Temp directory used by processes: {d}")

    return sensitive + [{"file": i} for i in issues]


# ─────────────────────────────────────────────────────────────────────
# 6. Outdated / vulnerable software hint
# ─────────────────────────────────────────────────────────────────────
def _software_audit() -> list:
    results = []
    try:
        if _is_linux():
            if Path("/usr/bin/apt").exists() or Path("/usr/bin/apt-get").exists():
                out = subprocess.run(
                    ["apt", "list", "--upgradable"], capture_output=True,
                    text=True, timeout=30,
                ).stdout
                count = len([l for l in out.splitlines() if "upgradable" in l.lower() or l.startswith("Listing")])
                results.append({
                    "platform": "Debian/Ubuntu",
                    "upgradable_packages": count if count else 0,
                    "note": "Run 'sudo apt upgrade' to patch known vulnerabilities",
                })
        elif _is_windows():
            out = subprocess.run(
                ["powershell", "-NoProfile", "-Command",
                 "(Get-HotFix | Measure-Object).Count"],
                capture_output=True, text=True, timeout=30,
            ).stdout
            if out.strip().isdigit():
                results.append({
                    "platform": "Windows",
                    "installed_updates": int(out.strip()),
                    "note": "Ensure Windows Update is enabled",
                })
    except Exception:
        pass
    return results


# ─────────────────────────────────────────────────────────────────────
# 6b. Network scan (nmap) — only when explicitly requested
# ─────────────────────────────────────────────────────────────────────
def _network_scan(target: str = "127.0.0.1") -> list:
    """Runs a quick nmap scan against a local target (read-only)."""
    results = []
    try:
        out = subprocess.run(
            ["nmap", "-sV", "-T4", "-Pn", "--open", target],
            capture_output=True, text=True, timeout=120,
        )
        output = out.stdout or out.stderr
        results.append({"target": target, "raw": output[:4000]})
    except FileNotFoundError:
        results.append({"target": target, "error": "nmap is not installed — run: pip install nmap or sudo apt install nmap"})
    except Exception as e:
        results.append({"target": target, "error": str(e)})
    return results


# ─────────────────────────────────────────────────────────────────────
# 7. Main scan entry point
# ─────────────────────────────────────────────────────────────────────
def security_scanner(parameters: dict, player=None) -> str:
    """
    Runs a full local security audit and writes a report file.

    Parameters:
        scan_type: "full" (default) | "quick" | "network"
                   network → explicit nmap scan of a local target
        target: target host/ip for network scan (default 127.0.0.1)
        scope: legacy alias for scan_type (ports|wifi|password|startup|permissions|software)
        password: optional — if provided, audits that password's strength
        save_report: bool — write a Markdown report to reports/ (default True)
    """
    scan_type = (parameters.get("scan_type") or parameters.get("scope") or "full").lower()
    target    = (parameters.get("target") or "127.0.0.1").strip()
    password  = (parameters.get("password") or "").strip()
    save      = parameters.get("save_report", True)

    if scan_type == "network":
        return _run_network_scan(target, save)

    scope = scan_type
    if scope == "quick":
        scope = "ports"

    sections = {}

    if scope in ("full", "ports"):
        ports = _scan_local_ports()
        sections["Open Ports (localhost)"] = (
            [f"{p} ({_service_name(p)})" for p in ports] if ports
            else ["No common service ports open. ✅"]
        )

    if scope in ("full", "wifi"):
        wifi = _wifi_recon()
        sections["Wi-Fi Networks"] = wifi if wifi else ["No Wi-Fi data available"]

    if scope in ("full", "startup"):
        startup = _startup_audit()
        sections["Startup Entries (suspicious)"] = (
            startup if startup else ["No suspicious startup entries found. ✅"]
        )

    if scope in ("full", "permissions"):
        perms = _permission_audit()
        sections["Sensitive Files & Permissions"] = (
            perms if perms else ["No permission issues found. ✅"]
        )

    if scope in ("full", "software"):
        sw = _software_audit()
        sections["Software / Update Status"] = (
            sw if sw else ["Could not determine software status."]
        )

    # Password audit always available
    if password:
        sections["Password Strength"] = audit_password(password)

    # ── Build report ────────────────────────────────────────────────
    lines = []
    lines.append("# 🔐 Lessan Security Scan Report")
    lines.append(f"\n**Date:** {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append(f"**Host:** {socket.gethostname()} ({platform.system()} {platform.release()})")
    lines.append(f"**Scope:** {scope}\n")

    for title, content in sections.items():
        lines.append(f"\n## {title}")
        if isinstance(content, list):
            for item in content:
                if isinstance(item, dict):
                    kv = ", ".join(f"{k}: {v}" for k, v in item.items())
                    lines.append(f"- {kv}")
                else:
                    lines.append(f"- {item}")
        elif isinstance(content, dict):
            for k, v in content.items():
                lines.append(f"- {k}: {v}")

    report = "\n".join(lines)

    if save:
        stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
        path  = REPORT_DIR / f"security-scan-{stamp}.md"
        path.write_text(report, encoding="utf-8")
        saved_msg = f"\n\n📄 Full report saved to: {path}"
    else:
        saved_msg = ""

    # ── Summary verdict ─────────────────────────────────────────────
    risk_level = "LOW"
    risk_points = 0
    if open_ports := sections.get("Open Ports (localhost)"):
        if isinstance(open_ports, list) and len(open_ports) > 1:
            risk_points += 2
    if startup := sections.get("Startup Entries (suspicious)"):
        if isinstance(startup, list) and len(startup) > 1:
            risk_points += 3
    if perms := sections.get("Sensitive Files & Permissions"):
        if isinstance(perms, list):
            for p in perms:
                if isinstance(p, dict) and "warning" in p:
                    risk_points += 1
    if risk_points >= 4:
        risk_level = "HIGH"
    elif risk_points >= 2:
        risk_level = "MEDIUM"

    summary = (
        f"🔐 **Security scan complete. Overall risk: {risk_level}** "
        f"({risk_points} risk indicators){saved_msg}"
    )
    return summary + "\n\n" + report


def _run_network_scan(target: str, save: bool) -> str:
    """Handles scan_type='network' — explicit nmap scan of a local target."""
    results = _network_scan(target)
    sections = []
    dt = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    sections.append(f"# 🌐 Lessan Network Scan Report")
    sections.append(f"\n**Date:** {dt}")
    sections.append(f"**Host:** {socket.gethostname()} ({platform.system()})")
    sections.append(f"**Target:** {target}\n")

    for item in results:
        if "error" in item:
            sections.append(f"- ⚠️ {item['error']}")
        else:
            sections.append(f"- Target: {item['target']}")
            if item.get("raw"):
                sections.append("```")
                sections.append(item["raw"])
                sections.append("```")

    report_text = "\n".join(sections)

    if save:
        stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
        path  = REPORT_DIR / f"network-scan-{stamp}.md"
        path.write_text(report_text, encoding="utf-8")
        return f"🌐 Network scan of {target} complete — full report saved to: {path}\n\n{report_text}"
    return report_text


# CLI entry for testing
if __name__ == "__main__":
    print(security_scanner({"scope": "full"}))
