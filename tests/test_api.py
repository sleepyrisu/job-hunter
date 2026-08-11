"""End-to-end tests for the Flask API (auth, settings, jobs, status, scheduler)."""
import config
from tests.conftest import seed_job

# --- Authentication -------------------------------------------------------

def test_api_rejects_request_without_token(client):
    res = client.get("/api/jobs")
    assert res.status_code == 401


def test_api_accepts_valid_token(client, auth_headers):
    res = client.get("/api/jobs", headers=auth_headers)
    assert res.status_code == 200


def test_api_rejects_wrong_token(client):
    res = client.get("/api/jobs", headers={"X-Auth-Token": "wrong"})
    assert res.status_code == 401


# --- Settings -------------------------------------------------------------

def test_settings_round_trip(client, auth_headers):
    res = client.post("/api/settings", headers=auth_headers, json={
        "preferences": {"use_ai": True, "match_threshold": 75}
    })
    assert res.status_code == 200
    data = client.get("/api/settings", headers=auth_headers).get_json()
    assert data["preferences"]["use_ai"] is True
    assert data["preferences"]["match_threshold"] == 75


def test_settings_deep_merge_preserves_unset_sections(client, auth_headers):
    client.post("/api/settings", headers=auth_headers, json={"preferences": {"use_ai": True}})
    data = client.get("/api/settings", headers=auth_headers).get_json()
    # Sections not touched by the partial save must survive.
    assert "search" in data
    assert "scheduler" in data
    assert "ai" in data
    assert data["preferences"]["use_ai"] is True


def test_resume_info_reports_stored_filename(client, auth_headers):
    import database as db
    info = client.get("/api/resume/info", headers=auth_headers).get_json()
    assert info["has_resume"] is False
    assert info["filename"] == ""
    db.save_user_profile(resume_text="hello", resume_filename="cv.pdf")
    info = client.get("/api/resume/info", headers=auth_headers).get_json()
    assert info["has_resume"] is True
    assert info["filename"] == "cv.pdf"


# --- Jobs -----------------------------------------------------------------

def test_jobs_list_and_seed(client, auth_headers):
    jid = seed_job()
    jobs = client.get("/api/jobs", headers=auth_headers).get_json()
    assert any(j["id"] == jid for j in jobs)


def test_job_status_update_via_api(client, auth_headers):
    jid = seed_job()
    res = client.post("/api/jobs/status", headers=auth_headers,
                      json={"id": jid, "status": "applied"})
    assert res.status_code == 200
    jobs = client.get("/api/jobs", headers=auth_headers).get_json()
    updated = next(j for j in jobs if j["id"] == jid)
    assert updated["status"] == "applied"


def test_job_status_invalid_via_api(client, auth_headers):
    jid = seed_job()
    res = client.post("/api/jobs/status", headers=auth_headers,
                      json={"id": jid, "status": "bogus"})
    assert res.status_code == 400


def test_job_delete_via_api(client, auth_headers):
    jid = seed_job()
    res = client.post("/api/jobs/delete", headers=auth_headers, json={"id": jid})
    assert res.status_code == 200
    jobs = client.get("/api/jobs", headers=auth_headers).get_json()
    assert all(j["id"] != jid for j in jobs)


def test_job_delete_nonexistent_via_api(client, auth_headers):
    res = client.post("/api/jobs/delete", headers=auth_headers, json={"id": 999999})
    assert res.status_code == 404


def test_stats_endpoint(client, auth_headers):
    import database as db
    seed_job()
    jid2 = seed_job("https://example.com/jobs/2")
    db.update_job_status(jid2, "applied")
    res = client.get("/api/jobs/stats", headers=auth_headers)
    assert res.status_code == 200
    stats = res.get_json()
    assert stats["new"] == 1
    assert stats["applied"] == 1


# --- Resume upload + auto-search ------------------------------------------

def test_upload_resume_triggers_auto_search(client, auth_headers, monkeypatch):
    import io

    import app as app_module
    started = {}

    class FakeThread:
        def __init__(self, target=None, daemon=None, **kw):
            self.target = target
            self.daemon = daemon

        def start(self):
            started["target"] = self.target

    monkeypatch.setattr("webapp.routes.resume.threading.Thread", FakeThread)
    monkeypatch.setattr("webapp.state.is_running_flag", False)
    data = {"resume": (io.BytesIO(b"Junior Data Analyst with SQL and Python"), "resume.txt"),
            "auto_run": "1"}
    res = client.post("/api/upload-resume", data=data, headers=auth_headers,
                      content_type="multipart/form-data")
    assert res.status_code == 200
    body = res.get_json()
    assert body["success"] is True
    assert body["auto_search"] is True
    assert started.get("target") is app_module.run_job_hunter_async


def test_upload_resume_skips_auto_search_when_disabled(client, auth_headers, monkeypatch):
    import io
    started = []

    class FakeThread:
        def __init__(self, target=None, daemon=None, **kw):
            self.target = target
            self.daemon = daemon

        def start(self):
            started.append(self.target)

    monkeypatch.setattr("webapp.routes.resume.threading.Thread", FakeThread)
    monkeypatch.setattr("webapp.state.is_running_flag", False)
    data = {"resume": (io.BytesIO(b"Junior Data Analyst"), "resume.txt"),
            "auto_run": "0"}
    res = client.post("/api/upload-resume", data=data, headers=auth_headers,
                      content_type="multipart/form-data")
    assert res.status_code == 200
    body = res.get_json()
    assert body["success"] is True
    assert body["auto_search"] is False
    assert started == []


# --- Scheduler ------------------------------------------------------------

def test_scheduler_get_defaults(client, auth_headers):
    # The real settings.json on the dev machine may have enabled=true; force a
    # clean scheduler state so this stays about defaults, not local state.
    config._settings["scheduler"]["enabled"] = False
    config._settings["scheduler"]["next_run_at"] = None
    res = client.get("/api/scheduler", headers=auth_headers)
    assert res.status_code == 200
    state = res.get_json()
    assert state["enabled"] is False
    assert state["interval_hours"] >= 1


def test_scheduler_enable(client, auth_headers):
    res = client.post("/api/scheduler", headers=auth_headers,
                      json={"enabled": True, "interval_hours": 3})
    assert res.status_code == 200
    state = client.get("/api/scheduler", headers=auth_headers).get_json()
    assert state["enabled"] is True
    assert state["interval_hours"] == 3
    assert state["next_run_at"] is not None

    client.post("/api/scheduler", headers=auth_headers, json={"enabled": False})
    state = client.get("/api/scheduler", headers=auth_headers).get_json()
    assert state["enabled"] is False
    assert state["next_run_at"] is None
