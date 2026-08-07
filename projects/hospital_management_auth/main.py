"""Hospital Management System — application entry point."""

import logging
import os

from flask import Flask

from auth import auth as auth_blueprint


def create_app() -> Flask:
    """Build the Flask application with secure defaults."""
    app = Flask(__name__)

    env = os.getenv("HMS_ENV", "development")
    secret_key = os.getenv("FLASK_SECRET_KEY")

    # In production the secret key MUST come from the environment.
    if env == "production" and not secret_key:
        raise RuntimeError("FLASK_SECRET_KEY must be set when HMS_ENV=production.")
    app.config["SECRET_KEY"] = secret_key or "dev-secret-key"

    # Hardened session cookies.
    app.config["SESSION_COOKIE_HTTPONLY"] = True
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
    app.config["SESSION_COOKIE_SECURE"] = env == "production"

    app.register_blueprint(auth_blueprint)
    return app


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    app = create_app()
    # Never run the debugger/reloader in production.
    app.run(
        host="0.0.0.0",
        port=int(os.getenv("PORT", "5000")),
        debug=os.getenv("HMS_ENV") != "production",
    )
