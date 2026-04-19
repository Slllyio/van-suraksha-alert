# Path C Pilot Finding — NDMA/MPFD Hindi Label Enrichment is DATA-BLOCKED

**Date:** 2026-04-19
**Pilot duration:** ~1 hour (vs. 3-day budget in memo)
**Verdict:** **Cannot proceed.** The data sources the memo assumed exist publicly don't.

## Background

The earlier memo `docs/research/low_hawkes_77_percent_gap_memo.md` recommended Path C
as the highest-value workstream against the 77% low-Hawkes new-outbreak gap. Plan:

1. Scrape NDMA daily Situation Reports (PDFs) for village-level fire mentions
2. Scrape MPFD Vanagni daily Hindi bulletins
3. Hindi NER + Nominatim geocoding
4. Treat geocoded village fires as PU-positive labels not in FIRMS DBSCAN
5. Retrain v17 (→ v19) with weighted news-confirmed positives

Expected uplift: +5–12 pp R@top-5% (per Dolatabadi 2024 IJWF on Australian fires).

## What the probe found

### NDMA SitRep daily archive — **not publicly indexed**

Searches against `site:ndma.gov.in` and `site:nidm.gov.in` for daily situation
reports surfaced only:

- `FOREST_FIRE_REPORT_Oct%2024.pdf` — workshop summary, not a daily SitRep
- `BestPracticesForestFire_final.pdf` — global best-practices policy doc
- `IAF_Praveen_Kumar.pdf` — IAF response speech transcript
- `Forest_Fire_Proceedings.pdf` — proceedings of a closed conference
- `Annual_Report_2024-25_English.pdf` — yearly summary
- `Report_10May2023akg.pdf` — NIDM brainstorming workshop

NDMA's operational fire alerts go through the **Sachet portal**
(`sachet.ndma.gov.in`), which is a real-time mobile-alert dispatch system with
**no publicly-accessible historical archive**.

### MPFD Vanagni Hindi bulletins — **not publicly indexed**

Searches against `site:mpforest.gov.in` and `site:mp.gov.in` for daily fire
bulletins (Hindi वनाग्नि or English "Vanagni") surfaced only:

- `FireCompendium.pdf` — Madhya Pradesh forest fire compendium 2016-2022
- `Initiative.pdf` — m-Mantra technology initiatives
- `Madhya Pradesh Forest Management.pdf` — training module
- Various organisation-structure and tender pages

**No daily Vanagni PDF archive** is reachable from the public web.

### FSI VanAgni geo-portal — only FIRMS data

`fsiforestfire.gov.in` exposes:

- Archived NRT data — same FIRMS hotspots we ingest from FIRMS direct
- Archived LFF (Large Forest Fire) data — derived from same source
- Reports & publications — annual aggregations, not daily

**No additional village-level reporting** beyond what's in FIRMS.

### MP Fire Compendium (downloaded + inspected)

Structured per-circle × per-year aggregates, 7 years (2016-2022):

- Monthly + weekly fire-point time-series plots
- Table: top divisions by fire points
- Table: top ranges by fire points
- Table: top beats by name (e.g. TALLABODI 1 BEAT, CHOURIYA BEAT) with annual
  fire counts and division attribution

**Crucially: every fire-point count is computed from the same FIRMS MODIS+VIIRS
detections we already use.** The compendium is a packaged aggregation, not a
new label source. It cannot break the VIIRS ceiling because it *is* VIIRS data.

## Why this happened

The memo's data assumption was based on:

- Reasonable inference that a state forest department running a fire-alert
  programme would publish daily bulletins
- One published article mentioning Vanagni bulletins
- The NDMA Reports landing page

In reality:

1. MPFD Vanagni is an **internal SMS/WhatsApp dissemination programme**, not
   a public PDF archive
2. NDMA SitReps for forest fires are likely **internal control-room documents**
   that are not posted to the public web
