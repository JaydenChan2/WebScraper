#!/usr/bin/env python3
"""
variants.py — CDC SARS-CoV-2 variant-proportion fetcher.

Source: CDC's "SARS-CoV-2 Variant Proportions" Socrata dataset
(data.cdc.gov, resource id jr58-6ysp) — verified live 2026-09-17/18, most
recent period at check time was week ending 2026-08-01, published
2026-08-28. This is currently the only still-updating, credible source
found for variant/case-adjacent data — WHO's and ECDC's variant pages are
descriptive-only now, and global per-country case-count reporting has
mostly been discontinued (flagged in the original CDC pull's write-up).
US-only until another country's live source is confirmed.

CDC publishes *share* (proportion of sequenced specimens), not raw case
counts or a sequencing total, so Total_Infections is always left blank here
per PROMPT.md's rule against back-calculating from an assumed total.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional, Tuple
from urllib.parse import urlencode

from ..csv_merge import merge_write
from ..http import get_json

_OUTPUT_DIR = Path(__file__).parent.parent.parent / "output"
_SOCRATA_BASE = "https://data.cdc.gov/resource/jr58-6ysp.json"


def fetch_cdc_variant_shares(since_date: Optional[str] = None) -> Tuple[Path, Optional[str]]:
    """
    Pull USA-level, empiric (non-modeled), 4-week variant-share estimates
    and merge them into a wide CSV: Date,Region,Total_Infections,<VARIANT_1>,...
    matching the format-A shape from PROMPT.md. Values are percentages
    (share * 100) — flagged, not silently presented as counts.

    Returns (output_path, latest_week_ending_seen). The caller should use
    the latter as the next --update watermark: CDC only publishes every
    ~4 weeks, so "today" would overshoot the next actual publication and
    make the following --update fetch nothing.
    """
    where_clause = "usa_or_hhsregion='USA' AND modeltype='empiric' AND time_interval='4_week'"
    if since_date is not None:
        where_clause += f" AND week_ending >= '{since_date}'"

    page_size = 5000
    raw_rows = []
    offset = 0
    while True:
        query = urlencode({
            "$where": where_clause, "$order": "week_ending ASC",
            "$limit": page_size, "$offset": offset,
        })
        page = get_json(f"{_SOCRATA_BASE}?{query}")
        raw_rows.extend(page)
        if len(page) < page_size:
            break
        offset += page_size

    def norm_variant(v: str) -> str:
        return v.strip().upper()

    dates = sorted(set(r["week_ending"][:10] for r in raw_rows))
    table = {d: {} for d in dates}
    for r in raw_rows:
        d = r["week_ending"][:10]
        v = norm_variant(r["variant"])
        table[d][v] = round(float(r["share"]) * 100, 3)

    new_rows = [{"Date": d, "Region": "USA", "Total_Infections": "", **table[d]} for d in dates]

    out_path = _OUTPUT_DIR / "cdc_usa_variant_shares.csv"
    latest_date = merge_write(
        out_path,
        new_rows,
        key_fields=["Date", "Region"],
        leading_fields=["Date", "Region", "Total_Infections"],
        column_sort_key=lambda v: (v == "OTHER", v),
    )
    return out_path, latest_date
