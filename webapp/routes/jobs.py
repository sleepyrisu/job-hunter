"""Job data and application-status routes."""
from __future__ import annotations

from flask import Blueprint, jsonify, request

import database as db
from models import validate_job_id
from webapp.security import json_error

bp = Blueprint("jobs", __name__, url_prefix="/api")


@bp.route("/jobs", methods=["GET"])
def handle_jobs():
    try:
        return jsonify(db.get_all_jobs())
    except Exception as e:
        return json_error(500, "Failed to load jobs", str(e))


@bp.route("/jobs/clear-all", methods=["POST"])
def clear_all_jobs():
    try:
        db.clear_all_jobs()
        return jsonify({"success": True, "message": "All job data cleared."})
    except Exception as e:
        return json_error(500, "Failed to clear jobs", str(e))


@bp.route("/jobs/delete-batch", methods=["POST"])
def delete_jobs_batch():
    try:
        data = request.json or {}
        ids_to_delete = data.get("ids", [])
        if not ids_to_delete:
            return jsonify({"success": True, "message": "No jobs specified for deletion."})
        # Reject control characters / non-string ids before they reach SQL.
        for job_id in ids_to_delete:
            if validate_job_id(job_id) is not None:
                return json_error(400, f"Invalid job id in batch: {job_id!r}")
        deleted_count = db.delete_jobs_batch(ids_to_delete)
        return jsonify({"success": True, "message": f"Successfully deleted {deleted_count} jobs."})
    except Exception as e:
        return json_error(500, "Failed to delete jobs", str(e))


@bp.route("/jobs/<job_id>", methods=["DELETE"])
def delete_job(job_id):
    # Legacy route: works only for simple (non-URL) job ids.
    try:
        deleted = db.delete_job(job_id)
        if not deleted:
            return json_error(404, "Job not found")
        return jsonify({"success": True, "message": f"Job '{job_id}' deleted."})
    except Exception as e:
        return json_error(500, "Failed to delete job", str(e))


@bp.route("/jobs/delete", methods=["POST"])
def delete_job_body():
    # Job ids may be full URLs (slashes), so accept them in the JSON body.
    try:
        data = request.json or {}
        job_id = data.get("id") or data.get("job_id")
        if not job_id:
            return json_error(400, "Missing job id")
        deleted = db.delete_job(job_id)
        if not deleted:
            return json_error(404, "Job not found")
        return jsonify({"success": True, "message": f"Job '{job_id}' deleted."})
    except Exception as e:
        return json_error(500, "Failed to delete job", str(e))


@bp.route("/jobs/status", methods=["POST"])
def set_job_status():
    try:
        data = request.json or {}
        job_id = data.get("id") or data.get("job_id")
        status = (data.get("status") or "").strip().lower()
        if not job_id:
            return json_error(400, "Missing job id")
        ok, message = db.update_job_status(job_id, status)
        if not ok:
            return json_error(400, message)
        return jsonify({"success": True, "message": message})
    except Exception as e:
        return json_error(500, "Failed to update status", str(e))


@bp.route("/jobs/stats", methods=["GET"])
def job_status_stats():
    try:
        return jsonify(db.get_status_stats())
    except Exception as e:
        return json_error(500, "Failed to load stats", str(e))


@bp.route("/applications", methods=["GET"])
def list_applications():
    try:
        from application_tracker import ApplicationTracker
        tracker = ApplicationTracker()
        return jsonify(tracker.list_applications())
    except Exception as e:
        return json_error(500, "Failed to load applications", str(e))
