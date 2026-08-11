"""Tests for the requirement-driven preference layer (score_adjuster.py).

Every expectation is built from an explicit requirements string so results do
not depend on whatever settings.json happens to hold on the machine running
the tests.
"""
from score_adjuster import adjust_score


def _settings(custom_requirements="", **overrides):
    prefs = {
        "min_salary": 0,
        "max_age_days": 30,
        "safe_first": False,
        "company_type": "",
        "custom_requirements": custom_requirements,
    }
    prefs.update(overrides)
    return {"preferences": prefs}


def _job(**kw):
    base = {
        "title": "QA Analyst",
        "company": "Some Local Company",
        "location": "",
        "salary_monthly": 5000,
        "salary_raw": "RM 5,000",
        "posted_days_ago": None,
        "description": "",
    }
    base.update(kw)
    return base


def _ai(score=80, **kw):
    base = {
        "score": score,
        "reason": "skill match",
        "risk": {"level": "low", "reason": "MNC"},
        "salary": None,
        "kl_transfer": False,
        "kl_potential": False,
        "fit_type": "unknown",
    }
    base.update(kw)
    return base


def test_no_requirement_is_neutral():
    score, _, _ = adjust_score(_job(), _ai(), _settings())
    assert score == 80


def test_empty_location_with_base_requirement_is_neutral():
    score, _, _ = adjust_score(_job(location=""), _ai(), _settings("基地在Penang"))
    assert score == 80


def test_base_mismatch_capped_but_shown():
    score, reason, extras = adjust_score(
        _job(location="Kuala Lumpur"), _ai(), _settings("基地在Penang（槟城）")
    )
    assert score == 62
    assert "基地需Penang" in reason
    assert extras["base_ok"] is False


def test_base_match_small_boost():
    score, reason, _ = adjust_score(
        _job(location="Bayan Lepas, Penang"), _ai(), _settings("基地在Penang")
    )
    assert score == 82
    assert "基地匹配" in reason


def test_excluded_location_capped_at_25():
    score, reason, _ = adjust_score(
        _job(location="Singapore"), _ai(), _settings("不要新加坡")
    )
    assert score == 25
    assert "排除地点" in reason


def test_explicit_relocation_boost_scales_with_intensity():
    strong = adjust_score(
        _job(description="we offer rotation to kuala lumpur after a year"),
        _ai(), _settings("强烈偏好能调往KL"),
    )[0]
    soft = adjust_score(
        _job(description="we offer rotation to kuala lumpur after a year"),
        _ai(), _settings("最好能调往KL"),
    )[0]
    assert strong > soft
    assert strong == 96  # 80 + 16 (strong x1.6)
    assert soft == 86  # 80 + 6 (soft x0.6)


def test_dual_location_only_when_base_present():
    # Posting covers BOTH Penang and KL -> dual-location relocation boost.
    score, _, extras = adjust_score(
        _job(location="Penang, Kuala Lumpur"),
        _ai(), _settings("基地在Penang，调往KL"),
    )
    # 80 + 2 base + 10 reloc (medium "调往") = 92
    assert score == 92
    assert extras["relocation_level"] == "dual_location"
    assert extras["kl_transfer"] is True

    # Posting sits entirely in KL -> that is an OUT-of-base job, not a path.
    score, _, extras = adjust_score(
        _job(location="Kuala Lumpur"),
        _ai(), _settings("基地在Penang，调往KL"),
    )
    assert score == 62
    assert extras["relocation_level"] == "none"


def test_mnc_potential_when_employer_has_hub_office():
    score, reason, extras = adjust_score(
        _job(company="Intel", location="Bayan Lepas, Penang"),
        _ai(), _settings("基地在Penang，希望调往KL"),
    )
    assert score == 80 + 2 + 6  # base match + KL potential (0.55x10) => 88
    assert "MNC，存在内部调动可能" in reason
    assert extras["kl_potential"] is True


def test_mnc_boost_only_when_requirement_asks():
    no_req = adjust_score(_job(company="Intel"), _ai(), _settings())[0]
    with_req = adjust_score(_job(company="Intel"), _ai(), _settings("MNC preferred"))[0]
    assert no_req == 80
    assert with_req == 86  # mnc weight 6 (medium)


def test_mnc_word_boundary_no_false_positive():
    score, _, extras = adjust_score(
        _job(company="Meyer Software GmbH"), _ai(), _settings("MNC preferred")
    )
    assert score == 80
    assert extras["mnc"] is False


def test_salary_hidden_penalized():
    score, reason, _ = adjust_score(
        _job(salary_monthly=None, salary_raw="Salary not stated"), _ai(), _settings()
    )
    assert score == 74  # 80 - 6
    assert "未写明薪资" in reason


def test_salary_ai_estimate_lighter_penalty():
    score, _, _ = adjust_score(
        _job(salary_monthly=4800, salary_raw="~RM 4,800/mo (AI estimate)"),
        _ai(), _settings(),
    )
    assert score == 77  # 80 - 3


def test_clear_salary_no_penalty():
    score, _, _ = adjust_score(
        _job(salary_monthly=4800, salary_raw="RM 4,800"), _ai(), _settings()
    )
    assert score == 80


def test_salary_below_minimum_capped():
    settings = _settings(min_salary=3500)
    score, reason, _ = adjust_score(_job(salary_monthly=3000), _ai(90), settings)
    assert score == 50
    assert "低于最低要求" in reason


def test_stale_posting_capped():
    settings = _settings(max_age_days=30)
    score, reason, _ = adjust_score(_job(posted_days_ago=45), _ai(85), settings)
    assert score == 40
    assert "超过" in reason


def test_safe_first_bonus():
    settings = _settings(safe_first=True)
    score, reason, _ = adjust_score(_job(), _ai(80, fit_type="safe"), settings)
    assert score == 85
    assert "稳妥岗" in reason


def test_remote_preference_match_and_mismatch():
    match = adjust_score(
        _job(description="fully remote role"), _ai(), _settings("要远程办公")
    )[0]
    mismatch = adjust_score(
        _job(description="on-site role"), _ai(), _settings("要远程办公")
    )[0]
    assert match == 88  # 80 + 8 remote
    assert mismatch == 72  # 80 - 8 (remote requirement vs onsite posting)


def test_total_boost_capped_and_high_score_fade():
    req = "基地在Penang，强烈调往KL，MNC preferred，要远程"
    job = _job(
        company="Intel", location="Bayan Lepas, Penang",
        description="fully remote, rotation to kuala lumpur",
    )
    # 2 + 16 + 6 + 8 = 32 -> capped at MAX_BOOST 30.
    score, _, _ = adjust_score(job, _ai(60), _settings(req))
    assert score == 90

    # At content 100 the boost must fade to zero (keeps ordering by content).
    top = adjust_score(job, _ai(100), _settings(req))[0]
    assert top == 100


def test_score_never_negative():
    score, _, _ = adjust_score(
        _job(location="Singapore", salary_monthly=None,
             salary_raw="none", description="on-site"),
        _ai(20), _settings("不要新加坡，要远程"),
    )
    assert 0 <= score <= 100