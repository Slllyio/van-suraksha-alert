# Burn scars for all of Madhya Pradesh (15 Oct 2026)

Akkshay asked on 15 Oct (09:22Z) to run the scars for all of MP, check them, then make them live. He also set two ground rules:
- The scars are for senior officials to monitor, not for field staff.
- The fire season is 15 Feb to 15 June, so January fires are out of scope.

The method is the same as for Ratapani (`../scripts/alert_scar.py`, with grown outlines).

## Inputs
- FIRMS yearly India files for 2017-25: MODIS, S-NPP and NOAA-20. NOAA-21 has no yearly files yet.
  - These were clipped to MP beats (`../../ratapani/beats/mp_beats.geojson`) and to 15 Feb-15 Jun.
  - That leaves 480,590 alerts (`alerts/mp_season_beats.csv`).
  - Alerts are grouped into 203,286 fire events: same day, within 1 km.
- Forest filter: the event point needs at least 10% tree + shrub (ESA WorldCover) within 375 m. 184,352 events pass (`out/mp_events.csv`).
- Scripts: `scripts/clip_mp.py`, `mp_events.py`, `mp_sample.py`, `mp_run.py`, `mp_eval.py`, `tr_summary.py`.

## Check across MP (`out/set_sample.csv`, `out/scars_sample.csv`, `out/eval_sample_by_division.csv`)
- **Sample.** Up to 40 forest fire events per division, 2,905 measured.
- **Controls.** 1,472 control points. Each is 3 km away on the same date, in forest inside a beat, with no FIRMS alert within 1.5 km and 30 days.
- **Scar found.** 84.4% of real fires get a clear scar, against 4.0% of controls. Including faint scars, it is 90.5% against 5.0%. Ratapani was about 89% against 6.5%.
- **By division.** The median division is 85% (10th-90th percentile 72-95%). The lowest are Shajapur 33%, Morena 50% and Kuno, Satna and Rewa at about 68%. Kanha is 72%, likely because its moist sal canopy hides surface burns.
- **By month.** Feb 76%, Mar-Apr 86%, May 80%, Jun 71%.
- **By year.** Between 78% and 91% in every year.

## Tiger reserves, full history 2017-25
- **Coverage.** All forest fire events in the 8 reserve divisions besides Ratapani: BTR, Kanha, Pench, Panna, Satpura, Sanjay-Dubri, Noradehi (Veerangana Durgavati) and Madhav. That is 12,586 events.
- **Files.**
  - Outlines: `out/tiger_reserve_scars.geojson`.
  - Per-event results: `out/scars_tiger_reserves.csv`, joined to `out/set_tiger_reserves.csv` on event_id.

| Reserve division | Events | Scar found | Median scar (ha) |
|---|---|---|---|
| BTR (Bandhavgarh) | 3,061 | 89% | 31 |
| Kanha | 1,671 | 78% | 20 |
| Madhav | 303 | 77% | 118 |
| Noradehi | 1,710 | 84% | 122 |
| Pench | 498 | 81% | 25 |
| Panna | 1,443 | 83% | 71 |
| Sanjay-Dubri | 2,469 | 82% | 35 |
| Satpura | 1,385 | 83% | 67 |

**Against FSI's Large Forest Fire archive** (`out/tr_lff_check.csv`): of 616 large fires recorded in the reserve divisions, 84% have one of our scars inside their detection box and dates. Ratapani was 98%. The scars cover a median 43% of each box.

## Live
`../scripts/live.py` now runs on all of MP with `mp_beats_aoi.geojson`, writing to `live/`. What changed:
- A WorldCover forest filter for NASA points (`LIVE_FOREST_MIN`, default 0.10). FSI points are already forest-masked.
- Parallel scar finding (`LIVE_THREADS`, default 8).
- Retries on the FSI portal.
- Beat tags from all MP beats.
- The alert ledger is written together with the events, so a crash never loses an event.

The test run on 15 Oct found 113 events and 18 scars, with no errors. The field app's daily scar job now points at this AOI and folder.

## Rest of MP (running)
`out/set_rest_of_mp.csv` holds the 153,817 remaining forest events, newest first. They are being processed into `out/scars_rest_of_mp.csv`. The run can be resumed, and at about 45 events a minute it takes roughly 2-3 days.

## Queued method upgrades (from the FSI thread's ML test, 16 Oct; ratapani/fsi/scouting/burn_scar_ml*.md)
These are deliberately not applied while the 2017-25 history run is going, so the whole history stays on one method.
1. Flag the learned-model (PN) patches that have no alert as `no_alert`, then spot-check them on Wayback. Recall goes from 0.84 to 0.87. Small fires get 74% of nearby burned ground instead of 49%.
2. Add a dMIRBI / dNBR2 vote, plus GABAM's "NBR below last year's minimum by >0.1" gate against leaf fall.
3. Build a hand-labelled truth set of about 200 Wayback chips, using a design-based sample (Padilla 2015), before any U-Net or Prithvi model.
Per-pixel burn dates were tested and add nothing: S2/Landsat cannot date a burn inside the image gap, so keep the dates from VIIRS and FSI.

