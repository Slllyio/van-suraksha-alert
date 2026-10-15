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

Data (Earth Engine CSVs, feature tables ~1 GB per division) stay local in `E:\FIRE\mp\<Division>\`.
Results: `results/` (added when the transfer run finishes).
