#!/usr/bin/env python3
"""
csv_merge.py — Merge-on-write CSV helper shared by the source fetchers.

An `--update` run only fetches rows newer than the last watermark, so
writing that alone would clobber all the older history a prior --backfill
already wrote. merge_write() instead folds new rows into whatever's already
on disk (new rows win on a matching key), and reports back the latest date
actually present in the merged result — which the caller should use as the
next watermark, NOT "the date this job happened to run." A source that
publishes monthly and gets updated today should have its watermark be its
latest data month, not today, or the next update run will ask for data
newer than has been published yet and get an empty response back.
"""
from __future__ import annotations

import csv
from pathlib import Path
from typing import Callable, Dict, List, Optional, Sequence


def merge_write(
    path: Path,
    new_rows: List[Dict[str, str]],
    key_fields: Sequence[str],
    leading_fields: Sequence[str],
    date_field: str = "Date",
    column_sort_key: Optional[Callable[[str], object]] = None,
) -> Optional[str]:
    """
    Merge new_rows into the CSV at `path`, keyed by `key_fields` (new rows
    replace existing ones with the same key; everything else is kept).
    `leading_fields` are always written first, in that fixed order; any
    remaining columns (e.g. dynamically-appearing variant names) are unioned
    across old + new data and sorted (alphabetically, or by
    `column_sort_key` if given).

    Returns the max value of `date_field` across the merged result, or None
    if there are no rows at all — the caller should use this as the next
    fetch watermark instead of the current date.
    """
    existing: Dict[tuple, dict] = {}
    if path.exists():
        with path.open(newline="") as f:
            for row in csv.DictReader(f):
                existing[tuple(row.get(k, "") for k in key_fields)] = row

    for row in new_rows:
        existing[tuple(row.get(k, "") for k in key_fields)] = row

    merged = list(existing.values())
    merged.sort(key=lambda r: tuple(r.get(k, "") for k in key_fields))

    extra_fields = set()
    for row in merged:
        extra_fields.update(row.keys())
    extra_fields.difference_update(leading_fields)
    extra_sorted = sorted(extra_fields, key=column_sort_key)
    fieldnames = list(leading_fields) + extra_sorted

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames, restval="")
        w.writeheader()
        for row in merged:
            w.writerow({k: row.get(k, "") for k in fieldnames})

    dates = [r.get(date_field, "") for r in merged if r.get(date_field)]
    return max(dates) if dates else None
