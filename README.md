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
python -m webscraper.cli all --update             # run every source
```

Sources: `vaccinations`, `outbreaks`, `variants`.

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
