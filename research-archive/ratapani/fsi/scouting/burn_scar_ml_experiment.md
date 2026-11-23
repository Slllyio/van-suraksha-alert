# Burn scars with machine learning: does a learned model beat the hand rule? (Ratapani, 16 Oct 2026)

Akkshay asked for a machine-learning view of how to decode the final burn scar more efficiently. This is a real experiment on 2019-2025 fire seasons (15 Feb - 15 Jun). Code and small outputs: `code/scar_ml/` (scripts, models, `results/`). Image stacks (3.4 GB) stay in scratch.

## Bottom line
- **No learned model beats the current rule at drawing the scar around an alert.** On sub-metre Esri Wayback images the rule finds about 84% of the visibly burned ground in a 1 km window. The best learned model finds 76%, and a plain NBR-drop threshold finds 80%.
- **The learned model wins at a burn map that does not need alerts.** Compared with the rule test run without the alert tie, the PN model (defined below) finds a bit more burned ground (76% vs 72%) and draws about a third as many scars at decoys (5% vs 14%).
- **The best practical result is the rule plus the model's alert-free patches** ("rule + PN"). It finds 87% of the burned ground (+2.5 points, 95% range +1.1 to +4.5). On small fires (under 20 ha) it finds 74% vs 69%. It covers 80% of the Sentinel-2/Landsat fire pixels that had no FIRMS alert, against 47% for the rule. The cost: decoys with a scar go from 6.7% to 10.4%. Some of those decoy scars look like real burns on Wayback (inferred).
- **A model trained on the rule's own labels just copies the rule.** The positive-unlabeled model's map matches the rule test without the alert tie almost exactly (median overlap 0.98). Better labels, not a better model, are the bottleneck.
- **Per-pixel burn dates from Sentinel-2/Landsat add nothing over the current image-pair window.** Both narrow the date to the gap between looks, a median of **5 days** (not 10). On mid-fire photos they cannot tell burned-before from burned-after (0.53, near guessing), while the distance to VIIRS dots can (0.87).

## Terms
- **Rule** = the current method (`fire-alert-scars/scripts/alert_scar.py`). It needs a relative NBR drop of at least 0.10 against the chip median, a darker NIR, and a drop that still holds at a later look. It then grows in two passes and keeps patches within 200 m of a VIIRS point (600 m for MODIS).
- **NBR** = normalised burn ratio (NIR vs SWIR2). It drops when vegetation burns. **MIRBI**, **NBR2** = other SWIR burn indices.
- **Chip** = a 3 km x 3 km image square at 20 m. **Look** = one clear Sentinel-2 or Landsat image.
- **Decoy** = a place 3-5 km from the fire, in forest, with no alert within 1.5 km or 30 days, imaged by the same Wayback image. It is presumed unburned.
- **PU / PN** = positive-unlabeled training (positives vs everything else) and positive-negative training (positives vs control chips).
- **AUC** = how well a score ranks true above false (0.5 = guessing, 1 = perfect).

## What was done
**Training labels (no independent truth used).** Choice (b) + (c) from the brief:
- **PU model.** Positives are the rule's strict pass-1 core pixels in 330 alert chips. Everything else in those chips, and in 130 control chips, is "unlabeled". The Elkan-Noto correction is used: c = 0.95, burned if P >= 0.5.
- **PN model.** The same positives against all pixels of the 130 control chips.
- **Fire-pixel model.** Its labels do not come from the NBR rule at all. Positives are 1,508 Sentinel-2/Landsat fire pixels in 184 other chips, with that scene removed from the stack. Negatives are the control pixels.
- All training chips sit at least 3 km or 45 days from every test chip.

**Features.** About 100 per pixel:
- NBR, NBR2, MIRBI, NDVI, red, NIR, SWIR1 and SWIR2 at the pre, post and check looks.
- Their differences, relative differences and drops relative to the chip median.
- Context: 3x3 and 7x7 means and spreads.
- Days since pre and days to check.
- WorldCover class, slope and canopy cover (`fuel-map/ratapani/canopy_cover_10m.tif`).
- BAIS2 is left out: it needs Sentinel-2 red-edge bands, which Landsat lacks.

**Model.** LightGBM, 300 trees. No U-Net: a U-Net trained on rule labels would also learn the rule (see the PU result), and the fire-pixel labels are too sparse for it.

**Rule check.** The rule was re-run on the same image stacks. On 60 training events it gives the same area as v2 for single-alert events. Where it differs, it is because it seeds from every alert in the chip, which suits a chip-wide map.

**Independent test (truth never used in training):**

| test set | what it is | n |
|---|---|---|
| Wayback real | FIRMS fires with a 0.3-0.5 m image 1-20 days after, 1 km window | 248 |
| Wayback decoys | same images, unburned forest 3-5 km away | 134 |
| Fire pixels | Sentinel-2/Landsat hot pixels, scene removed from the stack; 90 clusters with no FIRMS alert nearby, 90 with one | 180 clusters |
| Mid-fire photos | fuel thread's burned-so-far snapshots, photo scene removed | 171 |