3. The publicly-published artefacts (annual compendium, policy docs) are
   strict subsets of FIRMS data we already ingest

This pattern — "the data we want is internal, not public" — is the same one
that killed the GDELT pilot earlier (`memory/feedback_gdelt_district_centroid_geocoding.md`).
The 3-day pilot budget in the memo turned out to be 1 hour because the failure
mode was upstream (data doesn't exist as scrapable resource), not downstream
(scraper would have worked).

## Saved time

Would have spent: 10-14 days building scraper + Hindi NER + retraining v19.
Spent: ~1 hour confirming the data isn't there.

## Pivots that ARE feasible (in order of preference)

### Pivot A — Two-model retry with NEW behavioural features (Path B from memo)

The previous two-model attempt (commit `d134e18`) failed because the origination
Model B trained on the same feature set as v17 minus Hawkes — naturally
weather-dominated, naturally too smooth at 2km to discriminate adjacent cells.

A second attempt would need *genuinely new* features:

- Real (not synthetic) AgMarkNet NTFP prices for tendu + mahua
- Census-2011 habitation-polygon proximity (cell-to-fringe in metres)
- Festival-adjacency anchored to actual tribal festival dates (we have Holi,
  Akshaya, Bhagoria; need to verify dates carry signal)
- Soil moisture features (just shipped via `data_lake/fire_weather/soil_daily.parquet`)

Effort: 3–5 days. Realistic uplift: +2–4 pp R@5%. Already partly attempted,
new attempt requires NEW features, not the same set.

### Pivot B — Hindi regional newspaper scraping (Dainik Bhaskar / Naidunia / Patrika MP)

Dainik Bhaskar's MP edition runs daily Hindi articles on forest fires that
DO mention villages (e.g. "ग्राम कैलासपुरी के पास जंगल में आग"). Approach:

1. Scrape MP-edition headlines + leads via RSS or Google News
2. Hindi NER (spaCy/Stanza/IndicBERT) for village name extraction
3. Nominatim geocoding with MP bbox filter
4. PU-weighted retraining

Effort: 12–20 days. Higher technical bar than the original Path C plan
(anti-scraping defences, paywalls, OCR for image-heavy news articles, Hindi
NER quality).

### Pivot C — Accept v17 as ceiling, focus on operations

We already shipped:

- Operational alert decorator (trust tiers, budget caps, calendar hints)
- Per-fire validation with spatial + temporal offset analysis
- Per-Hawkes-regime patrol radius
- 4-tool diagnostic stack (StatsForecast + drift + matrix profile + change-point)
- Probability calibration (14× Brier improvement)
- Soil features ingest (for future v18)
- Field-response feedback loop

This is genuinely operationally complete. R@top-5%=47.41% with calibrated
probabilities + per-division precision cones is field-deployable.

## Recommendation

**Do NOT pursue Path C as memo'd.** Data is not publicly available.

**Default: Pivot A** (two-model retry with new features). Builds on already-existing
behavioural-feature scripts. Three of the four needed features either exist
(soil moisture, festival calendar) or can be built quickly (census proximity).

Reserve Pivot B (Hindi news scraping) only if Pivot A delivers <2 pp uplift
and we still want to push past v17.

## Sources of probe evidence

- [NDMA Reports & Studies index](https://ndma.gov.in/Resources/Reports-Studies)
- [Sachet portal (real-time alerts, no archive)](https://sachet.ndma.gov.in/)
- [MPFD homepage](https://mpforest.gov.in/)
- [MPFD Fire Compendium 2016-2022](https://mpforest.gov.in/publicdomain/atlas/FireCompendium.pdf)
- [FSI Forest Fire Alerts Dashboard](https://fsiforestfire.gov.in/)
- [FSI Fire Point Search](https://fsiforestfire.gov.in/FirePointSearch/Search)
- [Drishti IAS forest-fire summary citing FSI Vanagni programme](https://www.drishtiias.com/daily-updates/daily-news-analysis/forest-fires-9)
