# Soft burn dates per burned cell-season (`soft_dates.csv`)

Built 15 Oct 2026 for the cleaner fire-labels thread. Background and method tests: `../../daily_scar_dating.md` (§A2, §A4, §A5). Code: `../../code/daily_dating/` (`assemble.py` is the entry point).

## File

There is one row per burned cell-season: **20,007 rows**. Each row is a cell and season with at least one `burned==1` window in `research/ratapani-burn-labels/burn_windows.csv`.

Where a cell-season has more than one burned window (7,121 cell-seasons), the row is for the **first** window, the one with the earliest `window_start`. `n_windows` gives the number of windows.

| Column | Meaning |
|---|---|
| `cell_id`, `season` | as in `burn_windows.csv` |
| `date_lo`, `date_hi` | narrowest interval found, inclusive dates; the burn is on one of these days |
| `method` | `s3`, `l7`, `mcd64`, or `window` (the original interval was kept) |
| `burned_frac` | for `s3` only: burned fraction of the 300 m Sentinel-3 bin used, from the 20 m scars of this window |
| `confidence` | calibrated hit rate for that case class (see below) |
| `orig_lo`, `orig_hi` | original `window_start`, `window_end` |
| `n_windows`, `burned_ha` | extra columns: number of burned windows in this cell-season; ha of this window |

Inclusive-date convention:
- The original window runs from the S2 or Landsat look on `orig_lo` (about 10:40 IST, still unburned) to the look on `orig_hi` (burned).
- The burn day can therefore be `orig_lo` itself (afternoon) up to `orig_hi`. Width = `date_hi − date_lo` days.

## Methods, in order of use

1. **`s3`: Sentinel-3 SYN L2 daily 300 m.**
   - Source: Planetary Computer, keyless; Dec 10 to Jun 20 of seasons 2019, 2020, 2021, 2022, 2023 and 2026.
   - Signal: relative NBR = (Oa17 − S6N)/(Oa17 + S6N) minus unburned bins within about 3.3 km.
   - For each cell window, use the 300 m bin holding most of its scar pixels. Fit a one-step change between consecutive S3 looks inside the window, with 12 days of looks before and after.
   - Kept when SNR > 2 and the class hit rate is ≥ 0.75.
2. **`l7`: Landsat 7 ETM+** (Planetary Computer, 2017-2023).
   - For each L7 look inside the window: is the scar's scar-minus-ring NBR already lower than on an L7 look up to 48 days before the window, by more than half the scar's 20 m NBR-anomaly drop?
   - The first look that shows the scar ends the interval. The last look that does not show it starts the interval.
   - Only decisions with a pre-window L7 reference are kept. Decisions made against a post-window reference scored 0.58 and were dropped.
3. **`mcd64`: MCD64A1 C6.1** (Planetary Computer).
   - Burn date ± its uncertainty, clipped to the window, used only where neither of the above narrows the window and the MCD64 date falls inside the window.
4. **`window`:** otherwise, the original interval.

Where both `s3` and `l7` narrow a window, the narrower one is used. A tie goes to the higher confidence.

## Confidence (calibration against VIIRS)

Truth is the first VIIRS 375 m detection (S-NPP, NOAA-20/21, from `fire-alert-scars/alert_scar_lookup.csv`) in the same 500 m cell inside the original window. A hit means the VIIRS IST date falls in `[date_lo, date_hi]`. Rates are pooled over seasons.

**S3 hit rate by SNR class and burned fraction of the bin** (n)

| SNR | burned fraction < 0.1 | 0.1-0.3 | ≥ 0.3 |
|---|---|---|---|
| > 3 | 0.90 (100) | 0.93 (341) | 0.94 (643) |
| 2-3 | 0.77 (39) | 0.83 (198) | 0.88 (182) |
| ≤ 2 (not used) | 0.54 (96) | 0.64 (322) | 0.75 (205) |

**Other confidences:**
- `l7` = 0.80 (n = 964).
- `mcd64` = 0.89 (n = 875).
- `window` = 0.89: the share of VIIRS first detections within ±10 days of the window that fall inside it, in this inclusive-date convention.

**VIIRS check of the chosen interval, narrowed rows only: hit rate (uniform-prior baseline)**