**How the Wayback recall and precision are estimated (inferred).** No pixel is hand-labelled, so a brightness mixing estimate is used.
- On fresh images (10 days or less, 83 chips), "surely burned" = ground at least 4 of 5 chip methods map. "Unburned" = unmapped ground at least 100 m from any map.
- Every other patch counts as burned in proportion to how dark it is between those two.
- This only sees burns visible from above. Burns under canopy are missed.

## 1. Burned area: who wins

| method | Wayback recall* | precision* | F1* | mapped / burned* | decoys with a scar | fire pixels, no FIRMS | fire pixels, FIRMS |
|---|---|---|---|---|---|---|---|
| current rule (all alerts in chip) | 0.84 | 0.97 | 0.90 | 0.87 | 6.7%** | 47% | 77% |
| v2 event outline (frozen) | 0.79 | 0.97 | 0.87 | 0.82 | - | - | - |
| NBR drop >= 0.10 | 0.80 | 0.94 | 0.87 | 0.85 | 21.6% | 79% | 94% |
| rule test, no alert tie | 0.72 | 1.00 | 0.84 | 0.73 | 14.2% | 68% | 57% |
| LightGBM PU | 0.72 | 1.00 | 0.84 | 0.72 | 3.7% | 68% | 57% |
| LightGBM PN | 0.76 | 0.98 | 0.86 | 0.78 | 5.2% | 75% | 71% |
| LightGBM, fire-pixel labels | 0.61 | 0.90 | 0.73 | 0.68 | 2.2% | 87% | 89% |
| **rule + PN patches** | **0.87** | 0.96 | **0.91** | 0.90 | 10.4% | 80% | 84% |

\* Wayback brightness mixing estimate (inferred). The 95% ranges for recall minus the rule's recall, resampling chips:
- PN: −0.13 to −0.04
- v2: −0.09 to −0.02
- rule + PN: +0.01 to +0.05

\*\* On decoys the rule is given a pretend alert at the centre, so its number means "what the rule would draw if an alert sat here". The other methods map anywhere in the 1 km window. The 95% ranges for decoys with a scar:

| method | 95% range |
|---|---|
| rule | 3-11% |
| PN | 2-10% |
| NBR drop >= 0.10 | 15-28% |

Fire-pixel coverage: rule 37-57% and PN 67-84% (no FIRMS nearby).

**Other findings:**
- **Real vs decoy.** The score is the mapped ground's darkness on Wayback. AUC: rule 0.92, PU 0.92, PN 0.92, NBR drop 0.88, fire-pixel model 0.84.
- **Pixel AUC, fire pixels vs decoy pixels (no FIRMS nearby).**

  | score | AUC |
  |---|---|
  | NBR drop | 0.97 |
  | the rule's relative drop | 0.97 |
  | PU | 0.98 |
  | PN | 0.99 |
  | fire-pixel model | 0.996 |

  The fire-pixel model is favoured here because it was trained on the same kind of label. All the scores separate the strongly burning pixels well.
- **Decoy "false" scars may be real burns (inferred).** The models' decoy scars are much darker than their ring (12-14 brightness units) than the rule's are (6). So many of them are probably real burns with no alert, not false scars.
- **Ground where they disagree.** Ground the rule maps and PU does not (487 ha) is 84% burned-like, so the rule's growth step is mostly right on these fires. Ground PU adds beyond the rule (41 ha) is 91% burned-like.
- **Edges.** Unmapped ground within 100 m of any map is 13% burned-like. Edges are still slightly under-mapped by every method.
- **Small fires** (v2 under 20 ha, 30 fresh chips). Share of nearby burned ground found in the 1 km window:

  | method | share found |
  |---|---|
  | v2 outline | 49% |
  | rule (all alerts) | 69% |
  | PN | 57% |
  | NBR drop >= 0.10 | 68% (precision 0.86) |
  | rule + PN | 74% |

  The v2 outline of a small fire leaves half the burned ground around it unmapped. Part of that ground is neighbouring fires.

**Why the learned models do not win near alerts.** Nearly all of the PU model's weight sits on the rule's own variables (relative NBR drop and its 3x3 mean). With c = 0.95, the rule's labels are almost a function of the features, so the model can only copy the rule test (overlap 0.98). The rule's extra edge comes from its growth steps, which use each fire's own drop, and from the alert tie, which removes chance patches.

The fire-pixel model learns something different (it leads on MIRBI). It catches flaming ground, but it misses the lightly burned litter edges, which are most of the area.

## 2. Burn date per pixel
The variant was chosen on training chips: the first look with a persistent drop of at least 0.08. Results on the test chips (87,000 burned pixels in 336 chips, against the earliest VIIRS detection within 400 m):

