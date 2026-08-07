"""Authentication routes for the Hospital Management System.

Provides a login page, a protected dashboard, and logout. Admin
credentials are read from the environment (HMS_ADMIN_USER /
HMS_ADMIN_PASSWORD) with a development-only fallback, and a per-session
CSRF token protects the login form from cross-site request forgery.
"""

import hmac
import logging
import os
import secrets

from flask import Blueprint, redirect, render_template_string, request, session, url_for

from utils.security import hash_password, verify_password

logger = logging.getLogger(__name__)

auth = Blueprint("auth", __name__)

# ---------------------------------------------------------------------------
# Credentials
# ---------------------------------------------------------------------------
# Admin credentials come from the environment so no default password is baked
# into the source. The fallback exists only for local development and MUST be
# overridden in any deployed environment.
ADMIN_USER = os.getenv("HMS_ADMIN_USER", "admin")
_ADMIN_PASSWORD = os.getenv("HMS_ADMIN_PASSWORD", "change-me")

# In-memory user store: username -> bcrypt hashed password.
# NOTE: this store resets on every process restart and cannot persist new
# users. Replace it with a real database (or hashed users table) before use
# with multiple staff accounts.
_USERS = {ADMIN_USER: hash_password(_ADMIN_PASSWORD)}

LOGIN_TEMPLATE = """\
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Hospital Management System — Sign in</title>
<style>
  :root { color-scheme: light dark; }
  * { box-sizing: border-box; }
  body { margin:0; min-height:100vh; display:grid; place-items:center;
         font-family: system-ui, -apple-system, Segoe UI, Roboto, sans-serif;
         background: linear-gradient(135deg, #0b3d5c, #14607f); }
  .card { background:#fff; color:#123; width: min(92vw, 380px);
          padding:2rem 2rem 1.75rem; border-radius:14px; box-shadow:0 18px 45px rgba(0,0,0,.35); }
  .card h1 { margin:0 0 .25rem; font-size:1.35rem; }
  .card .subtitle { margin:0 0 1.25rem; color:#5a6b7a; font-size:.9rem; }
  label { display:block; margin:.8rem 0 .3rem; font-size:.85rem; font-weight:600; }
  input { width:100%; padding:.6rem .7rem; border:1px solid #b8c4cd; border-radius:8px; font-size:1rem; }
  input:focus { outline:2px solid #14607f; outline-offset:1px; }
  button { margin-top:1.25rem; width:100%; padding:.7rem; border:0; border-radius:8px;
           background:#14607f; color:#fff; font-size:1rem; font-weight:600; cursor:pointer; }
  button:hover { background:#0b3d5c; }
  .error { background:#fdecec; color:#a11; border:1px solid #f5c6c6; border-radius:8px;
           padding:.6rem .8rem; font-size:.85rem; margin:0 0 1rem; }
</style>
</head>
<body>
  <main class="card">
    <h1>Hospital Management System</h1>
    <p class="subtitle">Secure staff sign in</p>
    {% if error %}<p class="error" role="alert">{{ error }}</p>{% endif %}
    <form method="post" action="{{ url_for('auth.login') }}">
      <input type="hidden" name="csrf_token" value="{{ csrf_token }}">
      <label for="username">Username</label>
      <input id="username" name="username" type="text" required autofocus autocomplete="username">
      <label for="password">Password</label>
      <input id="password" name="password" type="password" required autocomplete="current-password">
      <button type="submit">Sign in</button>
    </form>
    <p style="font-size:.75rem;color:#8a98a5;margin:1.25rem 0 0;text-align:center">
      Protected area — authorised staff only.
    </p>
  </main>
</body>
</html>
"""

DASHBOARD_TEMPLATE = """\
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Dashboard — Hospital Management System</title>
<style>
  body { margin:0; font-family: system-ui, -apple-system, Segoe UI, Roboto, sans-serif;
         background:#eef3f6; color:#123; }
  header { background:#0b3d5c; color:#fff; padding:1rem 1.5rem; display:flex;
           justify-content:space-between; align-items:center; }
  header h1 { font-size:1.15rem; margin:0; }
  header a { color:#ffd76a; text-decoration:none; font-size:.9rem; }
  main { max-width:720px; margin:2rem auto; padding:0 1.5rem; }
  .panel { background:#fff; border-radius:12px; padding:1.5rem; box-shadow:0 6px 18px rgba(0,0,0,.08); }
</style>
</head>
<body>
  <header>
    <h1>Hospital Management System</h1>
    <a href="{{ url_for('auth.logout') }}">Sign out ({{ username }})</a>
  </header>
  <main>
    <div class="panel">
      <h2>Welcome, {{ username }}</h2>
      <p>You are signed in to the Hospital Management System dashboard.</p>
      <p style="color:#5a6b7a;font-size:.9rem">Session content placeholder — patient and staff modules plug in here.</p>
    </div>
  </main>
</body>
</html>
"""


def _get_csrf_token() -> str:
    """Return the session CSRF token, generating one on first use."""
    token = session.get("csrf_token")
    if not token:
        token = secrets.token_hex(16)
        session["csrf_token"] = token
    return token


def _valid_csrf(submitted: str) -> bool:
    return bool(submitted) and hmac.compare_digest(submitted, session.get("csrf_token", ""))


@auth.route("/login", methods=["GET", "POST"])
def login():
    if "user" in session:
        return redirect(url_for("auth.dashboard"))

    if request.method == "POST":
        if not _valid_csrf(request.form.get("csrf_token", "")):
            session.pop("csrf_token", None)  # force token rotation
            return (
                render_template_string(
                    LOGIN_TEMPLATE,
                    error="Session expired — please try again.",
                    csrf_token=_get_csrf_token(),
                ),
                400,
            )

        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        try:
            if username in _USERS and verify_password(password, _USERS[username]):
                session.clear()
                session["user"] = username
                session["csrf_token"] = secrets.token_hex(16)  # rotate after sign-in
                return redirect(url_for("auth.dashboard"))
            error = "Invalid username or password."
        except Exception:
            logger.exception("Unexpected error during login")
            error = "Authentication error — please try again."
        return (
            render_template_string(LOGIN_TEMPLATE, error=error, csrf_token=_get_csrf_token()),
            401,
        )

    return render_template_string(LOGIN_TEMPLATE, error=None, csrf_token=_get_csrf_token())


@auth.route("/dashboard")
def dashboard():
    if "user" not in session:
        return redirect(url_for("auth.login"))
    return render_template_string(DASHBOARD_TEMPLATE, username=session["user"])


@auth.route("/logout", methods=["GET", "POST"])
def logout():
    session.clear()
    return redirect(url_for("auth.login"))
