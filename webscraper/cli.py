#!/usr/bin/env python3
"""
cli.py — Entry point for the MAPS data scraper.

Usage:
    python -m webscraper.cli vaccinations --backfill
    python -m webscraper.cli vaccinations --update
    python -m webscraper.cli outbreaks --backfill
    python -m webscraper.cli variants --update
    python -m webscraper.cli all --update

--backfill ignores any saved state and pulls full history (or, for
Disease Outbreak News, up to --max-pages of it — there's no fixed backfill
start date for that source).
--update pulls only rows newer than the last successful run for that
dataset, recorded in output/.fetch_state.json, then advances the state to
the latest date actually seen in the fetched data — not the date this job
happened to run, since these sources publish on their own (often monthly
or annual) schedule and "today" would overshoot the next real update.
Both write into output/, matching the shape the existing PROMPT.md
extraction flow already produces by hand.

"vaccinations" covers two independent datasets (WHO routine-immunization
coverage, still updating; OWID COVID vaccinations, frozen since 2024-08-14)
with their own watermarks, since they update on different schedules.
"""
from __future__ import annotations

import argparse
from typing import Optional

from . import state_store
from .sources import vaccination, outbreaks, variants

_SOURCES = ("vaccinations", "outbreaks", "variants")


def _resolve_since(dataset_key: str, backfill: bool, since_arg: Optional[str]) -> Optional[str]:
    if backfill:
        return None
    if since_arg:
        return since_arg
    since = state_store.get_last_fetched(dataset_key)
    if since is None:
        print(f"[{dataset_key}] no saved state found; pulling full history (treat this as a first backfill).")
    return since


def _run_vaccinations(backfill: bool, since_arg: Optional[str]) -> None:
    who_since = _resolve_since("vaccinations_who", backfill, since_arg)
    who_since_year = int(who_since[:4]) if who_since else None
    who_path, who_latest = vaccination.fetch_who_immunization_coverage(since_year=who_since_year)
    print(f"[vaccinations_who] fetched since={who_since or 'beginning of history'} -> wrote {who_path}")
    if who_latest:
        state_store.set_last_fetched("vaccinations_who", who_latest)

    owid_since = _resolve_since("vaccinations_owid", backfill, since_arg)
    if owid_since is not None and owid_since > vaccination.OWID_LAST_KNOWN_UPDATE_DATE:
        print(
            f"[vaccinations_owid] skipped: requested since={owid_since} is after the dataset's "
            f"last known update ({vaccination.OWID_LAST_KNOWN_UPDATE_DATE}); it appears "
            "discontinued, so there is nothing newer to fetch."
        )
        return
    owid_path, owid_latest = vaccination.fetch_owid_covid_vaccinations(since_date=owid_since)
    print(f"[vaccinations_owid] fetched since={owid_since or 'beginning of history'} -> wrote {owid_path}")
    if owid_latest:
        state_store.set_last_fetched("vaccinations_owid", owid_latest)


def _run_outbreaks(backfill: bool, since_arg: Optional[str], max_pages: int) -> None:
    since = _resolve_since("outbreaks", backfill, since_arg)
    path, latest = outbreaks.fetch_who_outbreak_news(since_date=since, max_pages=max_pages)
    print(f"[outbreaks] fetched since={since or 'beginning of history'} -> wrote {path}")
    if latest:
        state_store.set_last_fetched("outbreaks", latest)


def _run_variants(backfill: bool, since_arg: Optional[str]) -> None:
    since = _resolve_since("variants", backfill, since_arg)
    path, latest = variants.fetch_cdc_variant_shares(since_date=since)
    print(f"[variants] fetched since={since or 'beginning of history'} -> wrote {path}")
    if latest:
        state_store.set_last_fetched("variants", latest)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="MAPS web data scraper")
    parser.add_argument("source", choices=_SOURCES + ("all",))
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--backfill", action="store_true", help="pull full history, ignoring saved state")
    mode.add_argument("--update", action="store_true", help="pull only rows newer than the last run")
    mode.add_argument("--since", metavar="YYYY-MM-DD", help="pull only rows on/after this date, ignoring saved state")
    parser.add_argument("--max-pages", type=int, default=50, help="outbreaks only: max API pages to page through (safety cap, not a real limit for a full backfill)")
    args = parser.parse_args(argv)

    sources = _SOURCES if args.source == "all" else (args.source,)

    for source in sources:
        if source == "vaccinations":
            _run_vaccinations(args.backfill, args.since)
        elif source == "outbreaks":
            _run_outbreaks(args.backfill, args.since, args.max_pages)
        elif source == "variants":
            _run_variants(args.backfill, args.since)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
