# Narrowing burn-scar dates below the 5-day optical gap, and sub-daily fire sources over central India (scouting round 9, topic "daily scar dating", 15 Oct 2026)

Scope: (1) sub-daily or extra fire sources over Ratapani not covered in earlier notes; (2) ways to cut the scar date window (median 5 days) using denser calendars, daily coarse reflectance and sub-pixel methods. Tested on our own labels where cheap.

Already covered elsewhere, not repeated: VIIRS S-NPP/NOAA-20/21, MODIS, SLSTR FRP (`slstr_frp_ratapani.md`), GK2A, Meteosat IODC (`geostationary_fire_timing.md`), FY-4A test (`fire_detection_sources.md` §4), Landsat/S2 active-fire rules (`fire_detection_sources.md` §8-9), OroraTech user guide and ECOSTRESS idea (§12), PlanetScope E&R access (`high_res_imagery.md` §2), Melchiorre persistence (`high_res_imagery.md` §10), MCD64/VNP64 user guides and dating recipe (`burn_dating_validation.md`).

Marks: **FULL** / **PARTIAL** / **ABSTRACT ONLY** for each source. [inference] = my reasoning, not a published or measured number.

Scripts: `/tmp/claude-0/-home-user/be9b8f54-cc26-52cb-bdbb-9c8008a24baf/scratchpad/r9code_dating/` (scratch only; copy to `fsi/scouting/code/` to keep). Data pulled: `/tmp/claude-0/-home-user/be9b8f54-cc26-52cb-bdbb-9c8008a24baf/scratchpad/r9data/`. Papers: `/tmp/claude-0/-home-user/be9b8f54-cc26-52cb-bdbb-9c8008a24baf/scratchpad/papers_r9_dating/`.

## Headline findings

1. **Daily Sentinel-3 reflectance dates our scars to about 1-2 days, and it works on our data.** Using free, keyless Sentinel-3 SYN L2 (300 m surface reflectance, about one look per day) from Planetary Computer, a simple step test inside each 20 m scar window picked the sub-interval that holds the VIIRS fire time **74-81% of the time, against 37% for a uniform prior** (2021: 571 VIIRS-dated 300 m bins; 2023: 292). The new interval is a median **1.0 day (2021) and 2.0 days (2023)**, against a 5-day window. For bins at least half burned it was right **88-90%** of the time. A drop with signal-to-noise above 2 was found in bins holding **62-67% of the burned area**. This is the biggest gain in this note (§A5).
2. **Planetary Computer's Sentinel-3 archive has a hole: Feb-May 2024 has 26 SYN items and 2025 has 32, against 108-134 in 2019-2023 and 74 in 2026.** The full archive is on the Copernicus Data Space (free account). For 2024-2025, use CDSE or the CLMS daily 300 m burnt-area product (§B5).
3. **HLS v2 adds no new dates.** HLS is built from the same Landsat 8/9 and Sentinel-2A/B/C scenes we already use. Over the box it has fewer S2 dates than Planetary Computer, not more (§A1).
4. **Sentinel-2C did not densify the calendar.** It replaced S2A on 21 Jan 2025. S2A's "extended campaign" adds one extra look about every 20 days over Ratapani (10 scenes in 2025-26), and those are already in our labels (§A1).
5. **Landsat 7 is the one unused optical source that splits windows.** 86 ETM+ scenes on path 145/044 (2017-2024) are in Planetary Computer but not in the labels. Reading their QA bands, an extra clear look falls inside **25% of burned windows** (2017: 80%; 2018-2021: 22-39%; 2022-2023: 15%; 2024-2026: about 0). Mean window length drops from 6.4 to 5.3 days; 2017's from 13.1 to 7.8 days (§A2).
6. **INSAT fire points have a long archive on MOSDAC.** The keyless catalogue search lists `3DIMG_L2P_FIR` for every Jan-Jun season 2014-2024 (about 7,500 files each), `3RIMG_L2P_FIR` 2017-2026 and `3SIMG_L2P_FIR` 2024-2026. Download needs a free MOSDAC login (§A6).
7. **Himawari does not reach Ratapani.** JAXA's wildfire product covers 80 E-160 W, and the sanctuary is at 77.3-78.1 E. View zenith would be 73.6° anyway (§B1).
8. **MCD64A1 sees 12% of our burned windows.** Where it does, its date falls inside our window 66% of the time, with a median uncertainty of 1 day. Detection rises from 8% for cells with ≤2 ha burned to 18% for 10-25 ha (§A4).
9. **ECOSTRESS passes over Ratapani at all hours.** There were 31-82 passes per Jan-Jun season in 2019-2026, about a quarter of them at 12:00-16:00 IST. At least one daytime pass falls inside 47% of burned windows; this is an upper bound, because cloud and partial coverage are not counted (§A3).

---

## Sources table

