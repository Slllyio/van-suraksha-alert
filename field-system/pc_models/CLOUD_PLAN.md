# Cloud morning scoring: input builder plan (19 Oct 2026)

`live_score.py` needs, each issue day, one feature table per division (129 inputs in all; definitions in van-suraksha-alert
`mp/scripts/mp_features.py`, `mp_seasonal.py`, `mp_dryness.py`, `mp_proximity.py`, `mp_ee.py`). Where each input can come from
without the PC:

| Inputs | What | Cloud source | When |
|---|---|---|---|
| cell_d1..30, nb3/nb7_d1..7, aoi_d1..7, dsl, fdist_d3..30, quiet | VIIRS fire history around the square | the app's own alerts (Bhuvan/FSI/NASA) + FIRMS archive | daily |
| clim_cell, clim_nb7, early_cell/nb3/nb7 | fire climate of earlier seasons | FIRMS archive (alerts_mp/) | once per season |
| tmax, rh, vpd_max, vpd_3, wind, prcp_mm/7/30, dry_days, swvl1 | division-mean weather (GFS of the issue day in the live models) | NOAA GFS on public AWS (no key) | daily |
| ndvi, ndmi, lst_k, *_anom, *_chg16/32, ndmi_d16, ndvi_peak, leaf_loss | MODIS 8-day (MOD09A1, MOD11A2), 9-day availability lag | Planetary Computer modis-09A1-061 / modis-11A2-061 (no key) | 8-daily |
| hls_* | HLS 10-day dryness | Planetary Computer HLS, or NASA LP DAAC with the Earthdata secret | 10-daily |
| ae00..ae15 | AlphaEarth of last year, PCA-16 | Earth Engine only | ONCE a year, exported by the PC before 15 Feb |
| terrain, WorldCover wc_*, population, proximity dist_*, the 33 static GIS | fixed per square | static_gis_v1.parquet + one PC export | once |

So the daily run needs no Earth Engine and no PC. The PC is needed once a year for one static table (AlphaEarth + EE statics).

## Needed from the PC (one-time)
1. `static_<season>.parquet`: cell, division, ae00..ae15 (the exact PCA it trains with) and every static column of the
   feature tables (terrain, wc_*, population, proximity), for all 430,776 division squares.
2. The GFS-to-feature code used for the live models (not in the pushed scripts; pushed code reads ERA5).
3. Two divisions' full feature tables for 2026-04-05 (as fed to live_score.py), to check the cloud rebuild column by column.
4. The 87 model files (waiting on Akkshay's shipping pick).

## Build order here
1. Fire-history inputs from the archive, checked against item 3.
2. GFS weather, MODIS and HLS readers, checked against item 3.
3. Daily job in the app: build tables -> live_score.py -> POST /api/v1/daily_scores. Then a replay of the 5 check days.

## Progress (19 Oct 2026, 13:20Z)
- Fire history (`app/cloud_features.py`): built from the FIRMS archive; the `quiet` column matches the PC's
  live_flags_2026-04-05 on all 430,776 squares (100%), so grid, IST dates and the 5 km box are right. Other columns wait for item 3.
- HLS dryness (`app/cloud_hls.py`, Planetary Computer, 45 s per 128 x 128-cell tile): against the PC's Earth Engine pull for
  2025-03-23, tile 6/5 (3,725 cells): r 0.98 for NDVI/NDMI/NBR, median difference 0.006-0.010, same means
  (`scripts/cloud_hls_check.py`). Planetary Computer misses some 2026 scenes (none for Ratapani in March 2026); NASA LP DAAC
  with the Earthdata secret is the fallback.
- MODIS (`app/cloud_modis.py`, Planetary Computer MOD09A1 / MOD11A2): reads; exact check waits for item 3.
- GFS weather: waits for item 2.

## 20 Oct: statewide replay (field-system/docs/cloud_scoring/README.md)
Cloud GFS + ERA5 soil + MODIS, all 87 divisions, 5 days: 92% same flagged squares, fires caught 60.2% vs PC 60.1%
(8,355 fire squares). Left: cloud HLS statewide (r 0.94 on Ujjain, slow), own_count state.
Issue time (PIPELINE, 20 Oct): the 2-day list goes out at 17:00-18:00 IST, after the ~16:30 IST VIIRS pass and that day's GFS.
Real input ages are MODIS about 21 days (the models assume 9), soil 15 days (they assume 5) and HLS about 10 days later than
assumed. PIPELINE is rescoring 2026 with those delays. Once it settles the delays, the cloud run will use the same ones, so a
statewide HLS step taking 6.5 min is not a problem.
Real-delay rescore (PIPELINE, commit 6000933): with MODIS 21 days old, soil 15 days old and HLS 10 days late, the live rule
scores 66.7/47.3/82.1 against 67.5/47.6/82.3, so the models are not retrained. The cloud job runs at about 17:00-18:00 IST and
uses the newest MODIS, soil and HLS that have arrived, with GFS 00Z from NOAA.
20 Oct, every input from the cloud (HLS + mapped soil too): 92.1% same squares, fires caught 60.5% vs PC 60.1%. Still to do:
a nightly runner with the season's own_count state, timed for 17:00-18:00 IST.
Big-fire watch list (Akkshay, 20 Oct 09:22Z): the large-fires model becomes a separate daily watch list of the top 1-2% of
squares. It is its own layer in the evening runner and in the app, and it never changes the daily list. The large-fires
thread is packaging the model; numbers are in research/large-fires/README.md.
Division start dates (Akkshay, Prithvi thread card, 20 Oct 12:41Z): scripts/cloud_daily.py issues a division only from 20 Feb
(early group, 7 divisions), 1 Mar (mid group) or 20 Mar (late group, 9 divisions). The big-fire watch list uses the same dates.
"Early March" is read as 1 Mar and "late March" as 20 Mar. The 10 small divisions keep their own models: the timing-group
fallback lost in PIPELINE's 2026 live-rule check.
