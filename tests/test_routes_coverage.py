"""Coverage for webapp routes (browser, run, jobs, resume, settings) and state."""
import contextlib
import io
import json

import webapp.state
from tests.conftest import seed_job


class FakeThread:
    def __init__(self, target=None, daemon=None, **kw):
        self.target = target
        self.daemon = daemon

    def start(self):
        pass


def _auth():
    return {"X-Auth-Token": "test-token"}


# --- Browser routes --------------------------------------------------------

def test_browser_start_success(client, auth_headers, monkeypatch):
    monkeypatch.setattr("webapp.routes.browser.threading.Thread", FakeThread)
    monkeypatch.setattr("webapp.routes.browser.browser_running", False)
    res = client.post("/api/browser/start", headers=auth_headers, json={})
    assert res.status_code == 200
    assert res.get_json()["success"] is True


def test_browser_start_already_running(client, auth_headers, monkeypatch):
    monkeypatch.setattr("webapp.routes.browser.browser_running", True)
    res = client.post("/api/browser/start", headers=auth_headers, json={})
    assert res.status_code == 400


def test_browser_stop(client, auth_headers, monkeypatch):
    monkeypatch.setattr("webapp.routes.browser.threading.Thread", FakeThread)
    res = client.post("/api/browser/stop", headers=auth_headers)
    assert res.status_code == 200


# --- Run / status / reset --------------------------------------------------

def test_run_starts_background(client, auth_headers, monkeypatch):
    import webapp.routes.run as rr
    monkeypatch.setattr("webapp.state.is_running_flag", False)
    monkeypatch.setattr("webapp.state.threading.Thread", FakeThread)
    started = {"called": False}

    def fake_start():
        started["called"] = True
        return True

    monkeypatch.setattr(rr, "start_background_run", fake_start)
    res = client.post("/api/run", headers=auth_headers)
    assert res.status_code == 200
    assert res.get_json()["success"] is True
    assert started["called"] is True


def test_run_already_running(client, auth_headers, monkeypatch):
    import webapp.routes.run as rr

    def fake_start():
        return False

    monkeypatch.setattr(rr, "start_background_run", fake_start)
    res = client.post("/api/run", headers=auth_headers)
    assert res.status_code == 400
    assert "already running" in res.get_json()["message"].lower()


def test_status_returns_json(client, auth_headers):
    res = client.get("/api/status", headers=auth_headers)
    assert res.status_code == 200
    body = res.get_json()
    assert "status" in body and "is_running" in body


def test_reset_sets_idle(client, auth_headers):
    import webapp.state as state
    state.update_status("scraping", True)
    res = client.post("/api/reset", headers=auth_headers)
    assert res.status_code == 200
    assert state.is_running_flag is False
    assert state.current_status == "idle"


# --- Jobs routes error paths -----------------------------------------------

def test_jobs_500_error(client, auth_headers, monkeypatch):
    import database as db

    def boom():
        raise RuntimeError("db down")

    monkeypatch.setattr(db, "get_all_jobs", boom)
    res = client.get("/api/jobs", headers=auth_headers)
    assert res.status_code == 500
    assert res.get_json()["error"] == "Failed to load jobs"


def test_clear_all_error(client, auth_headers, monkeypatch):
    import database as db

    monkeypatch.setattr(db, "clear_all_jobs", lambda: (_ for _ in ()).throw(RuntimeError("boom")))
    res = client.post("/api/jobs/clear-all", headers=auth_headers)
    assert res.status_code == 500


def test_delete_batch_empty_is_success(client, auth_headers):
    res = client.post("/api/jobs/delete-batch", headers=auth_headers, json={"ids": []})
    assert res.status_code == 200
    assert "No jobs" in res.get_json()["message"]


def test_delete_batch_deletes(client, auth_headers):
    jid = seed_job()
    res = client.post("/api/jobs/delete-batch", headers=auth_headers, json={"ids": [jid]})
    assert res.status_code == 200
    assert "deleted 1" in res.get_json()["message"]


def test_delete_job_body_missing_id(client, auth_headers):
    res = client.post("/api/jobs/delete", headers=auth_headers, json={})
    assert res.status_code == 400


def test_delete_job_body_not_found(client, auth_headers):
    res = client.post("/api/jobs/delete", headers=auth_headers, json={"id": "missing"})
    assert res.status_code == 404


