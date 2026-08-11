"""
Requirement-driven preference scorer (no AI).

The candidate's scoring preferences live as free text in
``settings.preferences.custom_requirements`` (plus the legacy
``company_type`` field). On every run this module re-derives a
``PreferenceProfile`` from that text and scores each job against that profile
generically - so editing the requirement text re-routes scoring with zero code
changes. Penang/KL/MNC are NOT special-cased anywhere; they are simply what
the default requirement text happens to ask for.

This is the SINGLE preference layer for BOTH pipelines: ``score_adjuster``
calls :func:`score_preferences`, regardless of whether AI is on. The LLM only
scores content; location / company / relocation / salary signals come from
here.

The dimension taxonomy is fixed (base location, exclusions, relocation path,
company type, work mode, industry, salary transparency) but every value and
weight inside it is read from the requirement text; anything the taxonomy
cannot consume falls back to weighted fuzzy keyword overlap.
"""
from __future__ import annotations

import re
from typing import Any

from company_knowledge import HUBS_WITH_MNC, is_mnc, mnc_matches

# --------------------------------------------------------------------------- #
# Lexicons
# --------------------------------------------------------------------------- #

# Canonical place key -> match tokens (latin tokens matched on word boundaries).
PLACE_ALIASES: dict[str, tuple[str, ...]] = {
    "penang": ("penang", "pulau pinang", "bayan lepas", "batu kawan",
               "george town", "georgetown", "槟城", "槟岛"),
    "kuala_lumpur": ("kuala lumpur", "吉隆坡", "kl"),
    "singapore": ("singapore", "新加坡"),
    "johor": ("johor", "jb", "柔佛", "新山"),
    "selangor": ("selangor", "petaling jaya", "shah alam", "雪兰莪"),
}

BASE_MARKERS = ("基地在", "基地：", "基地是", "基地位于", "base in", "based in",
                "located in", "常驻", "現居", "现居", "岗位在", "驻在")
RELOC_MARKERS = ("调往", "调到", "调任", "转调", "輪調", "轮岗", "外派", "調往",
                 "transfer to", "transferred to", "relocate to",
                 "relocation to", "rotate to", "rotation to", "secondment",
                 "seconded to", "mobility", "dispatch to", "有机会到", "能去")
EXCLUDE_MARKERS = ("不要", "排除", "避免", "不希望", "不希望到", "不要到",
                   "except", "excluding", "exclude", "avoid", "not in",
                   "outside")

STRONG = ("强烈", "非常", "必须", "一定", "最重要", "重点", "strongly",
          "very", "must", "top priority", "definitely")
SOFT = ("最好能", "最好", "若有", "可考虑", "勉强", "nice to have",
        "ideally", "hopefully")

MNC_WORDS = ("mnc", "multinational", "跨国公司", "跨国企业", "外企", "外资",
             "大厂", "world top", "500强", "top 500", "foreign company", "跨国")
STARTUP_WORDS = ("startup", "初创", "创业", "新创", "start-up")

REMOTE_WORDS = ("remote", "远程", "wfh", "work from home", "在家办公",
                "remote-first", "fully remote")
ONSITE_WORDS = ("on-site", "onsite", "现场", "驻场", "on site", "in office")
HYBRID_WORDS = ("hybrid", "混合")

INDUSTRY_KEYWORDS: dict[str, tuple[str, ...]] = {
    "semiconductor": ("半导体", "semiconductor", "晶圆", "wafer", "芯片", "chip",
                      "ic design", "fab", "foundry", "asic"),
    "fintech": ("fintech", "金融", "bank", "banking", "支付", "payment", "银行"),
    "ecommerce": ("电商", "ecommerce", "e-commerce", "marketplace", "shopee",
                  "lazada", "零售"),
    "healthcare": ("医疗", "healthcare", "pharma", "制药", "biotech"),
    "data_ai": ("数据分析", "data analyst", "machine learning", "人工智能",
                "big data", "数据"),
}

SALARY_WORDS = ("薪资", "工资", "薪資", "待遇", "写明薪资", "薪资透明",
                "工资写明", "salary", "pay range", "salary shown")

