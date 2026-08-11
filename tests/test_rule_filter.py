"""Tests for the resume-driven rule-based filter (no AI needed)."""
import rule_filter
from rule_filter import RuleFilter


def test_good_match_junior_rpa(rule_resume):
    result = rule_filter.evaluate_batch([{
        "index": 1,
        "title": "Junior RPA Developer",
        "company": "Intel Malaysia",
        "description": "Looking for junior RPA developer. Power Automate preferred. Diploma welcome. Entry level.",
    }], rule_resume)[0]
    assert result["score"] >= 80
    assert result["fit_type"] == "safe"


def test_bad_match_senior_architect(rule_resume):
    result = rule_filter.evaluate_batch([{
        "index": 1,
        "title": "Senior Software Architect",
        "company": "Google",
        "description": "10+ years experience, bachelor degree required, deep distributed systems.",
    }], rule_resume)[0]
    assert result["score"] < 40


def test_penang_mnc_signal_metadata(rule_resume):
    result = rule_filter.evaluate_batch([{
        "index": 1,
        "title": "QA Analyst",
        "company": "Jabil",
        "location": "Bayan Lepas, Penang, Malaysia",
        "description": "QA testing, data validation. Junior welcome.",
    }], rule_resume)[0]
    # Location/company no longer inflate the CONTENT score (that is the single
    # preference layer owned by score_adjuster); they must still surface as
    # metadata the downstream adjuster + risk model consume.
    assert result["kl_potential"] is True
    assert result["risk"]["level"] == "low"


def test_score_clamped_0_to_100(rule_resume):
    for job in [
        {"index": 1, "title": "Senior Staff Director", "company": "Google",
         "description": "15+ years experience required, phd required, senior lead."},
        {"index": 2, "title": "Perfect Entry RPA", "company": "Intel",
         "description": "Junior RPA developer, power automate, diploma welcome, no experience."},
    ]:
        result = rule_filter.evaluate_batch([job], rule_resume)[0]
        assert 0 <= result["score"] <= 100


def test_evaluate_batch_returns_index():
    results = rule_filter.evaluate_batch([
        {"index": 0, "title": "A", "company": "Co", "description": "job a"},
        {"index": 1, "title": "B", "company": "Co", "description": "job b"},
    ])
    assert len(results) == 2
    # Unified 1-based contract, matching the AI filters.
    assert results[0]["index"] == 1
    assert results[1]["index"] == 2


def test_rule_filter_cover_letter_no_ai(rule_resume_on_disk):
    rf = RuleFilter()
    cl = rf.generate_cover_letter("QA Analyst", "Jabil", "some description")
    assert "Jabil" in cl
    assert "QA Analyst" in cl