def test_delete_job_legacy_success(client, auth_headers):
    jid = "legacy-id-1"
    seed_job(jid)
    res = client.delete(f"/api/jobs/{jid}", headers=auth_headers)
    assert res.status_code == 200


def test_delete_job_legacy_not_found(client, auth_headers):
    res = client.delete("/api/jobs/nope", headers=auth_headers)
    assert res.status_code == 404


def test_set_job_status_missing_id(client, auth_headers):
    res = client.post("/api/jobs/status", headers=auth_headers, json={})
    assert res.status_code == 400


def test_applications_list(client, auth_headers):
    res = client.get("/api/applications", headers=auth_headers)
    assert res.status_code == 200


def test_applications_error(client, auth_headers, monkeypatch):
    def boom():
        raise RuntimeError("tracker down")

    monkeypatch.setattr("application_tracker.ApplicationTracker.list_applications", boom)
    res = client.get("/api/applications", headers=auth_headers)
    assert res.status_code == 500


# --- Settings error paths --------------------------------------------------

def test_save_settings_invalid_json_falls_back(client, auth_headers, monkeypatch):
    import config
    tmp = config.SETTINGS_FILE
    with open(tmp, "w", encoding="utf-8") as f:
        f.write("{broken")
    res = client.post("/api/settings", headers=auth_headers,
                      json={"preferences": {"use_ai": False}})
    assert res.status_code == 200
    data = client.get("/api/settings", headers=auth_headers).get_json()
    assert data["preferences"]["use_ai"] is False


def test_preferences_preview(client, auth_headers):
    """The read-only preview reflects what the requirement text parses into."""
    res = client.get("/api/preferences/preview", headers=auth_headers)
    assert res.status_code == 200
    data = res.get_json()
    assert data["success"] is True
    assert "profile" in data


def test_preferences_preview_error(client, auth_headers, monkeypatch):

    def boom():
        raise RuntimeError("boom")

    monkeypatch.setattr("requirement_scorer.parse_preferences", boom)
    res = client.get("/api/preferences/preview", headers=auth_headers)
    assert res.status_code == 500
    assert res.get_json()["error"]


def test_get_settings_error(client, auth_headers, monkeypatch):
    import webapp.routes.settings as sr

    monkeypatch.setattr(sr.config, "load_settings", lambda: (_ for _ in ()).throw(RuntimeError("load fail")))
    res = client.get("/api/settings", headers=auth_headers)
    assert res.status_code == 500
    assert res.get_json()["error"]


def test_save_settings_error_500(client, auth_headers, monkeypatch):
    import webapp.routes.settings as sr

    def boom():
        raise RuntimeError("io")

    monkeypatch.setattr(_json_loader := sr.json, "load", boom) if False else None
    # Simpler: force an exception in the write step.
    monkeypatch.setattr(sr.json, "dump", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("disk full")))
    res = client.post("/api/settings", headers=auth_headers, json={"a": 1})
    assert res.status_code == 500


# --- Resume routes ---------------------------------------------------------

def test_resume_scan_success(client, auth_headers):
    res = client.post("/api/resume-scan", headers=auth_headers)
    # May succeed or fail gracefully; must be a valid JSON response.
    assert res.status_code == 200


def test_resume_upload_txt_parse(client, auth_headers, monkeypatch):
    import webapp.routes.resume as rr
    monkeypatch.setattr(rr.threading, "Thread", FakeThread)
    monkeypatch.setattr("webapp.state.is_running_flag", False)
    data = {"resume": (io.BytesIO(b"Junior Data Analyst\nSkills: SQL, Python"), "resume.txt"),
            "auto_run": "0"}
    res = client.post("/api/upload-resume", data=data, headers=auth_headers,
                      content_type="multipart/form-data")
    assert res.status_code == 200
    assert res.get_json()["success"] is True
    assert res.get_json()["auto_search"] is False


def test_resume_upload_pdf_parse_fail_still_ok(client, auth_headers, monkeypatch):
    import webapp.routes.resume as rr
    monkeypatch.setattr(rr.threading, "Thread", FakeThread)
    monkeypatch.setattr("webapp.state.is_running_flag", False)

    def boom_fitz(path):
        raise ImportError("no fitz")

    monkeypatch.setattr(rr, "_parse_pdf", boom_fitz)
    data = {"resume": (io.BytesIO(b"%PDF-1.4 fake"), "resume.pdf"), "auto_run": "0"}
    res = client.post("/api/upload-resume", data=data, headers=auth_headers,
                      content_type="multipart/form-data")
    assert res.status_code == 200
    assert res.get_json()["success"] is True