# Human-friendly labels for locale keys used in reasons / the preview.
DISPLAY_NAMES = {"penang": "Penang", "kuala_lumpur": "KL", "singapore": "SG",
                 "johor": "Johor", "selangor": "Selangor"}

STOPWORDS = frozenset({
    "a", "an", "the", "and", "or", "for", "in", "on", "of", "to", "with",
    "from", "that", "this", "is", "are", "be", "was", "were", "will", "can",
    "prefer", "preferred", "preference", "job", "jobs", "role", "roles",
    "work", "works", "working", "have", "has", "provides", "provide", "also",
    "not", "any", "all", "over", "under", "please", "ideal", "great",
})

# Baseline salary-transparency weight (a posting that hides salary is always
# penalised a little, even if the requirement text stays silent about it).
DEFAULT_SALARY_TRANSPARENCY = 6

MAX_BOOST = 30


# --------------------------------------------------------------------------- #
# Low-level helpers
# --------------------------------------------------------------------------- #

def _has_latin(token: str) -> bool:
    return any("a" <= ch <= "z" or "A" <= ch <= "Z" for ch in token)


def _token_spans(text: str, token: str) -> list[tuple[int, int]]:
    """Offsets of every occurrence of ``token`` in ``text``.

    Latin tokens use ASCII-alnum lookarounds (not ``\\b``): ``\\b`` sees CJK
    characters as word characters, so a Latin token sitting right after Chinese
    (e.g. "在Penang") would never match. The lookarounds keep "kl" out of
    "Klang"/"Keyword" while still matching "调往KL".
    """
    if _has_latin(token):
        pat = rf"(?<![A-Za-z0-9]){re.escape(token.lower())}(?![A-Za-z0-9])"
        return [(m.start(), m.end()) for m in re.finditer(pat, text.lower())]
    spans = []
    start = 0
    while True:
        idx = text.find(token, start)
        if idx < 0:
            break
        spans.append((idx, idx + len(token)))
        start = idx + len(token)
    return spans


def _mention_has(canonical: str, text: str) -> bool:
    return any(_token_spans(text, alias) for alias in PLACE_ALIASES.get(canonical, ()))


def _find_place_mentions(text: str) -> list[tuple[str, int, int]]:
    """All place mentions in ``text`` as (canonical, start, end)."""
    mentions: list[tuple[str, int, int]] = []
    for canon, aliases in PLACE_ALIASES.items():
        for alias in aliases:
            mentions.extend((canon, s, e) for s, e in _token_spans(text, alias))
    mentions.sort(key=lambda m: (m[1], m[0]))
    return mentions


_CLAUSE_SEPS = "。！!；;"


def _clause_start(text: str, pos: int) -> int:
    """Index just after the nearest preceding sentence separator (or 0)."""
    best = 0
    for sep in _CLAUSE_SEPS:
        i = text.rfind(sep, 0, pos)
        if i > best:
            best = i + 1
    return best


def _intensity(text: str, window_start: int, end: int) -> float:
    """Intensity multiplier from the window before ``window_start``, bounded to
    the same clause (a "强烈" about relocation must not bleed into an unrelated
    later "MNC preferred" clause). SOFT markers only count when they sit right
    before the keyword; STRONG markers count up to 12 chars back."""
    lo = max(_clause_start(text, window_start), window_start - 12)
    window = text[lo:end].lower()
    tight_lo = max(_clause_start(text, window_start), window_start - 6)
    tight = text[tight_lo:end].lower()
    if any(w in window for w in STRONG):
        return 1.6
    if any(w in tight for w in SOFT):
        return 0.6
    return 1.0


def _scaled(base: float, text: str, ws: int, we: int) -> int:
    return max(0, int(round(base * _intensity(text, ws, we))))


def _scaled_near(text: str, base: float, keys) -> int:
    """Scale ``base`` by the intensity adverb sitting right before the first
    matching keyword (so a "强烈" about relocation does NOT bleed into an
    unrelated "MNC preferred" clause)."""
    low = text.lower()
    pos = -1
    for key in keys:
        idx = low.find(key.lower())
        if idx >= 0:
            pos = idx
            break
    if pos < 0:
        return 0
    return _scaled(base, text, pos + 1, pos + 1)


