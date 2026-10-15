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
