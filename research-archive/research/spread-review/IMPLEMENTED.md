# Spread improvements: what was built and how well it works (16 Oct 2026)

> **Correction (16 Oct, 17:40Z): see [HONEST_TESTS.md](HONEST_TESTS.md).** On mid-fire photos, which are truth not built from the dots, the plain rule "ground closest to any dot burns first" beats the chance model (AUC 0.84 vs 0.63). The model's "70% vs 39% for persistence" below was mostly self-graded. The arrival map (82%) and "model beats the 600 m ring" still hold.

Follows the ranked list in [README.md](README.md) section 4. All of it was built from VIIRS points and scar outlines v1 only, with the season held out when scoring. Scripts are in `scripts/`.

## Item 2: a "when did the fire reach here" map for each fire (`arrival/`)

**How it works.** Each 20-40 m pixel gets an arrival time:
- Pixels inside a VIIRS pixel footprint (the real scan x track box, not just the point) get the time of that detection.
- Pixels outside every footprint get the detection time plus their distance from the footprint, crossed at a set speed.
- The speed and an optional "started before first alert" offset are chosen with each season held out. Every season picked 10-15 m/h and no offset.

Script: `scripts/a1_arrival.py`.

**Checked against 340 mid-fire Sentinel-2/Landsat photos** of 288 fires, each a 20 m picture of burned-so-far at an exact minute (fuel thread's chips):

| method | pixels right (burned / not yet) | median error in share burned |
|---|---|---|
| arrival map | **82%** | **8 points** |
| VIIRS footprints only | 77% | 12 points |
| "whole scar burned once first detected" | 67% | 22 points |

**Dated truth for 848 multi-look fires** (`arrival/arrival_px.parquet`, from `scripts/a2_arrival_all.py`): every 40 m pixel of each outline with its arrival time. 98% of outline pixels date to within 24 h of the fire's last detection. This replaces the 10-day image window as the spread truth.

## Items 1, 4 and 5: calibrated chance that a cell burns in the next 12 / 24 / 48 h (`forecast_burn/`)

**Issue times.**
- A forecast is issued at every 13:30 and 01:30 IST satellite look of every fire, from its first detection to two looks after its last one.
- Only points seen up to that look are used.
- The silent looks after a fire are included, so the model learns how likely it is that a fire is still going (item 4).
- 15,041 issue times, 5.5 million cells on a 150 m grid within 2 km of the fire.

**What it learns from:**
- distance from the latest points and from all points so far
- the fire's direction of travel from its first look to its latest (item 5)
- hours since the fire was last seen and number of silent looks
- fire strength (FRP)
- ground that burned earlier this season
- height relative to the fire, slope and land cover

**Chances.**
- The model is LightGBM, with isotonic calibration learned only from other seasons' held-out predictions.
- Training labels come from the arrival maps above (`scripts/f1_build.py`, `f3_arrival_labels.py`, `f2_train.py`).
- Final models trained on 2017-26 are saved (`f4_final.py`).

**Results, newly burned ground.** "Caught in the same area as persistence" means the share of newly burned ground covered when each method picks the same amount of ground as persistence. Persistence = 475 m around everything seen.

| | caught in the same area as persistence, 24 h | AUC 24 h | Brier skill 24 h |
|---|---|---|---|
| persistence | 32% (LOSO) / 39% (2025-26) | | |
| 600 m ring, as calibrated chances | 52% / 59% | 0.86 / 0.89 | 0.16 / 0.17 |
| **new model** | **63% / 70%** | **0.91 / 0.93** | **0.21 / 0.22** |

- **Shorter and longer horizons.**
  - At 12 h the model catches 81% in held-out seasons and 85% in 2025-26.
  - The ring catches 67% and 72%, and persistence 48% and 55%.
  - At 48 h the model catches 53% and 60%, against 45% and 52% for the ring.
- **The chances are honest.** When the model says 30-40%, 35% of those cells burned in held-out seasons and 34% in 2025-26. When it says 10-20%, 13% and 12% burned (`forecast_burn/reliability.csv`).
  - In 2025-26 it runs 1-2 points high below 30%.
  - Above 70% there are few cells, and the forecast is a little too high.
- **Forward test.** 2025-26 was never used for choosing settings, and it scores as well as the held-out seasons.
- **What matters most:** distance from the latest look, then the hours since the fire was last seen.

**The same model scored on raw VIIRS points instead of arrival maps** (`forecast/`, harder because a satellite sees only about half the fire):
- At 12 h it catches 37% in 2025-26, against 29% for the ring and 21% for persistence.
- AUC is 0.79 against 0.74.
- The order of the three methods is the same.

**Honest limit.** The arrival-map labels are built from the same VIIRS footprints plus a fixed speed. So part of what the model learns is that rule, and the raw-point score above is the stricter test. A fire that jumps 1.5-2 km gets only a low chance. One case is in `forecast_burn/example_2026-03-16.png`: the fire that moved south-west the next day.

**Run it for any moment.**

```
python3 scripts/forecast.py 2026-03-16T09:00 out.geojson
```

This writes 150 m squares with p12, p24 and p48 for every fire seen in the last 36 h. Squares already inside a detection footprint are marked `burned=1`.

## Not done here, and who has it
- **Item 3, redrawing outlines cut at the 3 km image edge:** the scar thread has it (v2), so this folder doesn't edit `fire-alert-scars/`.
- **Item 6, physics only for flame size:** this is a recommendation for the spread thread.
- **Item 7, more timed images:** new data downloads; not started.
