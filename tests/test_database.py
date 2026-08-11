"""Tests for the SQLite persistence layer (database.py)."""
import sqlite3

import database as db
from tests.conftest import seed_job


def test_upsert_and_get(client):
    jid = seed_job()
    job = db.get_job(jid)
    assert job["id"] == jid
    assert job["title"] == "Junior QA Analyst"
    assert job["score"] == 85
    assert job["status"] == "new"
    assert job["kl_potential"] is True
    assert job["risk"]["level"] == "low"


def test_upsert_overwrites_existing(client):
    jid = seed_job(score=85)
    db.upsert_job(jid, {"title": "Senior QA Analyst", "company": "Intel", "score": 92})
    job = db.get_job(jid)
    assert job["title"] == "Senior QA Analyst"
    assert job["score"] == 92
    assert db.count_jobs() == 1


def test_upsert_batch(client):
    db.upsert_jobs_batch({
        "j1": {"title": "A", "company": "Co", "score": 70},
        "j2": {"title": "B", "company": "Co", "score": 80},
    })
    assert db.count_jobs() == 2


def test_delete_job(client):
    jid = seed_job()
    assert db.delete_job(jid) is True
    assert db.delete_job(jid) is False
    assert db.get_job(jid) is None


def test_delete_batch_and_clear(client):
    db.upsert_jobs_batch({"a": {"title": "A"}, "b": {"title": "B"}, "c": {"title": "C"}})
    assert db.delete_jobs_batch(["a", "b"]) == 2
    assert db.count_jobs() == 1
    db.clear_all_jobs()
    assert db.count_jobs() == 0


def test_job_exists(client):
    jid = seed_job()
    assert db.job_exists(jid) is True
    assert db.job_exists("nope") is False


def test_update_job_status_valid(client):
    jid = seed_job()
    ok, msg = db.update_job_status(jid, "applied")
    assert ok is True
    job = db.get_job(jid)
    assert job["status"] == "applied"
    assert job["applied_at"] is not None


def test_update_job_status_resets_applied_at(client):
    jid = seed_job()
    db.update_job_status(jid, "applied")
    db.update_job_status(jid, "new")
    job = db.get_job(jid)
    assert job["status"] == "new"
    assert job["applied_at"] is None


def test_update_job_status_invalid(client):
    jid = seed_job()
    ok, msg = db.update_job_status(jid, "not-a-status")
    assert ok is False
    assert "Invalid status" in msg


def test_update_job_status_missing_job(client):
    ok, msg = db.update_job_status("missing", "applied")
    assert ok is False
    assert "not found" in msg


def test_status_stats(client):
    db.upsert_jobs_batch({
        "j1": {"title": "A"},
        "j2": {"title": "B"},
        "j3": {"title": "C"},
    })
    db.update_job_status("j1", "applied")
    db.update_job_status("j2", "rejected")
    stats = db.get_status_stats()
    assert stats["new"] == 1
    assert stats["applied"] == 1
    assert stats["rejected"] == 1


def test_get_stats(client):
    seed_job(score=95)
    seed_job("https://example.com/jobs/2", score=85)
    seed_job("https://example.com/jobs/3", score=60)
    stats = db.get_stats()
    assert stats["total"] == 3
    assert stats["excellent"] == 1
    assert stats["good"] == 1
    assert stats["moderate"] == 1


def test_migrates_old_schema(tmp_path):
    """A database created before status/applied_at columns gets migrated on init."""
    db_path = tmp_path / "legacy.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute("""
        CREATE TABLE jobs (
            id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            company TEXT, url TEXT, platform TEXT, location TEXT,
            score INTEGER DEFAULT 0, reason TEXT, risk TEXT,
            salary_monthly INTEGER, salary_raw TEXT,
            kl_transfer INTEGER DEFAULT 0, kl_potential INTEGER DEFAULT 0,
            fit_type TEXT, posted_days_ago INTEGER, posted_age_label TEXT,
            scraped_at TEXT, cover_letter TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.execute("INSERT INTO jobs (id, title) VALUES ('legacy', 'Old Job')")
    conn.commit()
    conn.close()

    old_path = db.DB_PATH
    db.DB_PATH = str(db_path)
    db._local.conn = None
    try:
        db.init_db()
        row = db.get_job("legacy")
        assert row["status"] == "new"
        assert row["applied_at"] is None
    finally:
        db.DB_PATH = old_path
        db._local.conn = None
