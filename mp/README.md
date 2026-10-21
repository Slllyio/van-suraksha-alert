# MP fire outlook — all 87 forest divisions (research)

## Headline: every MP division (`scripts/mp_all_eval.py`, `results/all_divisions.csv`)
Best design applied to all 87 divisions (~1.05 M cells of 500 m): each division's own LightGBM model on
3-satellite VIIRS labels/fire history (S-NPP + NOAA-20 + NOAA-21) plus the 10-day HLS dryness; train 2019–2021,
test 2022–2024 (246,790 fire cell-days, scored against fires seen by any of the three satellites).
Top 10% of each division's test cell-days flagged, a fire counts if a flagged cell is within 1 cell:

| | |
|---|---|
| MP-wide fires caught (fire-weighted) | **80.5%** |
| Median division | 80.8% |
| Brand-new fires (no fire within 5 km in 7 days) | 46.8% |
| Divisions at 80–90% / 90%+ | 45 / 3 |
| Divisions at 70–80% | 29 |
| Divisions below 70% | 10 (mostly small, low-fire divisions: Shajapur 26 test fires, Rajgarh 54, Mandsaur 275) |
| Best | Barwani 94.3%, North Balaghat 92.7%, Singrauli 91.5% |

Recall rises with the amount of local fire history (correlation with log fire count 0.39), so the weakest divisions
are candidates for borrowing from neighbouring divisions. `scripts/mp_repair.py` finds and removes corrupted
Earth Engine CSVs left by interrupted runs (17 files in 13 divisions were regenerated).

## Forward test: frozen 2019–2024 model scored on 2025 and 2026 (`results/officer/forward_fwd*.csv`)
Per division one model trained on 2019–2024 only (own data; neighbour borrowing if < 1000 own training fire cell-days:
14 of 87 divisions), frozen, then run unchanged on the 2025 and 2026 seasons. Same seasonal rules and scoring as below;
labels S-NPP + NOAA-20 + NOAA-21 (VIIRS standard processing). Feature inputs for 2025–26 use the AlphaEarth PCA and
MODIS anomaly climatology frozen on <= 2024 (2024 features reproduce the earlier tables exactly).
Note: S-NPP has no data after 27 Apr 2026, so 28 Apr–31 May 2026 labels come from NOAA-20/21 only.

| Season | Fires | Fires caught strict / loose | Brand-new fires (model / rule) | Other fires (model / rule) | Beat episodes strict / loose | Ground flagged-or-next | Flagged beats per range per day |
|---|---|---|---|---|---|---|---|
| 2025 | 30,057 | 74.6% / 76.3% | 34.0% / 3.9% | 80.7% / 56.7% | 84.1% / 85.6% | 21.0% | 3.1 |
| 2026 | 24,057 | 69.3% / 70.9% | 34.8% / 4.5% | 77.3% / 54.8% | 80.4% / 81.7% | 21.8% | 3.3 |
| **both** | **54,114** | **72.3% / 73.9%** | **34.4% / 4.2%** | **79.2% / 55.9%** | **82.5% / 83.9%** | **21.4%** | **3.2** |

"Fires nearby" rule (score = fires in the 7×7 block in the last 7 days + 0.01 × local burn climatology), all fires strict:
49.8% (2025), 45.4% (2026), 47.9% (both); beat episodes strict 62.6%. Brand-new = no detection within 5 km in the 7 days
before the first day (15.5% of fires). Back-test for comparison (train 2019–2021, test 2022–2024, same rules):
fires strict 73.2%, beats strict 81.6%, ground 20.3%, 3.0 beats per range per day. Per-cell-day predictions are kept locally.

### Static GIS inputs + separate brand-new-fire head (vanagni `data/static-gis-2026-10-18`, section 6) on the 87-division models (`results/officer/gis_{held,fwd}*.csv`)
Same divisions, labels, own/borrow rule and PC LightGBM settings for every variant (only the inputs / heads change).
gis = + 33 static inputs from `static_gis_v1.parquet` joined on mp_cell; gis_head = gis + a second model trained only on
"clear" cell-days (no type-0 fire within +-10 cells on days t-6..t), whose score is used on clear cells.
Matched ground = flag share set per division so ground flagged-or-next equals the base model's.

| Test | Model | Fires strict | Brand-new | Other fires | Beats strict | Ground |
|---|---|---|---|---|---|---|
| Held-out 2022-24 (ERA5; 50,991 fires, 11,279 new) | base | 73.2% | 39.9% | 82.7% | 81.6% | 20.3% |
| | gis, matched ground | 73.2% | 40.5% | 82.5% | 82.2% | 20.3% |
| | gis_head, matched ground | 73.2% | 37.2% | 83.5% | 82.1% | 20.3% |
| | burned before (top 10%) | 53.1% | 44.8% | 55.5% | 77.7% | 30.4% |
| Forward 2025+26 (GFS; 54,114 fires, 8,405 new) | base | 72.3% | 35.2% | 79.1% | 82.6% | 21.4% |
| | gis, matched ground | 72.4% | 36.0% | 79.1% | 82.9% | 21.4% |
| | gis_head, matched ground | 72.4% | 31.9% | 79.8% | 82.7% | 21.4% |
| | burned before (top 10%) | 49.0% | 39.5% | 50.8% | 74.1% | 30.1% |

