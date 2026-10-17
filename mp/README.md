# MP fire outlook — all 87 forest divisions (research)

## Headline: every MP division (`scripts/mp_all_eval.py`, `results/all_divisions.csv`)
Best design applied to all 87 divisions (~1.05 M cells of 500 m): each division's own LightGBM model on
3-satellite VIIRS labels/fire history (S-NPP + NOAA-20 + NOAA-21) plus the 10-day HLS dryness; train 2019–2021,
test 2022–2024 (246,790 fire cell-days, scored against fires seen by any of the three satellites).
Top 10% of each division's test cell-days flagged, a fire counts if a flagged cell is within 1 cell:

| | |
|---|---|
| MP-wide fires caught (fire-weighted) | **80.5%** |
| Median division | 80.8% |
| Brand-new fires (no fire within 5 km in 7 days) | 46.8% |
| Divisions at 80–90% / 90%+ | 45 / 3 |
| Divisions at 70–80% | 29 |
| Divisions below 70% | 10 (mostly small, low-fire divisions: Shajapur 26 test fires, Rajgarh 54, Mandsaur 275) |
| Best | Barwani 94.3%, North Balaghat 92.7%, Singrauli 91.5% |

Recall rises with the amount of local fire history (correlation with log fire count 0.39), so the weakest divisions
are candidates for borrowing from neighbouring divisions. `scripts/mp_repair.py` finds and removes corrupted
Earth Engine CSVs left by interrupted runs (17 files in 13 divisions were regenerated).

## Officer-style scoring, neighbour borrowing, seasonal rules (`scripts/mp_officer_eval.py`, `scripts/mp_seasonal.py`)
All 87 divisions, train 2019–2021, test 2022–2024, top 10% of each division's test cell-days flagged (more on bad days).
- **Each fire once**: fire detections linked across touching cells and consecutive days form one fire.
  STRICT = caught only if a first-day cell had a flag within 1 cell on the issues of day −1 or −2;
  LOOSE = any part of the fire was flagged 1–2 days before it burned. Fires starting on a season's first 2 days are skipped.
- **By beat** (cells mapped to beats from `data/aoi/mp_beats_wgs84.geojson`): a beat episode is a run of burning days;
  STRICT = the beat had ≥1 flagged cell on day −1/−2 before its first day; LOOSE = any day of it was preceded by a flag.
- **Neighbour borrowing**: own data (weight 3) + divisions within 5 km (weight 1); used for "weak" divisions
  (< 1000 training fire cell-days, rule fixed in advance).
- **Seasonal rules ("with")**: targets only 15 Feb–31 May; fires 1 Oct–14 Feb are an "early burn" input
  (cell / 3×3 / 7×7 counts), never targets; on 15–28 Feb likely control burns are dropped from targets
  (day-only same-day cluster within 1 km, ≤ 2 points, max FRP ≤ 5 MW, nothing within 1 km from day −2 to +3):
  4,950 clusters / 5,708 points over 2019–2024.

Recommended model (own; borrow if weak), MP-wide:

| Rules | Labels | Fires caught strict / loose | Beat episodes strict / loose | Ground flagged / flagged-or-next | Beats flagged per day | Flagged beats per range per day |
|---|---|---|---|---|---|---|
| without | 3 satellites | 77.0% / 77.9% | 84.1% / 85.0% | 10% / 19.5% | 28.3% | 2.8 |
| without | S-NPP + NOAA-20 | 77.9% / 78.7% | 84.9% / 85.7% | 10% / 19.5% | 28.3% | 2.8 |
| **with** | **3 satellites** | **73.2% / 74.6%** | **81.6% / 83.0%** | **10% / 20.3%** | **30.6%** | **3.0** |
| with | S-NPP + NOAA-20 | 74.2% / 75.5% | 82.3% / 83.6% | 10% / 20.4% | 30.6% | 3.0 |

Neighbour borrowing for weak divisions: +0.4 to +1.5 pts (fires, strict). Per-division: `results/officer/per_division_recommended.csv`;
full table `results/officer/combined_summary.csv`.

# MP step 1 — does the Ratapani model carry across Madhya Pradesh? (research)

Nine contrasting forest divisions on one shared 500 m grid (EPSG:32643, X0 399000, Y1 2996000, 1829 columns;
`mp_cell = row * 1829 + col`, aligned with the Ratapani grid and the all-MP HLS dryness pull):

| Division | Cells | Character |
|---|---|---|
| Obedullahganj | 7,677 | contains Ratapani; central dry teak |
| Guna | 9,921 | north, dry deciduous |
| Shivpuri | 13,798 | north, driest |
| Khandwa | 11,348 | south-west teak |
| Satpura_TR | 8,286 | central highlands |
| Kanha_Tiger_Reserve | 8,474 | east, moist sal |
| Dindori | 10,129 | east, tribal sal |
| South_Panna | 8,059 | Bundelkhand dry |
| Singrauli | 10,621 | far east, mining belt |

