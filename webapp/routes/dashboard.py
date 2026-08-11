"""Dashboard page routes."""
from __future__ import annotations

from flask import Blueprint, make_response, send_from_directory

import webapp.state

bp = Blueprint("dashboard", __name__)


def _serve_dashboard():
    # No caching: the single-file dashboard changes often during development and
    # a stale cached copy otherwise sends users an outdated upload handler.
    resp = make_response(send_from_directory(webapp.state.DIRECTORY, "dashboard.html"))
    resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    resp.headers["Pragma"] = "no-cache"
    resp.headers["Expires"] = "0"
    return resp


@bp.route("/")
def serve_dashboard():
    return _serve_dashboard()


@bp.route("/dashboard.html")
def serve_dashboard_direct():
    return _serve_dashboard()