| Source | Coverage over Ratapani | Cadence | Resolution | Latency | Access | Usable? |
|---|---|---|---|---|---|---|
| **Sentinel-3 SYN L2 (OLCI + SLSTR surface reflectance)** | Full; tested | ~1 look/day (S3A+S3B) at ~09:50-10:50 IST; 97 usable looks Feb-May 2021 and 2023 | 300 m | ~1-2 days (NTC later) | Planetary Computer, keyless (gaps 2024-25); CDSE full archive, free login | **Yes, tested (§A5)** |
| CLMS Burnt Area 300 m v4 (daily, S3 + VIIRS AF) | Global | Daily; day of burn + burned fraction | 300 m | NRT: day after sensing; NTC: 2-6 months | CDSE (free login); daily v4 from Jan 2025, monthly from Jul 2018 | Yes, to test |
| Landsat 7 ETM+ C2 L2 | Path 145/044 covers 99% of AOI | 16 days; 2017-2024 | 30 m, SLC-off gaps | n/a (archive) | Planetary Computer, keyless | **Yes, for labels 2017-2023** |
| Landsat 8/9 path 146/044 | 3-5% of AOI (west edge) | 16 days each | 30 m | n/a | Planetary Computer | Minor (dropped by the 5% rule in `fetch.py`) |
| Sentinel-2C | Full | Replaced S2A from 21 Jan 2025 | 10-20 m | ~1 day | PC, CDSE | Already used; no extra dates |
| Sentinel-2A extended campaign | Full | ~1 look per 20 days (2025-03-28 onward) | 10-20 m | ~1 day | PC | Already used |
| HLS v2 (L30/S30) | Full | Same scenes as above | 30 m | ~1.7 days | PC (`hls2-l30`, `hls2-s30`), LP DAAC | No new dates |
| MCD64A1 C6.1 | Full | Monthly file, daily burn date | 500 m | ~1-2 months | PC, keyless (tested) | Partly (12% of windows) |
| VNP64A1 C2 | Full | Monthly, daily date | 500 m | months | LP DAAC (login), GEE | Same class as MCD64A1 |
| VIIRS I-band SDR (I1-I3) | Full | 2-3 looks/day (S-NPP, NOAA-20, NOAA-21) ~13:30 IST | 375 m TOA | hours | NOAA AWS buckets, keyless; archive from 2021 (NOAA-20) / 2022 (S-NPP) | Yes, untested |
| VNP09GA / VJ109GA, MOD09GA/GQ | Full | Daily | 500 m (I-band 375 m), MODIS 250 m | days | LP DAAC (free Earthdata login) or GEE | Yes, untested |
| MCD43A4 daily NBAR | Full | Daily, 16-day kernel window | 500 m | weeks | PC, keyless | No for dating [inference: smoothed] |
| Sentinel-3 OLCI LFR L2 | Full | Daily | 300 m | ~1 day | PC | No (indices only, no SWIR); use SYN |
| ECOSTRESS LST (ECO_L2_LSTE v2) | Granules overlap the box on 31-82 days per Jan-Jun season | Irregular, all hours | 70 m | days | LP DAAC (free login), AppEEARS | Maybe (thread 2 test) |
| INSAT-3D / 3DR / 3DS FIR (KML) | India and beyond | ~every 30 min (~41 files/day) | 4 km MIR | ~30 min | MOSDAC; catalogue search keyless, download with free login | Yes for timing of larger fires |
| Himawari-8/9 JAXA WLF | **Not covered** (80 E-160 W) | 10 min | 2 km | ~30 min | JAXA P-Tree | No |
| FY-4A/B FHS | Disk covers India | 15 min | 2 km | <1 h | NSMC | No (prior FY-4A test missed tiger-reserve fires) |
| OroraTech OT-NRT | Not stated for India | ~04:00 and ~16:00 local | 200 m | minutes | Commercial | Ask for trial |
| FireSat (EFA) | Global target | ≥2/day from Q4 2026 for early adopters | ~5 × 5 m fire claim | minutes | Early-adopter programme; wider 2027, global 2028 | Apply |
| PlanetScope | Full | Near-daily | 3 m | ~1 day | E&R (university) or ESA TPM | Yes if eligible (see `high_res_imagery.md` §2) |
| BA-Net (VIIRS 750 m daily) | Global | Daily | 0.01° | days | GitHub `mnpinto/banet` | No (min 25 pixels at 0.01°) |

---

## Part A. Our own tests (DATA, computed 15 Oct 2026)

### A1. The real acquisition calendar over the box (Planetary Computer STAC, every cloud cover)

Script: `stac_cal.py`, `cal_compare.py`. Box 77.34-78.07 E, 22.82-23.11 N; season = 1 Dec to 20 Jun.

**Distinct dates per season**

| Season | S2 dates (all clouds) | S2 dates used in labels | Landsat items (L7 / L8 / L9) | Landsat dates used |
|---|---|---|---|---|
| 2017 | 10 | 10 | 24 / 25 / 0 | 14 |
| 2018 | 35 | 32 | 26 / 25 / 0 | 12 |
| 2019 | 40 | 39 | 25 / 25 / 0 | 16 |
| 2020 | 41 | 36 | 25 / 26 / 0 | 15 |
| 2021 | 41 | 37 | 25 / 26 / 0 | 13 |
| 2022 | 41 | 36 | 8 / 21 / 22 | 20 |
| 2023 | 41 | 37 | 12 / 23 / 24 | 21 |
| 2024 | 41 | 33 | 2 / 24 / 26 | 24 |
| 2025 | 45 | 40 | 0 / 23 / 24 | 23 |
| 2026 | 45 | 40 | 0 / 25 / 25 | 23 |

What this shows:
- **Sentinel-2.** Two satellites give 41 dates per season, a 5-day revisit. S2A items: 2018-2024 about 40-60 per season; 18 in 2025 and 12 in 2026. S2C: 31 items in 2025, 41 in 2026.
  - On tile 43QGF the sequence is S2B and S2A alternating every 5 days until 20 Jan 2025, then S2B and S2C from 25 Jan 2025.
  - S2A extended-campaign looks fall on 2025-03-28, 04-17, 05-27, 06-16, 2025-12-13, 2026-03-23, 04-02, 04-22, 05-12 and 06-01: one every 20 days. All are already in `clear_calendar`.
  - So the 2025-26 calendar has 45 dates instead of 41, not the "2-3 day" revisit sometimes quoted for three S2 satellites [inference: that figure assumes three satellites in one phased orbit].
