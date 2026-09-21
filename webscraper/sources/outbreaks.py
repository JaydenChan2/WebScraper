#!/usr/bin/env python3
"""
outbreaks.py — WHO Disease Outbreak News (DON) fetcher.

Source: https://www.who.int/api/emergencies/diseaseoutbreaknews (verified
live 2026-09-20 — most recent entry at check time was 2026-DON617, published
2026-09-10). This is event data, not a time series: one row per outbreak
report, not one row per date/country/variant. It does NOT fit the
Date,Region,Total_Infections,<VARIANT> CSV shape from PROMPT.md — instead it
maps naturally onto edit_namelist.py's Tier-1 OVERRIDE mechanism, since an
outbreak alert is a one-off event adjustment, not a continuous grid.

WHO's API gives no structured country/disease fields, only a free-text
Title formatted as "<Disease> - <Country>". This module parses that
best-effort and leaves Country_ISO3 blank (never guesses) when the trailing
segment doesn't resolve to a known country, since the spec requires flagging
ambiguity to a human rather than silently resolving it.

Severity is likewise inferred, not structured: WHO exposes free-text
Overview/Assessment/Epidemiology/Response fields but no severity field, so
severity.classify_severity() runs a keyword heuristic over that text. The
raw narrative isn't kept in the output CSV (it's long and mostly redundant
with Title) -- only the resulting tier and the phrase that triggered it.
"""
from __future__ import annotations

import re
import time
from pathlib import Path
from typing import List, Optional, Tuple
from urllib.parse import urlencode

from .. import country_ids
from ..csv_merge import merge_write
from ..http import get_json
from ..severity import classify_severity, strip_html

_OUTPUT_DIR = Path(__file__).parent.parent.parent / "output"
_API_BASE = "https://www.who.int/api/emergencies/diseaseoutbreaknews"
_PAGE_SIZE = 100
_TITLE_SPLIT_RE = re.compile(r"\s[-–—]\s")  # hyphen, en dash, or em dash


def _split_title(title: str) -> tuple[str, Optional[str]]:
    """Split '<Disease> - <Country>' into (disease_raw, country_raw|None)."""
    parts = _TITLE_SPLIT_RE.split(title)
    if len(parts) < 2:
        return title.strip(), None
    return " - ".join(parts[:-1]).strip(), parts[-1].strip()


def fetch_who_outbreak_news(since_date: Optional[str] = None, max_pages: int = 20) -> Tuple[Path, Optional[str]]:
    """
    Page through WHO's Disease Outbreak News, newest first, stopping once
    entries are older than `since_date` (ISO date string) or `max_pages` is
    reached. Merges results into:
        Date,Disease_raw,Country_raw,Country_ISO3,Severity,Severity_Basis,Title,Url
    keyed by Url (unique per DON report), so re-running never duplicates an
    entry. Country_ISO3 is left blank when the free-text country segment
    can't be confidently resolved — check Flags in the run summary before
    trusting it. Severity is a best-effort heuristic tier (see severity.py)
    with Severity_Basis showing what triggered it, for the same reason.

    Returns (output_path, latest_publication_date_seen), for use as the
    next --update watermark.
    """
    rows_out: List[dict] = []
    skip = 0
    exhausted = False
    for _ in range(max_pages):
        query = urlencode({
            "sf_provider": "dynamicProvider372",
            "sf_culture": "en",
            "$orderby": "PublicationDateAndTime desc",
            "$top": _PAGE_SIZE,
            "$skip": skip,
        })
        data = get_json(f"{_API_BASE}?{query}")
        page = data.get("value", [])
        if not page:
            exhausted = True
            break

        stop = False
        for item in page:
            pub_date = item["PublicationDate"][:10]
            if since_date is not None and pub_date < since_date:
                stop = True
                break
            disease_raw, country_raw = _split_title(item.get("Title", ""))
            iso3 = country_ids.resolve_iso3(country_raw) if country_raw else None
            title = item.get("Title", "")
            body_text = " ".join(strip_html(item.get(field, "")) for field in
                                  ("Overview", "Assessment", "Epidemiology", "Response"))
            severity, severity_basis = classify_severity(title, body_text)
            rows_out.append({
                "Date": pub_date,
                "Disease_raw": disease_raw,
                "Country_raw": country_raw or "",
                "Country_ISO3": iso3 or "",
                "Severity": severity,
                "Severity_Basis": severity_basis,
                "Title": title,
                "Url": f"https://www.who.int{item.get('ItemDefaultUrl', '')}",
            })
        if stop:
            exhausted = True
            break
        skip += _PAGE_SIZE
        time.sleep(0.5)  # be polite to WHO's API -- rapid-fire deep pagination has been timing out

    if not exhausted:
        print(
            f"WARNING: hit max_pages={max_pages} ({max_pages * _PAGE_SIZE} entries) before reaching "
            f"since_date or the end of the feed — results may be missing older entries. Re-run with "
            "a higher --max-pages if this is a full backfill."
        )

    out_path = _OUTPUT_DIR / "who_outbreak_news.csv"
    latest_date = merge_write(
        out_path,
        rows_out,
        key_fields=["Url"],
        leading_fields=["Date", "Disease_raw", "Country_raw", "Country_ISO3",
                         "Severity", "Severity_Basis", "Title", "Url"],
    )
    return out_path, latest_date
