"""
Job freshness / posting-age extraction.

Job boards usually show relative age in the card snippet ("Posted 5 days ago",
"30+ days ago", "Just posted"). We parse that into an integer number of days
since posting. If no signal is present, we return None (unknown) rather than
guessing — callers must NOT penalize unknown age.

Strategy is best-effort and free (regex only).
"""

import re
from datetime import date

_JUST = re.compile(r"\b(just posted|posted today|today|posted (?:this|an?) (?:hour|day))\b", re.I)
_HOURS = re.compile(r"(\d+)\s*hours?\s*ago", re.I)
_DAYS = re.compile(r"(\d+)\s*days?\s*ago", re.I)
_WEEKS = re.compile(r"(\d+)\s*weeks?\s*ago", re.I)
_MONTHS = re.compile(r"(\d+)\s*months?\s*ago", re.I)
_PLUS = re.compile(r"(\d+)\s*\+\s*days?\b", re.I)          # "30+ days"
_OVER_MONTH = re.compile(r"(?:over|more than)\s+a\s+month", re.I)
_ISO_DATE = re.compile(r"(\d{4})[-/](\d{1,2})[-/](\d{1,2})")  # YYYY-MM-DD


def extract_posted_days_ago(text):
    """
    Return integer days since the job was posted, or None if unknown.

    Notes:
      - "just posted" / "today" / "X hours ago" -> 0
      - "30+ days" -> 30 (treated as at/over the typical 30-day threshold)
    """
    if not text:
        return None
    low = text.lower()

    if _JUST.search(low):
        return 0
    m = _HOURS.search(low)
    if m:
        return 0
    m = _DAYS.search(low)
    if m:
        return int(m.group(1))
    m = _WEEKS.search(low)
    if m:
        return int(m.group(1)) * 7
    m = _MONTHS.search(low)
    if m:
        return int(m.group(1)) * 30
    m = _PLUS.search(low)
    if m:
        return int(m.group(1))
    if _OVER_MONTH.search(low):
        return 31
    m = _ISO_DATE.search(text)
    if m:
        try:
            posted = date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
            return max(0, (date.today() - posted).days)
        except Exception:
            pass
    return None


def format_age(days_ago):
    """Human-readable age label for the UI."""
    if days_ago is None:
        return "发布时间未知"
    if days_ago <= 0:
        return "今天发布"
    if days_ago == 1:
        return "昨天发布"
    return f"{days_ago}天前发布"


if __name__ == "__main__":
    samples = [
        "Just posted",
        "Posted 5 days ago by Acme",
        "30+ days ago",
        "Posted 2 weeks ago",
        "Posted 3 months ago",
        "No date mentioned here",
    ]
    for s in samples:
        print(f"{extract_posted_days_ago(s)!s:5} <- {s}")
