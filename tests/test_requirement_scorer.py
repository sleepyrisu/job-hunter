"""Tests for requirement_scorer: requirement text -> profile -> job scoring.

The core property is requirement-rot resistance: changing the text must change
the derived profile and therefore the scoring, with no Penang/KL/MNC
special-casing baked into the code.
"""
from company_knowledge import is_mnc, matches_any
from requirement_scorer import (
    parse_preferences,
    salary_transparency_penalty,
    score_preferences,
)

DEFAULT_REQ = ("基地在 Penang（槟城）。强烈偏好能提供明确调往 Kuala Lumpur (KL) "
               "发展/轮岗/外派路径的岗位。MNC preferred.")


def _job(**kw):
    base = {
        "title": "QA Analyst",
        "company": "Some Local Company",
        "location": "",
        "description": "",
        "salary_monthly": 5000,
        "salary_raw": "RM 5,000",
    }
    base.update(kw)
    return base


# --- parsing --------------------------------------------------------------- #

def test_parse_default_penang_kl_mnc():
    p = parse_preferences(DEFAULT_REQ)
    assert p["base_locations"] == ["penang"]
    assert p["relocation"]["targets"] == ["kuala_lumpur"]
    assert p["relocation"]["weight"] == 16  # "strong" -> x1.6
    assert p["company_type"]["mnc"] == 6  # "preferred" -> medium
    assert p["excluded_locations"] == []
    assert p["salary_transparency"] == 6  # silent baseline


def test_parse_requirement_change_re_routes_profile():
    p = parse_preferences("我要远程办公，最好在新山JB，要金融行业，薪资要写明。")
    assert p["base_locations"] == ["johor"]
    assert p["relocation"]["targets"] == []
    assert p["company_type"]["mnc"] == 0
    assert p["work_mode"]["remote"] == 8
    assert p["industries"] == {"fintech": 8}
    assert p["salary_transparency"] > 6


def test_parse_intensity_variants():
    assert parse_preferences("我想强烈要求调往KL")["relocation"]["weight"] == 16
    assert parse_preferences("要调往KL")["relocation"]["weight"] == 10
    assert parse_preferences("最好能调往KL")["relocation"]["weight"] == 6


def test_parse_intensity_does_not_leak_across_clauses():
    # "strong" adjacent to relocation must NOT bleed into MNC ("preferred").
    p = parse_preferences("强烈偏好调往KL。MNC preferred.")
    assert p["relocation"]["weight"] == 16
    assert p["company_type"]["mnc"] == 6


def test_parse_exclusion():
    p = parse_preferences("基地在Penang，不要新加坡。")
    assert p["base_locations"] == ["penang"]
    assert p["excluded_locations"] == ["singapore"]


def test_parse_empty_requirement_is_neutral_profile():
    p = parse_preferences("")
    assert p["base_locations"] == []
    assert p["relocation"]["weight"] == 0
    assert p["company_type"]["mnc"] == 0


# --- company knowledge / word boundaries ----------------------------------- #

def test_mnc_word_boundary_matching():
    assert is_mnc("Intel Malaysia") is True
    assert is_mnc("EY") is True
    assert is_mnc("Money App") is False      # old substring "ey" false positive
    assert is_mnc("Meyer GmbH") is False
    assert "flex" in matches_any("Flex Ltd", ("flex",))
    assert "flextronics" in matches_any("Flextronics Ltd", ("flex", "flextronics"))
    assert "flex" not in matches_any("Flextronics Ltd", ("flex",))


# --- scoring ---------------------------------------------------------------- #

def test_dual_location_boost_requires_base_too():
    p = parse_preferences("基地在Penang，调往KL")
    dual = score_preferences(_job(location="Penang, Kuala Lumpur"), p)
    assert dual["flags"]["relocation_level"] == "dual_location"
    assert dual["boost"] >= 10

    kl_only = score_preferences(_job(location="Kuala Lumpur"), p)
    assert kl_only["flags"]["relocation_level"] == "none"
    assert kl_only["caps"]  # out-of-base cap present


