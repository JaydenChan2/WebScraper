#!/usr/bin/env python3
"""
state_store.py — Tracks the last successful fetch per source so `--update`
runs can pull only new data instead of re-downloading full history.

One JSON file, one key per source name. Deliberately dumb (no locking, no
concurrent-writer support) since this is a single-operator scraper run from
cron/launchd, not a multi-worker service.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

_STATE_PATH = Path(__file__).parent.parent / "output" / ".fetch_state.json"


def get_last_fetched(source: str) -> Optional[str]:
    """Return the last recorded date string for `source`, or None if never run."""
    if not _STATE_PATH.exists():
        return None
    state = json.loads(_STATE_PATH.read_text())
    return state.get(source, {}).get("last_fetched_date")


def set_last_fetched(source: str, date_str: str) -> None:
    _STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    state = json.loads(_STATE_PATH.read_text()) if _STATE_PATH.exists() else {}
    state[source] = {"last_fetched_date": date_str}
    _STATE_PATH.write_text(json.dumps(state, indent=2, sort_keys=True))
