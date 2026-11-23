# Ratapani burn-label check: 102 points for an independent reviewer

Purpose: the burn-scar labels behind every model so far were judged only by Claude from satellite images (precision ~0.83, area recall ~0.71 on 400 points). A forest officer or anyone who knows the ground can tell us how much of the fire the satellites miss and how many "scars" are not fires.

## What to give the reviewer (blinded)
- `check_sheet.csv`: 102 points (point_id, season, lat, lon) with empty answer columns. The reviewer fills in: burned this season (yes / no / unsure), approximate date or month, size class, cause if known, notes.
- `check_points.kml`: the same points for Google Earth or a phone map app, each pin named by point_id.
Each point is the centre of a 500 m square. The question is whether any part of that square burned in the named season (Jan to Jun 2025 or 2026).

## What the reviewer must NOT see
- `answer_key.csv`: which points are satellite scars (new ignition or spread; caught or missed by the model) and which are unburned by the satellites (25 random, 25 the model flags often but satellites never show burning).

## Mix
| Group | Points | Tells us |
|---|---|---|
| Satellite scar, new ignition, model caught | 13 | precision of scars; date accuracy |
| Satellite scar, new ignition, model missed | 13 | are the misses real fires? |
| Satellite scar, spread, model caught | 13 | |
| Satellite scar, spread, model missed | 13 | |
| No satellite scar, model flags the cell often | 25 | fires the satellites miss (small, understory, cloudy) |
| No satellite scar, random | 25 | baseline miss rate |

## How it will be read
Scar precision = yes / (yes + no) in the scar groups; satellite miss rate = yes in the no-scar groups (random vs model-hot tells whether the model is right where the labels are blind). Dates compare with each scar's window (in the key). 100 points give about ±8 points on each rate.

Made 14 Oct 2026 by the Fire prediction research thread from `/mnt/project-files/research/ratapani-ignition/` (patches.csv, combined model 2025-26 rates) and `/mnt/project-files/ratapani/grid_500m.geojson`.