| Season | s3 | l7 | mcd64 | all narrowed |
|---|---|---|---|---|
| 2017 | not run | 0.91 (0.55), n = 287 | 0.91, n = 11 | 0.91 |
| 2018 | not run | 0.80 (0.55), n = 166 | 0.88, n = 40 | 0.82 |
| 2019 | 0.93 (0.45), n = 230 | 0.72, n = 127 | 0.91, n = 94 | 0.87 |
| 2020 | 0.91 (0.43), n = 212 | 0.64, n = 33 | none | 0.87 |
| 2021 | 0.89 (0.43), n = 401 | 0.70, n = 63 | 0.83, n = 23 | 0.86 |
| 2022 | 0.94 (0.47), n = 339 | 0.65, n = 31 | 0.89, n = 142 | 0.91 |
| 2023 | 0.88 (0.42), n = 177 | n = 5 | n = 3 | 0.88 |
| 2024 | not done | none | n = 6 | n = 6 |
| 2025 | not done | none | 0.88, n = 80 | 0.88 |
| 2026 | 0.92 (0.56), n = 65 | none | 0.83, n = 72 | 0.88 |

The "uniform" baseline is the hit rate expected if the narrowed interval were placed at random inside the window.

## Results

| Method | Rows | Share | Median width, new → old (days) | Mean width, new → old |
|---|---|---|---|---|
| `s3` | 3,999 | 20.0% | 2 → 5 | 1.9 → 5.7 |
| `l7` | 3,653 | 18.3% | 6 → 10 | 5.6 → 11.1 |
| `mcd64` | 892 | 4.5% | 2 → 5 | 2.3 → 5.5 |
| `window` | 11,465 | 57.3% | 5 | - |

Mean width over all rows falls from 6.5 to 4.6 days.

Share narrowed by season:

| Season | Narrowed | Mean width, old → new (days) |
|---|---|---|
| 2017 | 75% | 13.1 → 8.0 |
| 2018 | 41% | 7.5 → 5.3 |
| 2019 | 51% | 5.6 → 3.8 |
| 2020 | 67% | 5.2 → 2.8 |
| 2021 | 69% | 6.0 → 3.2 |
| 2022 | 54% | 5.5 → 3.6 |
| 2023 | 43% | 5.9 → 3.9 |
| 2024 | 1% | 6.2 → 6.2 |
| 2025 | 9% | 5.1 → 4.9 |
| 2026 | 16% | 4.4 → 4.0 |

## Not done

- **S3 for 2024 and 2025.** Planetary Computer holds only 26 and 32 SYN scenes in Feb-May of those years, against 108-134 in other years. The full archive needs a Copernicus Data Space account. Rows for 2024-2025 use MCD64A1 or the original window.
- **2026 S3 is thin.** 67 usable looks; only 1,220 of 3,740 cell-windows could be tested.
- **2019 S3 is partial.** 112 looks; 3,149 of 5,742 cell-windows tested.
- **No Landsat 7 after 2023.** Imaging was suspended in Jan 2024.

## Caveats

- **The truth set is VIIRS-detected fires.** These are larger and hotter than typical scars, so true hit rates for the 62% of scars VIIRS never saw are probably lower. The SNR and burned-fraction classes are the best guide: bins under 10% burned score 0.77-0.90 when kept.
- **Confidence is a class average, not a per-row probability.** Seasons are pooled, so there is no hold-out by season.
- **Only the first window per cell-season is dated.** Second and later burns in the same cell keep no soft date here.
- **The S3 bin is 300 m (9 ha).** When a bin also holds scar pixels of a different window, the step may reflect the other burn. The `dominance` column in `s3soft_<year>.csv` (scratch) records how mixed each bin is; it was not used as a filter.
- **Landsat 7 2022-2023** comes from a drifted, lowered orbit (before 08:45 local). Those years have few L7 rows (124 and 153), with lower hit rates.
- **L7 widths are longer** (median 6 days), because most L7 rows are in 2017-2018, when windows are 10-16 days.
- **MCD64A1 confirms only where it agrees with the window.** It covers 12% of burned windows, and its dates outside the window were ignored.
