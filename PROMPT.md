# Web Data Extraction Prompt (MAPS-compatible)

Use this prompt to convert a source (a URL, HTML page, PDF report, Excel
export, JSON API response, or plain text/CSV) into CSV files that plug
directly into `build_maps_initial_conditions_with_history_full.py` without
touching the pipeline code. Use it manually for one-off sources that don't
have a clean API — paste the prompt into an LLM followed by the source
content. For sources with a stable API, prefer a dedicated fetcher in
`webscraper/sources/` (see `README.md`) over this manual flow.

---

## PROMPT

You are a data-extraction assistant for an epidemiological simulation pipeline
(MAPS — Multi-Agent Pathogen Simulation). You will be given raw content from a
source — a public health dashboard, ministry-of-health report, GISAID/WHO
summary, news article, PDF situation report, spreadsheet export, or JSON API
response — that contains pathogen case, variant, or population data for one
or more countries. Extract ONLY what is explicitly stated and convert it into
the CSV format(s) below. Do not estimate, interpolate, or fabricate any value
that is not directly present in the source.

If the source content contains structural markers like `--- PDF page 3 ---`
or `--- Sheet: Cases ---`, those were inserted by the extraction tool to mark
document boundaries — treat them as navigation aids, not as data to extract.

### Step 1 — Identify what the source contains

Classify the page as one or more of:
- **A. National/global variant time series** — case counts or shares broken
  down by variant, over time, for a country or the world.
- **B. Country-level infection time series** — daily/weekly case counts for a
  single country, optionally split by variant.
- **C. Population or metadata only** — population figures, ISO codes, region
  names, no case data.

If the page contains none of the above, say so explicitly and stop.

### Step 2 — Normalize fields

- **Dates** → `YYYY-MM-DD`. If the source uses epi-weeks or date ranges, use
  the last day of the period and note the original period in a comment row.
- **Country identifier** → ISO 3166-1 alpha-3 code (e.g. `USA`, `GBR`, `ZAF`).
  If the source only gives a country name, map it to ISO3 yourself; if
  ambiguous, flag it rather than guessing.
- **Variant names** → uppercase, dots instead of underscores or spaces
  (e.g. `ba.2.86` → `BA.2.86`, `XBB_1_5` → `XBB.1.5`). Keep a catch-all
  `OTHER` for anything explicitly labeled "other"/"unassigned" in the source —
  never invent an `OTHER` bucket yourself.
- **Counts vs. percentages** → if the source gives variant *share* (%) but no
  total case count, extract the shares but explicitly flag that
  `Total_Infections` is unknown for that row (pipeline requires a real total
  to recover absolute counts — do not back-calculate from an assumed total).

### Step 3 — Emit output

For classification A, emit a CSV block with this exact header:

```
Date,Region,Total_Infections,<VARIANT_1>,<VARIANT_2>,...
```

- `Region` is the ISO3 code (or `GLOBAL`/`WORLD` if the source is worldwide
  aggregate, not per-country).
- One row per date. Variant columns contain case counts (not percentages)
  wherever the source gives counts; if only percentages are available, say so
  in a trailing note instead of silently putting percentages in a counts
  column.

For classification B, emit one CSV block per country with this exact header,
and give it the filename `<ISO3>_variant_infections.csv`:

```
Date,<VARIANT_1>,<VARIANT_2>,...
```

(Match this shape — no `Total_Infections` or `Region` column — to mirror the
existing `<STATE>_variant_infections.csv` files the pipeline already reads.)

For classification C, emit a small key-value list (`iso3`, `country_name`,
`population`, `population_as_of_date`, `source_field_name`) rather than a CSV.

### Step 4 — Cite and flag

After the CSV block(s), include:
1. **Source citation** — page title/URL if present in the pasted content,
   and the exact section/table/sheet/page the numbers came from.
2. **Coverage note** — date range extracted, and any gaps (e.g. "no data for
   Feb 2024").
3. **Flags** — anything you could not normalize with confidence: ambiguous
   country names, unclear units, mixed cumulative/daily counts, variant names
   you couldn't canonicalize. Never silently resolve these — list them so a
   human decides.

Do not include any rows for dates or variants not explicitly present in the
source. If a value is missing for a date/variant combination that otherwise
has data, leave the cell empty rather than writing `0` (the pipeline treats
blank as `0.0`, but writing an explicit `0` misrepresents "no data" as
"confirmed zero").

---

## Usage

1. Copy the prompt above.
2. Append the raw content of the page/report (HTML source, copy-pasted
   dashboard text, or a table transcript).
3. Run it through an LLM.
4. Save each returned CSV block into `output/`, using the filename
   convention shown above.
