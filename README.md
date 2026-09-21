# WebScraper

Data-collection layer for **MAPS** (Multi-Agent Pathogen Simulation). Pulls
vaccination, outbreak, and variant-surveillance data from a small set of
curated, credible sources and writes it into `output/` as CSVs that
[`build_maps_initial_conditions_with_history_full.py`](build_maps_initial_conditions_with_history_full.py)
and [`edit_namelist.py`](edit_namelist.py) can consume. The Fortran
simulation core lives in a separate repo and only ever reads the
NetCDF/namelist files those two scripts produce — this scraper never talks
to Fortran directly.

## Usage

```
python -m webscraper.cli <source> --backfill      # full history
python -m webscraper.cli <source> --update        # only new data since last run
python -m webscraper.cli <source> --since 2026-01-01
python -m webscraper.cli all --update             # run every fetch source
python -m webscraper.cli impute                   # fill vaccination gaps with peer-country data
```

Fetch sources: `vaccinations`, `outbreaks`, `variants`. `impute` is a
separate, non-network step (see Imputation below) and takes no
`--backfill`/`--update`/`--since` flag.

`--update` reads/writes `output/.fetch_state.json` to track the last
successful pull per source, so a cron/launchd job can call `--update` on a
schedule without re-downloading full history each time. Run `--backfill`
(or `--since`) once per source before the first `--update`.

## Sources

| Source | Module | Provider | Live? | Notes |
|---|---|---|---|---|
| Vaccination (routine) | `webscraper/sources/vaccination.py` → `fetch_who_immunization_coverage` | WHO GHO OData API (WUENIC) | Yes, annual | DTP3, measles, BCG, HepB3, polio coverage by country |
| Vaccination (COVID-19) | `webscraper/sources/vaccination.py` → `fetch_owid_covid_vaccinations` | Our World in Data | **No — discontinued 2024-08-14** | Backfill-only; `--update` will skip it once `--since` is past that date |
| Outbreak alerts | `webscraper/sources/outbreaks.py` | WHO Disease Outbreak News API | Yes | Event data, not a time series — see Limitations |
| Variant shares (US) | `webscraper/sources/variants.py` | CDC SARS-CoV-2 Variant Proportions | Yes, ~monthly | US-only; percentage share, not case counts |

`webscraper/country_ids.py` is the shared ISO3 registry (from WHO's own
COUNTRY dimension, cached in `webscraper/data/who_countries.json`) used to
resolve country names/aliases across all three sources and to flag ones that
can't be resolved confidently rather than guessing.

## Imputation (peer-country fallback for missing vaccination data)

`python -m webscraper.cli impute` reads `who_immunization_coverage.csv` and
`owid_covid_vaccinations.csv` and writes `*_filled.csv` siblings with gaps
filled from a "peer" country of similar standing — e.g. North Korea has no
COVID vaccination data in OWID at all, so its entire series is copied from
the closest-matching country that does report. The raw fetched files are
never modified; the filled files are a separate, rebuildable artifact.

**Peer-matching methodology** (`webscraper/country_classification.py`,
built from the World Bank Country and Lending Groups API): a peer is chosen
by relaxing match criteria in tiers until a candidate with real data is
found — (1) same World Bank region + income level + population bracket,
(2) same region + income level, (3) same income level only, (4) closest
population as a last resort. This is a coarse, defensible proxy for
"similar standing," not a rigorous similarity model — North Korea, for
example, has no same-region same-income peer with data and falls back to
Syria on income level alone.

**Every filled value is flagged, never blended in silently**: each row gets
`Is_Imputed` (Yes/No), `Proxy_Source_Country` (the ISO3 it was copied from,
blank for real rows), and `Match_Tier` (how strong the match was). This
matters because it feeds a scientific model — the model (and anyone
auditing it) needs to be able to tell fabricated inputs from observed ones,
and to exclude proxy rows later if needed.

**Scope:** vaccination files only. Variant shares are US-only (no
cross-country gaps to fill), and outbreak alerts are discrete events — a
missing outbreak just means none was reported, not a data gap, so
fabricating one would be actively wrong rather than a reasonable estimate.
Within the vaccination files, imputation only fires for a country with **no
real data anywhere** in that dataset — a country that reports on a sparse
or irregular cadence (normal for OWID) is left exactly as fetched; only a
whole-country absence gets a proxy series.

A handful of WHO's own registry entries aren't real, currently-reportable
countries (`ME1` — the former Serbia and Montenegro union, `PRS` —
"Pristina," a city, `SDN736` — pre-2011 Sudan) and are excluded from
imputation entirely rather than assigned a nonsensical peer. A few current
French overseas territories (Guadeloupe, Martinique, Réunion, French
Guiana, Saint Pierre and Miquelon, Mayotte) aren't separately classified by
the World Bank and are attributed to France's classification for matching
purposes, since that's a factual description of their economic/legal
system, not a similarity judgment call.

## Outbreak severity (who_outbreak_news.csv)

Each outbreak report gets a best-effort `Severity` tier — `PHEIC` >
`EPIDEMIC` > `OUTBREAK` > `CLUSTER` > `WATCH` — plus `Severity_Basis`
showing the exact phrase (or structural signal) that drove the call.
WHO's API exposes no structured severity field, only free-text narrative
(Overview/Assessment/Epidemiology/Response), so `webscraper/severity.py`
runs a keyword heuristic over that text — e.g. "Public Health Emergency of
International Concern" → `PHEIC`, "sustained transmission" → `EPIDEMIC`,
"cluster of cases" → `OUTBREAK`, a single/isolated case → `WATCH`, and no
escalation language at all defaults to `WATCH`. This is a **rough triage
signal, not a validated epidemiological severity score** — treat it the
same way as the free-text country parsing: useful for sorting/prioritizing,
but check `Severity_Basis` before trusting an individual row.

## Known limitations

- **No global country/population grid yet.** `country_ids.py` assigns each
  ISO3 code a sequential placeholder `grid_id` — it is *not* tied to any real
  spatial raster. `build_maps_initial_conditions_with_history_full.py` still
  only has `STATE_ABBR_TO_FIPS` for US states; a real global population grid
  (e.g. GPWv4/WorldPop) and an `ISO3_TO_GRID_ID` mapping aligned to it are
  needed before scraped country-level data can be placed spatially.
- **No global case-count source.** Most countries stopped publishing
  national COVID-19 case counts by 2026; `variants.py` is US-only because
  that's the only still-updating, credible source found. Don't backfill a
  fake global case-count series from this.
- **Outbreak data is event-based, not a time series.** WHO's API has no
  structured country/disease fields — only a free-text title parsed
  best-effort as `"<Disease> - <Country>"`. Rows with an unresolved
  `Country_ISO3` need a human to check `Country_raw` before use. This data
  doesn't fit the `Date,Region,Total_Infections,<VARIANT>` CSV shape; it's
  meant to feed `edit_namelist.py`'s Tier-1 per-member OVERRIDE mechanism as
  a discrete event adjustment, not a continuous grid.
- **OWID COVID vaccination data is frozen at 2024-08-14.** Treat it as
  historical backfill only, not a current signal.

## Manual / ad-hoc extraction

For one-off sources that don't have a clean API (a PDF situation report, an
Excel export, a news article), use the LLM extraction prompt in `PROMPT.md`
manually — paste it into an LLM followed by the source content, and drop the
resulting CSV(s) into `output/` by hand.