# --------------------------------------------------------------------------- #
# Profile builder
# --------------------------------------------------------------------------- #


def parse_preferences(text: str = "", company_type: str = "") -> dict[str, Any]:
    """Parse requirement text (+ legacy company_type) into a preference profile.

    The profile is a plain dict so it JSON-serialises cleanly for the dashboard
    "what did the system understand" preview.
    """
    raw = text or ""
    profile: dict[str, Any] = {
        "raw_text": raw,
        "base_locations": [],
        "excluded_locations": [],
        "relocation": {"targets": [], "weight": 0},
        "company_type": {"mnc": 0, "startup": 0},
        "work_mode": {"remote": 0, "onsite": 0, "hybrid": 0},
        "industries": {},
        "salary_transparency": DEFAULT_SALARY_TRANSPARENCY,
        "fuzzy_terms": [],
        "parsed_from": "custom_requirements",
    }
    if not raw.strip():
        return profile

    mentions = _find_place_mentions(raw)
    base_assigned: set[str] = set()
    reloc_assigned: set[str] = set()

    # Role each place mention via the nearest leading marker, precedence
    # exclude > relocation > base.
    for role, markers in (("exclude", EXCLUDE_MARKERS),
                          ("relocation", RELOC_MARKERS),
                          ("base", BASE_MARKERS)):
        for marker in markers:
            for ms, me in _token_spans(raw, marker):
                for canon, start, _end in mentions:
                    if start < me or start > me + 16:
                        continue
                    if role == "exclude":
                        if canon not in profile["excluded_locations"]:
                            profile["excluded_locations"].append(canon)
                    elif role == "relocation":
                        if canon not in profile["relocation"]["targets"]:
                            profile["relocation"]["targets"].append(canon)
                        reloc_assigned.add(canon)
                        profile["relocation"]["weight"] = max(
                            profile["relocation"]["weight"],
                            _scaled(10, raw, ms, me),
                        )
                    elif role == "base" and canon not in base_assigned:
                        profile["base_locations"].append(canon)
                        base_assigned.add(canon)
                    break  # only the nearest mention takes the role

    if profile["relocation"]["targets"] and not profile["relocation"]["weight"]:
        profile["relocation"]["weight"] = 10

    # Leftover place mentions default to base location.
    for canon, _s, _e in mentions:
        if (canon not in base_assigned and canon not in reloc_assigned
                and canon not in profile["excluded_locations"]
                and canon not in profile["base_locations"]):
            profile["base_locations"].append(canon)

    # --- company type ---------------------------------------------------- --
    combined_cfg = " ".join([raw, company_type or ""]).lower()
    if any(w in combined_cfg for w in MNC_WORDS):
        profile["company_type"]["mnc"] = _scaled_near(combined_cfg, 6, MNC_WORDS) or 6
    if any(w in combined_cfg for w in STARTUP_WORDS):
        profile["company_type"]["startup"] = _scaled_near(combined_cfg, 3, STARTUP_WORDS) or 3

    # --- work mode ------------------------------------------------------- --
    wl = raw.lower()
    if any(w in wl for w in REMOTE_WORDS):
        profile["work_mode"]["remote"] = _scaled_near(raw, 8, REMOTE_WORDS) or 8
    if any(w in wl for w in ONSITE_WORDS):
        profile["work_mode"]["onsite"] = _scaled_near(raw, 8, ONSITE_WORDS) or 8
    if any(w in wl for w in HYBRID_WORDS):
        profile["work_mode"]["hybrid"] = _scaled_near(raw, 8, HYBRID_WORDS) or 8

    # --- industries ------------------------------------------------------ --
    for industry, kws in INDUSTRY_KEYWORDS.items():
        if any(kw in raw or kw in wl for kw in kws):
            profile["industries"][industry] = _scaled_near(raw, 8, kws) or 8

    # --- salary transparency --------------------------------------------- --
    if any(w in raw or w in wl for w in SALARY_WORDS):
        profile["salary_transparency"] = min(
            14, DEFAULT_SALARY_TRANSPARENCY
            + (_scaled_near(raw, 6, SALARY_WORDS) or 6))

    # --- fuzzy fallback tokens ------------------------------------------- --
    consumed = set()
    for _canon, aliases in PLACE_ALIASES.items():
        for a in aliases:
            consumed.add(a.lower())
            if _has_latin(a):
                consumed.update(a.lower().split())
    for kws in INDUSTRY_KEYWORDS.values():
        for kw in kws:
            consumed.add(kw.lower())
            if _has_latin(kw):
                consumed.update(kw.lower().split())
    for term in re.findall(r"[a-zA-Z]{4,}", wl):
        if term in STOPWORDS or term in consumed:
            continue
        profile["fuzzy_terms"].append({"term": term, "weight": 1})
        if len(profile["fuzzy_terms"]) >= 20:
            break

    return profile