- **2017 is thin for a real reason.** Element84's Earth Search lists only 8 S2 L1C dates in the 2017 season (16 items), the same as PC. The thin 2017 archive is an ESA acquisition gap, not a PC problem. Landsat 7 is the only fix (§A2).
- **HLS v2 on PC** (`hls2-s30`, `hls2-l30`) has 29-44 S30 dates and 8-51 L30 dates per season, starting 2020 (L30 partly 2018). That is a subset of what we already use. HLS is useful for its harmonised BRDF and bandpass, not for dates.
- **Landsat path 146/044** is in the catalogue (122 L8 and 58 L9 scenes, mostly unused). It covers only 3-5% of the AOI, so `fetch.py` drops it under its `frac < 0.05` rule. It is a small edge gain for the westernmost cells.
- **Landsat 7** (145/044) has 86 unused scenes with a median scene cloud of 1%. USGS: the orbit drifted earlier from 2017; it was lowered in May 2022 to an equator crossing before 08:45; imaging was suspended on 19 Jan 2024. Planetary Computer lists 8 and 12 L7 scenes for 2022 and 2023.

**Concrete action for us (labels thread):** add `landsat-7` to the platform filter in `fetch.py` for seasons 2017-2023. Mask SLC-off gaps with the QA fill bit. Lower the AOI-coverage threshold for Landsat from 5% to 1%, so path 146 helps the west edge. Leave HLS out.

### A2. How many scar windows a denser calendar would split (real QA, not scene cloud)

Script: `qa_extra.py` (QA band of each unused scene read at 100 m, per 500 m cell clear fraction), then `split2.py`. Scenes: 86 Landsat 7 scenes plus 65 Sentinel-2 scenes with scene cloud ≥ 60%, all 2017-2026. A cell counts as seen if ≥ 50% of it is clear (≥ 80% given in brackets).

| Season | Burned windows | Split by an extra clear look | Mean window (days) now → after |
|---|---|---|---|
| 2017 | 3,065 | 79.7% (56.7%) | 13.1 → 7.8 |
| 2018 | 4,961 | 38.9% | 6.9 → 4.9 |
| 2019 | 4,775 | 22.1% | 5.3 → 4.7 |
| 2020 | 1,429 | 35.2% | 5.2 → 4.4 |
| 2021 | 2,221 | 34.4% | 5.9 → 5.1 |
| 2022 | 2,960 | 15.1% | 5.5 → 5.0 |
| 2023 | 2,090 | 15.2% | 6.0 → 5.5 |
| 2024 | 1,636 | 2.1% | 6.1 → 6.0 |
| 2025 | 2,754 | 0.0% | 5.1 → 5.1 |
| 2026 | 3,075 | 0.1% | 4.4 → 4.4 |
| **All** | **28,966** | **25.9% (19.4%)**; L7 25.3%, cloudy S2 1.4% | **6.44 → 5.25** |

- "After" is the expected length of the sub-window that holds the burn, assuming the burn is equally likely anywhere in the window.
- The median window stays 5 days. Windows of ≤ 3 days rise from 13.3% to 17.8%.
- Cloudy S2 scenes (≥ 60% scene cloud) almost never give a clear look over a cell (mean clear fraction 0.07). Raising the cloud limit is not worth it.
- With scene cloud as a crude proxy (`split.py`) the estimate was 27%, close to the QA result.

**For alert scars** (`alert_split.py`, 13,207 alerts with a scar and a `gap_days`): 20.4% of pre/post brackets would be split. That is 80% in 2017 (median gap 16 → 8 days), 18-30% in 2018-2022, 11% in 2023 and 0-1% in 2024-2026. `gap_days` is 5 days at the median and 10 days at the 90th percentile.

**Concrete action for us:**
- Labels thread: re-run `fetch.py` → `detect.py` → `rollup.py` with Landsat 7 for 2017-2023. Expect about a quarter of windows to shorten, and 2017 to become usable (mean window 13 → 8 days).
- Field alerts: no change. 2024-2026 gain nothing from this.

### A3. ECOSTRESS calendar over Ratapani (NASA CMR, keyless)

Script: `cmr_list.py`, `eco_stats.py`, `eco_windows.py`. Collection `ECO_L2_LSTE` v002 (C2076114664-LPCLOUD): 1,420 swath granules intersect the box (969 distinct orbits, Jul 2018 - Oct 2026). The tiled `ECO_L2T_LSTE` v002 has 2,876 tile granules. A v003 collection (C3998139651) now also exists.

**Passes per Jan-Jun season, by IST time of day**

| Season | 00-06 | 06-10 | 10-12 | 12-16 | 16-19 | 19-24 | Total |
|---|---|---|---|---|---|---|---|
| 2019 | 2 | 8 | 4 | 11 | 6 | 0 | 31 |
| 2020 | 12 | 6 | 5 | 14 | 8 | 9 | 54 |
| 2021 | 11 | 18 | 7 | 22 | 8 | 6 | 72 |
| 2022 | 7 | 17 | 8 | 10 | 8 | 8 | 58 |
| 2023 | 9 | 13 | 9 | 12 | 8 | 9 | 60 |
| 2024 | 7 | 10 | 4 | 7 | 4 | 7 | 39 |
| 2025 | 10 | 19 | 4 | 19 | 15 | 15 | 82 |
| 2026 | 11 | 18 | 5 | 17 | 13 | 6 | 70 |

- Mar-Apr passes at 12:00-19:00 IST: 2-14 per year.
- Share of 2019-2026 burned windows with at least one pass inside: daytime 09-17 IST **46.6%**; 12-17 IST 35.5%; night 29.1%.
  - These are upper bounds: no cloud screening, and a granule that touches the box may not cover the cell.
- Two uses [inference]:
  - a hot pixel (LST ≥ 60 °C, per the UCI study cited in `fire_detection_sources.md` §12) dates a fire to the hour;
  - a burned surface is darker and drier, so it should stay several kelvin warmer than its surroundings for days. An afternoon LST anomaly inside the window would then split it, the way the S3 test does with NBR.
- Download needs a free Earthdata login (LP DAAC / AppEEARS), so it was not tested here.

