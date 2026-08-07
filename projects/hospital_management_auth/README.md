# Hospital Management System — Secure Authentication

Secure authentication module for the Hospital Management System web
application, built with Flask and Python.

## Features
- Secure staff login with bcrypt-hashed credentials
- CSRF-protected login form (per-session token, HMAC-verified)
- Hardened session cookies (HttpOnly, SameSite=Lax, Secure in production)
- Protected dashboard — only reachable after sign-in
- Logout that clears the session
- Credentials from environment variables — no default passwords in source
- Modular design with Flask blueprints

## File structure
- `main.py` — Creates the Flask app, loads security settings, registers the auth blueprint
- `auth.py` — Login, logout, and dashboard routes
- `utils/security.py` — bcrypt password hashing and verification
- `test_auth.py` — End-to-end smoke tests (Flask test client, no server needed)

## Installation
1. Python 3.8+.
2. `pip install -r requirements.txt`

## Configuration (environment variables)
| Variable | Purpose | Default |
|---|---|---|
| `HMS_ENV` | `development` or `production` | `development` |
| `FLASK_SECRET_KEY` | Session signing key; **required** when `HMS_ENV=production` | `dev-secret-key` |
| `HMS_ADMIN_USER` | Admin username | `admin` |
| `HMS_ADMIN_PASSWORD` | Admin password | `change-me` (dev only) |
| `PORT` | Port the dev server binds | `5000` |

## Usage
- Development: `python main.py` → http://127.0.0.1:5000
- Production: set `HMS_ENV=production` and `FLASK_SECRET_KEY`, then run behind
a WSGI server, e.g. `gunicorn -w 2 main:create_app()`.

## Tests
`python test_auth.py`

## Security notes
- Passwords are hashed with bcrypt (per-user salt) — see `utils/security.py`.
- The user store is in-memory: it resets on restart. For multiple staff
  accounts, replace `_USERS` in `auth.py` with a real database and store
  bcrypt hashes (never plaintext).
- Never run the built-in server in production; the debugger is disabled when
  `HMS_ENV=production`.
