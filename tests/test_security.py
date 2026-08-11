"""Security tests: auth, CSRF, security headers, rate limiting, upload hardening."""
import io


def _headers(**kw):
    h = {"X-Auth-Token": "test-token"}
    h.update(kw)
    return h


def _real_project_dir():
    import os
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# --- Security headers ------------------------------------------------------

def test_security_headers_present(client, auth_headers):
    res = client.get("/api/jobs", headers=auth_headers)
    assert res.status_code == 200
    assert res.headers.get("X-Content-Type-Options") == "nosniff"
    assert res.headers.get("X-Frame-Options") == "DENY"
    assert res.headers.get("Referrer-Policy") == "no-referrer"
    assert "Content-Security-Policy" in res.headers
    assert res.headers.get("Cache-Control") == "no-store"


def test_static_pages_have_security_headers(client, monkeypatch):
    import webapp.state
    monkeypatch.setattr(webapp.state, "DIRECTORY", _real_project_dir())
    res = client.get("/")
    assert res.status_code == 200
    assert res.headers.get("X-Content-Type-Options") == "nosniff"


# --- CSRF defense ----------------------------------------------------------

def test_mutating_request_requires_custom_header_when_token_set(client, monkeypatch):
    """When a dashboard token is configured, POSTs without a custom header are rejected."""
    import config
    monkeypatch.setattr(config, "DASHBOARD_TOKEN", "test-token")
    res = client.post("/api/settings", json={"preferences": {"use_ai": False}})
    assert res.status_code in (401, 403)  # auth or CSRF layer rejects


def test_mutating_request_with_token_header_accepted(client, auth_headers):
    res = client.post("/api/settings", headers=auth_headers,
                      json={"preferences": {"use_ai": True}})
    assert res.status_code == 200


# --- Auth edge cases -------------------------------------------------------

def test_auth_accepts_query_token(client, monkeypatch):
    import config
    monkeypatch.setattr(config, "DASHBOARD_TOKEN", "test-token")
    res = client.get("/api/jobs?token=test-token")
    assert res.status_code == 200


def test_auth_rejects_wrong_query_token(client, monkeypatch):
    import config
    monkeypatch.setattr(config, "DASHBOARD_TOKEN", "test-token")
    res = client.get("/api/jobs?token=wrong")
    assert res.status_code == 401


def test_free_paths_never_require_auth(client, monkeypatch):
    import config
    import webapp.state
    monkeypatch.setattr(config, "DASHBOARD_TOKEN", "test-token")
    monkeypatch.setattr(webapp.state, "DIRECTORY", _real_project_dir())
    for path in ("/", "/dashboard.html"):
        res = client.get(path)
        assert res.status_code == 200


# --- Rate limiting ---------------------------------------------------------

def test_rate_limit_rejects_flood_when_enabled(client, auth_headers, monkeypatch):
    import app as app_module
    app_module.app.config["TESTING"] = False
    import webapp.security as security
    monkeypatch.setattr(security, "RATE_LIMIT_MAX", 3)
    monkeypatch.setattr(security, "RATE_LIMIT_WINDOW", 60)
    monkeypatch.setattr(security, "_RATE_LIMITS", {})
    try:
        for _ in range(3):
            client.post("/api/settings", headers=auth_headers, json={"preferences": {"use_ai": False}})
        res = client.post("/api/settings", headers=auth_headers, json={"preferences": {"use_ai": False}})
        assert res.status_code == 429
    finally:
        app_module.app.config["TESTING"] = True


# --- Upload hardening ------------------------------------------------------

def test_upload_rejects_disallowed_extension(client, auth_headers):
    data = {"resume": (io.BytesIO(b"malicious"), "evil.exe")}
    res = client.post("/api/upload-resume", data=data, headers=auth_headers,
                      content_type="multipart/form-data")
    assert res.status_code == 400


def test_upload_rejects_path_traversal_filename(client, auth_headers):
    data = {"resume": (io.BytesIO(b"content"), "../resume.txt")}
    res = client.post("/api/upload-resume", data=data, headers=auth_headers,
                      content_type="multipart/form-data")
    assert res.status_code == 400


def test_upload_rejects_oversized_file(client, auth_headers, monkeypatch):
    import webapp.routes.resume as resume_route
    monkeypatch.setattr(resume_route, "MAX_FILE_SIZE", 10)
    data = {"resume": (io.BytesIO(b"x" * 100), "resume.txt")}
    res = client.post("/api/upload-resume", data=data, headers=auth_headers,
                      content_type="multipart/form-data")
    assert res.status_code == 400


def test_upload_missing_file(client, auth_headers):
    res = client.post("/api/upload-resume", data={}, headers=auth_headers,
                      content_type="multipart/form-data")
    assert res.status_code == 400
