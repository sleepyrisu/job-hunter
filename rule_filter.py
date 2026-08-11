"""
Resume-driven rule-based job evaluator - no AI/API needed.
ALL scoring rules are generated from the uploaded resume data.
Enhanced with NLP skill extraction for better matching.

Scoring contract: :func:`score_job` computes the CONTENT match (skills,
education, experience, level, semantic similarity) and emits preference
signals (location fit, MNC/KL potential, transfer evidence) as metadata.
Policy adjustments that depend on fields the evaluator never receives
(real location, parsed salary, posting age) are applied ONCE downstream by
``score_adjuster.adjust_score``. This keeps AI-on and AI-off pipelines
comparable and prevents double counting location/company/salary bonuses.
"""
import json
import os
import re

from nlp_skills import compute_skill_match_score, get_skill_category
from score_adjuster import is_mnc
from semantic_match import compute_semantic_similarity

DIRECTORY = os.path.dirname(os.path.abspath(__file__))


def load_resume_data():
    """Load parsed resume data."""
    from resume_parser import parse_resume
    path = os.path.join(DIRECTORY, "resume.md")
    if os.path.exists(path):
        return parse_resume(path)
    return {}


def _edu_penalty(resume_edu, job_text):
    """Score education fit based on resume education level vs job requirements."""
    edu = resume_edu.lower() if resume_edu else ""
    score = 0
    reasons = []

    # Check if job REQUIRES degree (Bachelor/Master/PhD)
    requires_degree = any(kw in job_text for kw in [
        "bachelor", "degree required", "must have degree",
        "b.s.", "b.sc.", "b.a.", "master", "phd", "mba"
    ])
    # Check if job welcomes diploma / entry level
    welcomes_diploma = any(kw in job_text for kw in [
        "diploma", "fresh graduate", "entry level", "junior",
        "trainee", "graduate", "no experience", "no degree required",
        "open to graduates"
    ])

    if edu in ("diploma", "associate"):
        if requires_degree and not welcomes_diploma:
            score = -30
            reasons.append("要求Degree(-30)")
        elif welcomes_diploma:
            score = 15
            reasons.append("欢迎Diploma/应届(+15)")
    elif edu in ("bachelor", "master", "phd") and requires_degree:
        score = 5
        reasons.append("学历匹配(+5)")

    return score, reasons


def _exp_penalty(resume_yrs, job_text):
    """Score experience fit based on resume years vs job requirements."""
    yr_match = re.search(
        r"(\d+)\+?\s*(?:years?|yrs?)\s*(?:of\s+)?(?:experience|exp)",
        job_text
    )
    if not yr_match:
        return 0, []

    required = int(yr_match.group(1))
    if required >= 5:
        return -25, [f"要求{required}年经验(-25)"]
    elif required >= 3:
        return -20, [f"要求{required}年经验(-20)"]
    elif required <= 2:
        return 5, [f"仅要求{required}年经验(+5)"]
    return 0, []


def _skill_match(resume_skills, job_text):
    """Score how many resume skills appear in the job text using NLP extraction."""
    # Use NLP extraction for better matching
    score, matched, missing = compute_skill_match_score(resume_skills, job_text)

    # Weight by skill category (programming > frameworks > tools)
    category_weights = {
        "programming": 1.2,
        "framework": 1.1,
        "data": 1.0,
        "cloud": 1.0,
        "rpa": 1.3,  # RPA is the candidate's strength
        "ai_ml": 0.9,
        "tools": 0.8,
    }

    weighted_score = 0.0
    for skill in matched:
        cat = get_skill_category(skill)
        weight = category_weights.get(cat, 1.0)
        weighted_score += 10 * weight

    # Cap at 30
    final_score = min(30, int(weighted_score))

    reasons = []
    if len(matched) >= 3:
        reasons.append(f"技能匹配: {', '.join(matched[:4])}(+{final_score})")
    elif len(matched) >= 1:
        reasons.append(f"技能匹配: {', '.join(matched)}(+{final_score})")
    else:
        final_score = -5
        reasons.append("技能匹配度低(-5)")

    return final_score, reasons


def _level_match(resume_exp, job_text, title):
    """Score role level fit: junior vs senior based on experience."""
    senior_kw = ["senior", "lead", "principal", "staff", "manager", "director", "head of"]
    junior_kw = ["junior", "entry level", "fresh graduate", "trainee",
                 "graduate", "intern", "associate", "no experience"]
    title_lower = title.lower()

    is_senior = any(kw in title_lower for kw in senior_kw)
    is_junior = any(kw in title_lower for kw in junior_kw)

    if is_senior:
        if resume_exp <= 1:
            return -25, ["Senior岗位但经验不足(-25)"]
        elif resume_exp <= 3:
            return -10, ["Senior岗位(-10)"]
        return 0, []
    elif is_junior:
        return 10, ["Junior/Entry岗位(+10)"]

    # Check year range in description
    range_match = re.search(r"(\d+)\s*-\s*(\d+)\s*(?:years?|yrs?)", job_text)
    if range_match:
        low, high = int(range_match.group(1)), int(range_match.group(2))
        if resume_exp >= low and resume_exp <= high:
            return 8, [f"经验匹配{low}-{high}年(+8)"]
        elif resume_exp < low:
            return -5, [f"经验低于要求{low}年(-5)"]
    return 0, []


