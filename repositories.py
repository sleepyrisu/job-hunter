"""
Repository layer over the raw database module.

Provides domain-typed accessors (``Job``, ``UserProfile``), input validation
via ``models``, and a consistent API so callers never deal with bare SQL or
raw dicts for the core entities.
"""
from __future__ import annotations

from typing import Any

import database as db
from models import APPLICATION_STATUSES, Job, UserProfile, validate_application_status, validate_job_id


class JobNotFoundError(Exception):
    """Raised when a job does not exist."""


class InvalidJobIdError(ValueError):
    """Raised when a job id fails validation."""


class InvalidStatusError(ValueError):
    """Raised when an application status is unknown."""


class JobRepository:
    """Typed CRUD access to the jobs table."""

    def list(self) -> list[Job]:
        return [Job.from_dict(row) for row in db.get_all_jobs()]

    def get(self, job_id: str) -> Job | None:
        row = db.get_job(job_id)
        return Job.from_dict(row) if row else None

    def create_or_update(self, job: Job) -> None:
        error = validate_job_id(job.id)
        if error:
            raise InvalidJobIdError(error)
        db.upsert_job(job.id, job.to_dict())

    def delete(self, job_id: str) -> bool:
        error = validate_job_id(job_id)
        if error:
            raise InvalidJobIdError(error)
        return db.delete_job(job_id)

    def set_status(self, job_id: str, status: str) -> str:
        error = validate_application_status(status)
        if error:
            raise InvalidStatusError(error)
        ok, message = db.update_job_status(job_id, status)
        if not ok:
            raise JobNotFoundError(message)
        return message

    @property
    def statuses(self) -> tuple[str, ...]:
        return APPLICATION_STATUSES

    def stats(self) -> dict[str, int]:
        return db.get_status_stats()


class JobSearchStatsRepository:
    """Aggregated score-band statistics for the dashboard."""

    def get(self) -> dict[str, Any]:
        return db.get_stats()


class UserProfileRepository:
    """Typed access to the single user_profile row."""

    def get(self) -> UserProfile | None:
        row = db.get_user_profile()
        return UserProfile(
            resume_text=row.get("resume_text", ""),
            resume_filename=row.get("resume_filename", ""),
            preferences=row.get("preferences") or {},
        ) if row else None

    def save(self, profile: UserProfile) -> None:
        db.save_user_profile(
            resume_text=profile.resume_text or None,
            resume_filename=profile.resume_filename or None,
            preferences=profile.preferences if profile.preferences else None,
        )