"""
Company knowledge base shared by every scorer.

Single source of truth for MNC recognition and for "which multinationals are
known to run offices in each hub city". The requirement-driven preference
scorer uses the hubs dataset to infer a plausible internal transfer path even
when a posting does not say so explicitly; ``score_adjuster`` and
``rule_filter`` share the same MNC lists through ``is_mnc``.

Matching is false-positive-safe: multi-word names match as whole phrases and
short single tokens match on word boundaries, so a token like "ey" no longer
flags every company whose name merely *contains* the letters "ey".
"""
from __future__ import annotations

import re
from collections.abc import Iterable

# Curated list of well-known multinationals with operations in BOTH Penang and
# Kuala Lumpur. Used to flag a plausible internal transfer / rotation path to
# KL for Penang-based roles, even when the posting does not state it explicitly.
PENANG_MNC_KEYWORDS = [
    "intel", "amd", "advanced micro", "bosch", "western digital", "flex",
    "celestica", "dell", "hp", "hewlett", "motorola", "onsemi", "micron",
    "keysight", "broadcom", "jabil", "renesas", "infineon", "osram",
    "texas instruments", "avago", "plexus", "vestas", "b. braun", "braun",
    "agilent", "lam research", "applied materials", "vitrox", "inari",
    "globetronics", "epson", "schneider", "siemens", "honeywell", "nvidia",
    "cisco", "ibm", "accenture", "ericsson", "nokia", "umc", "skyworks",
    "qorvo", "microsoft", "apple", "google", "amazon", "toyota", "denso",
    "hitachi", "panasonic", "samsung", "sanmina", "bourns", "asm", "kla",
    "teradyne", "advantest", "tata consultancy", "tcs", "wistron", "compal",
    "pegatron", "flextronics", "texas inst",
]

# Canonical MNC name set. A company is only classified MNC to the extent its
# name matches an entry here (word/phrase matching, see ``mnc_matches``).
MNC_COMPANIES = frozenset(
    {
        # Tier-1 tech
        "google", "apple", "microsoft", "amazon", "meta", "netflix",
        # Tier-2 semiconductor / electronics manufacturers (Malaysia-heavy)
        "intel", "amd", "advanced micro", "bosch", "western digital", "flex",
        "celestica", "dell", "hp", "hewlett", "motorola", "onsemi", "micron",
        "keysight", "broadcom", "jabil", "infineon", "nxp", "st micro",
        "renesas", "osram", "texas instruments", "texas inst", "avago", "plexus",
        "vestas", "b. braun", "braun", "agilent", "lam research", "applied materials",
        "vitrox", "inari", "globetronics", "epson", "schneider", "siemens", "honeywell",
        "nvidia", "cisco", "ibm", "ericsson", "nokia", "umc", "skyworks", "qorvo",
        "toyota", "denso", "hitachi", "panasonic", "samsung", "sanmina", "bourns",
        "asm", "kla", "teradyne", "advantest", "wistron", "compal", "pegatron",
        "flextronics",
        # Tier-3 consultancies / IT services
        "experian", "accenture", "deloitte", "pwc", "ey", "kpmg", "cognizant",
        "wipro", "infosys", "tcs", "hcl", "tata consultancy",
    }
)

# Hub cities -> employers known to operate there. Used to infer a plausible
# internal-transfer path when a role is based in one hub but the candidate
# wants a path to another. Only hubs named in the requirement are consulted.
HUBS_WITH_MNC: dict[str, frozenset[str]] = {
    "kuala_lumpur": frozenset(PENANG_MNC_KEYWORDS + list(MNC_COMPANIES)),
    "singapore": frozenset({
        "google", "apple", "microsoft", "amazon", "meta", "intel", "micron",
        "infineon", "nxp", "st micro", "broadcom", "avago", "renesas", "hp",
        "dell", "schneider", "siemens", "honeywell", "nvidia", "cisco", "ibm",
        "accenture", "deloitte", "pwc", "ey", "kpmg", "cognizant", "infosys",
        "tcs", "tata consultancy",
    }),
}


def matches_any(company: str, keywords: Iterable[str]) -> list[str]:
    """Return every keyword (implying a company classification) hit in the
    employer name.

    Multi-word names match as substrings; single words match on word
    boundaries so short tokens like "ey" or "asm" cannot false-positive on
    unrelated company names.
    """
    c = (company or "").lower()
    hits: list[str] = []
    for kw in keywords:
        k = kw.strip().lower()
        if not k:
            continue
        if " " in k:
            if k in c:
                hits.append(k)
        elif re.search(rf"\b{re.escape(k)}\b", c):
            hits.append(k)
    return hits


def mnc_matches(company: str) -> list[str]:
    """Matched canonical MNC keywords for an employer name."""
    return matches_any(company, MNC_COMPANIES)


def is_mnc(company) -> bool:
    """True if the employer name matches a known multinational."""
    return bool(mnc_matches(company))


def is_penang_mnc(company, location) -> bool:
    """True if the role is Penang-based and the employer is a known MNC likely
    to also have a Kuala Lumpur office (plausible KL rotation path)."""
    loc = (location or "").lower()
    if not ("penang" in loc or "pulau pinang" in loc or "george town" in loc or "bayan lepas" in loc):
        return False
    return bool(matches_any(company, PENANG_MNC_KEYWORDS))