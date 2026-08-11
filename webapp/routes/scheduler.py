"""Scheduler configuration routes (GET/POST /api/scheduler)."""
from __future__ import annotations

import contextlib
import time
from typing import Any

from flask import Blueprint, jsonify, request

from webapp.security import json_error
from webapp.state import load_scheduler_state, save_scheduler_state

bp = Blueprint("scheduler", __name__, url_prefix="/api")


@bp.route("/scheduler", methods=["GET"])
def get_scheduler():
    try:
        return jsonify(load_scheduler_state())
    except Exception as e:
        return json_error(500, "Failed to load scheduler", str(e))


@bp.route("/scheduler", methods=["POST"])
def set_scheduler():
    try:
        data: dict[str, Any] = request.json or {}
        state = load_scheduler_state()
        if "enabled" in data:
            state["enabled"] = bool(data["enabled"])
        if "interval_hours" in data:
            with contextlib.suppress(TypeError, ValueError):
                state["interval_hours"] = max(1, int(data["interval_hours"]))
        if state["enabled"] and not state.get("next_run_at"):
            state["next_run_at"] = time.time() + state["interval_hours"] * 3600
        if not state["enabled"]:
            state["next_run_at"] = None
        save_scheduler_state(state)
        return jsonify({"success": True, "scheduler": state})
    except Exception as e:
        return json_error(500, "Failed to update scheduler", str(e))
