# actions/whatsapp.py
# WhatsApp Web automation via Playwright.
#
# Drives web.whatsapp.com with a persistent Chromium profile so the login
# (QR scan) is only needed ONCE. After that, the session is reused.
#
# Usage (parameters):
#   contact : recipient name exactly as shown in WhatsApp (required)
#   message : the message text to send (required)
#   action  : "send" (default) | "login" | "status"  (optional)

import threading
import time
from pathlib import Path
from typing import Callable

from playwright.sync_api import sync_playwright

WA_PAGE        = "https://web.whatsapp.com"
PROFILE_DIR    = Path.home() / ".lessan_whatsapp_profile"
LOGIN_TIMEOUT  = 90      # seconds to wait for the user to scan the QR code
LOAD_TIMEOUT   = 20      # seconds to wait for the app/QR to appear after goto

_pw           = None
_context      = None
_driver_lock  = threading.Lock()
_driver_started = False


# ── Persistent browser context (stays logged in across runs) ────────────────

def _get_driver():
    """Launches (once) a persistent Chromium context pre-logged into WhatsApp."""
    global _pw, _context, _driver_started
    with _driver_lock:
        if _driver_started:
            try:
                if _context is not None and _context.browser and _context.browser.is_connected():
                    return _context
            except Exception:
                pass

        PROFILE_DIR.mkdir(parents=True, exist_ok=True)
        _pw = sync_playwright().start()
        try:
            _context = _pw.chromium.launch_persistent_context(
                str(PROFILE_DIR),
                headless=False,
                no_viewport=True,
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--start-maximized",
                ],
            )
        except Exception as e:
            try:
                _pw.stop()
            except Exception:
                pass
            _pw = None
            raise RuntimeError(
                "Could not launch Chromium for WhatsApp Web. "
                "Run 'python -m playwright install chromium' first. "
                f"({e})"
            )
        _driver_started = True
        return _context


def _get_page(context):
    """Returns a usable page from the persistent context."""
    for p in context.pages:
        if not p.is_closed():
            return p
    return context.new_page()


# ── Login state helpers ──────────────────────────────────────────────────────

def _app_loaded(page) -> bool:
    """WhatsApp Web is loaded and logged in when the left side panel exists."""
    try:
        return page.locator("#side").count() > 0 or page.locator("#main").count() > 0
    except Exception:
        return False


def _qr_visible(page) -> bool:
    """A QR login screen is showing when the scan canvas / data-ref is present."""
    try:
        return (
            page.locator('canvas[aria-label="Scan me!"]').count() > 0
            or page.locator("div[data-ref]").count() > 0
        )
    except Exception:
        return False


def _ensure_whatsapp_ready(page, speak: Callable | None = None,
                           on_login_prompt: Callable | None = None) -> str | None:
    """
    Waits until the WhatsApp Web app is usable. If a QR code is displayed,
    prompts the user to scan it (once) and waits for login to complete.
    Returns None on success, or an error message string.
    """
    deadline = time.time() + LOAD_TIMEOUT
    while time.time() < deadline:
        if _app_loaded(page):
            return None
        if _qr_visible(page):
            break
        time.sleep(1)

    if _app_loaded(page):
        return None

    if not _qr_visible(page):
        return "WhatsApp Web did not load in time. Check your internet connection."

    # Login required — ask the user to scan the QR code shown in the browser.
    msg = (
        "WhatsApp Web is not logged in. Please open WhatsApp on your phone, "
        "go to Settings → Linked devices, and scan the QR code on the screen. "
        "Take your time."
    )
    print(f"[WhatsApp] 📱 {msg}")
    if on_login_prompt:
        on_login_prompt(msg)
    if speak:
        speak(msg)

    wait_until = time.time() + LOGIN_TIMEOUT
    while time.time() < wait_until:
        if _app_loaded(page):
            print("[WhatsApp] ✅ Logged in successfully.")
            return None
        time.sleep(2)

    return (
        "WhatsApp login timed out — no QR code scanned. "
        "Just say the message again once you have scanned the code."
    )


# ── Element locators (with fallbacks for WhatsApp Web DOM changes) ───────────

_SEARCH_BOX_SELECTORS = [
    'div[contenteditable="true"][data-tab="3"]',
    'div[role="textbox"][aria-label*="search" i]',
    'div[role="textbox"][contenteditable="true"]',
]

_MESSAGE_BOX_SELECTORS = [
    'footer div[contenteditable="true"]',
    'div[contenteditable="true"][data-tab="10"]',
    'div[role="textbox"][aria-label="Type a message"]',
    'div[role="textbox"][contenteditable="true"]',
]


def _first_visible(page, selectors: list):
    for selector in selectors:
        try:
            loc = page.locator(selector).first
            if loc.count() > 0 and loc.is_visible():
                return loc
        except Exception:
            continue
    return None