**Concrete action for us (labels thread, then spread thread):**
- Pull ECO_L2T_LSTE tiles 43QGF/43QHF for windows that contain a daytime pass (AppEEARS point or area request).
- Test whether scar-minus-ring LST is above zero after the burn and not before, using the VIIRS-dated scars as truth, as in §A5.
- Hot pixels at 13:00-17:00 IST also give spread-thread fire-front snapshots at 70 m.

### A4. MCD64A1 over our scars (Planetary Computer `modis-64A1-061`, tile h25v06, keyless)

Script: `mcd64.py`. Burn Date and Burn Date Uncertainty sampled at each 500 m cell centre, Jan-Jun 2017-2026.

| Measure | Value |
|---|---|
| Burned cell-seasons with an MCD64A1 burn in the same cell | **12.1%** |
| Same, by cell burned area ≤2 / 2-5 / 5-10 / 10-25 ha | 8.0% / 9.9% / 11.8% / 18.4% |
| MCD64A1 date inside our window (±1 day) | 66.2% |
| Median MCD64A1 burn-date uncertainty | 1 day (smaller than our window in 96%) |
| MCD64A1 cell detections not in any of our burned windows | 24.8% |

[inference] MCD64A1 is a cheap second opinion that gives a 1-day date for about one window in eight. It disagrees with our window a third of the time, so use it only as a soft prior. The 25% of MCD64 cells with no scar of ours are worth a look as possible label misses (light ground fires) or MCD64 commission.

**Concrete action for us (labels thread):** join `mcd64_cells.csv` to the labels as an extra dating source (weight below VIIRS and S3).

### A5. Daily Sentinel-3 SYN reflectance: does it pick the burn day inside our window? (the main test)

Scripts: `rangefile.py` (HTTP range reader so `h5py` reads only the needed chunks), `s3pull.py` (box cut-out of Oa17 0.865 µm, Oa08, S5N 1.61 µm, S6N 2.25 µm, CLOUD and SYN flags plus lat/lon), `s3date2.py` (test) and `s3summ.py` (summary). It costs about 30-60 s per scene; one season of 134 scenes took about 50 minutes.

Method:
- Bin S3 pixels to a 300 m UTM grid matched to our 20 m scar raster (15 × 15 pixels per bin).
- Daily NBR = (Oa17 − S6N)/(Oa17 + S6N), minus the mean of unburned bins (burned fraction < 2%) within about 3.3 km on the same date. This takes out haze, view angle and regional leaf fall, the same idea as `detect.py`.
- For each bin ≥ 10% burned, take its window (ws, we] from the 20 m raster. Fit a one-step change to the series: S3 looks up to 12 days before ws, the looks inside, and up to 12 days after we.
  - Choose the split between consecutive inside looks that minimises squared error against the pre and post medians.
- Signal-to-noise (SNR) = (pre median − post median) / residual standard deviation.
- Truth: the first VIIRS detection (`alert_scar_lookup.csv`, IST time) inside the same 300 m bin.
- Baseline: picking a sub-interval with probability equal to its share of the window, which is what a uniform prior does.
- "Hit" allows the VIIRS time to be up to 6 h after the chosen post look (fire still burning at the 13:30 pass after an S3 look at about 10:00). "Strict" allows no slack.

| | 2021 | 2023 |
|---|---|---|
| Usable S3 looks, Feb-May | 97 (clear share per bin 0.69) | 97 (0.67) |
| Bins ≥ 10% burned | 2,580 | 2,249 |
| Bins with ≥ 1 S3 look inside the window | 99.9% | 90.3% |
| Median dNBR at 300 m (bins 10-30% / 30-50% / 50-75% / > 75% burned) | 0.054 / 0.071 / 0.100 / 0.134 | 0.044 / 0.066 / 0.087 / 0.128 |
| Share of bins with SNR > 2 (same classes) | 45% / 60% / 82% / 90% | 35% / 53% / 73% / 88% |
| Burned area in bins with SNR > 2 | 66.8% | 61.6% |
| VIIRS-dated test bins | 571 | 292 |
| **Hit rate, all** (strict) vs uniform baseline | **0.81** (0.69) vs 0.37 | **0.74** (0.64) vs 0.37 |
| Hit rate, SNR > 2 | 0.88 (0.75), n = 381 | 0.85 (0.75), n = 192 |
| Hit rate, SNR > 3 | 0.91 (0.78), n = 255 | 0.91 (0.81), n = 123 |
| Hit rate, bins < 30% burned | 0.74 (0.62) vs 0.37 | 0.58 (0.49) vs 0.38 |
| Hit rate, bins ≥ 50% burned | 0.88 (0.80) vs 0.35 | 0.90 (0.76) vs 0.32 |
| Median new interval (window 5 days) | **1.0 day** | **2.0 days** |
| New / old interval, mean | 0.34 | 0.33 |

In 2023, by number of S3 looks inside the window (hit vs baseline): 1 look 0.82 vs 0.80; 2 looks 0.73 vs 0.53; 3 looks 0.85 vs 0.37; 4-5 looks 0.70 vs 0.26; 6 or more 0.69 vs 0.15.

Reading:
- A litter fire that burns half of a 9 ha bin drops relative NBR at 300 m by about 0.09-0.10. Day-to-day noise after the background correction is small enough that the step is found 3-4 times in 5.
- This is sub-pixel temporal unmixing in its simplest form: the burned fraction is known from the 20 m scar, and S3 supplies only the timing.
- Caveats:
  - The truth set is VIIRS-detected fires, which are larger and hotter than the average scar, so hit rates for undetected scars will be lower [inference]. The < 30%-burned rows (0.58-0.74) are the better guide for small scars.
  - Two seasons only.
  - 2024-2025 cannot be repeated from PC (§B5).

**Concrete actions for us:**
- **Labels thread (highest value):** run `s3pull.py` + `s3date2.py` for 2019-2023 and 2026 from PC, and for 2024-2025 from CDSE with a free account. For each burned 300 m bin, store (sub-interval start, end, SNR). Use them as a soft date:
  - SNR > 3: about 90% in the S3 interval;
  - SNR 2-3: about 80%;
  - below 2: keep the 20 m window.
  - This turns many 5-day windows into 1-2-day windows. For the true-lead label it decides whether the d-1/d-2 positives sit on the right days.
