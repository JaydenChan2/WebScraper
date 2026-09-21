#!/usr/bin/env python3
"""
http.py — Minimal HTTP GET helpers shared by the source fetchers.

Uses only the standard library so the scraper has no install step beyond
Python itself (the format-specific extras like pypdf/openpyxl mentioned in
PROMPT.md are separate and only needed for manual, ad-hoc extraction).
"""
from __future__ import annotations

import csv
import io
import json
import time
import urllib.error
import urllib.request
from typing import List, Dict, Any

_USER_AGENT = "MAPS-WebScraper/1.0 (+https://github.com/; research use)"
_TIMEOUT_SECONDS = 30
_MAX_RETRIES = 3
_RETRY_BACKOFF_SECONDS = 2.0


def get_text(url: str) -> str:
    last_error: Exception = RuntimeError("unreachable")
    for attempt in range(_MAX_RETRIES):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
            with urllib.request.urlopen(req, timeout=_TIMEOUT_SECONDS) as resp:
                return resp.read().decode("utf-8")
        except (urllib.error.URLError, TimeoutError, ConnectionError) as exc:
            last_error = exc
            if attempt < _MAX_RETRIES - 1:
                time.sleep(_RETRY_BACKOFF_SECONDS * (attempt + 1))
    raise last_error


def get_json(url: str) -> Any:
    return json.loads(get_text(url))


def get_csv_rows(url: str) -> List[Dict[str, str]]:
    text = get_text(url)
    return list(csv.DictReader(io.StringIO(text)))
