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

import csv
from pathlib import Path
from typing import List, Optional
from urllib.parse import urlencode

from ..http import get_json

_OUTPUT_DIR = Path(__file__).parent.parent.parent / "output"
_SOCRATA_BASE = "https://data.cdc.gov/resource/jr58-6ysp.json"


def fetch_cdc_variant_shares(since_date: Optional[str] = None) -> Path:
    """
    Pull USA-level, empiric (non-modeled), 4-week variant-share estimates
    and write a wide CSV: Date,Region,Total_Infections,<VARIANT_1>,...
    matching the format-A shape from PROMPT.md. Values are percentages
    (share * 100) — flagged, not silently presented as counts.
    """
    where_clause = "usa_or_hhsregion='USA' AND modeltype='empiric' AND time_interval='4_week'"
    if since_date is not None:
        where_clause += f" AND week_ending >= '{since_date}'"
    query = urlencode({"$where": where_clause, "$order": "week_ending ASC", "$limit": 5000})
    raw_rows = get_json(f"{_SOCRATA_BASE}?{query}")

    def norm_variant(v: str) -> str:
        v = v.strip().upper()
        return v

    dates = sorted(set(r["week_ending"][:10] for r in raw_rows))
    variants = sorted(
        set(norm_variant(r["variant"]) for r in raw_rows),
        key=lambda x: (x == "OTHER", x),
    )
    table = {d: {} for d in dates}
    for r in raw_rows:
        d = r["week_ending"][:10]
        v = norm_variant(r["variant"])
        table[d][v] = round(float(r["share"]) * 100, 3)

    rows_out: List[List] = []
    for d in dates:
        row = [d, "USA", ""] + [table[d].get(v, "") for v in variants]
        rows_out.append(row)

    out_path = _OUTPUT_DIR / "cdc_usa_variant_shares.csv"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["Date", "Region", "Total_Infections"] + variants)
        w.writerows(rows_out)
    return out_path
