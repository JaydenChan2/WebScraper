#!/usr/bin/env python3
"""
severity.py — Best-effort qualitative severity tier for WHO Disease
Outbreak News reports, since the API exposes no structured severity field
(only free-text narrative). This is a keyword heuristic, not a validated
epidemiological score: treat it as a rough triage signal for prioritizing
review, not ground truth.

Scale (highest to lowest), evaluated in this priority order -- the first
tier whose pattern matches anywhere in the report text wins:
    PHEIC     - WHO has invoked or discussed a Public Health Emergency of
                International Concern for this event
    EPIDEMIC  - language indicating rapid/substantial growth, widespread or
                sustained transmission, or a title spanning multiple
                countries/regions
    OUTBREAK  - active but not clearly escalating transmission (a
                confirmed cluster, an ongoing/declared outbreak)
    CLUSTER   - a handful of linked cases, not (yet) framed as an outbreak
    WATCH     - a single/isolated/first case, or (default) no escalation
                language found at all

Every classification reports which phrase triggered it (or that none did),
so a human can audit the call instead of trusting it blindly -- the same
principle applied to country-name resolution elsewhere in this package.
"""
from __future__ import annotations

import re
from typing import Tuple

_TEXT_RULES = [
    ("PHEIC", [
        r"public health emergency of international concern",
        r"\bpheic\b",
    ]),
    ("EPIDEMIC", [
        r"increased? (rapidly|substantially|significantly)",
        r"widespread transmission",
        r"sustained transmission",
        r"spread(?:ing)? to (?:multiple|several) (?:countries|regions|provinces)",
        r"\blarge outbreak\b",
        r"\bmajor outbreak\b",
        r"rapid increase",
        r"significant increase",
    ]),
    ("OUTBREAK", [
        r"cluster of cases",
        r"confirmed cases and deaths",
        r"active (?:outbreak|transmission)",
        r"ongoing transmission",
        r"outbreak (?:has been )?declared",
    ]),
    ("CLUSTER", [
        r"\bcluster\b",
        r"several cases",
        r"(?:a )?(?:small )?number of cases",
        r"\bfew cases\b",
    ]),
    ("WATCH", [
        r"single case",
        r"isolated case",
        r"\bone case\b",
        r"first case",
        r"sporadic case",
    ]),
]

_SCOPE_KEYWORDS = ("global", "multi-country", "multi-countries", "multi-location", "worldwide")


def strip_html(raw: str) -> str:
    text = re.sub(r"<[^>]+>", " ", raw or "")
    text = text.replace("&nbsp;", " ")
    return re.sub(r"\s+", " ", text).strip()


def classify_severity(title: str, body_text: str) -> Tuple[str, str]:
    """
    Returns (tier, basis). `basis` is the matched phrase, or a note that
    the call fell back to a structural (title-scope) or default rule.
    """
    text = body_text.lower()
    title_lower = (title or "").lower()

    for tier, patterns in _TEXT_RULES:
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                return tier, f'text match: "{match.group(0)}"'

    if "&" in (title or "") or any(kw in title_lower for kw in _SCOPE_KEYWORDS):
        return "EPIDEMIC", "title indicates multiple countries/regions"

    return "WATCH", "no escalation language found (default)"