def _location_match(resume_locations, job_location, job_text):
    """Score location fit based on resume preferred locations."""
    loc_lower = job_location.lower()
    combined = f"{loc_lower} {job_text.lower()}"

    for loc in resume_locations:
        loc_key = loc.lower().split(",")[0].strip()
        if loc_key in combined:
            if "penang" in loc_key or "pulau pinang" in loc_key:
                return 10, ["Penang(+10)"], True, False
            elif "kuala lumpur" in loc_key or "kl" in loc_key:
                return 5, ["KL(+5)"], True, False

    # Check for excluded locations (Singapore, overseas)
    if any(kw in combined for kw in ["singapore"]):
        return -5, ["Singapore(-5)"], False, False
    if any(kw in combined for kw in ["remote", "work from home", "wfh"]):
        return 3, [], True, False

    return 0, [], False, False


def _company_fit(resume_data, company, job_text):
    """Assess company type, returning (raw_bonus, reasons, kl_potential, is_mnc).

    ``raw_bonus`` is INFORMATIONAL ONLY (used by unit tests / the reason text);
    score_job does NOT add it to the content score. KL potential and MNC flags
    are the signals the score adjuster and the risk model consume.
    """
    # Startup indicators
    startup_indicators = ["startup", "sdn bhd", "pte ltd", "berhad",
                          "founded in 20", "series a", "series b", "seed round"]

    company_lower = company.lower()
    mnc = is_mnc(company)

    is_startup = any(ind in company_lower for ind in startup_indicators)

    score = 0
    reasons = []
    kl_potential = False

    if mnc:
        score += 4
        reasons.append("MNC(+4)")

        # MNC in Penang → KL transfer potential
        for loc in resume_data.get("locations", []):
            if "penang" in loc.lower():
                kl_potential = True
                score += 5
                reasons.append("MNC Penang→KL潜力(+5)")
                break
    elif is_startup:
        score += 2
        reasons.append("创业公司(+2)")

    # Industry-specific adjustments
    industry_keywords = {
        "semiconductor": ["semiconductor", "chip", "wafer", "fab", "foundry"],
        "fintech": ["fintech", "banking", "financial", "payment"],
        "healthcare": ["healthcare", "medical", "pharma", "biotech"],
        "ecommerce": ["ecommerce", "e-commerce", "marketplace", "retail"],
    }

    for industry, keywords in industry_keywords.items():
        if any(kw in company_lower or kw in job_text for kw in keywords):
            if industry in ["semiconductor", "fintech"]:
                score += 2
                reasons.append(f"{industry}行业(+2)")
            break

    # Red flags
    red_flags = ["fast-paced startup", "wear many hats", "self-starter",
                 "hit the ground running", "must be able to work independently",
                 "no leave", "urgent hire"]
    if any(rf in job_text for rf in red_flags):
        score -= 5
        reasons.append("创业公司描述(-5)")

    return score, reasons, kl_potential, mnc


def _kl_transfer_check(job_text):
    """Check for an explicit KL transfer/rotation/relocation mention.

    Kept as a content-signal helper for the rule pipeline's legacy flags; the
    authoritative relocation decision now lives in requirement_scorer, driven
    by the requirement text.
    """
    kl_kw = ["transfer to kl", "rotation to kuala lumpur",
             "relocate to kuala lumpur", "transfer to kuala lumpur",
             "kl rotation", "opportunity in kl", "towards kuala lumpur",
             "secondment to kl", "kuala lumpur rotation", "relocation to kl"]
    if any(kw in job_text for kw in kl_kw):
        return True, 8, ["明确KL调动(+8)"]
    # Broader mobility wording (rotation/secondment/relocation language) that
    # implies a path towards KL even without the exact phrase.
    if any(w in job_text for w in ("secondment", "relocation package",
                                   "rotation program", "cross-site", "rotational",
                                   "global mobility", "international mobility")):
        return True, 6, ["可能有调动/轮岗机会(+6)"]
    return False, 0, []


