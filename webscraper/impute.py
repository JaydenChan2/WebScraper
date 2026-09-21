#!/usr/bin/env python3
"""
impute.py — Fills gaps in the vaccination CSVs with peer-country values,
using country_classification.find_peer() (region + income level +
population bracket, per the user's chosen methodology).

This is a separate post-processing step, not part of the fetchers
themselves: who_immunization_coverage.csv and owid_covid_vaccinations.csv
stay pure, fetched-only ground truth. Running `python -m webscraper.cli
impute` reads those and writes *_filled.csv siblings with every row tagged:
    Is_Imputed        -- "Yes" or "No"
    Proxy_Source_Country -- ISO3 of the peer the value was copied from, or "" for real rows
    Match_Tier        -- how strong the peer match was, or "" for real rows

Only vaccination data is imputed. Variant shares are US-only (no
cross-country gaps to fill), and outbreak alerts are discrete events where
"missing" just means no outbreak was reported -- fabricating one would be
actively wrong, not a reasonable estimate.
"""
from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Dict, List, Optional

from . import country_classification as cc

_OUTPUT_DIR = Path(__file__).parent.parent / "output"
_WHO_COUNTRIES_PATH = Path(__file__).parent / "data" / "who_countries.json"


def _all_iso3s() -> List[str]:
    raw = json.loads(_WHO_COUNTRIES_PATH.read_text())
    return [c["Code"] for c in raw["value"]]


def fill_missing_long(rows: List[dict], group_fields: List[str], value_field: str,
                       region_field: str = "Region") -> List[dict]:
    """
    For long-format data (one row per Region + group_fields, one value
    column): for every group-key seen in the real data (e.g. one specific
    Indicator + Date), fill in a proxy row for every known country that
    doesn't already have a real row for that exact group-key.
    """
    all_isos = _all_iso3s()

    by_group: Dict[tuple, Dict[str, dict]] = {}
    for row in rows:
        key = tuple(row[f] for f in group_fields)
        by_group.setdefault(key, {})[row[region_field]] = row

    out_rows: List[dict] = []
    for row in rows:
        out_rows.append({**row, "Is_Imputed": "No", "Proxy_Source_Country": "", "Match_Tier": ""})

    for key, region_rows in by_group.items():
        real_regions = list(region_rows.keys())
        for iso3 in all_isos:
            if iso3 in region_rows:
                continue
            match = cc.find_peer(iso3, real_regions)
            if match is None:
                continue  # unclassifiable target (e.g. an excluded non-country) -- leave the gap, don't guess
            peer_row = region_rows[match.peer_iso3]
            new_row = {**peer_row, region_field: iso3}
            for f, v in zip(group_fields, key):
                new_row[f] = v
            new_row["Is_Imputed"] = "Yes"
            new_row["Proxy_Source_Country"] = match.peer_iso3
            new_row["Match_Tier"] = match.tier
            out_rows.append(new_row)

    return out_rows


def fill_missing_wide(rows: List[dict], date_field: str, value_fields: List[str],
                       primary_field: str, region_field: str = "Region") -> List[dict]:
    """
    For wide-format data (one row per Region + Date, several value columns):
    a country "has data" at all if `primary_field` is non-blank on at least
    one of its rows. Only countries with NO real data anywhere get a proxy
    series, copying their peer's entire real date range and whichever
    value_fields the peer itself has for each date.

    Deliberately NOT applied per-date: OWID reports on an irregular cadence
    (a country with real data might still have blank cells on most
    individual days between reports), and that's a normal reporting gap
    within a country's own series, not a "this country has no data" case --
    substituting another country's values for a day a real-data country
    simply didn't file a fresh report would be wrong, not a reasonable
    baseline. Only whole-country absence (e.g. North Korea, never in the
    dataset) is a case where "borrow a peer's series" is the right idea.
    """
    all_isos = _all_iso3s()

    rows_by_region: Dict[str, List[dict]] = {}
    for row in rows:
        rows_by_region.setdefault(row[region_field], []).append(row)

    countries_with_data = [iso for iso, rs in rows_by_region.items()
                            if any(r.get(primary_field, "").strip() for r in rs)]

    out_rows: List[dict] = []
    for row in rows:
        out_rows.append({**row, "Is_Imputed": "No", "Proxy_Source_Country": "", "Match_Tier": ""})

    missing_isos = [iso3 for iso3 in all_isos if iso3 not in countries_with_data]
    for iso3 in missing_isos:
        match = cc.find_peer(iso3, countries_with_data)
        if match is None:
            continue  # unclassifiable target -- leave the gap, don't guess
        for peer_row in rows_by_region[match.peer_iso3]:
            if not peer_row.get(primary_field, "").strip():
                continue  # only mirror the peer's real report dates, not its own blank cells
            out_rows.append({
                date_field: peer_row[date_field],
                region_field: iso3,
                **{f: peer_row.get(f, "") for f in value_fields},
                "Is_Imputed": "Yes",
                "Proxy_Source_Country": match.peer_iso3,
                "Match_Tier": match.tier,
            })

    return out_rows


def _read_csv(path: Path) -> List[dict]:
    with path.open(newline="") as f:
        return list(csv.DictReader(f))


def _write_csv(path: Path, rows: List[dict], fieldnames: List[str]) -> None:
    with path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames, restval="")
        w.writeheader()
        for row in rows:
            w.writerow({k: row.get(k, "") for k in fieldnames})


def run_imputation() -> None:
    who_path = _OUTPUT_DIR / "who_immunization_coverage.csv"
    if who_path.exists():
        rows = _read_csv(who_path)
        filled = fill_missing_long(rows, group_fields=["Indicator", "Date"], value_field="Value")
        filled.sort(key=lambda r: (r["Region"], r["Indicator"], r["Date"]))
        out_path = _OUTPUT_DIR / "who_immunization_coverage_filled.csv"
        _write_csv(out_path, filled,
                   ["Date", "Region", "Indicator", "Value", "Is_Imputed", "Proxy_Source_Country", "Match_Tier"])
        n_imputed = sum(1 for r in filled if r["Is_Imputed"] == "Yes")
        print(f"wrote {out_path} ({len(filled)} rows, {n_imputed} imputed)")
    else:
        print(f"skipped who_immunization_coverage: {who_path} not found -- run `vaccinations --backfill` first")

    owid_path = _OUTPUT_DIR / "owid_covid_vaccinations.csv"
    if owid_path.exists():
        rows = _read_csv(owid_path)
        value_fields = ["total_vaccinations", "people_vaccinated", "people_fully_vaccinated", "total_boosters"]
        filled = fill_missing_wide(rows, date_field="Date", value_fields=value_fields,
                                    primary_field="total_vaccinations")
        filled.sort(key=lambda r: (r["Region"], r["Date"]))
        out_path = _OUTPUT_DIR / "owid_covid_vaccinations_filled.csv"
        _write_csv(out_path, filled,
                   ["Date", "Region"] + value_fields + ["Is_Imputed", "Proxy_Source_Country", "Match_Tier"])
        n_imputed = sum(1 for r in filled if r["Is_Imputed"] == "Yes")
        print(f"wrote {out_path} ({len(filled)} rows, {n_imputed} imputed)")
    else:
        print(f"skipped owid_covid_vaccinations: {owid_path} not found -- run `vaccinations --backfill` first")
