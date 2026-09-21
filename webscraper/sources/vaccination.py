#!/usr/bin/env python3
"""
vaccination.py — Vaccination-coverage fetchers.

Two complementary, independently-verified sources (checked live on 2026-09-20):

1. WHO Global Health Observatory (GHO) OData API, WUENIC indicators
   (https://ghoapi.azureedge.net/api/<INDICATOR_CODE>). Official WHO/UNICEF
   estimates of national immunization coverage, annual granularity, still
   being updated (e.g. USA DTP3 2025 value was published 2026-07-14). Good
   for ongoing/recurring updates. Covers routine childhood vaccines
   (DTP3, measles, polio, BCG, HepB3), not COVID-19 specifically.

2. Our World in Data COVID-19 vaccinations dataset
   (raw.githubusercontent.com/owid/covid-19-data). COVID-specific,
   ISO3-coded, daily granularity — but the dataset stopped updating on
   2024-08-14, so it's only useful for historical backfill, not recurring
   updates. Flagged explicitly rather than silently treated as current.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional, Tuple
from urllib.parse import urlencode

from .. import country_ids
from ..csv_merge import merge_write
from ..http import get_json, get_csv_rows

_OUTPUT_DIR = Path(__file__).parent.parent.parent / "output"

_GHO_INDICATORS = {
    "WHS4_100": "DTP3_coverage_pct",
    "WHS8_110": "MCV1_measles_coverage_pct",
    "WHS4_543": "BCG_coverage_pct",
    "WHS4_117": "HepB3_coverage_pct",
    "WHS4_544": "IPV_polio_coverage_pct",
}

_OWID_VACCINATIONS_URL = (
    "https://raw.githubusercontent.com/owid/covid-19-data/master/"
    "public/data/vaccinations/vaccinations.csv"
)
OWID_LAST_KNOWN_UPDATE_DATE = "2024-08-14"  # verified 2026-09-20; dataset appears discontinued past this date


def fetch_who_immunization_coverage(since_year: Optional[int] = None) -> Tuple[Path, Optional[str]]:
    """
    Pull WUENIC routine-immunization coverage for all WHO-registered
    countries and merge it into a long-format CSV:
        Date,Region,Indicator,Value
    Date is YYYY-12-31 (annual estimate, period-end per PROMPT.md convention).

    Returns (output_path, latest_year_end_date_seen), for use as the next
    --update watermark (this is an annual series, so "today" would overshoot
    the next real publication just like the CDC variant series).
    """
    rows_out = []
    for code, indicator_name in _GHO_INDICATORS.items():
        url = f"https://ghoapi.azureedge.net/api/{code}"
        if since_year is not None:
            url += f"?{urlencode({'$filter': f'TimeDim ge {since_year}'})}"
        data = get_json(url)
        for rec in data.get("value", []):
            if rec.get("SpatialDimType") != "COUNTRY":
                continue  # skip WHO-region and global aggregate rows; per-country only
            iso3 = rec["SpatialDim"]
            if not country_ids.is_known_iso3(iso3):
                continue
            year = rec["TimeDim"]
            value = rec.get("NumericValue")
            if value is None:
                continue
            rows_out.append({
                "Date": f"{year}-12-31",
                "Region": iso3,
                "Indicator": indicator_name,
                "Value": value,
            })

    out_path = _OUTPUT_DIR / "who_immunization_coverage.csv"
    latest_date = merge_write(
        out_path,
        rows_out,
        key_fields=["Date", "Region", "Indicator"],
        leading_fields=["Date", "Region", "Indicator", "Value"],
    )
    return out_path, latest_date


def fetch_owid_covid_vaccinations(since_date: Optional[str] = None) -> Tuple[Path, Optional[str]]:
    """
    Pull the (discontinued-since-2024-08-14) OWID COVID-19 vaccinations
    dataset for historical backfill and merge it into one wide CSV:
        Date,Region,total_vaccinations,people_vaccinated,people_fully_vaccinated,total_boosters
    Rows for non-country aggregates (OWID's pseudo ISO codes like
    "OWID_WRL" for continents/income groups) are dropped — Region must be
    a real ISO3 the pipeline can place on the country grid.

    Returns (output_path, latest_date_seen). Since this dataset is frozen at
    OWID_LAST_KNOWN_UPDATE_DATE, the returned date will never advance past
    that regardless of when this is run.
    """
    raw_rows = get_csv_rows(_OWID_VACCINATIONS_URL)
    rows_out = []
    for r in raw_rows:
        iso = r.get("iso_code", "")
        if iso.startswith("OWID_") or not country_ids.is_known_iso3(iso):
            continue
        date = r["date"]
        if since_date is not None and date < since_date:
            continue
        rows_out.append({
            "Date": date,
            "Region": iso,
            "total_vaccinations": r.get("total_vaccinations", ""),
            "people_vaccinated": r.get("people_vaccinated", ""),
            "people_fully_vaccinated": r.get("people_fully_vaccinated", ""),
            "total_boosters": r.get("total_boosters", ""),
        })

    out_path = _OUTPUT_DIR / "owid_covid_vaccinations.csv"
    latest_date = merge_write(
        out_path,
        rows_out,
        key_fields=["Date", "Region"],
        leading_fields=[
            "Date", "Region", "total_vaccinations", "people_vaccinated",
            "people_fully_vaccinated", "total_boosters",
        ],
    )
    return out_path, latest_date
