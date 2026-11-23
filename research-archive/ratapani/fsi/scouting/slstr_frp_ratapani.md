# Sentinel-3 SLSTR fire pixels over Ratapani, 2021-2026 (FSI thread, 15 Oct 2026)

**What this is.** These are the Sentinel-3A/3B SLSTR Level-2 fire radiative power (FRP) pixels from the EUMETSAT Data Store (collection `EO:EUM:DAT:0417`), pulled for January to June of 2021-2026. The box is 77.3-78.4 E, 22.6-23.4 N. They were then compared with every FIRMS alert in `fire-alert-scars/alert_scar_lookup.csv` (S-NPP, NOAA-20 and MODIS) and with the first-burn scar windows. This is our own analysis; there is no literature in this note.

**Access.** The Data Store needs Akkshay's EUMETSAT consumer key and secret, read from the env vars `EUM_KEY` and `EUM_SECRET`. These are never stored anywhere. Note that the Data Store does NOT carry the LSA SAF Meteosat FRP-PIXEL product, which needs a separate LSA SAF account. Each SLSTR product is about 21 MB, and about 500 products cover the box each Jan-Jun season. The archive over Ratapani starts in January 2021.

**Files**
- `data/slstr_frp_fires_box_2021_2026.csv`: 20,247 fire pixels in the box. `time` is in microseconds since 2000-01-01 UTC. The FRP columns are in MW, and the box includes farmland.
- `data/slstr_frp_passes_2021_2026.csv`: 2,970 products that cover the box.
- `data/slstr_frp_ingrid_matched.csv`: the 1,191 pixels inside the Ratapani 500 m grid, with FIRMS-match, scar and control flags.
- `code/slstr/pull_slstr_frp.py` is the resumable puller. `code/slstr/analyse3.py` is the comparison.
- Products from 2025 onward use a new layout (`FRP_MWIR1km_standard.nc`, processing baseline 003); the puller handles both layouts.

## Pass times over Ratapani
- Day pass: 09:00-10:59 IST, mostly around 10:20-10:50.
- Night pass: 21:00-22:59 IST, mostly around 22:00.
- The polar VIIRS passes are at about 01:30 and 13:30, so these two passes fill the morning and late-evening gaps.
- Products are created about 2 h after sensing (NR timeliness).

## Results (in-grid pixels; controls are random grid cells at the same times)
| | n | FIRMS within 1 km, ±12 h | control | on a first-burn scar window | control |
|---|---|---|---|---|---|
| Morning (~10:30) | 373 | 25.5% | 4.8% | 22.8% | 5.4% |
| Night (~22:00) | 818 | 58.7% | 7.1% | 29.2% | 12.6% |

- **Night pixels are real fire.** Of the night pixels, 33% had a FIRMS detection in the previous 15 h, and 31% had none before but one in the next 16 h. So about a third of the 22:00 pixels are the first sighting of a fire that VIIRS sees only at 01:30 or 13:30 the next day.
- **Morning quality depends on the processing version.**
  - In 2022 there was a burst of 218 low-FRP (5-10 MW) morning pixels near cloud. Only 10% match FIRMS, against 6% for controls, so they are artefacts.
  - Old-baseline morning pixels with no FIRMS match sit on a scar only 7.9% of the time, close to random.
  - On the new 2025-26 baseline, morning pixels match FIRMS 72-75% of the time and sit on a scar 45-72% of the time (controls 3-5% / 6-15%).
  - Morning pixels above 20 MW (any year): FIRMS match 74%, scar 64%.
- **Little gain for dating or labels.**
  - SLSTR gives 115-136 in-grid cell-days per season, against 1,366-1,807 FIRMS alerts.
  - Only 5 (2025) and 10 (2026) SLSTR pixels sat on a scar with no FIRMS detection within ±12 h.
  - It adds at most about 1% new dated burns. It is useful mainly as an extra time point (22:00) for fires VIIRS already sees.

## What to do with it
1. **Cleaner fire labels:** use the night (~22:00) pixels as an extra time point when dating.
   - A burn first seen by SLSTR at 22:00 started that day.
   - Do not add old-baseline (2021-24) morning pixels unless FRP is above 20 MW and there is no cloud nearby.
   - Expected gain is small (about 1% more dated burns).
2. **Field alerts:** a "morning fire" hint from SLSTR is usable only on the current baseline, and the volume is low (about 20-40 in-grid hits per season).
   - Suggested filter: FRP above 10 MW and `n_cloud == 0`.
   - The 22:00 pass could give an overnight alert about 2 h later, roughly 3.5 h before VIIRS's 01:30 pass reaches FIRMS.
   - This needs `EUM_KEY` / `EUM_SECRET` in the environment settings.
3. **2-day / spread:** SLSTR does not add enough cell-days to change any target. The spread thread can use the 22:00 time stamps as an extra front position for multi-day fires.