## Wider search around the alert? (17 Oct, big-fires result 14c; `scripts/radius_test.py` -> `out/radius_test.csv`)
Big fires found that real hot pixels sit at the edge of their VIIRS block or just outside it, with ~250 m position error. So we tested a search circle reaching the block edge + 250 m (median 565 m) and 450 m, against today's 200 m, on the same 250 fires and 250 controls from the MP sample (same images for every radius).

| search radius | fires with a clear scar | controls with a "scar" | fires minus controls |
|---|---|---|---|
| 200 m (current) | 73.6% | 4.4% | 69.2 |
| 450 m | 83.6% | 13.6% | 70.0 |
| block edge + 250 m | 86.8% | 19.2% | 67.6 |

**Verdict: keep 200 m.** A wider circle finds 10-13 more fires in 100, but it also gives a "scar" to 9-15 more control points in 100, so the extra finds are mostly other burns that happen to be nearby, not this alert's fire. The 200 m circle already works despite the block-edge offset because the scar is a connected burned patch, which is much bigger than the hot line and reaches back toward the alert point. Scars found at both radii keep the same area in the median case (total +13%, from neighbouring patches). This sample scores lower than the 84.4% headline (different random draw); the comparison between radii is what matters.

## History outline files (changed 18 Oct)
The old single appended file `out/scars_mp_hist_geom.csv.gz` had 7 corrupt batches, from runs killed mid-write or the shared-folder outage on 17 Oct (only one process ever wrote to it), so plain `pd.read_csv` stopped part way. It is kept untouched as `out/scars_mp_hist_geom.backup_2026-10-18.csv.gz`.
- `out/scars_mp_hist_geom_part1.csv.gz`: everything recovered from it, rewritten as one clean gzip (73,310 outlines, passes `gzip -t`).
- `out/scars_mp_hist_geom/`: one small gzip per batch of 50 events from now on, written to a temp name and renamed, so a killed run cannot leave a broken file. The 57 events whose outlines were lost were redone and are in here too.
- Read everything with `scripts/read_geom.py` `read_hist_geom()` (columns event_id, geometry as WKT); the weekly report uses it. Stats per event stay in `out/scars_mp_hist.csv`.

## MP 2017-25 history: finished 19 Oct 2026 (`out/history_by_year.csv`)
All 153,817 forest fire events outside the tiger reserves are done (plus the 12,586 tiger-reserve events and the check sample run earlier). Results per event: `out/scars_mp_hist.csv`; outlines via `read_geom.read_hist_geom()`. 36 events ended in an error and 86 are "waiting" (no clear later image); they are left as they are.

| year | fire events | clear scar | any scar | burned ha (each patch once) |
|---|---|---|---|---|
| 2017 | 18,898 | 89.5% | 94.4% | 996,692 |
| 2018 | 22,139 | 90.1% | 94.4% | 1,067,774 |
| 2019 | 14,614 | 89.5% | 94.0% | 591,727 |
| 2020 | 6,477 | 82.2% | 89.7% | 210,798 |
| 2021 | 30,983 | 78.5% | 89.1% | 1,167,136 |
| 2022 | 23,762 | 87.3% | 92.2% | 1,024,731 |
| 2023 | 12,570 | 83.1% | 90.0% | 393,488 |
| 2024 | 11,318 | 79.4% | 88.5% | 349,166 |
| 2025 | 27,688 | 89.5% | 93.3% | 1,087,652 |

- Burned area is the union of grown outlines at 20 m, all of MP, 15 Feb-15 Jun; adding up each fire's scar would give about 2.3x more because neighbouring fires share ground.
- The outlines are not clipped to forest, so some of this is grass, scrub or farm edge next to the forest. Treat the yearly totals as upper values and the year-to-year pattern as the reliable part.
- Fire years swing about 5x (2020: 0.2 M ha, 2021: 1.2 M ha).

**"Normal for this date" now works.** The 2025 example report (week 14-20 Apr 2025, `live/reports/example_2025-04-20_with_normal/`) compares each division's season so far with the median of 2017-24 to the same day. MP had 0.90 M ha burned by 20 Apr 2025 against a normal of 0.62 M ha (1.4x); 44 of 84 divisions were more than 1.5x their normal (e.g. Shivpuri 10x, Neemuch 6.8x, Panna TR 4.8x).
