"""Settings routes (GET/POST /api/settings) with deep-merge persistence."""
from __future__ import annotations

import json
from typing import Any

from flask import Blueprint, jsonify, request

import config
from models import validate_settings_update
from webapp.security import json_error

bp = Blueprint("settings", __name__, url_prefix="/api")


def _deep_merge(base: dict, update: dict) -> None:
    """Recursively merge update dict into base dict (preserves unspecified keys)."""
    for key, value in update.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            _deep_merge(base[key], value)
        else:
            base[key] = value


@bp.route("/settings", methods=["GET"])
def get_settings():
    try:
        return jsonify(config.load_settings())
    except Exception as e:
        return json_error(500, "Failed to load settings", str(e))


@bp.route("/preferences/preview", methods=["GET"])
def preferences_preview():
    """Read-only preview: shows exactly what the system understood from the
    custom_requirements text (and company_type), before any run."""
    try:
        from requirement_scorer import parse_preferences
        settings = config.load_settings()
        prefs = settings.get("preferences", {}) or {}
        profile = parse_preferences(
            prefs.get("custom_requirements", "") or "",
            prefs.get("company_type", "") or "",
        )
        return jsonify({"success": True, "profile": profile})
    except Exception as e:
        return json_error(500, "Failed to parse preferences", str(e))


@bp.route("/settings", methods=["POST"])
def save_settings():
    try:
        new_data: dict[str, Any] = request.json or {}
        # Apply the model-layer validation BEFORE persistence so an invalid
        # patch (e.g. match_threshold=150 or interval_hours="x") is rejected
        # server-side rather than silently merged into settings.json.
        validation_error = validate_settings_update(new_data)
        if validation_error:
            return json_error(400, validation_error)
        settings_file = config.SETTINGS_FILE
        try:
            with open(settings_file, encoding="utf-8") as f:
                current = json.load(f)
        except Exception:
            current = {}
        # Deep merge so the AI/security sections are never wiped by a partial save.
        _deep_merge(current, new_data)
        with open(settings_file, "w", encoding="utf-8") as f:
            json.dump(current, f, indent=2, ensure_ascii=False)
        config.load_settings()
        return jsonify({"success": True, "message": "Settings saved successfully."})
    except Exception as e:
        return json_error(500, "Failed to save settings", str(e))
