"""
Domain models for the AI Job Hunter.

These dataclasses formalise the business entities that flow through the
pipeline (jobs, applications, user profile, search settings) and centralise
the validation rules. They are intentionally dependency-free so any layer
(scraper, evaluator, storage, API) can construct and validate them.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

# Application lifecycle states (order matters for progression UX).
APPLICATION_STATUSES = ("new", "saved", "applied", "interviewing", "offered", "rejected")

VALID_STATUSES = set(APPLICATION_STATUSES)
_STATUS_TRANSITIONS = {
    "new": ("saved", "applied", "rejected"),
    "saved": ("new", "applied", "rejected"),
    "applied": ("saved", "interviewing", "rejected"),
    "interviewing": ("applied", "offered", "rejected"),
    "offered": ("interviewing", "rejected"),
    "rejected": ("new", "saved"),
}

# A job id is either a URL or a short token. We reject control characters
# (which are never legitimate) via the DB-key safety check.
_ID_FORBIDDEN = re.compile(r"[\x00-\x1f\x7f]")

# Invariant: every source AND target status in the transition map must be a
# valid application status. Enforced at import time so a future edit fails
# loudly instead of silently creating the can_transition()/validate_* drift
# that previously pointed "offered" at a non-existent "accepted" status.
for _source, _targets in _STATUS_TRANSITIONS.items():
    if _source not in VALID_STATUSES or any(t not in VALID_STATUSES for t in _targets):
        raise ValueError(f"Illegal status in transition map for {_source!r}")


@dataclass
class Job:
    """A single scraped job posting."""

    id: str
    title: str
    company: str = ""
    url: str = ""
    platform: str = ""
    location: str = ""
    score: int = 0
    reason: str = ""
    risk: dict[str, Any] = field(default_factory=dict)
    salary_monthly: int | None = None
    salary_raw: str = ""
    kl_transfer: bool = False
    kl_potential: bool = False
    fit_type: str = ""
    posted_days_ago: int | None = None
    posted_age_label: str = ""
    scraped_at: str = ""
    cover_letter: str | None = None
    status: str = "new"
    applied_at: str | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Job:
        """Build a Job from a dict (e.g. a scraper result or DB row)."""
        known = {f for f in cls.__dataclass_fields__}
        return cls(**{k: v for k, v in data.items() if k in known})

    def to_dict(self) -> dict[str, Any]:
        return self.__dict__.copy()

    @property
    def is_match(self) -> bool:
        return self.score >= 80


@dataclass
class Application:
    """A job the user has decided to apply to."""

    company: str
    role: str
    job_url: str = ""
    overall_score: int = 0
    verdict: str = ""
    cover_letter: str | None = None
    status: str = "applied"

    def to_dict(self) -> dict[str, Any]:
        return self.__dict__.copy()


@dataclass
class UserProfile:
    """Persisted resume + search preferences for the user."""

    resume_text: str = ""
    resume_filename: str = ""
    preferences: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return self.__dict__.copy()


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def validate_job_id(job_id: str) -> str | None:
    """Return an error message if the id is not safe to use as a DB key, else None."""
    if not job_id or not isinstance(job_id, str):
        return "Job id must be a non-empty string."
    if len(job_id) > 2048:
        return "Job id is too long."
    if _ID_FORBIDDEN.search(job_id):
        return "Job id contains invalid characters."
    return None


def validate_application_status(status: str) -> str | None:
    """Return an error message if status is not a known application status."""
    if status not in VALID_STATUSES:
        return f"Invalid status '{status}'. Allowed: {', '.join(APPLICATION_STATUSES)}"
    return None


def can_transition(current: str, target: str) -> bool:
    """Return True if target is reachable from current status."""
    if current == target:
        return True
    return target in _STATUS_TRANSITIONS.get(current, ())


def validate_settings_update(patch: dict[str, Any]) -> str | None:
    """Validate a partial settings patch. Returns an error message or None."""
    if not isinstance(patch, dict):
        return "Settings must be a JSON object."
    prefs = patch.get("preferences")
    if prefs is not None:
        if not isinstance(prefs, dict):
            return "preferences must be an object."
        threshold = prefs.get("match_threshold")
        if threshold is not None and (not isinstance(threshold, (int, float)) or not (1 <= threshold <= 100)):
            return "match_threshold must be between 1 and 100."
        interval = prefs.get("interval_hours")
        if interval is not None:
            try:
                if int(interval) < 1:
                    return "interval_hours must be >= 1."
            except (TypeError, ValueError):
                return "interval_hours must be a number."
    sched = patch.get("scheduler")
    if sched is not None:
        if not isinstance(sched, dict):
            return "scheduler must be an object."
        interval = sched.get("interval_hours")
        if interval is not None:
            try:
                if int(interval) < 1:
                    return "interval_hours must be >= 1."
            except (TypeError, ValueError):
                return "interval_hours must be a number."
    return None
