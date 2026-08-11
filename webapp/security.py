"""
Security middleware for the dashboard API.

Implements, with zero extra dependencies:

- Auth via ``X-Auth-Token`` header, compared in constant time (``hmac.compare_digest``)
  so token checks do not leak timing information.
- CSRF defense: every state-changing request (POST/PUT/DELETE) must present either
  an ``X-Auth-Token`` header or a matching ``X-CSRF-Token`` header; the dashboard
  sends both. Custom headers cannot be forged by a cross-site form or image, so
  this neutralises CSRF without cookies.
- A simple in-memory sliding-window rate limiter for the mutating endpoints.
- Hardened security headers on every response (CSP, HSTS, frame/type/mime guards).
- Central JSON error handling so the API never leaks HTML or stack traces.
"""
from __future__ import annotations

import hmac
import time
from collections import defaultdict, deque
from collections.abc import Callable

from flask import jsonify, request

import config

FREE_PATHS = {"/", "/dashboard.html"}
MUTATING_METHODS = {"POST", "PUT", "PATCH", "DELETE"}

# --- Rate limiting (in-memory sliding window) ------------------------------

_RATE_LIMITS: dict[str, deque] = defaultdict(deque)
RATE_LIMIT_WINDOW = 60  # seconds
RATE_LIMIT_MAX = 60  # requests per window per client key


def _client_key() -> str:
    return request.remote_addr or "unknown"


def is_rate_limited(limit: int | None = None, window: int | None = None) -> bool:
    """Return True if the current client has exceeded the window budget."""
    limit = RATE_LIMIT_MAX if limit is None else limit
    window = RATE_LIMIT_WINDOW if window is None else window
    now = time.time()
    key = f"{_client_key()}:{request.method}:{request.path}"
    hits = _RATE_LIMITS.setdefault(key, deque())
    while hits and now - hits[0] > window:
        hits.popleft()
    hits.append(now)
    return len(hits) > limit


# --- Auth -------------------------------------------------------------------

def _check_auth() -> bool:
    if not config.DASHBOARD_TOKEN:
        return True
    if request.path in FREE_PATHS:
        return True
    supplied = request.headers.get("X-Auth-Token") or request.headers.get("X-CSRF-Token") or request.args.get("token")
    if not supplied:
        return False
    expected = config.DASHBOARD_TOKEN
    return hmac.compare_digest(str(supplied), expected)


def require_auth() -> dict | tuple | None:
    """before_request hook. Returns a 401 JSON response when unauthenticated."""
    if not _check_auth():
        return jsonify({"error": "Unauthorized", "message": "Valid access token required."}), 401
    return None


def require_csrf() -> dict | tuple | None:
    """before_request hook enforcing CSRF defense on state-changing requests.

    When the dashboard token is empty the app is intended for local use only,
    so the check is skipped. Otherwise at least one custom header must be sent.
    """
    if request.method not in MUTATING_METHODS:
        return None
    if not config.DASHBOARD_TOKEN:
        return None
    if _check_auth():
        return None
    return jsonify({"error": "Forbidden", "message": "CSRF token required."}), 403


def apply_security_headers(response):
    """Attach hardened security headers to every response."""
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "no-referrer")
    response.headers.setdefault("X-XSS-Protection", "1; mode=block")
    response.headers.setdefault(
        "Content-Security-Policy",
        "default-src 'self'; img-src 'self' data: https:; style-src 'self' 'unsafe-inline'; "
        "script-src 'self' 'unsafe-inline'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'",
    )
    if request.is_secure:
        response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
    response.headers.setdefault("Cache-Control", "no-store")
    return response


def apply_rate_limit() -> dict | tuple | None:
    """before_request hook limiting the mutating endpoints per client.

    Skipped while ``TESTING`` so the test suite can hammer endpoints freely.
    """
    if request.method in MUTATING_METHODS:
        from flask import current_app
        if not current_app.config.get("TESTING") and is_rate_limited():
            return jsonify({"error": "Too Many Requests", "message": "Slow down."}), 429
    return None


# --- Helpers -----------------------------------------------------------------

def json_error(status_code: int, error: str, message: str = "") -> tuple:
    return jsonify({"error": error, "message": message or error}), status_code


def wrap_route(handler: Callable):
    """Decorator converting unexpected exceptions into a clean 500 JSON response.

    The real dashboard already wraps each route in try/except; this provides a
    consistent fallback so an unexpected exception never leaks a stack trace.
    """
    def wrapper(*args, **kwargs):
        try:
            return handler(*args, **kwargs)
        except Exception as e:
            import traceback
            print(f"Unhandled error in {handler.__name__}: {e}\n{traceback.format_exc()}")
            return json_error(500, "Internal Server Error")
    wrapper.__name__ = handler.__name__
    wrapper.__doc__ = handler.__doc__
    return wrapper