def test_mnc_potential_level():
    p = parse_preferences("基地在Penang，调往KL")
    res = score_preferences(_job(company="Intel", location="Bayan Lepas, Penang"), p)
    assert res["flags"]["relocation_level"] == "mnc_potential"
    assert res["flags"]["mnc"] is True


def test_salary_transparency_penalty():
    p = parse_preferences("")
    pts, reason = salary_transparency_penalty(p, _job(salary_monthly=None,
                                                      salary_raw="not stated"))
    assert pts == 6
    assert "未写明薪资" in reason

    ai_pts, _ = salary_transparency_penalty(
        p, _job(salary_monthly=4800, salary_raw="~RM 4,800/mo (AI estimate)"))
    assert ai_pts == 3

    clear = salary_transparency_penalty(p, _job())
    assert clear == (0, "")


def test_parse_work_mode_variants():
    assert parse_preferences("要驻场办公")["work_mode"]["onsite"] > 0
    assert parse_preferences("要混合办公")["work_mode"]["hybrid"] > 0
    p = parse_preferences("要远程办公")
    assert p["work_mode"]["remote"] > 0
    assert p["work_mode"]["onsite"] == 0


def test_parse_startup_preference():
    assert parse_preferences("要去初创公司")["company_type"]["startup"] > 0


def test_parse_industry_variants():
    assert "semiconductor" in parse_preferences("要半导体芯片行业")["industries"]
    assert "ecommerce" in parse_preferences("要电商行业")["industries"]


def test_explicit_mobility_level():
    p = parse_preferences("基地在Penang，调往KL")
    res = score_preferences(
        _job(company="Local Co", location="Bayan Lepas, Penang",
             description="transfer opportunities across regional offices"),
        p,
    )
    assert res["flags"]["relocation_level"] == "explicit_mobility"
    assert res["boost"] >= 10


def test_fuzzy_keywords_add_residual_boost():
    p = parse_preferences("强调要有analytics能力")  # "analytics" is not a known dim
    assert p["fuzzy_terms"]
    res = score_preferences(_job(description="you bring strong analytics depth"), p)
    assert any("关键词共鸣" in r for r in res["reasons"])


def test_base_unknown_is_neutral_not_capped():
    p = parse_preferences("基地在Penang")
    res = score_preferences(_job(location=""), p)
    assert res["flags"]["base_unknown"] is True
    assert not res["caps"]


def test_startup_penalty_when_mnc_required():
    p = parse_preferences("MNC preferred")
    res = score_preferences(_job(description="a bootstrapped startup, fast paced"), p)
    assert res["deduct"] == 5


def test_onsite_and_hybrid_scoring_branches():
    onsite_p = parse_preferences("要驻场办公")
    res = score_preferences(_job(description="on-site role at factory"), onsite_p)
    assert res["boost"] >= 8

    hybrid_p = parse_preferences("要混合办公")
    res = score_preferences(_job(description="hybrid: some remote, some on-site"),
                            hybrid_p)
    assert res["boost"] >= 8


def test_salary_transparency_escalation_with_text():
    silent = parse_preferences("")
    explicit = parse_preferences("必须写明薪资")
    assert explicit["salary_transparency"] > silent["salary_transparency"]


def test_scoring_depends_on_requirement_text():
    penang_kl = parse_preferences("基地在Penang，调往KL")
    remote = parse_preferences("要远程办公")
    job = _job(company="Intel", location="Bayan Lepas, Penang",
               description="rotation to kuala lumpur; remote friendly")
    first = score_preferences(job, penang_kl)["boost"]
    second = score_preferences(job, remote)["boost"]
    assert first > second  # same job, different requirement -> different score
    assert any("远程办公" in r for r in score_preferences(job, remote)["reasons"])