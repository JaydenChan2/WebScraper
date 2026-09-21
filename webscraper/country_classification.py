#!/usr/bin/env python3
"""
country_classification.py — Peer-country matching for filling in missing
vaccination data, per the user's methodology: when a country has no public
data for some indicator, fall back on a country with "similar standing"
rather than leaving the model with a hole or an arbitrary global average.

"Similar standing" is operationalized as three World Bank dimensions,
cached in data/world_bank_classification.json (World Bank Country and
Lending Groups API, fetched 2026-09-21):
  - region        (World Bank region, e.g. "Sub-Saharan Africa")
  - income_level  (World Bank income group: Low/Lower middle/Upper middle/High income)
  - population    (most recent total population estimate) -> bucketed into
    a bracket so "similar size" doesn't require an exact population match.

This is a real methodological choice with a real limitation: region +
income + population are a coarse, defensible proxy for "similar standing,"
not a rigorous similarity model. A peer match is always reported with the
tier it was found at (see PeerMatch) so a human can see how strong the
match actually was, and every filled-in value is traceable back to its
source country rather than blended in silently.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Sequence

_DATA_PATH = Path(__file__).parent / "data" / "world_bank_classification.json"

# WHO's own COUNTRY dimension includes a few entries the World Bank doesn't
# separately classify. Genuine current territories are attributed to their
# sovereign parent's classification, since that's a factual description
# (same currency/legal/economic system), not a similarity judgment call.
# Defunct/erroneous WHO entries are excluded outright -- they're not real,
# currently-reportable countries and have no sensible "peer."
_TERRITORY_PARENT_OVERRIDES = {
    "GLP": "FRA",  # Guadeloupe
    "MTQ": "FRA",  # Martinique
    "REU": "FRA",  # Réunion
    "GUF": "FRA",  # French Guiana
    "SPM": "FRA",  # Saint Pierre and Miquelon
    "MYT": "FRA",  # Mayotte
}
_EXCLUDED_NON_COUNTRIES = {
    "ME1",      # "The former state union Serbia and Montenegro" -- dissolved 2006
    "PRS",      # "Pristina" -- a city, not a country (WHO data artifact)
    "SDN736",   # "Sudan (former)" -- pre-2011 (pre-South Sudan split) Sudan
}

# Population brackets, in millions. Coarse on purpose: the point is "similar
# order of magnitude," not a precise population match.
_POPULATION_BRACKETS = [
    (1, "under_1M"),
    (10, "1M_to_10M"),
    (50, "10M_to_50M"),
    (100, "50M_to_100M"),
    (300, "100M_to_300M"),
    (float("inf"), "over_300M"),
]


@dataclass(frozen=True)
class PeerMatch:
    peer_iso3: str
    tier: str  # "region_income_population" > "region_income" > "income_only" > "population_only"


def population_bracket(population: float) -> str:
    millions = population / 1_000_000
    for threshold, label in _POPULATION_BRACKETS:
        if millions < threshold:
            return label
    return _POPULATION_BRACKETS[-1][1]


def _load() -> Dict[str, dict]:
    raw = json.loads(_DATA_PATH.read_text())
    classification = {}
    for iso3, info in raw.items():
        classification[iso3] = {
            "region": info["region"],
            "income_level": info["income_level"],
            "population": info["population"],
            "population_bracket": population_bracket(info["population"]),
        }
    return classification


CLASSIFICATION: Dict[str, dict] = _load()


def classify(iso3: str) -> Optional[dict]:
    """Return {region, income_level, population, population_bracket} for an
    ISO3 code, resolving known territories to their sovereign parent's
    classification. Returns None if unclassifiable (excluded non-countries,
    or a code the World Bank simply doesn't cover)."""
    if iso3 in _EXCLUDED_NON_COUNTRIES:
        return None
    lookup_iso3 = _TERRITORY_PARENT_OVERRIDES.get(iso3, iso3)
    return CLASSIFICATION.get(lookup_iso3)


def find_peer(target_iso3: str, candidate_iso3s: Sequence[str]) -> Optional[PeerMatch]:
    """
    Find the best-matching peer for `target_iso3` among `candidate_iso3s`
    (countries known to actually have real data for whatever's missing).
    Relaxes match criteria in tiers until a candidate is found:
      1. same region + same income level + same population bracket
      2. same region + same income level (closest population)
      3. same income level only (closest population)
      4. closest population only (last resort)
    Returns None if the target itself can't be classified, or there are no
    candidates at all.
    """
    target = classify(target_iso3)
    candidates = [(c, classify(c)) for c in candidate_iso3s if c != target_iso3]
    candidates = [(c, info) for c, info in candidates if info is not None]
    if target is None or not candidates:
        return None

    def closest_population(pool: List[tuple]) -> str:
        return min(pool, key=lambda item: abs(item[1]["population"] - target["population"]))[0]

    tier1 = [(c, i) for c, i in candidates
             if i["region"] == target["region"]
             and i["income_level"] == target["income_level"]
             and i["population_bracket"] == target["population_bracket"]]
    if tier1:
        return PeerMatch(closest_population(tier1), "region_income_population")

    tier2 = [(c, i) for c, i in candidates
             if i["region"] == target["region"] and i["income_level"] == target["income_level"]]
    if tier2:
        return PeerMatch(closest_population(tier2), "region_income")

    tier3 = [(c, i) for c, i in candidates if i["income_level"] == target["income_level"]]
    if tier3:
        return PeerMatch(closest_population(tier3), "income_only")

    return PeerMatch(closest_population(candidates), "population_only")
