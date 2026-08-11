"""Additional tests for rule_filter internal branches (education, experience, level, location,
company, semantic similarity, salary, risk, resume loading)."""
import json

import rule_filter
from rule_filter import (
    RuleFilter,
    _company_fit,
    _edu_penalty,
    _exp_penalty,
    _kl_transfer_check,
    _level_match,
    _location_match,
    score_job,
)


def _resume(**kw):
    base = {
        "name": "Tan Wei Ming",
        "education": "Diploma",
        "experience_years": 1,
        "skills": ["Python", "Power Automate", "RPA", "SQL", "Data Analysis"],
        "locations": ["Penang, Malaysia"],
        "raw_text": "",
    }
    base.update(kw)
    return base


def _job(**kw):
    base = {
        "index": 1,
        "title": "QA Analyst",
        "company": "Some Local Co",
        "location": "",
        "description": "entry level QA role",
    }
    base.update(kw)
    return base


# --- Education -----------------------------------------------------------------

def test_edu_penalty_bachelor_degree_required():
    score, reasons = _edu_penalty("bachelor", "must hold a bachelor degree required for the role")
    assert score == 5
    assert "学历匹配(+5)" in reasons


# --- Experience -----------------------------------------------------------------

def test_exp_penalty_three_years_penalizes_20():
    score, reasons = _exp_penalty(1, "3 years experience required")
    assert score == -20
    assert "要求3年经验(-20)" in reasons


def test_exp_penalty_one_year_is_fine():
    score, reasons = _exp_penalty(1, "only 1 year experience needed")
    assert score == 5
    assert "仅要求1年经验(+5)" in reasons


# --- Skill match -----------------------------------------------------------------

def test_skill_match_three_or_more_skills(rule_resume_on_disk):
    rf = RuleFilter()
    res = rf.evaluate_job_batch([{
        "index": 1,
        "title": "RPA Developer",
        "company": "Jabil",
        "description": "python power automate rpa required, sql and data analysis a plus",
    }])[0]
    assert "技能匹配" in res["reason"]


# --- Level match -----------------------------------------------------------------

def test_level_match_senior_with_two_years():
    score, reasons = _level_match(2, "senior lead role", "Senior QA Engineer")
    assert score == -10
    assert "Senior岗位(-10)" in reasons


def test_level_match_senior_with_plenty_experience():
    score, reasons = _level_match(6, "senior role", "Senior Staff Engineer")
    assert score == 0
    assert reasons == []


def test_level_match_in_experience_range():
    score, reasons = _level_match(3, "2-5 years experience", "QA Analyst")
    assert score == 8
    assert "经验匹配2-5年(+8)" in reasons


def test_level_match_below_experience_range():
    score, reasons = _level_match(1, "3-5 years experience", "QA Analyst")
    assert score == -5
    assert "经验低于要求3年(-5)" in reasons


# --- Location -----------------------------------------------------------------

def test_location_match_kuala_lumpur():
    score, reasons, loc_ok, _ = _location_match(
        ["Kuala Lumpur, Malaysia"], "Kuala Lumpur, Malaysia", "QA role in KL"
    )
    assert score == 5
    assert "KL(+5)" in reasons
    assert loc_ok is True


def test_location_match_singapore_penalty():
    score, reasons, loc_ok, _ = _location_match(
        ["Penang, Malaysia"], "Singapore", "work Singapore based"
    )
    assert score == -5
    assert "Singapore(-5)" in reasons
    assert loc_ok is False


def test_location_match_remote():
    score, reasons, loc_ok, _ = _location_match(
        ["Penang, Malaysia"], "", "remote work from home role"
    )
    assert score == 3
    assert loc_ok is True


# --- Company fit -----------------------------------------------------------------

def test_company_fit_non_penang_mnc_matched():
    score, reasons, kl_potential, is_mnc = _company_fit(
        {"locations": ["Kuala Lumpur, Malaysia"]}, "Intel", "some job text"
    )
    assert is_mnc is True
    assert kl_potential is False
    assert "MNC(+4)" in reasons


def test_company_fit_startup_sdn_bhd():
    score, reasons, kl_potential, is_mnc = _company_fit(
        {"locations": []}, "StartupTech Sdn Bhd", "early stage company"
    )
    assert is_mnc is False
    assert score == 2
    assert "创业公司(+2)" in reasons


def test_company_fit_semiconductor_industry():
    score, reasons, _, _ = _company_fit(
        {"locations": ["Penang, Malaysia"]}, "Intel", "semiconductor chip wafer fab"
    )
    assert "semiconductor行业(+2)" in reasons
    assert "MNC Penang→KL潜力(+5)" in reasons


def test_company_fit_red_flags():
    score, reasons, _, is_mnc = _company_fit(
        {"locations": []}, "Some Co", "fast-paced startup urgent hire, wear many hats"
    )
    assert score == -5
    assert "创业公司描述(-5)" in reasons


# --- KL transfer / semantic / salary / risk via score_job -----------------------

def test_kl_transfer_check_explicit():
    ok, bonus, reasons = _kl_transfer_check("opportunity in kl for rotation")
    assert ok is True
    assert bonus == 8
    assert "明确KL调动(+8)" in reasons


def test_scored_job_kl_transfer_flag():
    res = score_job(_job(description="relocate to kuala lumpur transfer to kl available"), _resume())
    assert res["kl_transfer"] is True


def test_semantic_similarity_high_branch():
    resume = _resume()
    resume["raw_text"] = "data analyst with python sql power automate and rpa skills penang"
    res = score_job(_job(description="data analyst with python sql power automate and rpa skills penang"),
                    resume)
    assert "语义相似度" in res["reason"]


def test_semantic_similarity_medium_branch():
    resume = _resume()
    resume["raw_text"] = "data analyst python sql power automate rpa docker git aws react java c sharp excel power bi"
    res = score_job(_job(description="data analyst role requires sql and python and excel"), resume)
    assert "语义相似度" in res["reason"]


def test_salary_not_double_scored_in_rule_filter():
    # Salary drives the preference layer (score_adjuster), which main.py applies
    # once with the REAL parsed monthly figure. The content scorer must not also
    # credit/penalise a scraper-provided salary field -- that was the double count.
    high = score_job(_job(salary=4000, description="qa"), _resume())
    low = score_job(_job(salary=2000, description="qa"), _resume())
    assert high["score"] == low["score"]
    assert "不错" not in high["reason"] and "偏低" not in low["reason"]


def test_crypto_risk_high():
    res = score_job(_job(description="crypto investment opportunity"), _resume())
    assert res["risk"]["level"] == "high"


# --- evaluate_batch / load_resume_data / RuleFilter.read_resume -----------------

def test_evaluate_batch_with_explicit_resume_data():
    results = rule_filter.evaluate_batch([
        {"index": 0, "title": "A", "company": "Co", "description": "job a"},
        {"index": 1, "title": "B", "company": "Co", "description": "job b"},
    ], _resume())
    assert len(results) == 2
    assert results[0]["index"] == 1


def test_load_resume_data_missing_file_returns_empty(tmp_path, monkeypatch):
    monkeypatch.setattr(rule_filter, "DIRECTORY", str(tmp_path))
    assert rule_filter.load_resume_data() == {}


def test_rule_filter_read_resume_returns_json(rule_resume_on_disk):
    rf = RuleFilter()
    parsed = json.loads(rf.read_resume())
    assert "name" in parsed
    assert isinstance(parsed.get("skills", []), list)