- Improvements to try:
  - add S3A+S3B same-day pairs as two looks;
  - use the SLSTR oblique view (S6O) as a second sample;
  - fit the burned fraction explicitly with the CLMS fire-effects model (§B5) instead of an NBR step;
  - push the method to 20 m by assigning every 20 m scar pixel the date of its 300 m bin, splitting bins whose 20 m pixels have different windows.
- **Field alerts:** S3 looks arrive about 1-2 days after sensing. A drop on day d+1 with SNR > 3 is a cheap "this alert produced a scar" check at 300 m, about 3-4 days sooner than the next S2 look [inference].
- **Spread thread:** S3 gives a daily burned-fraction map at 300 m. The fraction growing across consecutive days in neighbouring bins is a daily spread record for multi-day fires (10% of VIIRS-dated cells burn on two consecutive days, `burn_dating_validation.md` §0).

### A6. INSAT fire archive on MOSDAC (keyless catalogue search)

Script: `mosdac_count.py`. The endpoint `https://mosdac.gov.in/apios/datasets.json?datasetId=…&startTime=…&endTime=…` comes from MOSDAC's own `mdapi.py` client; its manual says search needs no login. Download goes through `download_api` with a free MOSDAC account.

**Files per Jan-Jun season**

| Product | 2014-2016 | 2017 | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 | 2025 | 2026 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| `3DIMG_L2P_FIR` (INSAT-3D) | 7,559-7,923 | 7,473 | 7,737 | 7,551 | 7,792 | 7,467 | 7,700 | 7,433 | 5,521 | none | none |
| `3RIMG_L2P_FIR` (INSAT-3DR) | none | 7,740 | 7,559 | 11,473 | 9,099 | 7,235 | 7,499 | 6,951 | 7,432 | 7,431 | 7,946 |
| `3SIMG_L2P_FIR` (INSAT-3DS) | none | none | none | none | none | none | none | none | 144 | 8,279 | 8,295 |

- Smoke (`*_L2P_SMK`) has a similar archive.
- One day (5 Apr 2024) of 3DR: 36 KML files, 10 MB in total.
- Each catalogue entry carries the bounding box of that file's fire points. In the sample, boxes ranged from a 0.1° box in Africa to south-east Asia, so the disk extends far beyond India. Boxes are too wide to tell Ratapani fires apart without downloading.
- Expectation: the 4 km MIR detection limit is like SEVIRI's, and FY-4A missed tiger-reserve fires of 0.6-4 km² (`fire_detection_sources.md` §4) [inference: INSAT will see only the larger Ratapani fires]. But with 2-3 satellites at a 27° view angle and 30-minute steps over 12 seasons, it is the longest sub-daily record available.

**Concrete action for us:**
- Field alerts / dating: register on MOSDAC (free) and pull `3RIMG_L2P_FIR` and `3DIMG_L2P_FIR` KML for Mar-Apr 2019-2024 (about 15 MB per day for both).
- Match the points to VIIRS-dated Ratapani scars ≥ 10 ha and measure the hit rate and the first-detection hour.
- If more than about 20% of those scars are seen, INSAT gives the ignition hour for the big fires (spread thread) and an afternoon check on fires lit after the 13:30 VIIRS pass.

---

## Part B. Sources, one section each

### B1. JAXA Himawari-8 Wild Fire product README, v1.00, Jan 2020. https://www.eorc.jaxa.jp/ptree/documents/README_H08_L2WLF.txt **FULL** (whole file)

- Coverage: **"full disk (60N-60S, 80E-160W)"**. Grid 0.02° (2 km at nadir), 10-minute L2.
- Detection: the 3.9 µm brightness temperature is tested against a background from 10.8 µm on an 11 × 11 window. FRP comes from a bi-spectral 2.3/3.9 µm fit.
- Output CSV fields: fire level (0 cold, 1 smouldering, 2 flaming), reliability 1-3 ("frequently detected hot spots … will be rated as low reliability"), FRP in W m⁻² per grid cell.
- My geometry: the view zenith at 23 N, 77.7 E from 140.7 E is **73.6°**. For comparison: GK2A 61.8°, FY-4B at 105 E 40.8°, a satellite at 86.5 E (one reported FY-4A slot; positions conflict, see `fire_detection_sources.md` §4) 28.7°, INSAT at 74-82 E 27°, Meteosat IODC at 45.5 E 45.0°.

**Concrete action for us:** none. Ratapani (77.3-78.1 E) is outside the product. Drop Himawari from every thread.

### B2. Li & Roy 2017, "A global analysis of Sentinel-2A, Sentinel-2B and Landsat-8 data revisit intervals and implications for terrestrial monitoring", Remote Sens. 9:902. https://doi.org/10.3390/rs9090902 (PDF from the mdpi-res CDN) **FULL**

- Orbit modelling with COVE for 2016 on a 0.05° grid; cloud is not counted.
- Global median average revisit:
  - **L8 + one S2: 4.5 days**;
  - **S2A + S2B: 3.7 days**;
  - **L8 + S2A + S2B: 2.9 days**, with a median maximum revisit of 7.0 days.
- Median annual observations: 23 (L8), 37 (each S2), 127 (all three).
- With 50% cloud they expect a clear look "better than every six days" with all three.
- A Sensors 2020 follow-up (Li & Chen) gives 2.3 days with L9 added (search snippet only).

Our counts are close: 41 S2 dates per 201-day season (4.9 days) and about 20-25 Landsat dates. Our median window of 5 days is what the clear-sky calendar allows. Further optical gains need other satellites, not other products.

**Concrete action for us:** none beyond §A2. Use these numbers when reviewers ask why windows are 5 days.