# --------------------------------------------------------------------------- #
# Evidence extraction
# --------------------------------------------------------------------------- #

def _relocation_evidence(job: dict, profile: dict) -> tuple[str, str]:
    """Best available relocation evidence for the job. Returns (level, reason)
    with level one of "dual_location", "explicit_mobility", "mnc_potential",
    "none"."""
    targets = profile["relocation"]["targets"]
    if not targets:
        return "none", ""
    loc = job.get("location", "")
    desc = (job.get("description") or "").lower()
    combined = f"{loc} {desc}"

    base = profile["base_locations"]
    in_base = (not base) or any(_mention_has(b, combined) for b in base)
    in_target = any(_mention_has(t, combined) for t in targets)

    target_names = ", ".join(DISPLAY_NAMES.get(t, t) for t in targets)

    # "dual_location" only when the posting covers BOTH the base and the target
    # (e.g. multi-city "Penang, Kuala Lumpur"). A job sitting entirely IN the
    # target city is not a relocation path - it is just an out-of-base job.
    dual = in_base and in_target

    mobility = ("transfer", "transferred", "relocate", "relocation",
                "rotation", "rotational", "secondment", "seconded",
                "mobility", "cross-site", "cross site", "multi-site",
                "global mobility", "international mobility", "regional")
    explicit = in_base and any(w in desc for w in mobility)

    mc = mnc_matches(job.get("company", ""))
    potential = False
    for t in targets:
        if mc and any(k in HUBS_WITH_MNC.get(t, frozenset()) for k in mc):
            potential = True
            break

    if dual:
        return "dual_location", f"岗位已覆盖多地：{target_names}"
    if explicit:
        return "explicit_mobility", f"写明调动/轮岗/外派前往{target_names}"
    if potential:
        return "mnc_potential", f"{target_names}有据点的MNC，存在内部调动可能"
    return "none", ""