def score_job(job, resume_data):
    """
    Score a single job against resume data (CONTENT MATCH ONLY, 0-100).

    Preference/context signals that require the real job record - location
    base, salary vs. minimum, posting age, explicit KL transfer, safe-fit -
    are intentionally NOT part of this score. They are emitted as metadata
    (``kl_transfer``, ``kl_potential``, ``risk``) and applied exactly once by
    ``score_adjuster.adjust_score`` in main.py for BOTH the rule and AI paths.
    """
    title = (job.get("title") or "").lower()
    desc = (job.get("description") or job.get("snippet") or "").lower()
    company = (job.get("company") or "").lower()
    location = (job.get("location") or "").lower()
    combined = f"{title} {desc} {location}"

    resume_skills = resume_data.get("skills", [])
    resume_edu = resume_data.get("education", "")
    resume_exp = resume_data.get("experience_years", 1)
    resume_locs = resume_data.get("locations", [])

    score = 50  # Start neutral
    all_reasons = []

    # 1. Skill match (from resume, NLP-enhanced)
    s, r = _skill_match(resume_skills, combined)
    score += s - 10  # Normalize
    all_reasons.extend(r)

    # 2. Semantic similarity (TF-IDF based)
    raw_text = resume_data.get("raw_text", "")
    if raw_text:
        semantic_score = compute_semantic_similarity(raw_text, combined)
        if semantic_score >= 30:
            score += min(15, semantic_score // 3)
            all_reasons.append(f"语义相似度{semantic_score}%(+{min(15, semantic_score // 3)})")
        elif semantic_score >= 15:
            score += 5
            all_reasons.append(f"语义相似度{semantic_score}%(+5)")

    # 3. Education fit (from resume)
    s, r = _edu_penalty(resume_edu, combined)
    score += s
    all_reasons.extend(r)

    # 4. Experience fit (from resume)
    s, r = _exp_penalty(resume_exp, combined)
    score += s
    all_reasons.extend(r)

    # 5. Role level fit (from resume experience)
    s, r = _level_match(resume_exp, combined, title)
    score += s
    all_reasons.extend(r)

    # --- Preference SIGNALS (metadata only, no score contribution) ---------
    # Location fit informs risk; company/MNC and KL-transfer evidence flow to
    # the score adjuster which owns the single preference layer.
    _, _, loc_ok, _ = _location_match(resume_locs, location, combined)

    kl_potential = False
    _, _, kl_pot, is_mnc = _company_fit(resume_data, company, combined)
    kl_potential = kl_pot

    kl_transfer, _, kl_r = _kl_transfer_check(combined)
    if kl_r:
        all_reasons.extend(kl_r)

    # Clamp
    score = max(0, min(100, score))

    # Fit type
    if score >= 80:
        fit_type = "safe"
    elif score >= 60:
        fit_type = "stretch"
    else:
        fit_type = "unknown"

    # Risk
    risk_level = "low"
    if not is_mnc and not loc_ok:
        risk_level = "medium"
    if any(kw in combined for kw in ["crypto", "investment", "mlm", "pyramid", "upfront fee"]):
        risk_level = "high"

    return {
        "score": score,
        "reason": " | ".join(all_reasons) if all_reasons else "中等匹配",
        "fit_type": fit_type,
        "kl_potential": kl_potential,
        "kl_transfer": kl_transfer,
        "risk": {"level": risk_level, "reason": "MNC" if is_mnc else "一般雇主"},
    }


def evaluate_batch(jobs, resume_data=None):
    """Score a batch of jobs.

    Result indexes are 1-based, matching the AI filter contract (main.py builds
    batch input with ``index = position + 1``) so callers never have to guess
    which convention a filter returned.
    """
    if not resume_data:
        resume_data = load_resume_data()
    results = []
    for idx, job in enumerate(jobs):
        scored = score_job(job, resume_data)
        scored["index"] = idx + 1
        results.append(scored)
    return results


class RuleFilter:
    """Drop-in replacement for AI filters. No API key needed."""

    def __init__(self):
        self.is_configured = True
        self.profile = load_resume_data()

    def read_resume(self):
        return json.dumps(self.profile, ensure_ascii=False)

    def evaluate_job_batch(self, jobs_batch, custom_requirements=""):
        results = []
        for position, j in enumerate(jobs_batch, start=1):
            scored = score_job(j, self.profile)
            # Honour the caller's index when given (main passes 1-based); fall
            # back to position so index-less batches still align per job.
            scored["index"] = int(j.get("index", 0) or 0) or position
            results.append(scored)
        return results

    def generate_cover_letter(self, title, company, description):
        skills = ", ".join(self.profile.get("skills", [])[:5])
        name = self.profile.get("name", "Your Name")
        edu = self.profile.get("education", "Diploma")
        exp = self.profile.get("experience_years", 1)
        return f"""Dear Hiring Manager,

I am writing to express my interest in the {title} position at {company}.

With my {edu} qualification and {exp} year(s) of experience in {skills},
I am confident in my ability to contribute to your team.

Thank you for considering my application.

Best regards,
{name}"""


if __name__ == "__main__":
    import sys
    path = sys.argv[1] if len(sys.argv) > 1 else "resume.md"
    data = load_resume_data()
    print("Resume-driven rule filter test")
    print("  Name:", data.get("name", "Unknown"))
    print("  Education:", data.get("education"))
    print("  Experience:", data.get("experience_years"), "years")
    print("  Skills:", data.get("skills", [])[:5])
    print("  Locations:", data.get("locations"))

    test_job = {
        "title": "Junior RPA Developer",
        "company": "Intel Malaysia",
        "location": "Penang, Malaysia",
        "description": "Looking for junior RPA developer. Power Automate preferred. Entry level welcome."
    }
    result = score_job(test_job, data)
    print("\nTest score:", result["score"])
    print("  Reason:", result["reason"])
    print("  Fit:", result["fit_type"])