### B3. Boschetti et al. 2019, "Global validation of the collection 6 MODIS burned area product", RSE 235:111490 (PMC7241595). **FULL** (Europe PMC full-text XML)

- Stage 3 validation with 558 Landsat 8 image pairs 16 days apart, stratified by biome and fire season.
- Global: **omission 72.6%, commission 40.2%**, relative bias −54%.
- **Tropical forest, temperate forest and Mediterranean: omission > 90%, commission > 50%.** Boreal is best (omission 27.0%, commission 23.9%).
- MCD64A1 "systematically underestimates the reference area burned in cells with smaller burned areas". Omission dominates below about 0.6 burned proportion of a 5 km cell.
- It cites the 29-day global median persistence (Melchiorre & Boschetti 2018), and says the random selection of reference dates avoids a persistence bias.

**Concrete action for us:** this matches §A4 (12% capture). MCD64A1 can only ever be a minor dating aid at Ratapani. Do not use it for area or recall.

### B4. Giglio, Boschetti, Roy, Hall, Zubkova, Humber, Huang & Oles 2025, "The NASA VIIRS burned area product, global validation, and intercomparison with the NASA MODIS burned area product", RSE 331:115006. https://geog.umd.edu/sites/geog.umd.edu/files/pubs/1-s2.0-S0034425725004109-main.pdf **PARTIAL** (abstract, algorithm §2-3, regional consistency, validation tables and §5.2 temporal uncertainty read)

- VNP64A1 C2 uses daily VNP09GHKM 500 m surface reflectance. The VI is the normalised ratio of **1.24 µm (M8) and 2.25 µm (M11)**.
  - Pre- and post-burn sliding windows of **8 daily observations** each, with 10% trimmed statistics.
  - Change is flagged by separability S(x, y, k) at each day k.
  - "Three months of daily … observations are used to map the central month."
- Validation (561 Landsat pairs): omission 72.4%, commission 36.7%, nearly the same as MCD64A1 (71.5% / 35.2%).
- **Temporal: 38% of VNP64A1 cells match the MODIS active-fire date, against 46% for MCD64A1; 71% (72%) are within 2 days.**
  - The paper puts the gap down to MODIS having morning and afternoon looks; VIIRS has only the afternoon ones.
- In south Asia the products differ on the dates of the Oct-Nov north-west India crop burning.

**Concrete action for us:**
- Labels thread: borrow two ideas for the S3 test (§A5): **trimmed medians in ±8-look windows**, and a separability score.
- Our S3 version already gets about 75-80% in the right 1-2-day interval for VIIRS-dated bins, better than VNP64's 38% exact-day [inference: different truth sets, so not a like-for-like comparison].

### B5. Copernicus Land Monitoring Service, Burnt Area 300 m: Product User Manual v4.0 (CGLOPS1_PUM_BA300m-V4.0, 20 May 2025) **PARTIAL** (algorithm, limitations, layer and access sections); ATBD v3.1 (CGLOPS1_ATBD_BA300m-V3.1, 17 Jun 2024) **PARTIAL** (method sections 4.2.2-4.2.5 and the validation figure list). https://land.copernicus.eu/en/technical-library/

- **Inputs:** Sentinel-3 OLCI Oa08 (0.665), Oa12 (0.754) and Oa17 (0.865 µm); SLSTR S5 (1.613) and S6 (2.256 µm); plus acquisition angles. VIIRS 375 m active fires: VNP14IMGTDL for NRT, VNP14IMGML for NTC.
- **Method:** a CNN (2-D convolutions over spectral and time dimensions) followed by an LSTM. It is trained on synthetic reflectance series made from two semi-empirical models:
  - (1) a **spectral fire-effects model**, which mixes the pre-fire reflectance with ash/char and soil endmembers to give the burned fraction f_b;
  - (2) a kernel **BRDF model** fitted with a temporal constraint (Quaife & Lewis 2010) at each VIIRS active fire.
- Targets are f_b and P(f_b > 0.2), the latter "useful to date the burns". A logistic model of VIIRS fire density filters out farming and senescence changes.
- "The minimum mapping unit is a single pixel."
- **Layers (v4):** `day_of_burn` (1-366), `burned_fraction` (0-1 at the burn day), `large_fraction_probability` (P > 0.1), plus a classification probability.
- **Stated limits:** ash/char dissipation and regrowth are not modelled, so area is underestimated when the first clear look comes days or weeks after the fire. "Omission errors are particularly prevalent on small and patchy burns." The AF filter assumes VIIRS saw the fire, so cloudy-area fires are missed.
- **Latency:** NRT the day after sensing. NTC waits 2-6 months for the VIIRS science fire product.
- **Coverage:** daily v4 from January 2025 (catalogue); monthly from July 2018; v3/v3.1 daily for 2023-2025.
- **Access:** free through CDSE (OData, S3 `/eodata/CLMS/bio-geophysical/burnt_area/…`, Copernicus Browser). Download needs a free CDSE account.
- One ATBD v3.1 validation example in southern Africa: Dice 87.5%, commission 13.6%, omission 11.4%. Two other figure captions give omission of 82.2% and 74.6% (search-level reading of the figure list).

**Concrete actions for us:**
- Labels thread: pull CLMS BA v4 daily for Jan-Jun 2025 and 2026 over the box (one CDSE account) and score `day_of_burn` against our windows and VIIRS dates, as in §A4.
  - Expect it to see more than MCD64A1 (300 m, VIIRS-seeded, single-pixel unit), but only scars that VIIRS saw [inference]. Our own S3 step test (§A5) does not need a VIIRS seed.
- Copy the fire-effects mixing model, ρ_post = (1 − f_b)·ρ_pre + f_b·ρ_char, into §A5 to report a burned fraction alongside the date.

### B6. Pinto, Trigo, Trigo & DaCamara 2021, "A practical method for high-resolution burned area monitoring using Sentinel-2 and VIIRS", Remote Sens. 13:1608. https://doi.org/10.3390/rs13091608 **FULL**

