"""
Score Adjuster Module
Applies the post-evaluation preference layer ONCE for BOTH the rule and AI
pipelines. Salary / posting-age caps and the requirement-driven bonuses
(scoring the site/work-city/company/relocation/salary-transparency signals
derived from ``custom_requirements``) live here. Nothing in this file is
hardcoded to Penang/KL/MNC — the requirement text decides what gets boosted.

Shared company-registry helpers (``is_mnc``, ``is_penang_mnc``, the keyword
lists) are re-exported from ``company_knowledge`` so existing callers keep
working; the canonical definitions now live there.
"""

from __future__ import annotations

from typing import Any

from company_knowledge import (  # noqa: F401  (re-exported for back-compat)
    MNC_COMPANIES,
    PENANG_MNC_KEYWORDS,
    is_mnc,
    is_penang_mnc,
    mnc_matches,
)
from requirement_scorer import parse_preferences, score_preferences

# Bonus fade zone: above this content score the additive preference boost is
# scaled down linearly to zero at 100, so near-perfect matches keep ordering by
# content rather than being flattened against the 100 ceiling.
_FADE_START = 85


def adjust_score(job, ai_result, settings):
    """
    Apply post-AI / post-rule score adjustments based on the requirements.

    Args:
        job: dict with keys like title, company, location, salary_monthly,
             salary_raw, posted_days_ago, description (may be absent).
        ai_result: dict from the evaluator (score, reason, fit_type, ...).
        settings: the full settings dict from config.

    Returns:
        (score, reason, extras) — score is the final 0-100 integer, reason is
        the human-readable rationale, extras carries preference flags that the
        DB / dashboard consume (kl_transfer, kl_potential, relocation info).
    """
    score = int(ai_result.get("score") or 0)
    reason = (ai_result.get("reason") or "").strip()

    preferences = settings.get("preferences", {}) or {}
    min_salary = preferences.get("min_salary", 0) or 0
    max_age_days = preferences.get("max_age_days", 30) or 30
    safe_first = preferences.get("safe_first", True)
    custom_requirements = preferences.get("custom_requirements", "") or ""
    company_type = preferences.get("company_type", "") or ""

    profile = parse_preferences(custom_requirements, company_type)
    pref = score_preferences(job, profile)

    # Hard-ish caps: salary below minimum, stale posting, base mismatch,
    # excluded location. Applied to the content score BEFORE bonuses.
    caps: list[tuple[int, str]] = list(pref["caps"])

    salary_monthly = job.get("salary_monthly")
    if salary_monthly is not None and min_salary and salary_monthly < min_salary:
        caps.append((50, f"薪资RM{salary_monthly:,}低于最低要求RM{min_salary:,}。"))

    posted_days_ago = job.get("posted_days_ago")
    if posted_days_ago is not None and max_age_days and posted_days_ago > max_age_days:
        caps.append((40, f"已发布{posted_days_ago}天，超过{max_age_days}天限制。"))

    base = max(0, score - pref["deduct"])

    # Preference boosts (requirement-driven) with high-score fade.
    fit_type = ai_result.get("fit_type", "") or ""
    total_boost = pref["boost"]
    if safe_first and fit_type == "safe":
        total_boost += 5

    factor = 1.0 if base < _FADE_START else max(0.0, (100 - base) / (100 - _FADE_START))
    final = min(100, base + int(round(total_boost * factor)))

    # Hard caps are ABSOLUTE ceilings on the final score: a role outside the
    # required base, in an excluded location, paying below the minimum, or too
    # stale must not climb back over its ceiling via preference boosts.
    for cap_value, _cap_reason in caps:
        final = min(final, cap_value)
    final = max(0, final)

    # Assemble the reason string.
    extra_lines: list[str] = list(pref["reasons"])
    if safe_first and fit_type == "safe":
        extra_lines.append("你现有技能即可直接上手(稳妥岗)。")
    for _cap_value, cap_reason in caps:
        if cap_reason:
            extra_lines.append(cap_reason)
    if extra_lines:
        reason = f"{reason} {' '.join(extra_lines)}".strip()

    flags = pref["flags"]
    extras: dict[str, Any] = {
        "fit_type": fit_type,
        "kl_transfer": flags["relocation_level"] in ("dual_location", "explicit_mobility"),
        "kl_potential": flags["relocation_level"] == "mnc_potential",
        "relocation_level": flags["relocation_level"],
        "relocation_targets": flags["relocation_targets"],
        "mnc": flags["mnc"],
        "base_ok": flags["base_ok"],
        "base_unknown": flags["base_unknown"],
        "excluded": flags["excluded"],
    }
    return final, reason, extras