On the PC model the GIS inputs give a small gain (brand-new +0.6 / +0.8 pts, beats +0.3-0.6, all fires flat); the
per-division brand-new head lowers brand-new catch by 2.7-3.3 pts (it moves catches to continuing fires). The cloud
result (+6.9 / +13.6 on brand-new) was on a pooled 10-division stand-in model with a weaker brand-new baseline (31.8 / 23.3).
Isotonic calibration (per division and head, fitted on the previous test season): Brier skill raw -0.89 / -0.72 ->
-0.009 held-out (fit 2022, applied to quieter 2023-24) / +0.014 forward (fit 2025, applied to 2026).

### One brand-new-fire head pooled over all 87 divisions (`results/officer/pool_{held,fwd}*.csv`)
One LightGBM (PC settings) trained on every division's own "clear" training rows (held-out 2.79 M rows / 29,225 fire
cell-days; forward 5.45 M / 63,487), with division id as a categorical input and the GIS inputs kept. Clear test cells
take its score, others the division's +GIS model. All rows at matched ground (= the current model's).

| Test | Model | Fires strict | Brand-new | Continuing | Beats strict | Cells flagged |
|---|---|---|---|---|---|---|
| Held-out 2022-24 | current (top 10%) | 73.2% | 39.9% | 82.7% | 81.6% | 10.0% |
| | + GIS | 73.2% | 40.5% | 82.5% | 82.2% | 9.9% |
| | + GIS + pooled head | 70.7% | 55.6% | 75.0% | 82.0% | 9.6% |
| Forward 2025+26 | current (top 10%) | 72.3% | 35.2% | 79.1% | 82.6% | 10.0% |
| | + GIS | 72.4% | 36.0% | 79.1% | 82.9% | 9.9% |
| | + GIS + pooled head | 68.7% | 58.1% | 70.6% | 82.7% | 9.6% |

Pooling turns the head from harmful (per-division head: brand-new -2.7 / -3.3) into a large gain on brand-new fires
(+15.1 / +22.1 pts vs +GIS; better in 85/87 held-out divisions and 166/174 forward division-seasons). But at the same
ground it moves flags away from continuing fires: held-out +1,704 brand-new caught vs -3,011 continuing (net -1,307);
forward +1,853 vs -3,879 (net -2,026). Beats are unchanged. A choice of what matters more, not a free gain.

### Equal-share control and clear-square flag-share curve (`results/officer/share_{held,fwd}*.csv`, `share_curve.png`)
Per division-day the pooled-head run's flag count on clear squares (no fire within 5 km on days t-6..t) is kept, or
scaled by f = 0-100%, and the rest of the day's flags go to other squares by the +GIS score. Clear squares are ranked
either by the pooled head or by +GIS (the "equal-share control" is f = 100% ranked by +GIS). All points at matched ground
(f = 0 cannot reach it: 18.7% / 20.9% ground instead of 20.3% / 21.4%).

| Setting (fires strict, all / brand-new) | Held-out 2022-24 | Forward 2025+26 |
|---|---|---|
| current | 73.2 / 39.9 | 72.3 / 35.2 |
| +GIS (natural share: 22% / 13% of flags on clear squares) | 73.2 / 40.5 | 72.4 / 36.0 |
| pooled head (51% / 46% of flags on clear squares) | 70.7 / 55.6 | 68.7 / 58.1 |
| **equal-share control** (same clear counts, ranked by +GIS) | **70.2 / 55.0** | **68.4 / 58.8** |
| f = 25%, pooled-head ranking | 73.9 / 42.2 | 72.4 / 40.9 |
| f = 25%, +GIS ranking | 73.6 / 40.9 | 72.4 / 41.2 |
| f = 50%, pooled-head ranking | 73.4 / 47.8 | 71.6 / 48.1 |
| f = 50%, +GIS ranking | 73.1 / 46.9 | 71.5 / 48.5 |
| f = 75%, pooled-head ranking | 72.6 / 52.6 | 70.6 / 53.3 |

The pooled head's brand-new gain comes almost entirely from giving clear squares more flags, not from ranking them
better: the equal-share control matches it (held-out -0.5 / -0.6 pts, forward -0.3 / +0.7). The curve is a trade-off
frontier; f = 25-50% keeps all-fire catch at the current level (held-out 73.4-73.9, forward 71.6-72.4) while brand-new
fires rise to 42-48% (held-out) / 41-49% (forward). Beat episodes are best at f = 25-50% (82.8-84.3%).
Note: the daily clear counts come from the pooled-head run, so they carry its day-to-day pattern.

