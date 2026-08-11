"""
Salary extraction utility.

Job boards rarely expose structured salary, so we parse it from the free-text
job description / snippet. Returns a normalized MONTHLY figure in Malaysian Ringgit
(RM) plus the raw matched string for display.

Strategy:
  1. Rule-based regex extraction (deterministic, free) — handles the common
     "RM 4,500", "RM 4.5k", "RM 4000 - 5000", "MYR 60,000 per annum" forms.
  2. If the rule finds nothing, the AI evaluator provides an estimate
     (see the `salary` field in the filter prompts). This module only does (1);
     the AI estimate is merged in main.py.

Currency note: we only trust values explicitly denoted RM / MYR. Bare numbers
without a currency unit are ignored to avoid false positives.
"""

import re

# Currency-tagged number, e.g. RM 4,500 / MYR4500 / rm 4.5k
_AMOUNT_RE = re.compile(
    r"""
    (?:rm|myr)\s*               # currency prefix
    (\d[\d,]*(?:\.\d+)?)        # integer or decimal, possibly grouped
    \s*                         # optional space
    (k\b)?                      # optional 'k' suffix => *1000
    """,
    re.IGNORECASE | re.VERBOSE,
)

# Range form: RM 4000 - 5000  /  RM 4k to 5k
_RANGE_RE = re.compile(
    r"""
    (?:rm|myr)\s*
    (\d[\d,]*(?:\.\d+)?)\s*(k\b)?
    \s*(?:[-–—to]+)\s*
    (?:rm|myr)?\s*
    (\d[\d,]*(?:\.\d+)?)\s*(k\b)?
    """,
    re.IGNORECASE | re.VERBOSE,
)

_PERIOD_RE = re.compile(
    r"per\s*annum|per\s*year|annual|yearly|/\s*year|12\s*months?",
    re.IGNORECASE,
)


def _to_int(num_str, is_k):
    val = float(num_str.replace(",", ""))
    if is_k:
        val *= 1000
    return int(round(val))


def _is_annual(text, match):
    """True only if a per-annum keyword appears between this match and the
    NEXT currency amount (or within 18 chars if none). This prevents a
    distant 'per annum' from wrongly tagging an unrelated monthly figure."""
    start = match.end()
    nxt = _AMOUNT_RE.search(text, start)
    end = nxt.start() if nxt else start + 18
    return bool(_PERIOD_RE.search(text[start:end]))


def extract_salary(text):
    """
    Extract monthly salary (RM) from job text.

    Returns: (monthly_rm: int|None, raw: str|None)
    """
    if not text:
        return None, None

    # 1. Range first (most informative, e.g. "RM 4000 - 5000")
    m = _RANGE_RE.search(text)
    if m:
        low = _to_int(m.group(1), m.group(2))
        high = _to_int(m.group(3), m.group(4))
        monthly = (low + high) // 2
        raw = m.group(0).strip()
        if _is_annual(text, m):
            monthly = max(1, monthly // 12)
        return monthly, raw

    # 2. Collect every currency amount; prefer explicit annual figures.
    annual_vals = []
    monthly_vals = []
    for m in _AMOUNT_RE.finditer(text):
        val = _to_int(m.group(1), m.group(2))
        if val <= 0:
            continue
        if _is_annual(text, m):
            annual_vals.append(max(1, val // 12))
        else:
            monthly_vals.append(val)

    if annual_vals:
        # Explicit "per annum" present -> use it (averaged if several)
        monthly = sum(annual_vals) // len(annual_vals)
        return monthly, f"~RM {monthly:,}/mo (annual)"

    if monthly_vals:
        # Use the first explicit monthly figure (e.g. "Up to RM 5k" -> 5000)
        return monthly_vals[0], f"RM {monthly_vals[0]:,}"

    return None, None


def format_salary(monthly_rm):
    """Human-readable salary string for the UI."""
    if not monthly_rm:
        return "薪资未注明"
    return f"RM {monthly_rm:,}/mo"


if __name__ == "__main__":
    samples = [
        "Salary: RM 4,500 per month",
        "Compensation RM 4000 - RM 5000 monthly",
        "Up to RM 5k, MYR 60,000 per annum",
        "We offer RM 3.2k starting",
        "Great culture, competitive pay",   # no salary
        "RM 0 (negotiable)",                # guard
    ]
    for s in samples:
        print(f"{extract_salary(s)!s:45} <- {s}")