Pipeline (`scripts/`):
1. `mp_grids.py` — division grids from `data/aoi/mp_divisions_dissolved.geojson` (cells with >= 25% inside), saved in `grids/`.
2. `mp_ee.py <division_dir> static alphaearth era5 modis lst` — the Ratapani Earth Engine pulls per division.
3. `mp_proximity.py <division_dir>` — OSM roads / tracks / villages, division boundary, cropland edge.
4. `mp_features.py <division_dir>` — Ratapani v2 features + leaf-fall, one parquet per season (2014–2024, Jan–May);
   labels from the MP-wide VIIRS S-NPP archive (`data_lake/fire_detections/firms_mp_viirs/firms_mp_consolidated.parquet`),
   placed on the shared grid across each division's bounding box so neighbour features see fires just outside it.
5. `mp_transfer.py` — train 2014–2021, test 2022–2024 per division: (A) trained on the other 8 divisions,
   (B) trained on the division itself, (C) trained on all 9 pooled.

6. `mp_pooling.py` — follow-up: (D) pooled + division id, (E) pooled with the division's own rows weighted 5x.

Data (Earth Engine CSVs, feature tables ~1 GB per division) stay local in `E:\FIRE\mp\<Division>\`.

## Results (train 2014–2021, test 2022–2024; top 10% of cells flagged, 3×3 tolerance)

| Model | Fires caught | Brand-new fires | Worst / best division |
|---|---|---|---|
| A trained on the other 8 divisions only | 77.3% | 44.2% | 64.5 / 86.2% |
| **B trained on the division itself** | **83.3%** | **55.1%** | 72.9 / 93.1% |
| C all 9 pooled | 81.4% | 48.3% | 70.6 / 91.2% |
| D pooled + division id | 82.2% | 50.5% | 72.7 / 92.2% |
| E pooled, own rows x5 | 82.4% | 50.6% | 71.6 / 92.0% |

- The approach transfers: a model that never saw a division still catches ~77% of its fires.
- Local history is worth ~6 pts (up to +16 in Singrauli, +12 in Kanha); no pooling variant beats the division's own model.
- Practical design: a per-division model wherever fire history exists, the other-divisions model as a cold start for new areas.

Per-division numbers: `results/transfer_by_division.csv`, `results/pooling_by_division.csv`.

### Step 1c — 10-day HLS fuel dryness (`scripts/mp_dryness.py`)
Joins the separate all-MP HLS pull (`E:\FIRE\mp\tiles`, NDVI/NDMI/NBR every 10 days on the same grid, ~98% coverage)
as-of each issue day, plus 10- and 30-day changes. Division's own model, train 2017–2021, test 2022–2024:
base 82.8% → **83.6%** fires caught, brand-new 55.4% → 56.5%; better in 6 of 9 divisions (largest: South Panna +2.2,
Obedullahganj +1.9). `results/dryness_by_division.csv`.

### Step 1d — the same dryness from the packaged files (`scripts/mp_dryness_npz.py`)
`E:\FIRE\mp\push\mp_dry_<season>.npz` (cells, steps, X[step, cell, ndvi/ndmi/nbr/clear]) holds values identical to the
tiles (12,000 / 12,000 checked) for beat cells only; -32768 = no data, values outside ±10000 are overflow and masked.
Result: base 82.8% → **83.7%** fires caught, brand-new 55.4% → 56.7%, weakest division 71.4% → 74.4%.
This is now the default dryness input for the division models.

## Step 2 — three VIIRS satellites (`scripts/firms_noaa_pull.py`, `scripts/mp_multisat.py`)
NOAA-20 (2018-04+) and NOAA-21 (2023-03+) standard-processing detections over MP from the FIRMS area API
(key read from the `FIRMS_MAP_KEY` environment variable, never stored). `mp_features.py` now takes
`MP_FIRE_SOURCES` / `MP_FEATS_DIR` / `MP_YEARS`; 3-satellite tables are in `<division>/feats_multi/` (seasons 2019–2024).
Division's own model + dryness, train 2019–2021, test 2022–2024:

| Labels and fire history | vs S-NPP fires | vs all-satellite fires |
|---|---|---|
| S-NPP only | 82.8% | 80.4% |
| **S-NPP + NOAA-20 + NOAA-21** | **84.6%** | **82.4%** |

S-NPP alone records about half of the fire cell-days the three satellites see (23,913 vs 46,881 in the test years).
Brand-new-fire recall is not comparable between rows: with more fires visible fewer cells count as "brand-new".
`results/multisat_by_division.csv`.
