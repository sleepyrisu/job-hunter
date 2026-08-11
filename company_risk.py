"""
Company Background / Risk Investigation Module

Heuristic, free background check for job postings. Combines:
  1. Rule-based red-flag scanning of the job description + company name
     (catches scams / MLM / pyramid schemes / upfront-fee traps / shell agencies)
  2. A local blacklist (user-maintained blacklist.json)
  3. An optional LLM risk opinion (returned by the AI filters) for recognizable
     companies, treated as a SOFT signal.

Final risk = worst of (rule level, llm level). Rule results are authoritative:
a hard red-flag always wins over an LLM "looks fine".

Risk levels: "high" (🔴), "medium" (🟡), "low" (🟢)
"""

import json
import os
import re

LEVEL_ORDER = {"low": 0, "medium": 1, "high": 2}

# ---------------------------------------------------------------------------
# 1. Built-in red-flag rules
# ---------------------------------------------------------------------------

# HIGH risk: outright scams / pyramid / money schemes
HIGH_PATTERNS = [
    (r"传销|金字塔|拉人头|发展下线|pyramid\s*scheme|\bmlm\b", "疑似传销/金字塔模式(拉人头)"),
    (r"投资|理财|回报|收益|稳赚|被动收入|高额回报|日赚|月入过万|轻松赚",
     "提及投资/理财/高收益回报(疑似资金盘)"),
    (r"加密货币|crypto|bitcoin|区块链|外汇|forex|二元期权|binary\s*option|刷单|充值返利",
     "提及加密货币/外汇/刷单/充值返利(高风险)"),
    (r"先交|押金|保证金|入职费|培训费|服装费|资料费|垫付|预付|deposit|upfront\s*fee|training\s*fee",
     "要求先交费/垫付(典型诈骗特征)"),
    (r"赌博|betting|gamble", "涉及赌博/博彩"),
    (r"无经验.*高薪|高薪.*无经验|no\s*experience.*high\s*salary|earn\s*\$?\d{4,}\s*(a|per)\s*(day|month).*no\s*experience",
     "无经验高薪(夸大诱导)"),
]

# MEDIUM risk: shell-agency / black-agency signals
MEDIUM_PATTERNS = [
    (r"whatsapp|wa\.me", "仅通过 WhatsApp 联系(正规公司通常有官方渠道)"),
    (r"confidential|hidden\s*company|our\s*client|某公司|知名企业|某大厂",
     "公司信息含糊(未披露真实雇主)"),
    (r"@gmail\.com|@yahoo\.com|@hotmail\.com|@outlook\.com|@163\.com|@qq\.com",
     "使用免费个人邮箱作为联系/投递方式"),
    (r"急招|大量招聘|urgent\s*hire|hiring\s*(now|urgently)|mass\s*recruitment",
     "大量急招(中介批量拉人特征)"),
    (r"兼职刷|在家办公.*日结|足不出户.*赚钱|轻松日结", "疑似兼职刷单/日结诱导"),
]

# Companies whose name is a known recruitment agency "front" with no real employer
# disclosure are handled via blacklist.json instead of hardcoding here.

_blacklist_cache = None


def load_blacklist():
    """Load user-maintained blacklist from blacklist.json (cached)."""
    global _blacklist_cache
    if _blacklist_cache is not None:
        return _blacklist_cache
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "blacklist.json")
    default = {"companies": [], "keywords": []}
    if not os.path.exists(path):
        _blacklist_cache = default
        return _blacklist_cache
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        _blacklist_cache = {
            "companies": [c.lower() for c in data.get("companies", [])],
            "keywords": [k.lower() for k in data.get("keywords", [])],
        }
    except Exception:
        _blacklist_cache = default
    return _blacklist_cache


def _scan_patterns(text, patterns):
    """Return list of matched reason strings for given (regex, reason) patterns."""
    found = []
    for pat, reason in patterns:
        try:
            if re.search(pat, text, re.IGNORECASE):
                found.append(reason)
        except re.error:
            continue
    return found