### Fixed quiet-share rule, no second model (`results/officer/quiet_{held,fwd}*.csv`)
Each division-day, q = 20 / 25 / 30% of the day's flags go to clear squares (no fire within 5 km on days t-6..t), the
rest to other squares, all picked by the +GIS score (days with too few clear squares give the spare flags to others).
Daily count either danger-scaled (10% x today's mean +GIS score / season mean so far, 1-40%) or the +GIS top-10% daily
counts ("topx", a season-pooled cut). One factor per division matches the current model's ground. Strict, each fire once.

| Rule (all / brand-new / continuing / beats) | Held-out 2022-24 | Forward 2025+26 |
|---|---|---|
| current | 73.2 / 39.9 / 82.7 / 81.6 | 72.3 / 35.2 / 79.1 / 82.6 |
| +GIS | 73.2 / 40.5 / 82.5 / 82.2 | 72.4 / 36.0 / 79.1 / 82.9 |
| danger-scaled count, no reserve | 64.6 / 37.8 / 72.2 / 78.7 | 65.5 / 38.9 / 70.4 / 80.7 |
| danger-scaled + 20% quiet | 66.0 / 43.6 / 72.4 / 80.7 | 64.6 / 47.2 / 67.9 / 81.4 |
| danger-scaled + 25% quiet | 65.1 / 45.5 / 70.7 / 80.5 | 63.8 / 49.9 / 66.4 / 81.2 |
| danger-scaled + 30% quiet | 64.1 / 47.1 / 68.9 / 80.1 | 62.9 / 52.0 / 64.9 / 80.8 |
| +GIS top-10% counts + 20% quiet | 72.5 / 42.8 / 80.9 / 82.0 | 70.9 / 44.1 / 75.8 / 83.2 |
| +GIS top-10% counts + 25% quiet | 72.1 / 44.8 / 79.9 / 82.1 | 70.4 / 46.5 / 74.8 / 83.3 |
| +GIS top-10% counts + 30% quiet | 71.7 / 46.4 / 78.8 / 82.1 | 70.0 / 48.4 / 73.9 / 83.1 |

The quiet reserve works without a second model: on the +GIS daily counts, 20-30% quiet costs 0.7-1.5 pts of all fires
held-out (1.5-2.4 forward) for +2.3-5.9 (+8.1-12.4) on brand-new fires, beats unchanged or better. The danger-scaled
daily count itself loses 8-9 pts of all fires at matched ground (the earlier "matches the hindsight rule" comparison let
it use 27% vs 22% ground), so a live daily count is still the open problem.

### Current model on the burn-scar answer key (`results/officer/scar_{held,fwd}*`; key from vanagni `claude/project-thread-v0whah`, `data/scar_key/`)
Flags: the current model, top 10% of the division's test cell-days (held-out 2022-24 pooled; forward 2025). An event is
caught if one of its squares (alert square, or squares >= 10% under the scar outline) is flagged or next to a flag on
day ld-1 or ld-2; it belongs to every division whose grid holds its alert square. Brand-new = no detection within 5 km of
each alert square on days ld-7..ld-1. Simple rules from the cloud's `scar_rules_summary*.json` (same key and scoring).

Fires caught, all / brand-new (%):

| Key | Model held-out | Fires nearby | Burned before | Model forward 2025 | Fires nearby | Burned before |
|---|---|---|---|---|---|---|
| VIIRS events (usual key) | 73.2 / 39.9 | 54.7 / 11.4 | 40.8 / 33.3 | 74.3 / 34.3 | 49.9 / 5.4 | 38.4 / 30.4 |
| alert squares, all events | 80.8 / 42.9 | 64.5 / 11.5 | 45.1 / 35.9 | 82.2 / 37.9 | 64.7 / 6.1 | 43.7 / 33.3 |
| alert squares, scar-confirmed | 81.8 / 44.9 | 65.2 / 11.7 | 44.8 / 36.3 | 83.0 / 39.4 | 65.2 / 5.9 | 43.8 / 33.8 |
| all scar squares, scar-confirmed | 83.8 / 49.3 | 69.7 / 14.7 | 55.6 / 43.1 | 85.7 / 44.5 | 70.4 / 7.5 | 54.3 / 41.4 |
| alert squares, no scar seen | 71.7 / 32.6 | 57.6 / 11.0 | 44.9 / 31.9 | 73.8 / 28.8 | 58.2 / 7.6 | 43.6 / 29.5 |
| ground flagged-or-next | 20.3% | 16.8% | 22.9% | 20.9% | 15.6% | 22.2% |

Events: held-out 47,434 (40,025 scar-confirmed), forward 2025 28,077 (25,083); the cloud key counts 47,398 / 28,086.
On the scar key the model catches 81.8-85.7% of scar-confirmed fires 1-2 days ahead (vs 65-70% for "fires nearby" and
44-56% for "burned before"), and 39-49% of brand-new ones (vs 6-15% and 34-43%). Events with no scar seen are caught
less often (72-74%), consistent with many of them being small or non-forest burns.

### Live combined rule, no hindsight: statewide pool + 50% floor + 25% quiet reserve (`results/officer/live_{held,fwd}*.csv`)
+GIS scores calibrated per division on the PREVIOUS season only (isotonic), so only seasons with an earlier
out-of-sample season are scored: held-out 2023-24 (calibrated on 2022 / 2023) and forward 2026 (calibrated on 2025).
Same statewide daily total as the per-division danger-scaled counts. floor50_quiet25: each division keeps half its count
(25% of it on its clear squares, 75% on others, by +GIS; spare slots move between the two), the rest of the day's total
is pooled statewide by calibrated % (25% to clear squares). One factor per rule matches the current model's statewide
ground. Strict, each fire once.

| Rule (all / brand-new / continuing / beats; fires per 100 flags) | Held-out 2023-24 | Forward 2026 |
|---|---|---|
| current (top 10% per division of the season, hindsight) | 72.1 / 41.9 / 82.4 / 81.3; 0.23 | 69.7 / 35.9 / 77.5 / 80.6; 0.36 |
| per-division danger-scaled counts | 65.8 / 39.7 / 74.7 / 80.4; 0.26 | 62.9 / 38.2 / 68.6 / 78.8; 0.38 |
| floor50 | 71.6 / 41.4 / 81.9 / 82.8; 0.24 | 69.2 / 37.7 / 76.4 / 81.9; 0.38 |
| **floor50 + quiet25 (live rule)** | **71.1 / 45.8 / 79.7 / 83.2; 0.24** | **67.5 / 47.6 / 72.1 / 82.3; 0.38** |

**Update 21 Oct 2026: the live quiet share is now 35%** (Akkshay's choice). The same rule with the quiet share as a parameter
(`QF`, applied to the floor and the pool; vanagni `prithvi_finetune/analysis/live_quiet_curve/`), matched ground, 2026 / held-out 2023-24:

| Quiet share | All fires | Brand-new | Beats |
|---|---|---|---|
| 25% (tables above) | 67.5 / 71.1 | 47.6 / 45.8 | 82.3 / 83.2 |
| **35% (live now)** | 65.4 / 69.5 | 52.3 / 49.6 | 81.3 / 83.0 |
| 50% | 61.7 / 66.1 | 57.9 / 54.0 | 79.3 / 81.4 |
| 75% | 53.0 / 57.2 | 65.0 / 60.4 | 72.8 / 75.8 |

`field-system/pc_models/meta.json` now has `quiet` 0.35 and `k` 0.5844. That k was fitted by the field app on the five 2026
check days so the ground matches the 25% rule's (28.57%); replace it with the PC's bisected value for 35% when available.

No division keeps less than half of its own count under either floor rule. With no hindsight anywhere (calibration,
daily count and flag allocation all from past data), the live rule is within 1.0 / 2.2 pts of the hindsight rule on all
fires, catches 3.9 / 11.7 pts more brand-new fires and 1.9 / 1.7 pts more beat episodes, at the same ground.

### Timing-group fallback (`results/officer/livefb_*.csv`, `fallback_*_groups.csv`)
The 10 divisions with < 400 training fires (Barwani, Bhind, Datiya, Mandsaur, Mohgaon East Mandla, Morena, Rajgarh,
Shajapur, Tikamgarh, Ujjain) take the score of their early / mid / late group model instead of their own +GIS model:
one LightGBM per group pooled over every division of the group (same +GIS inputs and settings, plus division id and day
minus the division's usual onset), retrained on the run's training years (held-out 2019-21; live 2019-24). Groups come
from each division's own training fires in those years (median fire day < 26 Mar early, to 10 Apr mid, later late;
< 20 fires mid). All other divisions keep their live scores. Live rule (floor50_quiet25), strict, matched ground:

| Test | Scope | Fires | All: published / fallback | Brand-new | Beat episodes |
|---|---|---|---|---|---|
| held-out 2023-24 | 87 divisions | 29,690 | 71.1 / 71.2% | 45.8 / 45.9% | 83.2 / 83.4% |
| held-out 2023-24 | the 10 | 333 | 58.0 / 59.2% | 39.9 / 42.3% | 73.7 / 73.0% |
| 2026 | 87 divisions | 24,057 | 67.5 / 67.5% | 47.6 / 47.6% | 82.3 / 82.3% |
| 2026 | the 10 | 274 | 60.9 / 58.0% | 46.9 / 42.7% | 71.6 / 72.0% |

Better on held-out, worse on 2026, on a few hundred fires (each fire about 0.3-0.4 pts); statewide unchanged. No
consistent gain: the 10 keep their own (borrow-if-weak) models. Per division: `livefb_divisions.csv`.

### Fire-regime inputs (`results/officer/livereg_*.csv`, `regime_*_importance.csv`)
+GIS model retrained with 12 fire-regime inputs, each built for season S from S-NPP VIIRS fire-cell-days (15 Feb-31 May)
of seasons 2014..S-1 only: division calendar (10/50/90th pct fire day, share by 15 Mar / after 15 Apr, share of a usual
season burnt by today, usual daily share at today +-7 d, days from the usual median) and local regime (share of prior
seasons with fire in the 7x7 block, seasons since the last fire in the 3x3 block, mean fire day in the 15x15 block and
today minus it). Same rows, labels, own/borrow rule and settings; live rule at the same matched ground. The regime inputs
take 7-8% of model gain (median), yet:

| Live rule (strict, matched ground) | All fires | Brand-new | Beat episodes |
|---|---|---|---|
| held-out 2023-24, published | 71.1% | 45.8% | 83.2% |
| held-out 2023-24, + regime inputs | 71.2% | 46.2% | 83.1% |
| 2026, published | 67.5% | 47.6% | 82.3% |
| 2026, + regime inputs | 67.3% | 47.7% | 81.8% |

No gain: the existing fire-history and day-of-year inputs already carry the regime. Not adopted.

### Live input timing (`results/officer/livelat_fwd*.csv`)
Freshness of each input measured on 2026-10-20 12:17 IST (Earth Engine, FIRMS NRT):

| Input | Models assume | Actually on hand |
|---|---|---|
| FIRMS VIIRS NRT (3 satellites) | every detection of the issue day | night passes (~02:00 IST) by morning; the ~13:30 day pass arrives ~16:30 IST |
| GFS 00Z of the issue day | out ~10:00 IST | not yet on Earth Engine at 12:17 IST (NOAA NOMADS has it ~09:30 IST) |
| ERA5-Land soil moisture | 5 days old | 14 days old on Earth Engine |
| MODIS MOD09A1 / MOD11A2 8-day | usable 9 days after start | newest composite started 20 days ago |
| HLS (dryness npz) | current 10-day step | newest scene 9 days old |

So the live rule is an evening alert (issue ~17:00-18:00 IST for days +1 and +2, after the day pass), and MODIS, soil
moisture and HLS arrive later than in training. Cost, 2026 rescored with the saved models (no retraining), MODIS 21 days
old, soil moisture 15 days old, HLS dryness 10 days later (rebuilding these columns with the original timing reproduces the
stored values exactly):

| Live rule, 2026 (fires strict, matched ground) | All fires | Brand-new | Beat episodes | Ground |
|---|---|---|---|---|
| inputs as in training (published `live_fwd`) | 67.5% | 47.6% | 82.3% | 21.9% |
| inputs as they actually arrive | 66.7% | 47.3% | 82.1% | 22.0% |

The realistic delays cost 0.8 / 0.3 / 0.2 pts, inside the live rule's bootstrap intervals; no retraining needed.

### Stale AlphaEarth map (`results/officer/livestale_fwd*.csv`)
What 2027 would face if the 2026 AlphaEarth embedding is not yet published: the 2026 season rescored with the saved live
models, ae00-ae15 from the 2024 embedding (one year staler) through each division's same PCA (`field-system/pc_models/
ae_pca.npz`); 2025 scores unchanged, so the previous-season calibration is as it would be live. Same live rule (pool + 50%
floor + 25% quiet, matched ground). Check: the fresh map reproduces the stored 2026 scores exactly (0 difference).

| Live rule, 2026 (fires strict) | All fires | Brand-new | Beat episodes | Ground |
|---|---|---|---|---|
| 2025 embedding (published `live_fwd`) | 67.5% | 47.6% | 82.3% | 21.9% |
| 2024 embedding (one year stale) | 67.8% | 47.4% | 82.5% | 21.9% |

The stale map costs nothing measurable (differences 0.2-0.3 pts, well inside the +-2-4 pt bootstrap intervals of the live
rule): the AlphaEarth inputs change slowly from year to year. Using last year's embedding until the new one is published
is safe.

### Live combined rule on the burn-scar key, with bootstrap 95% intervals (`results/officer/livescar_*.csv`)
Same deterministic live rule as `live_*` (pool + 50% floor + 25% quiet, matched ground), scored per division-season on
the VIIRS key and on the scar key (alert squares; scar-confirmed and no-scar-seen events; all and brand-new; cloud scorer
rule). 95% intervals: 2000 bootstrap draws of division-seasons (same draws for every rule; paired difference vs current).
Calibration: previous season for 2023-24 and 2026 (no hindsight); 2025 has no out-of-sample 2024, so it is calibrated on
2026 (marked *). No scar key exists for 2026.

| Metric (%) | Held-out 2023-24: current | live rule | live - current | Forward 2025*: current | live rule | live - current |
|---|---|---|---|---|---|---|
| all fires (VIIRS) | 72.1 (70.5-73.6) | 71.1 (68.3-73.8) | -1.0 (-4.1 to +1.8) | 74.3 (73.2-75.6) | 69.9 (66.9-73.0) | -4.4 (-7.6 to -1.1) |
| brand-new (VIIRS) | 41.9 (39.1-44.6) | 45.8 (43.4-48.1) | +3.9 (+0.3 to +7.6) | 34.3 (31.7-37.2) | 54.2 (51.2-57.4) | +19.9 (+15.5 to +24.3) |
| beat episodes | 81.3 (80.2-82.4) | 83.2 (81.5-84.9) | +1.9 (-0.3 to +4.1) | 84.1 (83.1-85.2) | 84.6 (82.5-86.6) | +0.5 (-1.7 to +2.6) |
| fires per 100 flags | 0.23 (0.20-0.26) | 0.24 (0.22-0.26) | +0.01 (-0.01 to +0.03) | 0.48 (0.43-0.54) | 0.51 (0.47-0.55) | +0.03 (-0.02 to +0.07) |
| scar-confirmed, alert square, all | 79.4 (77.3-81.3) | 77.9 (75.6-80.4) | -1.5 (-4.4 to +1.5) | 83.0 (81.8-84.1) | 78.4 (75.6-81.2) | -4.6 (-7.5 to -1.8) |
| scar-confirmed, alert square, brand-new | 47.0 (43.7-50.4) | 50.5 (47.7-53.3) | +3.6 (-0.6 to +7.7) | 39.4 (36.1-42.6) | 58.2 (54.3-62.4) | +18.8 (+13.9 to +23.8) |
| no scar seen, alert square, all | 69.3 (65.7-72.5) | 68.3 (64.2-72.2) | -1.0 (-4.6 to +2.5) | 73.8 (70.0-77.7) | 67.2 (62.4-72.3) | -6.6 (-9.7 to -3.2) |
| no scar seen, alert square, brand-new | 35.1 (30.8-39.2) | 38.5 (34.2-43.1) | +3.5 (-1.6 to +8.6) | 28.8 (22.4-35.2) | 42.5 (36.1-49.4) | +13.7 (+6.9 to +20.6) |

Forward 2026 (VIIRS key only; previous-season calibration): all fires 69.7 (68.2-71.2) vs live 67.5 (63.8-70.8),
difference -2.2 (-5.8 to +0.9); brand-new 35.9 (33.0-39.0) vs 47.6 (44.6-50.6), +11.8 (+7.7 to +15.5); beats 80.6 vs
82.3, +1.7 (-1.0 to +4.0). Events: scar-confirmed 19,339 (2023-24) / 25,083 (2025); no scar seen 2,486 / 1,934.

### Statewide crew budget at the same daily total (`results/officer/state_{held,fwd}*.csv`; vanagni `data/scar_key/PC_TASKS.md` job A)
+GIS scores, calibrated per division (isotonic, leave-one-season-out: fitted on the division's other test season(s)).
Daily statewide total = sum of the danger-scaled per-division counts; per_division = each division its own count (top
+GIS squares); statewide = the day's total to the highest calibrated % squares anywhere in MP; floor50 = each division
keeps half its count, the rest pooled statewide. One factor per rule matches the current model's statewide ground.

| Rule (all / brand-new / beats; fires per 100 flags) | Held-out 2022-24 | Forward 2025 | Forward 2026 |
|---|---|---|---|
| current (top 10% per division, hindsight) | 73.2 / 39.9 / 81.6; 0.27 | 74.3 / 34.3 / 84.1; 0.49 | 69.7 / 35.9 / 80.6; 0.36 |
| per_division (danger-scaled counts) | 64.8 / 37.9 / 78.7; 0.29 | 66.3 / 39.9 / 81.3; 0.50 | 62.9 / 38.2 / 78.8; 0.38 |
| statewide pool | 73.0 / 40.7 / 81.3; 0.26 | 73.8 / 37.7 / 83.4; 0.46 | 70.6 / 38.3 / 81.4; 0.36 |
| floor50 | 71.0 / 39.5 / 81.7; 0.29 | 73.0 / 37.9 / 84.9; 0.51 | 69.2 / 37.7 / 81.9; 0.38 |
| divisions losing > half their flags (statewide / floor50) | 25 / 0 | 28 / 0 | 23 / 0 |

Pooling the same daily total statewide by calibrated % recovers the 8 pts the per-division danger-scaled counts lose
(it moves flags across divisions and days the way the hindsight top-10% cut does), but 23-28 divisions then lose more
than half their flags (always: Barwani, Bhind, Datiya, Jhabua, Kanha TR, Morena, Neemuch, PTR, Rajgarh, Satpura TR,
Shajapur, Sidhi, Tikamgarh, Ujjain). The 50% floor keeps every division at least half its flags and stays within
1-2 pts of the statewide pool. Ground is matched in total, so the number of flags (and fires caught per 100 flags) differs with how clustered the flags are.

### Forward test, live-ready setup: same-day weather and a daily flag rule (`results/officer/forward_fwd{lag5,gfs}*.csv`, `flagrules_*.csv`)
Weather (all retrained on 2019–2024 with that weather source, top 10% of the season flagged, 2025+2026):

| Weather input | Fires strict | Brand-new | Beat episodes strict |
|---|---|---|---|
| ERA5-Land same day (not available live: ~5-day delay) | 72.3% | 34.4% | 82.5% |
| ERA5-Land as available on the issue day (5 days old) | 71.1% | 32.5% | 81.4% |
| **GFS 00Z run of the issue day** (out ~10:00 IST; soil moisture = ERA5 5 days old) | **72.3%** | **35.2%** | **82.6%** |

GFS: division means of the 00Z run, forecast hours 3–24 (`gfs/gfs_daily.csv`, local); vs ERA5 in Feb–May (Guna):
Tmax r = 0.99 (GFS +1.4 °C), rainfall r = 0.86. No GFS run on 2022-04-20 (left missing).

Flag rules that need no hindsight (GFS model, 2026 season; 2025 provides the calibration):

| Rule | Fires strict | Brand-new | Beats strict | Cells flagged | Ground flagged-or-next | Beats per range per day |
|---|---|---|---|---|---|---|
| top 10% of the season (hindsight; reference) | 69.7% | 35.9% | 80.6% | 10.0% | 21.8% | 3.3 |
| top 10% of the division every day | 63.2% | 41.3% | 81.2% | 10.0% | 28.2% | 4.7 |
| top 10% of each range every day | 65.5% | 49.3% | 84.0% | 10.2% | 32.9% | 5.6 |
| previous season's score cut-off | 58.6% | 24.3% | 70.8% | 7.1% | 16.3% | 2.6 |
| **danger-scaled daily share, calibrated on 2025** | **69.3%** | **44.3%** | **83.1%** | **11.6%** | **27.0%** | **4.2** |

Danger-scaled rule: each day flag 10% x (today's mean score / this season's mean daily score up to yesterday) of the
division's cells (1–40%; plain 10% in the first week), with the base share shrunk by the rule's own overshoot in the
previous season, per division (MP average overshoot in 2025: 14.3% flagged vs 10%). It matches the hindsight rule on fires and catches more brand-new fires and beats,
at ~16% more flags. Uncalibrated it flags 14.8% and catches 76.1% of fires (2025+2026).

## Officer-style scoring, neighbour borrowing, seasonal rules (`scripts/mp_officer_eval.py`, `scripts/mp_seasonal.py`)
All 87 divisions, train 2019–2021, test 2022–2024, top 10% of each division's test cell-days flagged (more on bad days).
- **Each fire once**: fire detections linked across touching cells and consecutive days form one fire.
  STRICT = caught only if a first-day cell had a flag within 1 cell on the issues of day −1 or −2;
  LOOSE = any part of the fire was flagged 1–2 days before it burned. Fires starting on a season's first 2 days are skipped.
- **By beat** (cells mapped to beats from `data/aoi/mp_beats_wgs84.geojson`): a beat episode is a run of burning days;
  STRICT = the beat had ≥1 flagged cell on day −1/−2 before its first day; LOOSE = any day of it was preceded by a flag.
- **Neighbour borrowing**: own data (weight 3) + divisions within 5 km (weight 1); used for "weak" divisions
  (< 1000 training fire cell-days, rule fixed in advance).
- **Seasonal rules ("with")**: targets only 15 Feb–31 May; fires 1 Oct–14 Feb are an "early burn" input
  (cell / 3×3 / 7×7 counts), never targets; on 15–28 Feb likely control burns are dropped from targets
  (day-only same-day cluster within 1 km, ≤ 2 points, max FRP ≤ 5 MW, nothing within 1 km from day −2 to +3):
  4,950 clusters / 5,708 points over 2019–2024.

Recommended model (own; borrow if weak), MP-wide:

| Rules | Labels | Fires caught strict / loose | Beat episodes strict / loose | Ground flagged / flagged-or-next | Beats flagged per day | Flagged beats per range per day |
|---|---|---|---|---|---|---|
| without | 3 satellites | 77.0% / 77.9% | 84.1% / 85.0% | 10% / 19.5% | 28.3% | 2.8 |
| without | S-NPP + NOAA-20 | 77.9% / 78.7% | 84.9% / 85.7% | 10% / 19.5% | 28.3% | 2.8 |
| **with** | **3 satellites** | **73.2% / 74.6%** | **81.6% / 83.0%** | **10% / 20.3%** | **30.6%** | **3.0** |
| with | S-NPP + NOAA-20 | 74.2% / 75.5% | 82.3% / 83.6% | 10% / 20.4% | 30.6% | 3.0 |

Neighbour borrowing for weak divisions: +0.4 to +1.5 pts (fires, strict). Per-division: `results/officer/per_division_recommended.csv`;
full table `results/officer/combined_summary.csv`.

# MP step 1 — does the Ratapani model carry across Madhya Pradesh? (research)

Nine contrasting forest divisions on one shared 500 m grid (EPSG:32643, X0 399000, Y1 2996000, 1829 columns;
`mp_cell = row * 1829 + col`, aligned with the Ratapani grid and the all-MP HLS dryness pull):

| Division | Cells | Character |
|---|---|---|
| Obedullahganj | 7,677 | contains Ratapani; central dry teak |
| Guna | 9,921 | north, dry deciduous |
| Shivpuri | 13,798 | north, driest |
| Khandwa | 11,348 | south-west teak |
| Satpura_TR | 8,286 | central highlands |
| Kanha_Tiger_Reserve | 8,474 | east, moist sal |
| Dindori | 10,129 | east, tribal sal |
| South_Panna | 8,059 | Bundelkhand dry |
| Singrauli | 10,621 | far east, mining belt |

Pipeline (`scripts/`):
1. `mp_grids.py` — division grids from `data/aoi/mp_divisions_dissolved.geojson` (cells with >= 25% inside), saved in `grids/`.
2. `mp_ee.py <division_dir> static alphaearth era5 modis lst` — the Ratapani Earth Engine pulls per division.
3. `mp_proximity.py <division_dir>` — OSM roads / tracks / villages, division boundary, cropland edge.
4. `mp_features.py <division_dir>` — Ratapani v2 features + leaf-fall, one parquet per season (2014–2024, Jan–May);
   labels from the MP-wide VIIRS S-NPP archive (`data_lake/fire_detections/firms_mp_viirs/firms_mp_consolidated.parquet`),
   placed on the shared grid across each division's bounding box so neighbour features see fires just outside it.
5. `mp_transfer.py` — train 2014–2021, test 2022–2024 per division: (A) trained on the other 8 divisions,
   (B) trained on the division itself, (C) trained on all 9 pooled.

6. `mp_pooling.py` — follow-up: (D) pooled + division id, (E) pooled with the division's own rows weighted 5x.

Data (Earth Engine CSVs, feature tables ~1 GB per division) stay local in `E:\FIRE\mp\<Division>\`.

## Results (train 2014–2021, test 2022–2024; top 10% of cells flagged, 3×3 tolerance)

| Model | Fires caught | Brand-new fires | Worst / best division |
|---|---|---|---|
| A trained on the other 8 divisions only | 77.3% | 44.2% | 64.5 / 86.2% |
| **B trained on the division itself** | **83.3%** | **55.1%** | 72.9 / 93.1% |
| C all 9 pooled | 81.4% | 48.3% | 70.6 / 91.2% |
| D pooled + division id | 82.2% | 50.5% | 72.7 / 92.2% |
| E pooled, own rows x5 | 82.4% | 50.6% | 71.6 / 92.0% |

- The approach transfers: a model that never saw a division still catches ~77% of its fires.
- Local history is worth ~6 pts (up to +16 in Singrauli, +12 in Kanha); no pooling variant beats the division's own model.
- Practical design: a per-division model wherever fire history exists, the other-divisions model as a cold start for new areas.

Per-division numbers: `results/transfer_by_division.csv`, `results/pooling_by_division.csv`.

### Step 1c — 10-day HLS fuel dryness (`scripts/mp_dryness.py`)
Joins the separate all-MP HLS pull (`E:\FIRE\mp\tiles`, NDVI/NDMI/NBR every 10 days on the same grid, ~98% coverage)
as-of each issue day, plus 10- and 30-day changes. Division's own model, train 2017–2021, test 2022–2024:
base 82.8% → **83.6%** fires caught, brand-new 55.4% → 56.5%; better in 6 of 9 divisions (largest: South Panna +2.2,
Obedullahganj +1.9). `results/dryness_by_division.csv`.

### Step 1d — the same dryness from the packaged files (`scripts/mp_dryness_npz.py`)
`E:\FIRE\mp\push\mp_dry_<season>.npz` (cells, steps, X[step, cell, ndvi/ndmi/nbr/clear]) holds values identical to the
tiles (12,000 / 12,000 checked) for beat cells only; -32768 = no data, values outside ±10000 are overflow and masked.
Result: base 82.8% → **83.7%** fires caught, brand-new 55.4% → 56.7%, weakest division 71.4% → 74.4%.
This is now the default dryness input for the division models.

## Step 2 — three VIIRS satellites (`scripts/firms_noaa_pull.py`, `scripts/mp_multisat.py`)
NOAA-20 (2018-04+) and NOAA-21 (2023-03+) standard-processing detections over MP from the FIRMS area API
(key read from the `FIRMS_MAP_KEY` environment variable, never stored). `mp_features.py` now takes
`MP_FIRE_SOURCES` / `MP_FEATS_DIR` / `MP_YEARS`; 3-satellite tables are in `<division>/feats_multi/` (seasons 2019–2024).
Division's own model + dryness, train 2019–2021, test 2022–2024:

| Labels and fire history | vs S-NPP fires | vs all-satellite fires |
|---|---|---|
| S-NPP only | 82.8% | 80.4% |
| **S-NPP + NOAA-20 + NOAA-21** | **84.6%** | **82.4%** |

S-NPP alone records about half of the fire cell-days the three satellites see (23,913 vs 46,881 in the test years).
Brand-new-fire recall is not comparable between rows: with more fires visible fewer cells count as "brand-new".
`results/multisat_by_division.csv`.