def salary_transparency_penalty(profile: dict, job: dict) -> tuple[int, str]:
    """Points to deduct and a reason when the employer hid the salary."""
    weight = profile.get("salary_transparency") or DEFAULT_SALARY_TRANSPARENCY
    if job.get("salary_monthly") is not None:
        if "(AI estimate)" in (job.get("salary_raw") or ""):
            return max(2, weight // 2), "薪资未写明，仅估算(-)"
        return 0, ""
    return weight, "未写明薪资(-)"


# --------------------------------------------------------------------------- #
# Scoring
# --------------------------------------------------------------------------- #

def score_preferences(job: dict, profile: dict) -> dict[str, Any]:
    """Score a job against a preference profile.

    Returns ``boost`` (positive preference evidence), ``caps`` (list of
    (max_score, reason) hard caps), ``deduct`` (points to remove) and
    ``reasons`` (human-readable Chinese lines) plus ``flags``.
    """
    loc = job.get("location") or ""
    loc_l = loc.lower()
    title = (job.get("title") or "").lower()
    company = job.get("company") or ""
    desc = (job.get("description") or job.get("snippet") or "").lower()
    combined = f"{title} {company.lower()} {loc_l} {desc}"

    boost = 0
    deduct = 0
    caps: list[tuple[int, str]] = []
    reasons: list[str] = []
    flags: dict[str, Any] = {
        "base_ok": True,
        "base_unknown": False,
        "excluded": False,
        "relocation_level": "none",
        "relocation_targets": list(profile["relocation"]["targets"]),
        "mnc": False,
    }

    # --- base location ---------------------------------------------------- --
    base = profile["base_locations"]
    if base:
        if not loc_l.strip():
            flags["base_unknown"] = True
        elif any(_mention_has(b, loc) for b in base):
            boost += 2
            reasons.append("基地匹配(+)")
        else:
            flags["base_ok"] = False
            base_display = ",".join(DISPLAY_NAMES.get(b, b) for b in base)
            caps.append((62, f"基地需{base_display}，岗位在{loc}(压至62)"))

    # --- excluded locations --------------------------------------------- ---
    if any(_mention_has(ex, loc) for ex in profile["excluded_locations"]):
        flags["excluded"] = True
        exc_display = ",".join(DISPLAY_NAMES.get(e, e) for e in profile["excluded_locations"])
        caps.append((25, f"命中排除地点：{exc_display}"))

    # --- relocation path -------------------------------------------------- --
    level, reloc_reason = _relocation_evidence(job, profile)
    flags["relocation_level"] = level
    weight = profile["relocation"]["weight"]
    if level != "none" and weight:
        factor = {"dual_location": 1.0, "explicit_mobility": 1.0,
                  "mnc_potential": 0.55}.get(level, 1.0)
        pts = max(1, int(round(weight * factor)))
        boost += pts
        reasons.append(reloc_reason)

    # --- company type ----------------------------------------------------- --
    mc = bool(mnc_matches(company))
    flags["mnc"] = mc
    mnc_w = profile["company_type"]["mnc"]
    if mnc_w and mc:
        boost += mnc_w
        reasons.append(f"MNC企业(+{mnc_w})")
    if mnc_w and not mc and any(w in desc for w in ("startup", "初创",
                                                   "bootstrapped", "young company")):
        deduct += 5
        reasons.append("创业公司气息(-5)")

    # --- work mode -------------------------------------------------------- --
    remote_w = profile["work_mode"]["remote"]
    onsite_w = profile["work_mode"]["onsite"]
    hybrid_w = profile["work_mode"]["hybrid"]
    has_remote = any(w in combined for w in REMOTE_WORDS)
    has_onsite = any(w in combined for w in ONSITE_WORDS)
    if remote_w and has_remote and not has_onsite:
        boost += remote_w
        reasons.append("远程办公(+)")
    elif remote_w and has_onsite and not has_remote:
        deduct += remote_w
        reasons.append("要求坐班，非远程(-)")
    elif onsite_w and has_onsite and not has_remote:
        boost += onsite_w
        reasons.append("现场办公匹配(+)")
    elif hybrid_w and has_remote and has_onsite:
        boost += hybrid_w
        reasons.append("混合办公匹配(+)")

    # --- industries ------------------------------------------------------- --
    industry_pts = 0
    for industry, weight in profile["industries"].items():
        if industry_pts >= 8:
            break
        if any(kw in combined for kw in INDUSTRY_KEYWORDS[industry]):
            pts = min(weight, 8 - industry_pts)
            boost += pts
            industry_pts += pts
            reasons.append(f"{industry}行业(+{pts})")

    # --- salary transparency --- ------------------------------------------ --
    sal_pts, sal_reason = salary_transparency_penalty(profile, job)
    if sal_pts:
        deduct += sal_pts
        reasons.append(sal_reason)

    # --- fuzzy keywords --------------------------------------------------- --
    fuzzy_hits = sum(1 for f in profile["fuzzy_terms"]
                     if re.search(rf"\b{re.escape(f['term'])}\b", combined))
    if fuzzy_hits:
        pts = min(6, fuzzy_hits)
        boost += pts
        reasons.append(f"关键词共鸣(+{pts})")

    return {
        "boost": min(MAX_BOOST, boost),
        "caps": caps,
        "deduct": deduct,
        "reasons": reasons,
        "flags": flags,
    }


# Re-export for tests / callers that prefer the short register name.
is_mnc_exported = is_mnc