def rule_scan(company, description):
    """
    Rule-based + blacklist risk scan.

    Returns dict: {"level": "low"|"medium"|"high", "reasons": [...], "source": "rule"}
    """
    company = (company or "").strip()
    description = (description or "").strip()
    text = f"{company}\n{description}"

    reasons = []
    level = "low"

    # Blacklist: company name (exact or contained)
    bl = load_blacklist()
    comp_lower = company.lower()
    for name in bl["companies"]:
        if name and (name == comp_lower or name in comp_lower):
            reasons.append(f"公司在黑名单中: {name}")
            level = "high"
            break
    # Blacklist: keywords
    for kw in bl["keywords"]:
        if kw and kw in text.lower():
            reasons.append(f"命中黑名单关键词: {kw}")
            if LEVEL_ORDER[level] < LEVEL_ORDER["medium"]:
                level = "medium"

    # Hard red flags (HIGH)
    high_hits = _scan_patterns(text, HIGH_PATTERNS)
    if high_hits:
        reasons.extend(high_hits)
        level = "high"

    # Medium red flags (only if not already high)
    if level != "high":
        med_hits = _scan_patterns(text, MEDIUM_PATTERNS)
        if med_hits:
            reasons.extend(med_hits)
            level = "medium"

    if not reasons:
        reasons.append("未检测到明显风险信号（规则扫描）")

    return {"level": level, "reasons": reasons, "source": "rule"}


def worst_level(a, b):
    """Return the worse of two levels."""
    if LEVEL_ORDER.get(a, 0) >= LEVEL_ORDER.get(b, 0):
        return a
    return b


def combine_risk(rule_result, llm_risk=None):
    """
    Merge rule-based result with optional LLM risk opinion.
    Rule result is authoritative for 'high'; LLM only escalates when rules are clean.

    llm_risk: {"level": ..., "reason": ...} or None
    """
    final_level = rule_result["level"]
    reasons = list(rule_result["reasons"])
    sources = [rule_result.get("source", "rule")]

    if llm_risk:
        llm_level = llm_risk.get("level", "low")
        llm_reason = llm_risk.get("reason", "")
        if llm_level not in LEVEL_ORDER:
            llm_level = "low"
        # Escalate only if rules didn't already flag high
        if final_level != "high":
            final_level = worst_level(final_level, llm_level)
        if llm_reason and llm_reason not in reasons:
            reasons.append(f"[AI] {llm_reason}")
        sources.append("llm")

    return {
        "level": final_level,
        "reasons": reasons,
        "source": "+".join(sources),
    }


def assess_company_risk(company, description, llm_risk=None):
    """Full assessment: rule scan + combine with optional LLM opinion."""
    rule = rule_scan(company, description)
    return combine_risk(rule, llm_risk)


# Label/emoji helpers for the frontend
LEVEL_LABEL = {"high": "🔴 高风险", "medium": "🟡 注意", "low": "🟢 正常"}
LEVEL_COLOR = {"high": "#ef4444", "medium": "#f59e0b", "low": "#22c55e"}


def level_label(level):
    return LEVEL_LABEL.get(level, "🟢 正常")


def level_color(level):
    return LEVEL_COLOR.get(level, "#22c55e")


if __name__ == "__main__":
    tests = [
        ("Sketchy Crypto Ltd",
         "Join our crypto investment, guaranteed 10% monthly return. "
         "Pay training deposit via WhatsApp."),
        ("Accenture", "Junior Data Analyst at MNC. SQL, Python. Mentorship provided."),
        ("Some Agency", "We are hiring urgently for our client. Apply via WhatsApp wa.me/12345."),
    ]
    for c, d in tests:
        r = assess_company_risk(c, d)
        print(f"[{level_label(r['level'])}] {c}: {r['reasons']}")
