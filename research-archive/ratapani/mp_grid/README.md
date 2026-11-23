# All-MP 500 m grid and 10-day fuel dryness (Oct 15)

**Grid.** EPSG:32643, X0 399000, Y1 2996000, 1829 x 1332 cells of 500 m, cell = row * 1829 + col. It is aligned with the Ratapani grid (Ratapani cell x0/y0 map exactly). Akkshay's PC session uses the same grid for its 9 division feature tables (E:\FIRE\mp\<Division>\).
- `mp_cells.parquet`: 373,681 cells with at least 50% beat cover. The beat is chosen by majority area at 50 m, from `beats/mp_beats.geojson` (8,844 of 8,973 beats hold a cell). Within Ratapani, 99.4% of cells get the same beat as `beats/cell_beat.csv`.
- `mp_grid.json`: grid constants and the 105 tiles of 128 x 128 cells that hold beat cells.

**Dryness** (`dryness/mp_dry_{season}.npz`, seasons 2017-2026). Each file holds:
- `cells`: 373,672 cells. The PC rasterised a slightly different copy of the beats file, so join on `cell`.
- `steps`: Jan 2 to Jun 21, every 10 days.
- `X`: shape (step, cell, 4), int16. The four values are NDVI, NDMI and NBR x 10000, plus clear %; -9999 means no clear look.

How each value is made:
- Source is HLS S30 + L30. Pixels with Fmask cloud, adjacent, shadow or snow are dropped.
- Indices are computed per look, then the median over the 15 days before the step is taken.
- Values are read at 120 m and averaged over the 500 m cell. Reading at 30 m gives nearly the same values (within 1-2% on a test tile) but is about 18 times slower.

Missing cell-steps: 5% in 2017, about 1% or less in later seasons. A few values fall outside [-10000, 10000], under 0.05% of cell-steps. These include -32768 and other overflows from negative HLS reflectance in dark or water pixels. Treat them as missing, the same as -9999.

**Check against Ratapani's per-look cell values** (`s2_cells.parquet`, mean of clear looks in the same 15 days; 472k cell-steps):

| | Correlation | Correlation within each step (spatial) | Mean difference |
|---|---|---|---|
| NDVI | 0.90 | 0.92 | +0.04 |
| NDMI | 0.97 | 0.94 | -0.01 |
| NBR | 0.98 | 0.95 | 0.00 |

Script: pipeline container `scr/mp_dry_check.py`.

Pulled on Akkshay's PC (E:\FIRE\mp\, mp_dry_pull.py and mp_dry_pack.py, copied here). Pushed via the vanagni data branch `data/mp-dryness-2026-10-15`.
