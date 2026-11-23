# Multi-front tracker and growth/stop model (17 Oct 2026)

Akkshay's development order (17 Oct 07:43Z): build multi-front tracking first, then horizon-specific growth and stopping.

- Data: the 146 big fires; scar outlines v2.
- Truth: the burn state at any hour, from the fire-continuity blend map.
- Forecast: issued at every VIIRS look (813 issues), for the burn state 24 h later.
- Scripts: `../scripts/mf_tracker.py` (stage 1), `mf_eval.py` (stage 2), `mf_tracker_lib.py`.
- Files: `mf_fronts.parquet` (one row per front per issue), `mf_issues.parquet`, `mf_scores.csv`, `mf_summary.json`.

## Tracker
At each look it uses only what has been seen so far.

- **Fronts.** Dots so far are linked into fronts when they lie within 750 m of each other.
- **Active fronts.** A front is active if it had a dot in the latest two looks.
- **New dots.** A new dot farther than 750 m from everything earlier opens a **separate front**. Beyond 3 km it counts as an **independent start**.
- **What it found.**
  - 28% of looks (226 of 813) open at least one separate front: 257 separate fronts against 572 continuing ones.
  - Independent starts beyond 3 km are rare (8). This is within big fires only; separate fires are grouped apart already.
  - Separate fronts grow about as much as continuing ones: median 28 vs 32 ha in the next 24 h.

## Growth and stop model (per active front, LightGBM, each season held out)
Target: the true new burned area within 1 km of the front in the next 24 h. Median 24 ha; 33% of fronts add under 2 ha ("stopped").

| | Learned | Same for every front (training median) |
|---|---|---|
| Within 2x of the true growth | **39%** (first reported as 70%: scoring bug, corrected Oct 17) | 23% (first reported 59%) |
| Typical error (log scale) | 0.93 | 1.53 |
| Ranking of fronts by growth (Spearman) | 0.59 | - |
| "Will it stop?" (AUC, 0.5 = coin toss) | **0.80** | - |

The strongest inputs are how far the fire is into its run (look number and hours), the number of dots at the latest look, the fire's
dots so far, the grass share and the latest FRP. Correction (Oct 17): the first version of mf_eval.py counted every under-forecast as "within 2x" (a missing absolute value); the
corrected numbers are 39% vs 23%. The error and AUC rows were not affected. See unseen_validation/ for how this holds on new fires.
So the per-front growth and stop prediction works on these 146 fires. It is the first thing here that
explains the too-big and too-small fires.

## Maps for the burn state 24 h ahead (overlap with the real burn, median of 813 issues, 1 = perfect)
| Forecast | Overlap |
|---|---|
| Only what's already seen (375 m blocks of every look) | 0.49 |
| One blob around all dots, size from the growth model | **0.53** |
| Each active front grows its own predicted amount | **0.53** (difference -0.000, 95% range -0.001 to +0.001) |
| One blob, true size (oracle) | 0.59 |
| Each active front, true size of its own growth (oracle) | 0.55 |

Two findings:

- **The growth model adds +0.05** over the footprints alone (95% range +0.047 to +0.058). It recovers about half the gap to perfect size.
- **Tracking fronts separately does not change the map.** Growth is placed near dots either way, and the dots that matter are the
  recent ones. What still goes missing is fronts that haven't been seen yet. Pooled over all issues, **34% of the next day's new
  burning lies more than 1 km from every dot seen so far** (median issue 15%). No tracker can place a front before a satellite sees it.

## What this means for the development order
1. Keep the tracker for **describing** a fire: which parts are active, which are new fronts, how much each is likely to grow, and whether
   it will stop. That is useful to field staff even though the overlap score doesn't move.
2. The remaining gap is **new-front risk**, a separate output as the audit says. The spread review found that a 1-2 km ring finds new
   fires no better than random (6 vs 5%). The FSI check found these jumps are mostly separate human starts. So this belongs with the
   ignition-risk work (beats, villages, roads, time of day), not the spread engine.
3. Next here: put the growth/stop model into the per-look forecast. Then test new-front risk at 1-3 km from active fires using ignition
   history and distance to villages and roads, scored on the same issues.

