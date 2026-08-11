"""Run / status / reset routes for the background job-hunting pipeline."""
from __future__ import annotations

from flask import Blueprint, jsonify

from webapp.security import json_error
from webapp.state import get_run_status, reset_status, start_background_run

bp = Blueprint("run", __name__, url_prefix="/api")


@bp.route("/run", methods=["POST"])
def trigger_run():
    try:
        if not start_background_run():
            return jsonify({"success": False, "message": "Scraper is already running in background."}), 400
        return jsonify({"success": True, "message": "Job scraper started in the background."})
    except Exception as e:
        return json_error(500, "Failed to start run", str(e))


@bp.route("/status")
def get_run_status_route():
    try:
        return jsonify(get_run_status())
    except Exception as e:
        return json_error(500, "Failed to read status", str(e))


@bp.route("/reset", methods=["POST"])
def reset_status_route():
    reset_status()
    return jsonify({"success": True, "message": "Scraper status reset to idle."})
