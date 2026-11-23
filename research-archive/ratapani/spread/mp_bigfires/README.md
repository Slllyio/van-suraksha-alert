# 24 h burn-scar map on big unseen fires across MP (Oct 19 2026, Akkshay 09:30Z)

600 big fires outside Ratapani (+5 km), 2017-25: history scar >= 200 ha, >= 4 VIIRS looks, >= 10 alerts; 3,535 forecasts (every look with a later look).
Map = 265 m blocks + learned 24 h area (trained on Ratapani only), nearest-first. Prithvi order is Ratapani-only, so not used here.
Truth = union of MP history scars, timed by a straight-line blend of VIIRS looks (as s2_statewide.py). Scripts: ../scripts/mp_bigfire_apply.py, mp_bigfire_figs.py.

| Map | Mean overlap per fire | Median forecast |
|---|---|---|
| Blocks only | 0.456 | — |
| Today's rule (24.1 ha/front) | 0.490 | 0.521 |
| **New map (learned area)** | **0.529** | **0.568** |
| True area (ceiling) | 0.577 | 0.603 |

- New map vs rule +0.038 (CI 0.035-0.042); better on 500 fires, worse on 60; better in every year 2017-25.
- Median area added: rule 24 ha, learned 141 ha, true 242 ha: still under-drawn on big fires.
- Scores run higher than Ratapani (0.46-0.49) partly because the statewide timing truth is built straight from the VIIRS looks, which favours dot-based maps. Read the gain, not the level.
- best_cases.pdf / case_NN.png: 12 best fires (>= 4 looks, scar >= 300 ha, ranked by new-map score, max 2 per division). These are the best, not typical; fires_summary.csv has all 600.

## Small MP fires (20-200 ha scars, >= 2 looks, 2,000 fires / 6,187 forecasts)
Rule 0.457, learned area 0.462 (+0.005, CI 0.002-0.007; better 1,037 / worse 736), true area 0.506. The learned area mostly helps big fires; on small ones it is about the same as the rule. Rows appended to unseen_validation/app_handoff/mp/mp_rows.csv (size_class=small).

## Why some fires map well (Oct 19 ~12:45Z, Akkshay "are these interior or forest staff won't reach")
Script ../scripts/mp_bigfire_why.py; why/fire_table.csv (600 fires), why/why.json. Access = mp_grid static_gis_v1 averaged over the cells under each scar.

| Best quarter vs worst quarter (medians) | Best | Worst |
|---|---|---|
| Map score | 0.66 | 0.38 |
| Share of scar within 265 m of a VIIRS dot | 60% | 32% |
| Dots per 100 ha of scar | 5.7 | 3.3 |
| VIIRS looks | 7 | 5 |
| Scar ha | 549 | 670 |
| Distance to village (km) | 2.2 | 2.2 |
| Distance to road (km) | 1.4 | 1.4 |
| Depth inside forest (km) | 1.4 | 1.5 |

- NOT remoteness/access: every access layer has |Spearman| <= 0.06 with the score, also after removing dot coverage; held-out R2 of access + ground = -0.10 (no skill). Remote third 0.53 vs near-village third 0.53.
- It is how well the satellite saw the fire: dot coverage of the scar alone explains R2 0.39; fire record (coverage, dots per area, looks, compactness, hours) 0.50. Good cases = fires VIIRS saw densely and often, so the scar is mostly where the dots were. Bad cases = scars much larger than the dots: ground VIIRS never saw burning (weak/under-canopy burning, missed passes) or outline unions that took in nearby separate burns.
- Part of this is built in: the timing truth is drawn from the VIIRS looks, so dot-rich fires are easier on both sides.
- Divisions: North Betul 0.64, Kuno 0.64 best; Jabalpur 0.41, Khandwa 0.49 worst; these follow dot coverage, not access.

## Sentinel-3 SLSTR as extra looks (19 Oct; slstr/) — DEAD END
Akkshay 12:41Z "how to increase the satellite see". Free Sentinel-3 SLSTR (1 km, ~22:20 IST night and ~10:30 IST day passes) via Copernicus Sentinel Hub,
fetched per orbit for all 600 big fires (4 days before to 1 day after; 11,925 looks). Hot pixel = 3.7 µm (F1) and 3.7-11 µm contrast both above the box median
by a robust z and a kelvin margin; thresholds tuned on pre-fire looks (false) vs looks within 8 h of the fire's VIIRS dots (calib2.csv).

| threshold | false looks (pre-fire) | burning looks caught |
|---|---|---|
| night z4 / 8 K | 4.0% | 20% |
| day z4 / 8 K | 2.2% | 19% |
| strict z6 / 12 K | ~1% | 8-11% |

Added as extra points to every 24 h map (same learned area, same truth from VIIRS looks; s3_map_test.py):

| map (mean per fire, 600 fires) | normal | strict |
|---|---|---|
| learned (today) | 0.529 | 0.529 |
| + SLSTR points since last VIIRS look | 0.527 | 0.527 |
| + all SLSTR points so far | 0.510 | 0.522 |
| forecasts where SLSTR saw burning VIIRS had not (636 / 249) | 0.516 -> 0.483 | 0.507 -> 0.487 |

- Worse on 249-305 fires, better on 67-70. Only 29-33% of SLSTR's "new" points fall inside the final scar.
- Cause: position. Even within 4 h of a VIIRS look, SLSTR's hot pixel sits a median 1.5-1.8 km from the nearest VIIRS dot, and it sees only big hot fronts
  (1 in 5 burning looks). VIIRS 375 m is already the finest thermal look; a 1 km look cannot place burning finely enough for a 20 m map.
- The 30 m Sentinel-2 mid-fire scene (section 16 / unseen_validation s16-18) remains the only extra source that improves the map.
