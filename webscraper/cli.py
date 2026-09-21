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
source, recorded in output/.fetch_state.json, then advances the state.
Both write into output/, matching the shape the existing PROMPT.md
extraction flow already produces by hand.
"""
from __future__ import annotations

import argparse
import sys
from datetime import date, datetime

from . import state_store
from .sources import vaccination, outbreaks, variants

_SOURCES = ("vaccinations", "outbreaks", "variants")


def _run_vaccinations(mode_since: str | None) -> None:
    since_year = int(mode_since[:4]) if mode_since else None
    who_path = vaccination.fetch_who_immunization_coverage(since_year=since_year)
    print(f"wrote {who_path}")

    if mode_since is not None and mode_since > vaccination.OWID_LAST_KNOWN_UPDATE_DATE:
        print(
            f"skipped OWID COVID vaccinations pull: requested since={mode_since} is after "
            f"the dataset's last known update ({vaccination.OWID_LAST_KNOWN_UPDATE_DATE}); "
            "it appears discontinued, so there is nothing newer to fetch."
        )
    else:
        owid_path = vaccination.fetch_owid_covid_vaccinations(since_date=mode_since)
        print(f"wrote {owid_path}")


def _run_outbreaks(mode_since: str | None, max_pages: int) -> None:
    path = outbreaks.fetch_who_outbreak_news(since_date=mode_since, max_pages=max_pages)
    print(f"wrote {path}")


def _run_variants(mode_since: str | None) -> None:
    path = variants.fetch_cdc_variant_shares(since_date=mode_since)
    print(f"wrote {path}")


_RUNNERS = {
    "vaccinations": _run_vaccinations,
    "outbreaks": _run_outbreaks,
    "variants": _run_variants,
}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="MAPS web data scraper")
    parser.add_argument("source", choices=_SOURCES + ("all",))
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--backfill", action="store_true", help="pull full history, ignoring saved state")
    mode.add_argument("--update", action="store_true", help="pull only rows newer than the last run")
    mode.add_argument("--since", metavar="YYYY-MM-DD", help="pull only rows on/after this date, ignoring saved state")
    parser.add_argument("--max-pages", type=int, default=20, help="outbreaks only: max API pages to page through")
    args = parser.parse_args(argv)

    sources = _SOURCES if args.source == "all" else (args.source,)
    today = date.today().isoformat()

    for source in sources:
        if args.backfill:
            since = None
        elif args.since:
            since = args.since
        else:  # --update
            since = state_store.get_last_fetched(source)
            if since is None:
                print(f"[{source}] no saved state found; run with --backfill first. Skipping.", file=sys.stderr)
                continue

        print(f"[{source}] fetching since={since or 'beginning of history'}...")
        if source == "outbreaks":
            _RUNNERS[source](since, args.max_pages)
        else:
            _RUNNERS[source](since)

        if not args.since:
            state_store.set_last_fetched(source, today)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
