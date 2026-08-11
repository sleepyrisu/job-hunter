"""Browser-agent start/stop routes."""
from __future__ import annotations

import threading

from flask import Blueprint, jsonify, request

import config
from webapp.state import browser_running, update_status

bp = Blueprint("browser", __name__, url_prefix="/api/browser")


@bp.route("/start", methods=["POST"])
def browser_start():
    global browser_running
    if browser_running:
        return jsonify({"success": False, "message": "Browser agent already running."}), 400
    data = request.json or {}
    keywords = data.get("keywords") or config.SEARCH_KEYWORDS
    locations = data.get("locations") or config.LOCATIONS

    def run_browser_thread():
        global browser_running
        browser_running = True
        try:
            from browser_agent import run_search_sync
            update_status(f"Browser agent: searching {len(keywords)} keywords in {len(locations)} locations", True)
            jobs = run_search_sync(keywords, locations, headless=False)
            update_status(f"Browser agent done: {len(jobs)} jobs found", False)
        except Exception as e:
            import traceback
            update_status(f"Browser agent error: {e}", False)
            print(f"Browser agent error: {e}\n{traceback.format_exc()}")
        finally:
            browser_running = False

    thread = threading.Thread(target=run_browser_thread)
    thread.daemon = True
    thread.start()
    return jsonify({"success": True, "message": "Browser agent started. Watch it in a new Chrome window."})


@bp.route("/stop", methods=["POST"])
def browser_stop():
    global browser_running
    browser_running = False
    try:
        from browser_agent import request_stop
        request_stop()
    except Exception:
        # Stopping an absent browser is a no-op.
        pass  # nosec B110
    update_status("Browser agent stop requested", False)
    return jsonify({"success": True, "message": "Stop signal sent."})