| date estimate | median window | window holds the VIIRS day | midpoint within 2 days |
|---|---|---|---|
| per-pixel first persistent drop | 5 d | 81% | 67% |
| current image-pair window (pre, post] | 5 d | 85% | 69% |
| alert day of the event (circular here) | 0 d | - | 81% |

- **Late-burning pixels.** For pixels whose VIIRS day is 3 or more days from the event's alert day, both estimates get only 14% within 2 days.
- **Why per-pixel dates add nothing.** A burned pixel in a pair-based map has, by construction, burned inside that pair's window. Per-pixel dating could only help a map built over the whole season.
- **Mid-fire photos.** The pixel's look window straddles the photo moment for 92% of pixels. Per-pixel dates rank burned-by-photo at AUC 0.53, against 0.87 for distance to the VIIRS dots seen so far (as in `research/spread-review/HONEST_TESTS.md`).
- **The window is 5 days, not 10.** The image gap is a median 5 days. Day-level dates must come from VIIRS/FSI alert times and Sentinel-2/Landsat fire pixels. HLS would add no new looks, since it is built from the same Sentinel-2 and Landsat 8/9 scenes already read (inferred).

## 3. Cost
Measured on this 4-core cloud box, for a 3 km chip with 19 looks:

| step | time |
|---|---|
| read the image stack | median 9.7 s (about 0.5 s per look); about 0.6 chips/s with 6 parallel workers (network-bound) |
| rule | 0.04 s |
| learned-model features + prediction | 0.86 s on 1 thread (22,500 pixels) |
| per-pixel dating | 0.03 s |
| training (5-fold check + final fit) | 12 min on 4 cores |

**All of Madhya Pradesh, one season (estimate, inferred).** About 77,000 km² of forest is about 8,600 chips. Feb to mid-June is about 37 looks per chip.
- **Reading:** about 8 h at the measured parallel rate. This is network-bound, so a GPU does not help.
- **Learned model on every consecutive look pair** (about 36 per chip): about 74 core-hours. That is about 18 h on 4 cores or about 2.5 h on 32 cores.
- **Rule alone:** about 3.4 core-hours.
- **On a 16 GB AMD GPU:** porting the feature filters and tree inference to the GPU (for example PyTorch on ROCm) might cut the model step 10-30x, to about 3-7 h per season. Reading would then dominate. Not measured.
- **Seven seasons:** about 55 h of reading plus about 520 core-hours of model, or about 25-50 GPU-hours.
- **Live, per alert:** the learned model adds about 1 s to the 10-15 s the rule already takes.

## What fails
- **Training on rule labels.** It reproduces the rule (PU), so it cannot fix the rule's errors.
- **The fire-pixel model on its own.** Precision is about 0.90 and it misses light burns.
- **A plain NBR threshold.** About 1 decoy in 5 gets a scar.
- **Per-pixel dating from Sentinel-2/Landsat.** No better than the image-pair window, and blind inside it.

**Caveats:**
- **Wayback estimates.** The Wayback precision and recall are a brightness proxy calibrated on agreement between methods. This favours methods near the consensus. Canopy hides burns.
- **Decoys may hold real burns.**
- **The rule here is a re-implementation.** It runs on a 3 km chip without v2's chip enlargement. The v2 row is the frozen outline.
- **Assumed scaling.** The red band's Sentinel-2-to-Landsat scaling is assumed to be 1.0.

## Next step for the burn-scar thread
1. **Keep the rule for per-alert outlines.**
2. **Build the fire-independent season map** that `reference/v2_2026-10-16/USE_AND_LIMITS.md` lists as the next step.
   - Use LightGBM PN, not the bare rule test, for it.
   - Ship it as a v3 candidate layer: rule outlines plus PN patches flagged `no_alert`.
   - Spot-check the no-alert patches on Wayback first.
   - Models: `code/scar_ml/model_pn.txt` (and `apply.py`).
3. **Fix the labels before trying a bigger model.** Eye-label about 200 fresh Wayback chips at 20 m (burned / unburned / can't tell). Then retrain with those plus the fire pixels, and only then try a U-Net.
4. **Stop chasing per-pixel day dates from Sentinel-2/Landsat.** Date scars with VIIRS footprints, FSI times and fire pixels, and report the image-pair window (median 5 days) as the bounds.

## Files (`code/scar_ml/`)
| file | what it does |
|---|---|
| `lib.py` | reader, rule, features, dating |
| `build_sets.py`, `add_af_train.py` | chip lists, written to `chips.csv` |
| `fetch.py` | image stacks |
| `wayback_cells.py` | Wayback windows |
| `train.py`, `train_af.py` | `model_pu.txt`, `model_pn.txt`, `model_af.txt`, `train_meta.json`, `feature_importance.csv` |
| `apply.py` | runs every method on the test chips |
| `evaluate.py`, `dating.py` | write `results/*.csv` and `*.json` |