def _escape_css_string(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


# ── Core actions ────────────────────────────────────────────────────────────

def _open_chat(page, contact: str) -> None:
    """Searches for the contact in the chat list and opens the conversation."""
    box = _first_visible(page, _SEARCH_BOX_SELECTORS)
    if box is None:
        raise RuntimeError("Could not find the WhatsApp search box.")

    box.click()
    try:
        box.fill("")            # clear any previous search term
    except Exception:
        pass
    box.type(contact, delay=15)
    page.wait_for_timeout(1800)  # let the search results render

    # 1) Exact title match (fast & precise)
    exact = page.locator(f'span[title="{_escape_css_string(contact)}"]')
    if exact.count() > 0:
        exact.first.click()
        return

    # 2) Fuzzy match: first visible result row that starts with the name
    rows    = page.locator('div[role="listitem"]')
    contact_lower = contact.lower()
    for i in range(rows.count()):
        row = rows.nth(i)
        try:
            if not row.is_visible():
                continue
            text = row.inner_text(timeout=2000).strip()
            if text.lower().startswith(contact_lower):
                row.click()
                return
        except Exception:
            continue

    raise RuntimeError(f"Contact '{contact}' was not found in WhatsApp.")


def _send_message(page, message: str, contact: str) -> str:
    """Types the message into the open conversation and sends it."""
    box = _first_visible(page, _MESSAGE_BOX_SELECTORS)
    if box is None:
        raise RuntimeError("Could not find the WhatsApp message input.")

    box.click()
    box.type(message, delay=20)
    page.wait_for_timeout(400)

    send_btn = page.locator('[data-testid="compose-btn-send"]')
    if send_btn.count() > 0 and send_btn.first.is_visible():
        send_btn.first.click()
    else:
        box.press("Enter")

    page.wait_for_timeout(800)
    return f"Message sent to {contact} on WhatsApp Web."


# ── Public API ──────────────────────────────────────────────────────────────

def _login_and_wait(player=None, speak: Callable | None = None) -> str:
    context = _get_driver()
    page    = _get_page(context)

    def on_login_prompt(text: str):
        if player and hasattr(player, "write_log"):
            player.write_log(f"[wa] {text}")

    try:
        page.goto(WA_PAGE, wait_until="domcontentloaded", timeout=30000)
        err = _ensure_whatsapp_ready(page, speak=speak, on_login_prompt=on_login_prompt)
        return err if err else "WhatsApp Web is logged in and ready."
    except Exception as e:
        return f"WhatsApp error: {e}"


def _status() -> str:
    with _driver_lock:
        if not _driver_started or _context is None:
            return "WhatsApp session not started yet."
        try:
            if not (_context.browser and _context.browser.is_connected()):
                return "WhatsApp session not started yet."
        except Exception:
            return "WhatsApp session not started yet."

    page = next((p for p in _context.pages if not p.is_closed()), None)
    if page and _app_loaded(page):
        return "WhatsApp Web is logged in and ready."
    return "WhatsApp Web session is open but login is required."


def whatsapp(
    parameters:      dict,
    response=None,
    player=None,
    session_memory=None,
    speak: Callable | None = None,
) -> str:
    """
    Sends a WhatsApp message by driving WhatsApp Web with Playwright.

    parameters:
        contact : recipient's name exactly as shown in WhatsApp (required)
        message : the message text to send (required)
        action  : "send" (default) | "login" | "status"  (optional)

    If WhatsApp Web is not logged in, the Chromium window opens showing the
    QR code and the user is prompted (visually + via speak/log) to scan it once.
    """
    params  = parameters or {}
    action  = str(params.get("action", "send")).strip().lower()
    contact = str(params.get("contact") or params.get("receiver") or "").strip()
    message = str(params.get("message") or params.get("message_text") or "").strip()

    if action == "status":
        return _status()
    if action == "login":
        return _login_and_wait(player=player, speak=speak)
    if action != "send":
        return f"Unknown action '{action}'. Use 'send' (default), 'login', or 'status'."

    if not contact:
        return "Please specify the WhatsApp contact name, sir."
    if not message:
        return "Please specify the WhatsApp message, sir."

    print(f"[WhatsApp] 📨 {contact} ← {message[:60]}")
    if player and hasattr(player, "write_log"):
        player.write_log(f"[wa] Sending to {contact}...")

    try:
        context = _get_driver()
        page    = _get_page(context)

        def on_login_prompt(text: str):
            if player and hasattr(player, "write_log"):
                player.write_log(f"[wa] {text}")

        page.goto(WA_PAGE, wait_until="domcontentloaded", timeout=30000)
        err = _ensure_whatsapp_ready(page, speak=speak, on_login_prompt=on_login_prompt)
        if err:
            return err

        _open_chat(page, contact)
        result = _send_message(page, message, contact)

        print(f"[WhatsApp] ✅ {result}")
        if player and hasattr(player, "write_log"):
            player.write_log(f"[wa] {result}")
        return result

    except Exception as e:
        msg = f"WhatsApp error: {e}"
        print(f"[WhatsApp] ❌ {msg}")
        if player and hasattr(player, "write_log"):
            player.write_log(f"[wa] {msg}")
        return msg


__all__ = ["whatsapp"]