## Are "new fronts" really fronts that were hidden on a sideways pass? (heat-thread lead)
| How the look before was seen | Looks | Share that open a separate front |
|---|---|---|
| Pixel at or under 0.45 km (near straight down) | 289 | 32% |
| 0.45-0.6 km | 303 | 36% |
| 0.6-0.8 km (sideways, >~45 deg) | 51 | 26% |

| Hours since the previous look that saw the fire | Looks | Share that open a separate front |
|---|---|---|
| 6-14 h (the next regular pass) | 459 | 29% |
| 14-30 h (at least one pass saw nothing) | 130 | 42% |
| over 30 h | 78 | 47% |

So the sideways view of the previous detection doesn't matter. What matters is **missed passes**: after a gap with at least one pass
that saw nothing, a new front is 1.5x more likely. Part of the "new fronts" are fronts burning unseen during a missed pass. The fix is
to treat each covered-but-empty pass by its detection chance (view angle x leaf state, from the heat thread) rather than as "no fire".
That needs the per-pass coverage list (which passes looked at the spot), which isn't built yet.

## Are the "new fronts" a different fire? (Akkshay, 07:54Z)
A big fire here is one burn-scar outline. The big-fires thread joined scars dated within 3 days that overlapped by 30% or more, so two
fires that burned into each other count as one. Check on each new front: draw the straight line to the nearest earlier dot and see
whether it crosses ground that never burned at all (outside the final outline) for more than 300 m. Fire cannot creep across that.

| Front type | Fronts | Median distance to earlier dots | Cut off by never-burned ground |
|---|---|---|---|
| Continuing (within 750 m) | 572 | 370 m | 7% (noise level) |
| New front 0.75-1.5 km away | 201 | | 32% |
| New front 1.5-3 km away | 56 | | 73% |
| Independent, beyond 3 km | 8 | 3.5 km | 88% |

So **about 4 in 10 new fronts (41%) are cut off from the fire by unburned ground**. They are almost certainly a separate start: another
fire, or a person lighting it, that later merged into the same outline. That holds for most fronts beyond 1.5 km. The rest (the
majority at 0.75-1.5 km) are joined to the fire by burned ground and could be real spread hidden from a missed pass. Embers jumping
are unlikely in litter fires. The line test is straight, so fronts joined only around a bend count as connected, which errs on the
side of "same fire".

## New-front risk 1-3 km out (`mf_newfront.py`, `mf_newfront.json`)
Setup: 100 m cells 1-3 km from every dot so far, at all 813 issues (2.3 million cells). A cell counts as a hit if it gets new burning
in the next 24 h. Base rate 1.9%. LightGBM with each season held out, inputs known at issue time: distance to dots, direction vs the
fire's latest growth, distance to roads and buildings, forest and grass share, seasons burned before, hour, look number, dots so far.

| | Model | Distance alone | Random |
|---|---|---|---|
| Ranking over all cells (AUC) | 0.79 | 0.73 | 0.50 |
| New burning caught in the top 5% of cells, per issue | 33% | **35%** | 5% |

The model ranks better overall only because it knows which fires are still growing (look number, dots so far). **Within one fire, it
picks where the new front appears no better than "closer is likelier"**; direction, roads, villages and burn history add nothing.
Caveat: hits are counted only inside the fire's final outline, which flatters every method about equally.
So the new-front risk map is a distance band, scaled up for fires still growing. The cut-off fronts (separate starts) stay unpredictable in place.

## Per-look forecast tool (`../scripts/forecast_fronts.py`, models in `models/`)
`python3 forecast_fronts.py detections.csv out.geojson [issue_time_utc]` takes one fire's VIIRS detections so far and writes:
- **Each front** with its status (continuing, new front, separate start, old), its expected new burning in 24 h with a rough 2x band,
  and its chance of stopping.
- **The burned blocks so far.**
- **The 24 h forecast area**: each active front grows its own expected area, nearest ground first.
- **The 1-3 km new-front band.**

Demo: `demo_102.csv` gives `demo_102.geojson` (big fire 1, issued 28 Feb 2017 13:30 IST).

Limits: the models are trained on the 146 big Ratapani fires. The tool has not been checked on live alerts. The 24 h area has the
skill measured above: overlap 0.53, against 0.49 for the burned blocks alone.
