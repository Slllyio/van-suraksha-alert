# VIIRS 375 m fire masks: pulled, and what they add (17 Oct 2026, "Earthdata pulls" thread)

**Plainly: the masks add almost nothing to "has this front stopped?" or to the travel direction.** A pass that looked at the front in clear sky and saw no fire is followed by the fire showing up again 40% of the time. A cloudy or blind pass is followed by the same 40%. VIIRS misses burning surface fires in clear sky about as often as cloud hides them, so "looked, saw no fire" does not mean "out".

## What was pulled
- Secret route: the Earthdata secret is an agent-proxy header on `*.nasa.gov`, not an env var. The scripts send no header when `EARTHDATA_TOKEN` is unset.
- Passes: `code/squares_v2/tracking/results/fire_mask_pull_plan.csv` has 3,657 passes (845 tracking fires). `fire_mask_pull_plan_unseen.csv` has 10,894 passes on the 472 spread-unseen fires that plan left out (alerts box + 1.5 km, first alert −36 h to last +36 h; `build_unseen_mask_plan.py`).
- Pull: `pull_fire_masks_fast.py` uses 24-32 processes. It reads 03IMG geolocation over HTTP ranges (row band found from the granule's own fire pixels). 14,072 of 14,551 passes cropped; 353 had no granule, 118 fell outside the swath, 8 errored. Index: `results/fire_mask_index.csv`. The crops (276 MB) are in scratch only, at `/tmp/claude-0/fire_masks/crops/*.npz`, and are lost with the session. Rerun the pull to rebuild them (~1.5 h).

## Tables (in `code/squares_v2/tracking/results/`, built by `build_mask_tables.py`)
- **`mask_pixels_near_fires.parquet`** (55 MB, 3.83 M rows, 1,317 fires). One row per fire × pass × mask pixel within 2 km of any alert of that fire.
  - Columns: `fire, pass_key, sensor, t_pass` (UTC granule start), `lat, lon` (true 03IMG pixel centre), `cls, vza` (sensor zenith), `d_alert_m` (distance to the fire's nearest alert, any time), `d_prior_m` (to its nearest alert before this pass), `unseen` (spread-unseen fire).
  - Fire ids are the same as `research/big-fires/results/fire_alerts.csv`.
- **`mask_fire_pass_summary.csv`** (28,173 rows). One row per fire × pass, with pixel counts by class in the front zone (within 750 m of the fire's earlier alerts): `n_front, n_fire, n_clear, n_cloud, n_noinfo, n_missing`. Also `vza_med, seen_later, hours_since_last_alert`.

Mask classes: 0 not processed, 1 bow-tie deletion, 2 glint, 3 water, 4 cloud, 5 clear land no fire, 6 unclassified, 7/8/9 fire (low/nominal/high). "Looked, saw no fire" = 3 or 5; no information = 2, 4, 6; missing = 0, 1.

## Results
**Stop test** (`mask_stop_test.py`, `results/mask_stop_test.json`). Unit: a pass within 36 h of the fire's latest alert that showed no fire pixel in the front zone (12,328 passes, 1,317 fires).

| front zone in that pass | passes | fire seen again later |
|---|---|---|
| clear, no fire (≥80% class 3/5) | 7,909 | 40% |
| blind (≥50% cloud / bow-tie / etc.) | 1,845 | 40% |
| partial | 2,574 | 43% |
| (fire pixels present) | 3,856 | 73% |

- 64% of no-dot passes were clear and 15% were blind.
- By day, clear 36% vs blind 39%; by night, 42% vs 44%.
- Two clear passes in a row: 35% still come back.
- Held-out stop model (5-fold by fire): dots only (hours since last dot, view angle, satellite) AUC 0.629; adding the clear and blind shares gives AUC 0.630. No gain.

**Direction from 2-4 looks within 6 h** (`mask_direction_test.py`, `results/mask_direction_test.json`). Scored against where fire pixels sit 12-36 h later (random = 25% within 45°):

| method | within 45° |
|---|---|
| short look sequence | 18% |
| burnt-out side (fire earlier, clear now) → live side | 18% |

- Both are below chance, as positional noise predicts (the fire can be anywhere inside each 375-800 m pixel, plus ~75-150 m pointing error; big-fires README 15d, 18 Oct): a noisy middle look makes "recent motion" and "next motion" point opposite ways. Pure noise would give 4%.
- So there is some real motion in there, but it cannot be used as a direction.
- The direction signal that works is the 30 m scar edge + hot line: 51% vs 25% (`research/big-fires/README.md` §15e).

**Still useful from the masks.** They give true per-pixel geolocation and view angle on every pass, for checking footprint and offset models, and real cloud/bow-tie flags for likelihood models (`t2_lib.py` mask hook). Point `mask_dir` there after rerunning the pull.

**Confirmed by the continuity thread (21:29Z, research/fire-continuity/results/nofire.json).** Using clear no-fire pixels to delay arrival in its 20 m growth maps makes them worse on 340 mid-fire photos: 84.9% falls to 82.9 / 82.4 / 82.0% (D = 1.5 / 3 / 6 h; the CI excludes zero). Of the burned photo pixels, 25-35% sit under a clear no-fire pixel at the very look that should have seen them.

**Confirmed by the spread thread (21:30Z, ratapani/spread/unseen_validation/README.md §9), on all 818 unseen fires.**
- Fronts the satellite saw clear stopped 67% of the time, against 36% for the rest. But 95% of fronts with no dot at the latest look were seen clear anyway, so the masks repeat what the stop model already knows.
- Stop AUC stays at 0.802.
- Dropping seen-clear fronts from the 24 h map makes the map worse: 0.477 → 0.468. It was worse on 229 fires and better on 17.
