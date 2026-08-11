"""
webapp package.

Application factory (`create_app`) that wires together Flask, the route
blueprints, and the security middleware. This keeps the entry point tiny and
makes the app trivially testable without a running server.
"""
from __future__ import annotations

import logging
from datetime import datetime

from flask import Flask, request

import config
from webapp import security
from webapp.state import DIRECTORY, _requests_log, update_status  # noqa: F401

from .routes import browser, dashboard, jobs, resume, run, scheduler, settings


def create_app() -> Flask:
    app = Flask(__name__, static_folder=None)
    app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024  # 16MB uploads
    app.config["JSON_AS_ASCII"] = False
    app.config["SECRET_KEY"] = config.SECRET_KEY

    @app.before_request
    def log_request_info():
        try:
            safe_path = request.path.encode("ascii", "ignore").decode("ascii")
            print(f"REQUEST: {request.method} {safe_path}", flush=True)
            with open(_requests_log(), "a", encoding="utf-8") as f:
                f.write(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {request.method} {request.path}\n")
        except Exception:
            # Request logging is best-effort; failures must not break requests.
            pass  # nosec B110

    # Security middleware (order matters: auth + CSRF run before rate limit).
    app.before_request(security.require_auth)
    app.before_request(security.require_csrf)
    app.before_request(security.apply_rate_limit)
    app.after_request(security.apply_security_headers)

    # Close the per-request-thread SQLite handle after each request so pooled /
    # per-request threads do not accumulate connections (fd leak guard).
    import database as db
    app.teardown_appcontext(lambda exc: db.close_connection())

    # Blueprints
    app.register_blueprint(dashboard.bp)
    app.register_blueprint(jobs.bp)
    app.register_blueprint(settings.bp)
    app.register_blueprint(run.bp)
    app.register_blueprint(scheduler.bp)
    app.register_blueprint(browser.bp)
    app.register_blueprint(resume.bp)

    # Startup
    update_status("idle", False)

    logging.basicConfig(level=logging.INFO)
    return app
