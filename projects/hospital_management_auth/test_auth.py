"""End-to-end smoke tests for the Hospital Management System auth flow.

Run from the project directory with:
    python test_auth.py
Uses Flask's test client, so no server or network is required.
"""

import os
import sys

os.environ.setdefault("HMS_ADMIN_USER", "admin")
os.environ.setdefault("HMS_ADMIN_PASSWORD", "admin123")
os.environ.setdefault("FLASK_SECRET_KEY", "test-secret-key")

import main

FAILURES = []


def check(name, cond, extra=""):
    status = "PASS" if cond else "FAIL"
    print(f"[{status}] {name}" + (f"  ({extra})" if extra and not cond else ""))
    if not cond:
        FAILURES.append(name)


def test_login_page():
    app = main.create_app()
    with app.test_client() as c:
        r = c.get("/login")
        check("GET /login renders 200", r.status_code == 200, str(r.status_code))
        check("login page contains CSRF field", b'name="csrf_token"' in r.data)


def test_csrf_rejection():
    app = main.create_app()
    with app.test_client() as c:
        r = c.post("/login", data={"username": "admin", "password": "admin123"})
        check("POST without CSRF token rejected", r.status_code == 400, str(r.status_code))


def test_dashboard_redirects_when_logged_out():
    app = main.create_app()
    with app.test_client() as c:
        r = c.get("/dashboard")
        check("unauthenticated /dashboard -> 302", r.status_code == 302, str(r.status_code))
        check("redirect targets login", "/login" in r.headers.get("Location", ""))


def _login(client):
    client.get("/login")  # primes the CSRF token
    with client.session_transaction() as sess:
        token = sess["csrf_token"]
    return client.post(
        "/login",
        data={"username": "admin", "password": "admin123", "csrf_token": token},
        follow_redirects=False,
    )


def test_successful_login_and_dashboard():
    app = main.create_app()
    with app.test_client() as c:
        r = _login(c)
        check("valid credentials -> 302", r.status_code == 302, str(r.status_code))
        check("redirects to dashboard", r.headers.get("Location", "").endswith("/dashboard"))

        d = c.get("/dashboard")
        check("authenticated /dashboard -> 200", d.status_code == 200, str(d.status_code))
        check("dashboard greets user", b"admin" in d.data)


def test_invalid_credentials():
    app = main.create_app()
    with app.test_client() as c:
        c.get("/login")
        with c.session_transaction() as sess:
            token = sess["csrf_token"]
        r = c.post(
            "/login",
            data={"username": "admin", "password": "wrong", "csrf_token": token},
        )
        check("bad password -> 401", r.status_code == 401, str(r.status_code))
        check("error message shown", b"Invalid username" in r.data)


def test_logout():
    app = main.create_app()
    with app.test_client() as c:
        _login(c)
        r = c.get("/logout", follow_redirects=False)
        check("logout -> 302", r.status_code == 302, str(r.status_code))
        check("logout redirects to login", r.headers.get("Location", "").endswith("/login"))
        d = c.get("/dashboard")
        check("/dashboard protected after logout", d.status_code == 302, str(d.status_code))


if __name__ == "__main__":
    for fn in (
        test_login_page,
        test_csrf_rejection,
        test_dashboard_redirects_when_logged_out,
        test_successful_login_and_dashboard,
        test_invalid_credentials,
        test_logout,
    ):
        fn()
    print()
    if FAILURES:
        print(f"{len(FAILURES)} check(s) FAILED: {', '.join(FAILURES)}")
        sys.exit(1)
    print("All smoke tests passed.")