- **BA-Net** (Pinto et al. 2020, ISPRS J. 160:260; ABSTRACT ONLY, not OA) maps and dates burns from daily VIIRS 750 m sequences on a 0.01° grid. The burn-date uncertainty is "smaller than 2 days for more than 90% of the pixels".
- The 2021 method splits events "every time the temporal distance is greater than 2 days" and removes events under 25 pixels. It then refines each event with Sentinel-2 10 m before/after images in a U-Net. Dice is 0.87-0.94 on six Mediterranean fires (all large).
- Code: `pip install banet` / `FireHR` (GitHub `mnpinto/banet`, Apache-2.0). Weights and a 160 GB training set are on Google Drive.

**Concrete action for us:** none directly. A 25-pixel minimum at 0.01° (about 30 km²) is far above our 2-25 ha fires. The useful lesson is the order of work: date at coarse resolution daily, then draw the edges at fine resolution. That is what §A5 does.

### B7. Roy, Huang, Boschetti, Giglio, Yan, Zhang & Li 2019, "Landsat-8 and Sentinel-2 burned area mapping — a combined sensor multi-temporal change detection approach", RSE 231:111254. **ABSTRACT ONLY** (ScienceDirect 403; no author copy found)

- NBAR inputs from both sensors, with a random-forest change regression trained on synthetic data from a spectral fire-effects model.
- It runs on rolling 3-month windows.
- The combined 30 m product reports burn dates **about 3 days later** than MCD64A1, "because of the lower revisit frequency".

**Concrete action for us:** this confirms that L8 + S2 alone cannot date better than the revisit allows. A daily sensor (§A5) is what closes the gap.

### B8. MOSDAC Data Download API manual and client `mdapi.py`. https://www.mosdac.gov.in/user-manual-mosdac-data-download-api , https://www.mosdac.gov.in/software/mdapi.zip **FULL**

- Search endpoint `apios/datasets.json` (OpenSearch JSON). "You don't need to log in to search; an account is only required to download data."
- Download goes through `download_api/gettoken` and `download_api/download` with a username and password.
- The client lists `datasetId` examples such as `3SIMG_L1B_STD`. The fire product IDs in §A6 were confirmed by direct queries.

**Concrete action for us:** see §A6. The archive exists back to 2014 (INSAT-3D), which answers the open question in `fire_detection_sources.md` §3.

### B9. Sentinel-2A extended campaign (Copernicus/ESA news, Feb 2025) **PARTIAL** (search-level summaries of the CDSE and Sentinel Online news items)

- S2C took over S2A's duty on 21 Jan 2025. S2A was moved 36° away from S2B between January and March 2025. The extended campaign started on **13 March 2025** for one year, with a review after that.
- S2A looks fall "2 days apart from Sentinel-2B and 1 day apart from Sentinel-2C". The aim is better revisit "over tropical Africa and South America".
- Our STAC data show the campaign continuing into 2026, with S2A looks over Ratapani about every 20 days, not every 10.

**Concrete action for us:** none; these looks are already used. Re-check the PC calendar each season in case S2A tasking over India increases.

### B10. Landsat 7 mission status (USGS pages, search-level) **PARTIAL**

- The orbit drifted earlier from 2017. The nominal science mission ended 6 Apr 2022. Imaging resumed at 697 km on 5 May 2022, with an equator crossing "earlier than 8:45 AM", off the WRS-2 grid. Imaging was suspended on 19 Jan 2024.
- USGS: data from the lower orbit are "potentially unreliable for many scientific studies".

**Concrete action for us:**
- Use L7 for 2017-2021 without change.
- For 2022-2023 (20 scenes), accept lower sun and longer shadows. Because `detect.py` compares each pixel with its surroundings, it should tolerate this [inference]; check the 2022-23 L7-only splits visually on 10 cases.

### B11. FireSat (Earth Fire Alliance) news, 2025-2026 **ABSTRACT ONLY** (news and aggregator reports)

- Three operational satellites launched 7 Jul 2026. Early adopters get observations "at least twice daily" from Q4 2026. Wider availability "throughout 2027", global access by 2028. The first cohort is eight fire agencies (CAL FIRE, Australian agencies, Mediterranean, South America). No pricing and no public portal.

**Concrete action for us (field alerts):** write to EFA for 2027 access on behalf of MP Forest Department or FSI. An afternoon pass at about 5 m sensitivity is the one source that could see our litter fires as they burn.

### B12. HLS v2 facts (NASA HLS data page, LP DAAC FAQ; search-level) **PARTIAL**

- Products HLSS30 and HLSL30. Sentinel-2C is included from **21 Jan 2025**. Latency is about **1.7 days** from overpass when inputs arrive on time; a 6-hour low-latency version is a stated goal.
- V2.0 was completed in summer 2023.

**Concrete action for us:** HLS gives no new dates (§A1). Its only use is as a cleaner NRT feed for field alerts if PC's S2 L2A is late [inference].

### B13. Other sources checked (no new numbers)

- **NOAA AWS VIIRS buckets** (keyless; prefixes listed, not tested): `noaa-nesdis-n20-pds` holds `VIIRS-I1/I2/I3-SDR` from 2021 and `VIIRS-I2-IMG-EDR` from 2026; `noaa-nesdis-snpp-pds` holds I-band SDR from 2022.
  - `VIIRS_SurfaceReflectance_EDR` and `VIIRS-M11-SDR` hold only 2026, so they are rolling.
  - I2 SDR granules are about 24-30 MB each, uncompressed, so range reads are cheap.
  - This is the keyless route to 375 m daily I2 (0.86 µm) / I3 (1.61 µm) for an §A5-style test at 13:30 IST, with 2-3 satellites.
