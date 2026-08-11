"""
Database Module
SQLite-based persistent storage replacing jobs_db.json.
Provides thread-safe operations for the Flask web server.
"""
import contextlib
import json
import os
import sqlite3
import threading

from models import APPLICATION_STATUSES

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "jobs.db")
JSON_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "jobs_db.json")
_local = threading.local()


def get_connection():
    if not hasattr(_local, "conn") or _local.conn is None:
        _local.conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        _local.conn.row_factory = sqlite3.Row
        _local.conn.execute("PRAGMA journal_mode=WAL")
        _local.conn.execute("PRAGMA synchronous=NORMAL")
    return _local.conn


@contextlib.contextmanager
def get_db():
    conn = get_connection()
    try:
        yield conn
    finally:
        pass


def close_connection():
    """Close and discard the calling thread's cached connection.

    Prevents fd/SQLite-handle growth on request threads that never return to
    a pool. Safe: the connection is thread-local, and any later database call
    in the same thread transparently re-establishes it (WAL/journal settings
    are per-connection and re-applied in get_connection).
    """
    conn = getattr(_local, "conn", None)
    if conn is not None:
        _local.conn = None
        with contextlib.suppress(sqlite3.Error):
            conn.close()


def init_db():
    conn = get_connection()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS jobs (
            id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            company TEXT,
            url TEXT,
            platform TEXT,
            location TEXT,
            score INTEGER DEFAULT 0,
            reason TEXT,
            risk TEXT,
            salary_monthly INTEGER,
            salary_raw TEXT,
            kl_transfer INTEGER DEFAULT 0,
            kl_potential INTEGER DEFAULT 0,
            fit_type TEXT,
            posted_days_ago INTEGER,
            posted_age_label TEXT,
            scraped_at TEXT,
            cover_letter TEXT,
            status TEXT DEFAULT 'new',
            applied_at TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
        
        CREATE TABLE IF NOT EXISTS user_profile (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            resume_text TEXT,
            resume_filename TEXT,
            preferences TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
        
    """)
    conn.commit()

    # Schema migrations (idempotent, versioned).
    from schema_migrations import migrate
    migrate(conn)

    conn.executescript("""
        CREATE INDEX IF NOT EXISTS idx_jobs_score ON jobs(score DESC);
        CREATE INDEX IF NOT EXISTS idx_jobs_platform ON jobs(platform);
        CREATE INDEX IF NOT EXISTS idx_jobs_company ON jobs(company);
        CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status);
    """)
    conn.commit()


def _row_to_dict(row):
    """Convert a sqlite3.Row to a plain dict, deserializing JSON fields."""
    d = dict(row)
    for field in ("risk",):
        if d.get(field) and isinstance(d[field], str):
            with contextlib.suppress(json.JSONDecodeError, TypeError):
                d[field] = json.loads(d[field])
    for field in ("kl_transfer", "kl_potential"):
        d[field] = bool(d.get(field, 0))
    return d


def get_all_jobs():
    """Return all jobs as a list of dicts."""
    conn = get_connection()
    rows = conn.execute("SELECT * FROM jobs ORDER BY score DESC, created_at DESC").fetchall()
    return [_row_to_dict(r) for r in rows]


def get_job(job_id):
    """Return a single job by ID."""
    conn = get_connection()
    row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
    return _row_to_dict(row) if row else None


def upsert_job(job_id, data):
    """Insert or update a job record."""
    conn = get_connection()
    risk_val = json.dumps(data.get("risk"), ensure_ascii=False) if data.get("risk") else None
    
    conn.execute("""
        INSERT INTO jobs (id, title, company, url, platform, location, score, reason,
                          risk, salary_monthly, salary_raw, kl_transfer, kl_potential,
                          fit_type, posted_days_ago, posted_age_label, scraped_at, cover_letter)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
            title=excluded.title, company=excluded.company, url=excluded.url,
            platform=excluded.platform, location=excluded.location,
            score=excluded.score, reason=excluded.reason, risk=excluded.risk,
            salary_monthly=excluded.salary_monthly, salary_raw=excluded.salary_raw,
            kl_transfer=excluded.kl_transfer, kl_potential=excluded.kl_potential,
            fit_type=excluded.fit_type, posted_days_ago=excluded.posted_days_ago,
            posted_age_label=excluded.posted_age_label, scraped_at=excluded.scraped_at,
            cover_letter=excluded.cover_letter
    """, (
        job_id, data.get("title", ""), data.get("company", ""), data.get("url", ""),
        data.get("platform", ""), data.get("location", ""), data.get("score", 0),
        data.get("reason", ""), risk_val, data.get("salary_monthly"),
        data.get("salary_raw", ""), 1 if data.get("kl_transfer") else 0,
        1 if data.get("kl_potential") else 0, data.get("fit_type", ""),
        data.get("posted_days_ago"), data.get("posted_age_label", ""),
        data.get("scraped_at", ""), data.get("cover_letter")
    ))
    conn.commit()


def upsert_jobs_batch(jobs_dict):
    """Bulk upsert jobs. jobs_dict: {job_id: data_dict}."""
    conn = get_connection()
    for job_id, data in jobs_dict.items():
        risk_val = json.dumps(data.get("risk"), ensure_ascii=False) if data.get("risk") else None
        conn.execute("""
            INSERT INTO jobs (id, title, company, url, platform, location, score, reason,
                              risk, salary_monthly, salary_raw, kl_transfer, kl_potential,
                              fit_type, posted_days_ago, posted_age_label, scraped_at, cover_letter)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                title=excluded.title, company=excluded.company, url=excluded.url,
                platform=excluded.platform, location=excluded.location,
                score=excluded.score, reason=excluded.reason, risk=excluded.risk,
                salary_monthly=excluded.salary_monthly, salary_raw=excluded.salary_raw,
                kl_transfer=excluded.kl_transfer, kl_potential=excluded.kl_potential,
                fit_type=excluded.fit_type, posted_days_ago=excluded.posted_days_ago,
                posted_age_label=excluded.posted_age_label, scraped_at=excluded.scraped_at,
                cover_letter=excluded.cover_letter
        """, (
            job_id, data.get("title", ""), data.get("company", ""), data.get("url", ""),
            data.get("platform", ""), data.get("location", ""), data.get("score", 0),
            data.get("reason", ""), risk_val, data.get("salary_monthly"),
            data.get("salary_raw", ""), 1 if data.get("kl_transfer") else 0,
            1 if data.get("kl_potential") else 0, data.get("fit_type", ""),
            data.get("posted_days_ago"), data.get("posted_age_label", ""),
            data.get("scraped_at", ""), data.get("cover_letter")
        ))
    conn.commit()


def delete_job(job_id):
    """Delete a single job by ID."""
    conn = get_connection()
    cursor = conn.execute("DELETE FROM jobs WHERE id = ?", (job_id,))
    conn.commit()
    return cursor.rowcount > 0


def delete_jobs_batch(job_ids):
    """Delete multiple jobs by IDs."""
    conn = get_connection()
    placeholders = ",".join("?" * len(job_ids))
    # Parameterized with ? placeholders - no SQL injection.
    cursor = conn.execute(f"DELETE FROM jobs WHERE id IN ({placeholders})", job_ids)  # nosec B608
    conn.commit()
    return cursor.rowcount


def clear_all_jobs():
    """Delete all jobs."""
    conn = get_connection()
    conn.execute("DELETE FROM jobs")
    conn.commit()


def update_job_status(job_id, status):
    """Set the application status for a job. Returns (success, message)."""
    if status not in APPLICATION_STATUSES:
        return False, f"Invalid status. Allowed: {', '.join(APPLICATION_STATUSES)}"
    conn = get_connection()
    if not job_exists(job_id):
        return False, "Job not found."
    if status in ("applied", "interviewing", "offered", "rejected"):
        conn.execute(
            "UPDATE jobs SET status = ?, applied_at = COALESCE(applied_at, datetime('now', 'localtime')) WHERE id = ?",
            (status, job_id)
        )
    else:
        conn.execute(
            "UPDATE jobs SET status = ?, applied_at = "
            "CASE WHEN ? IN ('applied','interviewing','offered','rejected') "
            "THEN applied_at ELSE NULL END WHERE id = ?",
            (status, status, job_id)
        )
    conn.commit()
    return True, f"Status updated to '{status}'."


def job_exists(job_id):
    """Check if a job already exists in the database."""
    conn = get_connection()
    row = conn.execute("SELECT 1 FROM jobs WHERE id = ?", (job_id,)).fetchone()
    return row is not None


def count_jobs():
    """Return total number of jobs."""
    conn = get_connection()
    row = conn.execute("SELECT COUNT(*) as cnt FROM jobs").fetchone()
    return row["cnt"]


def get_matched_jobs(min_score=70):
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM jobs WHERE score >= ? ORDER BY score DESC, created_at DESC",
        (min_score,)
    ).fetchall()
    return [_row_to_dict(r) for r in rows]


def get_stats():
    conn = get_connection()
    total = conn.execute("SELECT COUNT(*) as c FROM jobs").fetchone()["c"]
    excellent = conn.execute("SELECT COUNT(*) as c FROM jobs WHERE score >= 90").fetchone()["c"]
    good = conn.execute("SELECT COUNT(*) as c FROM jobs WHERE score >= 80 AND score < 90").fetchone()["c"]
    moderate = conn.execute("SELECT COUNT(*) as c FROM jobs WHERE score >= 50 AND score < 80").fetchone()["c"]
    all_jobs = conn.execute("SELECT risk FROM jobs").fetchall()
    flagged = sum(1 for r in all_jobs if r["risk"] and any(
        f'"{item}"' in r["risk"] for item in ("high", "medium")
    ))
    return {
        "total": total, "excellent": excellent, "good": good,
        "moderate": moderate, "flagged": flagged
    }


def get_status_stats():
    """Count jobs grouped by application status."""
    conn = get_connection()
    rows = conn.execute(
        "SELECT status, COUNT(*) as cnt FROM jobs GROUP BY status"
    ).fetchall()
    stats = {s: 0 for s in APPLICATION_STATUSES}
    for r in rows:
        key = r["status"] if r["status"] in stats else "new"
        stats[key] = r["cnt"]
    return stats


def get_user_profile():
    conn = get_connection()
    row = conn.execute("SELECT * FROM user_profile WHERE id = 1").fetchone()
    if not row:
        return None
    d = dict(row)
    if d.get("preferences"):
        with contextlib.suppress(json.JSONDecodeError, TypeError):
            d["preferences"] = json.loads(d["preferences"])
    return d


def save_user_profile(resume_text=None, resume_filename=None, preferences=None):
    conn = get_connection()
    existing = conn.execute("SELECT id FROM user_profile WHERE id = 1").fetchone()
    prefs_json = json.dumps(preferences, ensure_ascii=False) if preferences else None
    if existing:
        conn.execute("""
            UPDATE user_profile SET
                resume_text = COALESCE(?, resume_text),
                resume_filename = COALESCE(?, resume_filename),
                preferences = COALESCE(?, preferences),
                updated_at = CURRENT_TIMESTAMP
            WHERE id = 1
        """, (resume_text, resume_filename, prefs_json))
    else:
        conn.execute("""
            INSERT INTO user_profile (id, resume_text, resume_filename, preferences)
            VALUES (1, ?, ?, ?)
        """, (resume_text or "", resume_filename or "", prefs_json or "{}"))
    conn.commit()


def migrate_from_json():
    if not os.path.exists(JSON_PATH):
        return 0
    try:
        with open(JSON_PATH, encoding="utf-8") as f:
            json_db = json.load(f)
    except Exception:
        return 0
    for jid, data in json_db.items():
        upsert_job(jid, data)
    return len(json_db)


def get_jobs_by_platform(platform):
    conn = get_connection()
    rows = conn.execute("SELECT * FROM jobs WHERE platform = ? ORDER BY score DESC", (platform,)).fetchall()
    return [_row_to_dict(r) for r in rows]


def get_jobs_by_min_score(min_score):
    conn = get_connection()
    rows = conn.execute("SELECT * FROM jobs WHERE score >= ? ORDER BY score DESC", (min_score,)).fetchall()
    return [_row_to_dict(r) for r in rows]


init_db()
