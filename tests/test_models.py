"""Tests for the domain model layer (models.py) and repository layer (repositories.py)."""
import pytest

from models import (
    _STATUS_TRANSITIONS,
    VALID_STATUSES,
    Job,
    UserProfile,
    can_transition,
    validate_application_status,
    validate_job_id,
    validate_settings_update,
)
from repositories import (
    InvalidJobIdError,
    InvalidStatusError,
    JobNotFoundError,
    JobRepository,
    UserProfileRepository,
)


class TestJobModel:
    def test_from_dict_ignores_unknown_keys(self):
        job = Job.from_dict({"id": "x", "title": "T", "bogus": 1})
        assert job.id == "x"
        assert job.title == "T"
        assert not hasattr(job, "bogus")

    def test_to_dict_roundtrip(self):
        job = Job.from_dict({"id": "u", "title": "QA", "score": 92})
        d = job.to_dict()
        assert d["id"] == "u"
        assert d["score"] == 92

    def test_is_match(self):
        assert Job(id="a", title="T", score=85).is_match is True
        assert Job(id="b", title="T", score=50).is_match is False


class TestValidation:
    @pytest.mark.parametrize("bad", ["", None, 5, "a" * 3000, "\x00evil"])
    def test_invalid_job_ids(self, bad):
        assert validate_job_id(bad) is not None

    @pytest.mark.parametrize("good", ["linkedin.com/jobs/view/123", "job-123", "urn:job:42", "../evil", "a/b", "a\\b"])
    def test_valid_job_ids(self, good):
        assert validate_job_id(good) is None

    def test_valid_application_status(self):
        assert validate_application_status("applied") is None

    def test_invalid_application_status(self):
        assert "Invalid status" in validate_application_status("bogus")

    def test_status_transitions(self):
        assert can_transition("new", "applied")
        assert can_transition("applied", "interviewing")
        assert can_transition("new", "new")
        assert not can_transition("new", "offered")

    def test_settings_validation(self):
        assert validate_settings_update({"preferences": {}}) is None
        assert validate_settings_update({"preferences": {"match_threshold": 101}}) is not None
        assert validate_settings_update({"preferences": {"match_threshold": 0}}) is not None
        assert validate_settings_update({"preferences": {"match_threshold": 60}}) is None
        assert validate_settings_update({"preferences": {"interval_hours": 0}}) is not None
        assert validate_settings_update({"scheduler": {"interval_hours": 6}}) is None
        assert validate_settings_update({"scheduler": {"interval_hours": 0}}) is not None
        assert validate_settings_update({"scheduler": {"interval_hours": "x"}}) is not None
        assert validate_settings_update([1, 2]) is not None

    def test_transition_targets_are_valid_statuses(self):
        # Regression guard: the "offered" target once pointed at a non-existent
        # "accepted" status, so can_transition and validate_application_status
        # disagreed. Every source and target must be a valid status.
        assert set(_STATUS_TRANSITIONS) <= VALID_STATUSES
        for source, targets in _STATUS_TRANSITIONS.items():
            assert validate_application_status(source) is None
            for target in targets:
                assert validate_application_status(target) is None

    def test_offered_no_longer_points_at_accepted(self):
        assert can_transition("offered", "accepted") is False
        assert can_transition("offered", "rejected") is True
        assert can_transition("offered", "interviewing") is True


class TestJobRepository:
    def test_create_list_get(self, client):
        repo = JobRepository()
        job = Job(id="repo/1", title="Junior", company="Jabil", score=88)
        repo.create_or_update(job)
        assert [j.id for j in repo.list()] == ["repo/1"]
        fetched = repo.get("repo/1")
        assert fetched is not None
        assert fetched.title == "Junior"
        assert fetched.score == 88

    def test_create_rejects_invalid_id(self, client):
        repo = JobRepository()
        with pytest.raises(InvalidJobIdError):
            repo.create_or_update(Job(id="\x00evil", title="T"))

    def test_delete(self, client):
        repo = JobRepository()
        repo.create_or_update(Job(id="job/1", title="T"))
        assert repo.delete("job/1") is True
        assert repo.delete("job/1") is False

    def test_set_status_valid_and_invalid(self, client):
        repo = JobRepository()
        repo.create_or_update(Job(id="job/1", title="T"))
        assert "applied" in repo.set_status("job/1", "applied")
        with pytest.raises(InvalidStatusError):
            repo.set_status("job/1", "bogus")

    def test_set_status_missing_job_raises(self, client):
        repo = JobRepository()
        with pytest.raises(JobNotFoundError):
            repo.set_status("missing", "applied")

    def test_stats(self, client):
        repo = JobRepository()
        repo.create_or_update(Job(id="a", title="A"))
        repo.create_or_update(Job(id="b", title="B"))
        repo.set_status("b", "rejected")
        stats = repo.stats()
        assert stats["new"] == 1
        assert stats["rejected"] == 1


class TestUserProfileRepository:
    def test_save_and_get(self, client):
        repo = UserProfileRepository()
        assert repo.get() is None
        repo.save(UserProfile(resume_text="hello", preferences={"k": "v"}))
        prof = repo.get()
        assert prof is not None
        assert prof.resume_text == "hello"
        assert prof.preferences == {"k": "v"}

    def test_overwrite_fields(self, client):
        repo = UserProfileRepository()
        repo.save(UserProfile(resume_text="v1", resume_filename="a.txt"))
        repo.save(UserProfile(resume_text="v2"))
        prof = repo.get()
        assert prof.resume_text == "v2"
        assert prof.resume_filename == "a.txt"  # COALESCE keeps old value