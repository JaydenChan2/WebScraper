#!/usr/bin/env python3
"""
country_ids.py — Global country registry for MAPS, analogous to STATE_ABBR_TO_FIPS
in build_maps_initial_conditions_with_history_full.py.

The canonical country list is WHO's own COUNTRY dimension (the same authority
that publishes the immunization-coverage and outbreak-news data this package
scrapes), cached locally in data/who_countries.json so runs don't depend on
network access just to resolve a country code.

Grid IDs assigned here are sequential integers, NOT tied to any real spatial
raster. build_maps_initial_conditions_with_history_full.py still needs an
actual global population/country-ID NetCDF grid (e.g. from GPWv4 or WorldPop)
before these IDs can be used to place data spatially — this module only
solves the "what ISO3 codes exist and how do I resolve messy input to one"
problem, not the geospatial one.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, Optional

_DATA_PATH = Path(__file__).parent / "data" / "who_countries.json"

# A handful of common names/aliases that don't exactly match WHO's official
# Title field, seen in dashboards, news articles, and CSV exports.
_ALIASES = {
    "USA": "USA", "US": "USA", "UNITED STATES": "USA", "UNITED STATES OF AMERICA": "USA",
    "UK": "GBR", "UNITED KINGDOM": "GBR", "GREAT BRITAIN": "GBR",
    "SOUTH KOREA": "KOR", "REPUBLIC OF KOREA": "KOR",
    "NORTH KOREA": "PRK", "DEMOCRATIC PEOPLE'S REPUBLIC OF KOREA": "PRK",
    "RUSSIA": "RUS", "RUSSIAN FEDERATION": "RUS",
    "VIETNAM": "VNM", "VIET NAM": "VNM",
    "IRAN": "IRN", "IRAN (ISLAMIC REPUBLIC OF)": "IRN",
    "SYRIA": "SYR", "SYRIAN ARAB REPUBLIC": "SYR",
    "LAOS": "LAO", "LAO PEOPLE'S DEMOCRATIC REPUBLIC": "LAO",
    "TANZANIA": "TZA", "UNITED REPUBLIC OF TANZANIA": "TZA",
    "MOLDOVA": "MDA", "REPUBLIC OF MOLDOVA": "MDA",
    "BOLIVIA": "BOL", "BOLIVIA (PLURINATIONAL STATE OF)": "BOL",
    "VENEZUELA": "VEN", "VENEZUELA (BOLIVARIAN REPUBLIC OF)": "VEN",
    "CZECHIA": "CZE", "CZECH REPUBLIC": "CZE",
    "IVORY COAST": "CIV", "COTE D'IVOIRE": "CIV", "CÔTE D'IVOIRE": "CIV",
    "DR CONGO": "COD", "DEMOCRATIC REPUBLIC OF THE CONGO": "COD", "DRC": "COD",
    "CONGO": "COG", "REPUBLIC OF THE CONGO": "COG",
    "BRUNEI": "BRN", "BRUNEI DARUSSALAM": "BRN",
    "CAPE VERDE": "CPV", "CABO VERDE": "CPV",
    "SWAZILAND": "SWZ", "ESWATINI": "SWZ",
    "MYANMAR": "MMR", "BURMA": "MMR",
    "PALESTINE": "PSE", "STATE OF PALESTINE": "PSE",
    "GLOBAL": "GLOBAL", "WORLD": "WORLD", "WORLDWIDE": "GLOBAL",
}


def _load_registry() -> Dict[str, dict]:
    raw = json.loads(_DATA_PATH.read_text())
    registry = {}
    for i, entry in enumerate(sorted(raw["value"], key=lambda e: e["Code"])):
        registry[entry["Code"]] = {
            "iso3": entry["Code"],
            "name": entry["Title"],
            "region": entry.get("ParentTitle"),
            # Sequential placeholder grid ID — see module docstring.
            "grid_id": i + 1,
        }
    return registry


COUNTRY_REGISTRY: Dict[str, dict] = _load_registry()
ISO3_TO_GRID_ID: Dict[str, int] = {k: v["grid_id"] for k, v in COUNTRY_REGISTRY.items()}
_NAME_LOOKUP: Dict[str, str] = {v["name"].strip().upper(): k for k, v in COUNTRY_REGISTRY.items()}


def resolve_iso3(raw: str) -> Optional[str]:
    """
    Resolve a country name, ISO3 code, or common alias to a canonical ISO3
    code. Returns None (never a guess) if the input can't be resolved
    confidently, so callers can flag it for a human instead of silently
    mismapping a country.
    """
    if not raw:
        return None
    key = raw.strip().upper()

    if key in COUNTRY_REGISTRY:
        return key
    if key in _ALIASES:
        return _ALIASES[key]
    if key in _NAME_LOOKUP:
        return _NAME_LOOKUP[key]

    return None


def is_known_iso3(code: str) -> bool:
    return code in COUNTRY_REGISTRY or code in ("GLOBAL", "WORLD")


if __name__ == "__main__":
    print(f"{len(COUNTRY_REGISTRY)} countries loaded from {_DATA_PATH.name}")
    for code in ("USA", "GBR", "COD"):
        print(code, "->", COUNTRY_REGISTRY[code])
    for name in ("United States", "DR Congo", "Nonexistentland"):
        print(repr(name), "->", resolve_iso3(name))
