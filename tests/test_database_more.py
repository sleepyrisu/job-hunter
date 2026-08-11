"""Additional tests for database: get_db context manager, JSON edge cases, stats, migration."""
import json

import database as db
from tests.conftest import seed_job


def test_get_db_context_manager(client):
    with db.get_db() as conn:
        row = conn.execute("SELECT 1 AS one").fetchone()
        assert row["one"] == 1


def test_row_to_dict_unparseable_risk_kept(client):
    jid = seed_job()
    conn = db.get_connection()
    conn.execute("UPDATE jobs SET risk = '{bad json' WHERE id = ?", (jid,))
    conn.commit()
    job = db.get_job(jid)
    assert job["risk"] == "{bad json"


def test_get_user_profile_no_row_returns_none(client):
    assert db.get_user_profile() is None


def test_get_user_profile_unparseable_preferences(client):
    db.save_user_profile(resume_text="hello", resume_filename="r.md", preferences={"k": "v"})
    conn = db.get_connection()
    conn.execute("UPDATE user_profile SET preferences = '{bad' WHERE id = 1")
    conn.commit()
    prof = db.get_user_profile()
    assert prof["preferences"] == "{bad"
    assert prof["resume_filename"] == "r.md"


def test_get_matched_jobs_min_score(client):
    seed_job(score=90)
    seed_job("https://example.com/jobs/2", score=80)
    seed_job("https://example.com/jobs/3", score=50)
    matched = db.get_matched_jobs(70)
    assert len(matched) == 2
    assert all(j["score"] >= 70 for j in matched)


def test_get_stats_counts_medium_and_high_risk(client):
    seed_job(risk={"level": "low", "reason": "MNC"})
    seed_job("https://example.com/jobs/2", risk={"level": "medium", "reason": "startup"})
    seed_job("https://example.com/jobs/3", risk={"level": "high", "reason": "crypto"})
    seed_job("https://example.com/jobs/4", risk={"level": "low", "reason": "safe"})
    stats = db.get_stats()
    assert stats["total"] == 4
    assert stats["flagged"] == 2


def test_migrate_from_json_missing_file_returns_zero(client, monkeypatch):
    monkeypatch.setattr(db, "JSON_PATH", "C:/does/not/exist/jobs_db.json")
    assert db.migrate_from_json() == 0


def test_migrate_from_json_success(client, monkeypatch, tmp_path):
    json_path = tmp_path / "jobs_db.json"
    json_path.write_text(json.dumps({
        "j1": {"title": "Job One", "company": "Co", "score": 70},
        "j2": {"title": "Job Two", "company": "Co", "score": 60},
    }), encoding="utf-8")
    monkeypatch.setattr(db, "JSON_PATH", str(json_path))
    assert db.migrate_from_json() == 2
    assert db.count_jobs() == 2
    assert db.get_job("j1")["title"] == "Job One"


def test_migrate_from_json_invalid_json_returns_zero(client, monkeypatch, tmp_path):
    json_path = tmp_path / "jobs_db.json"
    json_path.write_text("not json {{", encoding="utf-8")
    monkeypatch.setattr(db, "JSON_PATH", str(json_path))
    assert db.migrate_from_json() == 0
    assert db.count_jobs() == 0


def test_get_jobs_by_platform(client):
    seed_job(platform="linkedin")
    seed_job("https://example.com/jobs/2", platform="indeed")
    seed_job("https://example.com/jobs/3", platform="linkedin")
    result = db.get_jobs_by_platform("linkedin")
    assert len(result) == 2


def test_get_jobs_by_min_score(client):
    seed_job(score=88)
    seed_job("https://example.com/jobs/2", score=40)
    result = db.get_jobs_by_min_score(70)
    assert [j["id"] for j in result] == ["https://example.com/jobs/1"]