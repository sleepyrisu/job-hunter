"""Resume upload and resume-scan routes."""
from __future__ import annotations

import base64
import os
import threading
import xml.etree.ElementTree as ET  # nosec B405
import zipfile

from flask import Blueprint, jsonify, request

import database as db
import webapp.state
from webapp.security import json_error
from webapp.state import is_running_flag, run_job_hunter_async

bp = Blueprint("resume", __name__, url_prefix="/api")

ALLOWED_EXTENSIONS = {".pdf", ".doc", ".docx", ".md", ".txt"}
MAX_FILE_SIZE = 16 * 1024 * 1024


def _parse_pdf(save_path: str) -> str:
    import fitz
    doc = fitz.open(save_path)
    try:
        return "\n".join(page.get_text() for page in doc)
    finally:
        doc.close()


def _parse_docx(save_path: str) -> str:
    with zipfile.ZipFile(save_path) as z, z.open("word/document.xml") as f:
        xml_content = f.read()
    # DOCX document.xml is a controlled OOXML structure produced by office
    # software; uploads are already bounded by the 16MB limit and zip parsing.
    root = ET.fromstring(xml_content)  # nosec B314
    return "".join(t.text or "" for t in root.iter("{http://schemas.openxmlformats.org/wordprocessingml/2006/main}t"))


def _extract_content(ext: str, save_path: str) -> str:
    if ext == ".pdf":
        return _parse_pdf(save_path)
    if ext in (".md", ".txt"):
        with open(save_path, encoding="utf-8") as f:
            return f.read()
    if ext in (".doc", ".docx"):
        return _parse_docx(save_path)
    return ""


@bp.route("/upload-resume", methods=["POST"])
def upload_resume():
    """Accept a resume via multipart OR base64-JSON.

    Some user environments rewrite multipart bodies in transit (a proxy/AV MIME
    filter strips or rebuilds the boundary), which made Flask parse the part
    list as empty -> "No file uploaded" even though the bytes arrive. The JSON
    path sends the file base64-encoded inside a plain JSON body, avoiding the
    multipart parser entirely (and is the path the dashboard now uses).
    """
    if request.files and "resume" in request.files:
        file = request.files["resume"]
        filename = file.filename or ""
        raw = file.read()
        auto_run = (request.form.get("auto_run", "1") or "1").lower() not in ("0", "false", "no", "off")
        return _handle_upload(filename, raw, auto_run)

    payload = request.get_json(silent=True) or {}
    filename = payload.get("filename", "")
    data_url = payload.get("dataUrl", "")
    if not filename or not data_url or "," not in data_url:
        print("upload-resume: JSON path missing filename/dataUrl; "
              f"content_type={request.mimetype}, content_length={request.content_length}", flush=True)
        return json_error(400, "No file uploaded")
    try:
        raw = base64.b64decode(data_url.split(",", 1)[1], validate=True)
    except Exception:
        return json_error(400, "Invalid file data")
    return _handle_upload(filename, raw, bool(payload.get("auto_run", True)))


def _handle_upload(filename: str, raw: bytes, auto_run: bool):
    """Validate and persist an uploaded resume (shared by both transport paths)."""
    if raw is None or raw == b"":
        return json_error(400, "No file selected")

    ext = os.path.splitext(filename)[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        return json_error(400, f"File type {ext} not allowed. Use: {', '.join(sorted(ALLOWED_EXTENSIONS))}")

    # File size guard (also enforced server-side via MAX_CONTENT_LENGTH).
    if len(raw) > MAX_FILE_SIZE:
        return json_error(400, "File too large. Max 16MB allowed.")

    # Validate filename (no path separators) to prevent path traversal.
    if "/" in filename or "\\" in filename:
        return json_error(400, "Invalid filename")

    save_path = os.path.join(webapp.state.DIRECTORY, f"resume{ext}")
    with open(save_path, "wb") as f:
        f.write(raw)

    try:
        content = _extract_content(ext, save_path)
    except Exception as e:
        print(f"Resume parse error: {e}")
        content = ""

    resume_md_path = os.path.join(webapp.state.DIRECTORY, "resume.md")
    # resume.md write is best-effort; failure should not abort the upload.
    try:
        with open(resume_md_path, "w", encoding="utf-8") as f:
            f.write(content)
    except Exception:
        pass  # nosec B110

    db.save_user_profile(resume_text=content, resume_filename=filename)
    # Resume sync is best-effort; pipeline continues without it.
    try:
        from resume_scanner import sync_from_resume
        sync_from_resume(use_agy=False)
    except Exception:
        pass  # nosec B110

    # Auto-run the full search pipeline so uploading a resume immediately
    # starts hunting for matching jobs (no manual "Run" needed).
    auto_search = auto_run and not is_running_flag
    if auto_search:
        threading.Thread(target=run_job_hunter_async, daemon=True).start()
        message = (f"Resume uploaded: {filename}. "
                   f"Auto-searching matching jobs from your resume in the background...")
    else:
        message = f"Resume uploaded: {filename}. Settings updated from resume."
    return jsonify({"success": True, "message": message, "filename": filename, "auto_search": auto_search})


@bp.route("/resume-scan", methods=["POST"])
def resume_scan():
    try:
        from resume_scanner import sync_from_resume
        result = sync_from_resume(use_agy=True)
        return jsonify(result)
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@bp.route("/resume/info", methods=["GET"])
def resume_info():
    """Return metadata about the currently stored resume (no file content)."""
    try:
        profile = db.get_user_profile()
    except Exception:
        profile = None
    filename = (profile.get("resume_filename") if profile else None) or ""
    return jsonify({"has_resume": bool(filename), "filename": filename})