def test_resume_upload_txt_via_json_base64(client, auth_headers, monkeypatch):
    """The dashboard transports the resume base64-encoded in a JSON body."""
    import webapp.routes.resume as rr
    monkeypatch.setattr(rr.threading, "Thread", FakeThread)
    monkeypatch.setattr("webapp.state.is_running_flag", False)
    import base64
    raw = b"Junior Data Analyst\nSkills: SQL, Python"
    payload = {"filename": "resume.txt",
               "dataUrl": "data:text/plain;base64," + base64.b64encode(raw).decode(),
               "auto_run": False}
    res = client.post("/api/upload-resume", json=payload, headers=auth_headers)
    assert res.status_code == 200
    assert res.get_json()["success"] is True
    assert res.get_json()["auto_search"] is False


def test_resume_upload_json_missing_data(client, auth_headers):
    res = client.post("/api/upload-resume", json={"filename": "r.pdf"}, headers=auth_headers)
    assert res.status_code == 400


# --- webapp.state internals ------------------------------------------------

def test_state_get_run_status_with_file(client, monkeypatch):
    status_file = webapp.state._status_file()
    with open(status_file, "w", encoding="utf-8") as f:
        json.dump({"status": "scraping", "is_running": True}, f)
    data = webapp.state.get_run_status()
    assert data["is_running"] is True
    assert data["status"] == "scraping"


def test_state_get_run_status_without_file(client):
    data = webapp.state.get_run_status()
    assert "status" in data


def test_start_background_run_when_running(client, monkeypatch):
    monkeypatch.setattr("webapp.state.is_running_flag", True)
    assert webapp.state.start_background_run() is False


def test_start_background_run_when_idle(client, monkeypatch):
    monkeypatch.setattr("webapp.state.is_running_flag", False)
    monkeypatch.setattr("webapp.state.threading.Thread", FakeThread)
    assert webapp.state.start_background_run() is True


def test_load_and_save_scheduler_state(client):
    webapp.state.save_scheduler_state({"enabled": True, "interval_hours": 4, "next_run_at": 123.0})
    state = webapp.state.load_scheduler_state()
    assert state["enabled"] is True
    assert state["interval_hours"] == 4
    assert state["next_run_at"] == 123.0


# --- security extras -------------------------------------------------------

def test_https_request_gets_hsts(client, auth_headers):
    """WSGI over HTTPS adds the HSTS header."""
    res = client.get("/api/status", headers=auth_headers,
                     environ_overrides={"wsgi.url_scheme": "https"})
    assert res.status_code == 200
    assert res.headers.get("Strict-Transport-Security") == "max-age=31536000; includeSubDomains"


def test_wrap_route_success_and_error(client):
    from webapp.security import wrap_route

    with client.application.app_context():

        @wrap_route
        def ok():
            return {"result": 42}

        @wrap_route
        def bad():
            raise ValueError("x")

        assert ok() == {"result": 42}
        err = bad()
        assert err[1] == 500  # (jsonify_response, status_code) tuple


def test_scheduler_loop_disabled_iteration(client, monkeypatch):
    """scheduler_loop with enabled=False must not start a run and must keep looping."""
    monkeypatch.setattr("webapp.state.threading.Thread", FakeThread)
    import time as _time
    calls = {"n": 0}

    def fake_sleep(_secs):
        calls["n"] += 1
        if calls["n"] >= 2:
            raise SystemExit

    monkeypatch.setattr(_time, "sleep", fake_sleep)
    import webapp.state as state
    state.save_scheduler_state({"enabled": False, "interval_hours": 6, "next_run_at": None})
    with contextlib.suppress(SystemExit):
        state.scheduler_loop()
    assert calls["n"] >= 2


def test_scheduler_loop_enabled_due(client, monkeypatch):
    monkeypatch.setattr("webapp.state.threading.Thread", FakeThread)
    import time as _time
    monkeypatch.setattr("webapp.state.is_running_flag", False)
    calls = {"n": 0}

    def fake_sleep(_secs):
        calls["n"] += 1
        if calls["n"] >= 1:
            raise SystemExit

    monkeypatch.setattr(_time, "sleep", fake_sleep)
    import webapp.state as state
    state.save_scheduler_state({"enabled": True, "interval_hours": 6, "next_run_at": None})
    with contextlib.suppress(SystemExit):
        state.scheduler_loop()
    assert calls["n"] >= 1