- **Planetary Computer `modis-43A4-061`** (daily NBAR, 500 m): keyless, but each day is a 16-day BRDF retrieval, so it smooths a 1-day step [inference]. Not tried.
- **Planetary Computer `sentinel-3-olci-lfr-l2-netcdf`**: same gaps as SYN (25-30 items in Feb-May 2024-25). It holds indices, not SWIR. SYN is the better input.
- **CEOS FedEO** lists `clms_ba_global_300m_daily_v4_{nc,cog}` for 2025 and 2026, confirming the archive.
- **OroraTech India** search: no Indian agency contract found. The CSDA user-guide details are already in `fire_detection_sources.md` §12.
- **Libonati et al. 2015** (Cerrado, daily MODIS 4 µm burned area; Remote Sens. 7:15782), at INPE: search only, not read. It is a monthly product.
- **Boschetti et al. 2015**, MODIS-Landsat fusion (RSE 161:27): ABSTRACT ONLY. MODIS active fires keep or reject Landsat candidate burns over 1.9 M km² of the western US.

---

## Part C. How it fits each thread [inference]

- **Labels (thread 2):**
  - §A5 (S3 daily step) is the only route found that cuts most windows to 1-2 days with no field data and free inputs.
  - §A2 (Landsat 7) fixes 2017 and adds about 25% splits for 2017-2023.
  - §A4 (MCD64A1) and §B5 (CLMS) are soft priors.
  - Stack them in the `burn_dating_validation.md` recipe A (Step 5) as extra "clear passes": an S3 look that shows no drop is a "seen unburned" observation, and one that shows a drop ends the interval.
- **Spread (thread 4):**
  - daily S3 burned fraction for multi-day fires;
  - INSAT (§A6) and ECOSTRESS hot pixels for hour-level timing of the bigger fires.
- **Field alerts (thread 5):**
  - S3 SYN NRT (about 1-2 days) is the fastest free check that an alert produced a scar;
  - INSAT 30-minute points for afternoon fires missed at 13:30;
  - FireSat and OroraTech remain the only small-fire sub-daily options, both by application.

---

## Ranked action list

| Rank | Action | Thread | Expected gain (basis) | Effort |
|---|---|---|---|---|
| 1 | Run the S3 SYN step test (`s3pull.py` + `s3date2.py`) for 2019-2023 and 2026 from PC; store per-bin S3 sub-interval and SNR; feed it as soft dates | Labels | Median window 5 → 1-2 days in bins holding ~62-67% of burned area; ~75-90% reliable (measured, 2 seasons) | 2-3 days (≈1 h download per season) |
| 2 | Get a free CDSE account; pull S3 SYN for 2024-2025 (PC gap) and CLMS BA 300 m v4 daily for 2025-2026; score both as in §A4/§A5 | Labels, alerts | Closes the 2024-25 gap; tests an operational daily product (CLMS) | 1-2 days |
| 3 | Add Landsat 7 (2017-2023) and a 1% coverage rule for path 146 to `fetch.py`; rerun detect/rollup | Labels | 25.9% of burned windows split; 2017 mean window 13.1 → 7.8 days (measured from QA) | 1 day |
| 4 | Join MCD64A1 burn dates (`mcd64_cells.csv`) as a weak dating source; inspect its 25% of cells with no scar of ours as possible misses | Labels | 1-day date for ~12% of windows, 66% consistent (measured) | 0.5 day |
| 5 | Register on MOSDAC; pull 3DR + 3D FIR KML for Mar-Apr 2019-2024; match to VIIRS-dated scars ≥ 10 ha | Alerts, spread | Hour of ignition for larger fires if hit rate > ~20% (unknown) | 1 day |
| 6 | ECOSTRESS (Earthdata login): pull L2T LST for windows with a daytime pass; test scar-minus-ring warming and LST ≥ 60 °C hot pixels against VIIRS-dated scars | Labels, spread | Up to 47% of windows contain a daytime pass (upper bound, measured) | 1-2 days |
| 7 | VIIRS I-band SDR from NOAA AWS (keyless, 2021-): repeat §A5 at 375 m with 2-3 afternoon looks/day | Labels | Possibly finer than S3 on cloudy days; complements the 10:00 S3 look with 13:30 (unknown) | 2 days |
| 8 | In §A5 add same-day S3A/S3B pairs, SLSTR oblique view, and an explicit burned-fraction fit (CLMS fire-effects model) | Labels | Higher SNR for <30%-burned bins (currently 0.58-0.74 hit rate) [inference] | 1 day |
| 9 | Apply to EFA FireSat early-adopter programme and ask OroraTech for a Mar-Apr 2027 trial | Alerts | Only route to sub-daily small-fire detection | emails |
| 10 | Drop Himawari; drop HLS as a dating source; do not raise the S2 cloud limit | All | Saves effort (measured: HLS adds 0 dates; ≥60%-cloud S2 adds 1.4% splits) | none |

---

## Reading status

- **FULL (5):**
  - JAXA H08 WLF README;
  - Li & Roy 2017;
  - Boschetti et al. 2019;
  - Pinto et al. 2021;
  - MOSDAC API manual and client.
- **PARTIAL (6):**
  - Giglio et al. 2025 (VNP64A1);
  - CLMS BA PUM v4.0;
  - CLMS BA ATBD v3.1;
  - S2A extended-campaign news;
  - USGS Landsat 7 status pages;
  - HLS data page.
- **ABSTRACT ONLY (5):**
  - Roy et al. 2019;
  - Pinto et al. 2020 (BA-Net);
  - Boschetti et al. 2015;
  - FireSat news;
  - Libonati et al. 2015.
- **Data tests (7):**
  - PC STAC calendar (S2, Landsat, HLS);
  - QA-based split count (151 scenes);
  - alert-scar split;
  - ECOSTRESS CMR calendar;
  - MCD64A1 sampling (2017-2026);
  - Sentinel-3 SYN step test (2021 and 2023, 231 scenes);
  - MOSDAC INSAT catalogue counts.

