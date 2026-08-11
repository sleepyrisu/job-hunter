"""
Shared pytest fixtures.

Every test gets a fully isolated environment:
- a temporary SQLite database (the real jobs.db is never touched),
- a temporary settings.json (the real settings.json is never touched),
- deterministic dashboard auth (DASHBOARD_TOKEN=test-token).
"""
import copy
import os
import sys

import pytest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

# Deterministic auth for every test, set before any app/config import.
os.environ.setdefault("DASHBOARD_TOKEN", "test-token")
os.environ.pop("GEMINI_API_KEY", None)

import app as app_module  # noqa: E402
import config  # noqa: E402
import database as db  # noqa: E402
import rule_filter  # noqa: E402
import webapp.state  # noqa: E402


@pytest.fixture(autouse=True)
def _restore_config_state():
    """Restore config globals after every test (tests mutate the shared _settings dict)."""
    snapshot = copy.deepcopy(config._settings)
    yield
    config._settings.clear()
    config._settings.update(snapshot)
    config._sync_globals()


@pytest.fixture()
def client(tmp_path, monkeypatch):
    """Flask test client isolated from the real database and settings file."""
    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "jobs.db"))
    monkeypatch.setattr(db._local, "conn", None)
    db.init_db()

    monkeypatch.setattr(config, "SETTINGS_FILE", str(tmp_path / "settings.json"))
    monkeypatch.setattr(app_module, "DIRECTORY", str(tmp_path))
    monkeypatch.setattr(webapp.state, "DIRECTORY", str(tmp_path))

    app_module.app.config["TESTING"] = True
    app_module.app.config["SERVER_NAME"] = "localhost"
    yield app_module.app.test_client()


@pytest.fixture()
def auth_headers():
    return {"X-Auth-Token": "test-token"}


# --- Rule-filter resume isolation ------------------------------------------
# RuleFilter() reads `resume.md` from rule_filter.DIRECTORY. Everyone who
# uploads a new resume changes that file, which used to silently change what
# the rule tests asserted. These fixtures pin a stable, rich resume so the
# scorers are exercised against deterministic input instead of disk state.

RULE_RESUME = {
    "name": "Tan Wei Ming",
    "education": "Diploma",
    "experience_years": 1,
    "skills": ["Power Automate", "RPA", "Python", "Data Analysis", "SQL"],
    "locations": ["Penang, Malaysia"],
    "raw_text": "junior rpa developer power automate diploma welcome entry level "
                "data analysis python sql penang automation workflow",
}

RULE_RESUME_MD = """Tan Wei Ming
Email: tanweiming@example.com
Phone: +6012-345-6789
Location: Georgetown, Penang, Malaysia

## Professional Summary
Data Analyst with 1 year of hands-on experience classifying NLP datasets for Microsoft
and QA audits for Apple. RPA developer using Power Automate from a 3-month logistics internship.

## Technical Skills
- Python, C#, Java, SQL
- Power Automate (RPA), UiPath
- Data Analysis, Data Labeling, ML QA
- Microsoft Excel, Power BI

## Experience
Data Analyst (1 year) at Centific Global Solutions
Automation Intern at PKT Logistic

## Education
Diploma of Computer Science
"""


@pytest.fixture()
def rule_resume():
    """Deterministic structured resume for plugging into evaluate_batch directly."""
    return copy.deepcopy(RULE_RESUME)


@pytest.fixture()
def rule_resume_on_disk(tmp_path, monkeypatch):
    """Write the deterministic resume to a temp dir and point rule_filter at it."""
    (tmp_path / "resume.md").write_text(RULE_RESUME_MD, encoding="utf-8")
    monkeypatch.setattr(rule_filter, "DIRECTORY", str(tmp_path))
    return RULE_RESUME_MD


def seed_job(job_id="https://example.com/jobs/1", **overrides):
    """Insert a realistic job row. Returns the job id."""
    data = {
        "title": "Junior QA Analyst",
        "company": "Jabil",
        "url": job_id,
        "platform": "linkedin",
        "location": "Bayan Lepas, Penang, Malaysia",
        "score": 85,
        "reason": "skill match",
        "risk": {"level": "low", "reason": "MNC"},
        "salary_monthly": 3200,
        "salary_raw": "RM 3,200/mo",
        "kl_transfer": False,
        "kl_potential": True,
        "fit_type": "safe",
        "posted_days_ago": 3,
        "posted_age_label": "3 days ago",
        "scraped_at": "2026-01-01 00:00:00",
        "cover_letter": None,
    }
    data.update(overrides)
    db.upsert_job(job_id, data)
    return job_id
