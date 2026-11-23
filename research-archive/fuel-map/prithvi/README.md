# Does Prithvi show fuel load in Ratapani? (17-18 Oct 2026)

Akkshay's ask: "i am very certain prithvi model use will give us fuel load idea more prominent. apply ur full brains."

## Plain answer
Prithvi is not a fuel-load map. On the three tests that fuel should change, it adds:
- **Fire size: nothing** once remoteness is accounted for.
- **2-day model: nothing**, and the score drops slightly.
- **Seasonal burn share: a small real gain** (+0.017 AUC, better in 7 of 10 seasons). Nothing tells us that gain is litter rather than something else Prithvi sees, such as moisture or forest structure.

Fuel map v3 adds nothing on any of the three. The follow-up test (section "What the burn-share signal is made of") finds that the small gain does not behave like litter. With current data it cannot be pinned to any one cause.

## What was tried before
- `ratapani/prithvi_dyn/` fed 10-day Prithvi embeddings into the 2-day "where" model. They only copied the Sentinel-2 dryness signal.
- `research/ratapani-burn-labels/prithvi/` fine-tuned Prithvi for burn scars. It did no better than our detector.
- Neither looked at fuel.

## Ground truth
There is none. FSI never published its 15,114 plot values or per-stratum means (`ratapani/fsi/fuel_load_tables.md`). So nothing can be fine-tuned against "t/ha". Instead each test asks whether Prithvi predicts something fuel should change, beyond canopy cover. Every earlier satellite check agreed with the fuel map only through canopy.

## Setup
- **Model:** Prithvi-EO-2.0-300M-TL (Hugging Face ibm-nasa-geospatial), frozen encoder, on the cloud CPU (~5-9 min per season).
- **Images:** NASA HLS v2.0, S30 + L30, from LP DAAC, tiles T43QGF and T43QHF, 30 m. Four frames per season:
  - 1-30 Apr of the previous year (leaf-off)
  - 1-30 Nov of the previous year (full leaf)
  - 5-28 Jan
  - 1-14 Feb
  
  Each frame is the per-pixel median of up to 3 clear looks per tile, and every frame was ~100% clear. Seasons 2017-2026.
- **Features:** last-layer tokens (480 m), shifted by half a token to give a 240 m grid. PCA on 2017-24 only: 32 components of the frame mean, 16 of the Feb-minus-Nov change, 16 of layer 12.
- **Baselines:**
  - canopy cover
  - fuel map v3 (litter, grass, teak)
  - **raw HLS**: the same pixels Prithvi saw, averaged over the same 480 m window (6 bands + NDVI/NBR/NDMI, 4 frames). This tells us whether the model adds anything beyond its own input.
- **Leak guard:** only fires, cells and days from 15 Feb onwards are scored, so every image comes before the event.

## Results (held-out; higher is better)
| Test | Canopy (+ controls) | + fuel map v3 | + raw HLS | + Prithvi |
|---|---|---|---|---|
| 1. Fire grows to 200 ha+, AUC (2388 fires after 15 Feb; season + 10 km block held out; with access controls) | 0.708 | 0.712 | 0.721 | 0.707 |
| 1. Same, without access controls | 0.641 | 0.665 | 0.665 | 0.680 |
| 2. Forest cell mostly burns in a season, AUC (season + block held out; with access controls) | 0.779 | 0.779 | 0.783 | **0.796** |
| 2. Same, without access controls | 0.711 | 0.718 | 0.733 | 0.766 |
| 3. 2-day model recall@5, held-out seasons 2017-24 | 29.8% (none 29.9%) | 29.9% | 29.0% | 29.1% |
| 3. Same, trained 2017-24, scored 2025-26 | 26.3% (none 26.6%) | 26.4% | 26.8% | 26.1% |

Access controls:
- distance to road, track, village, crops and sanctuary boundary
- depth inside the forest
- forest share within 1 and 2 km
- elevation and relief
- place memory: size or burnt share of other seasons' fires nearby

Bootstrap and per-season checks (results/*.json):
- **Test 1:** the Prithvi gain without controls was +0.039 AUC (CI 0.017-0.064). With controls it is -0.001 (CI -0.017 to +0.016), and against raw HLS it is -0.014.
- **Test 2:** with controls, Prithvi beats canopy by +0.017 AUC (7/10 seasons) and raw HLS by +0.014 (9/10). Fuel map v3 adds +0.000 (4/10).
- **Test 3:** Prithvi lowers the 2-day score by 0.8 pt in held-out seasons and 0.5 pt on 2025-26.

## What is real, what is not
- **Real:** fires in remote, contiguous forest grow bigger and burn more ground. Prithvi picks this up well from 7 km of context around each spot. That is why it looked strong before the controls. It is about access (crews, roads, villages), not fuel.
- **Real but small:** after the controls, Prithvi still ranks which forest cells burn most of their area a bit better than canopy, v3 or its own raw pixels.
  - It does not say why. That residue could be litter, fuel continuity, Feb moisture, or stand type.
  - With no field data there is no way to call it "fuel load", and it gives no t/ha.
- **Not real:**
  - Prithvi as a fire-size predictor beyond access.
  - Prithvi as an input to the 2-day model.
  - Fuel map v3 detail beyond canopy, which was confirmed again here.

## What the burn-share signal is made of (18 Oct, `scripts/t2c_cells.py`, `t4_what.py`, `results/t4_what.json`)
Field data is off the table, so this test uses current data only. The extra score is what Prithvi adds on top of its own raw pixels and all controls. It is held out by season and 10 km block (+0.012 AUC, better in 9 of 10 seasons). It is compared at the same canopy tenth, 2020-26, 21,051 cell-seasons:

| Possible cause | Rank correlation with Prithvi's extra score | Reads as |
|---|---|---|
| Leaf fall amount (NDVI Nov minus Feb) | -0.11 | the wrong way for litter: more leaf drop gives a LOWER score |
| Years since last burn | +0.08 | weak |
| Feb / Jan moisture (NDMI) | +0.06 / +0.06 | weak |
| Teak share, v3 litter | +0.07 / +0.06 | weak |
| Forest share within 1-2 km | -0.03 / -0.04 | none |

- **Litter build-up cannot be used as a check here.** At the same canopy, cells unburnt for longer burn LESS, not more: the share mostly burnt is 7% after a burn last season, 5% at 2-3 years and 2% at 4+ years. This matches the earlier finding that teak litter regrows yearly. A cell that has not burnt for years is a place that rarely burns, not a place loaded with old litter.
- **Prithvi's gain is the same at every burn age:** +0.016 burnt last season, +0.011 at 2-3 years, +0.017 at 4+ years. A litter signal would grow with build-up time.
- **Verdict:** the extra signal is not litter build-up, not leaf-fall amount, and not plain moisture or forest continuity. It is a diffuse stand or landscape pattern that no single variable we have explains. Current data cannot isolate litter from the rest.

## What would be needed next
- Nothing in the current data can turn this into a litter measure.
- The one practical use is the burn-share score in the weekly risk picture, as "cells likely to burn wholesale this season". It is a small gain (+0.012 to +0.017 AUC) and must be described as that, not as fuel.
- Fine-tuning on Akkshay's GPU has no target to learn and would only relearn the proxies tested here.

## Files
- `scripts/`:
  - `hls_pull.py`: HLS pull (proxy signs *.nasa.gov; no token in code)
  - `embed.py`: Prithvi run
  - `feats.py`, `common.py`, `cells.py`: features
  - `fires_table.py`: fire table from research/fuel-from-heat h18
  - `t1_fires.py`, `t1b_confounds.py`, `t2_cells.py`, `t2b_cells.py`, `t3_lean.py`: tests. t3 is a copy of ratapani/scoring/pipeline_lean_model.py with one fuel layer per variant. It keeps the old seen-scar inputs, so its absolute numbers sit ~0.5 pt high, the same for every variant.
- `results/*.json`: all numbers above.
- The HLS frames (~1.3 GB) and embeddings (~4 GB) stayed in the session scratch and are not in the shared folder. Rerunning takes about 3 h on CPU.

## Every other use of Prithvi in the project (18 Oct, after "check thoroughly on each and every aspect")
| Use | Test (held out) | Without Prithvi | Raw HLS pixels | With Prithvi | Verdict |
|---|---|---|---|---|---|
| Fuel load | no field truth; proxies above | - | - | - | not a fuel map |
| Big fire at first alert | AUC, season + block, access controls | 0.708 | 0.721 | 0.707 | no |
| Cell burns wholesale this season | AUC, season + block, access controls | 0.779 | 0.783 | 0.796 | small yes (+0.012 over raw, 9/10 seasons) |
| 2-day "where" model | recall@5, 2017-24 / 2025-26 | 29.9 / 26.6 | 29.0 / 26.8 | 29.1 / 26.1 | no (also no in Oct 14 dynamic try) |
| **Which ground around the first dots burns** (t5, 2,388 fires, 757k points within 1.5 km) | pixel AUC, LOSO | 0.795 (distance + ground) | 0.808 | **0.821** | small yes: beats raw 9/10 seasons, ground 10/10 |
| same, scar overlap at true size | IoU | 0.314 (distance only 0.303) | 0.320 | 0.326 | +0.006 over raw: small |
| Cold start: fire-prone ground with no history (t6, new division) | AUC top quarter, 10 km blocks held out | 0.760 (maps + canopy) | 0.809 | 0.775 | no: plain pixels win |
| Burn-scar detection | Oct 14 fine-tune, 376 judged points | 0.86 detector | - | 0.86-0.87 | no (inside noise) |
| Control burn vs wildfire | not testable: no true labels (rule right ~52%) | | | | - |
| Spread direction, per-fire speed | earlier threads: direction is noise, speed unidentifiable | | | | not worth it |

- **Where Prithvi helps:** ranking which nearby ground burns (spread) and which cells burn most of their area in a season. Both gains are small (about +0.01 to +0.02 AUC over the same pixels without the model) but consistent across seasons.
- **What it is:** the frozen model reads the stand and landscape pattern in a 7 km window better than single-pixel band values. That is the job it was trained for.
- **What it is not:** a fuel, timing or size signal.
- **Next if wanted:** give the spread thread's learned footprint the Prithvi point features (t5 shows +0.013 AUC over raw HLS). Expected gain is about +0.01 overlap.

## Trained head on the spread question (18 Oct, `scripts/s1_chips.py`, `s2_head.py`, `results/s2_head.json`)
**Setup**
- A small 30 m map network (5 dilated conv layers) on 2,361 chips, each 3.1 km around a fire's first dots.
- Target: the final scar.
- Same network for every row; only the inputs change.
- Prithvi tokens are frozen (all 2048 values: frame mean + Feb-minus-Nov), learned through a 1x1 layer.
- 5 folds, two seasons held out per fold. Scored inside 1.5 km.

| Inputs | Pixel AUC | Overlap at true size |
|---|---|---|
| distance + canopy | 0.781 | 0.305 |
| + raw HLS 30 m | 0.793 | 0.321 |
| + raw HLS + Prithvi | **0.814** (better than raw in 10/10 seasons) | 0.323 |
| Prithvi without raw | 0.811 | 0.316 |
| (earlier, frozen PCA + LightGBM with roads/villages, t5) | 0.821 | 0.326 |

**Plain**
- Trained on the right task, Prithvi again ranks the burning ground better: +0.02 AUC, every season.
- The overlap with the true scar barely moves: +0.002. Distance from the dots and the true size decide the shape; Prithvi only reorders pixels at the edges.
- The head does no better than the simpler frozen PCA + LightGBM model.
- Full fine-tuning of the 300M model on the GPU is therefore not worth running. It would refine a ranking gain that does not turn into a better map.

## Statewide check of the burn-share gain (18 Oct, `scripts/mp_*.py`, `results/mp_statewide.json`)
Akkshay chose to test whether the Ratapani burn-share gain holds across MP.

**Setup**
- 10 regions of 40 x 40 km, each on the densest fire area of one division: Khandwa, Dewas, South Betul, South Chhindwara, South Balaghat, Dindori, Umaria/BTR, Chhatarpur, Panna TR and Satpura TR (`results/mp_regions.json`).
- Seasons 2022-25. Pipeline the same as Ratapani: the same 4 HLS frames, frozen Prithvi with 4 shifts, and cells sampled the same way.
- Target: a 500 m forest cell (50%+ forest) has most of its area inside burn-scar outlines from fires on or after 15 Feb (13,680 scars; 128,592 cell-seasons; 13.5% "most burnt"). Cells with a scar before 15 Feb are dropped.
- Controls from `ratapani/mp_grid/static_gis_v1.parquet`: roads, villages, forest edge, farm/settlement share, terrain and land cover, plus the cell's burn history from the other seasons.
- **A (main):** the region is held out. Train on the other 9 regions and other seasons, then score the unseen region-season. The Prithvi PCA is fitted on training regions only.
- **B:** 10 km blocks and the season held out, like the Ratapani test.

| Inputs | A: region held out, AUC | B: block held out, AUC |
|---|---|---|
| controls only | 0.693 | 0.706 |
| + forest type map | 0.704 | 0.711 |
| + raw HLS (same pixels) | 0.720 | 0.729 |
| + Prithvi | **0.736** | 0.739 |
| + raw HLS + Prithvi | 0.733 | 0.739 |

- **Prithvi over raw HLS, region held out:** +0.016 (region bootstrap CI +0.002 to +0.028), better in 9 of 10 regions. Dewas is the exception at -0.033.
- **Raw + Prithvi over raw alone:** +0.013 (CI +0.006 to +0.019), 9/10.
- **Ratapani, for comparison:** +0.012 to +0.017.

**Plain:** the small burn-share gain is real across MP, not a Ratapani quirk. It transfers to regions the model never saw, from teak in the west to sal in the east and dry forest in the north. It is the same size as in Ratapani: about +0.015 AUC over the same pixels without Prithvi. It is still a stand-pattern signal, not a fuel-load measure (see "What the burn-share signal is made of"). Usable as one input to a seasonal "which forest cells burn wholesale" map; not a breakthrough.

## Prithvi season score in the 2-day model, 10 MP regions (18 Oct, `scripts/mp_2day.py`, `results/mp_2day.json`)
- **Season score:** one number per forest cell-season, "burns wholesale", built from GIS and images only. Region and season are held out. Its AUC is 0.70 with raw HLS and 0.71 with raw HLS + Prithvi.
- **2-day model:** 15.3M cell-days, 15 Feb-13 Jun 2022-25. Target: a VIIRS fire event in the cell on t+1 or t+2. Base inputs: fires within 1/3/5 km in the last 1/3/7 days, days since a nearby fire, burned before, date and GIS. The region is held out (trained on the other 9 regions and other seasons).

| Model | Caught in daily top 5% | Caught in daily top 10% |
|---|---|---|
| Base | 20.0% | 30.7% |
| + season score (raw HLS) | 19.7% | 30.8% |
| + season score (raw HLS + Prithvi) | 19.9% | 30.6% |

- **Verdict:** no help. All changes are within ±0.3 pt, with no consistent direction across regions. This agrees with Ratapani: what decides the next 2 days is fires nearby now and the date, not the stand. Prithvi's seasonal signal stays a separate "which cells burn wholesale" ranking and is not an input to the 2-day model.

## PC GPU fine-tune (19 Oct 2026)
Asked by Akkshay 18 Oct ("train prithvi on pc"). Package: vanagni PR #8, `prithvi_finetune/`. Ran on his RX 9060 XT (AMD ROCm PyTorch, Windows), 02:39-13:07 IST, 10.5 h. Same 10 regions and labels as the statewide check; a cell counts as a hit if half or more of it burns after 15 Feb; two regions held out at a time (5 folds); 8 epochs.

Images only (no roads/villages/terrain/history), held-out AUC:

| Region | Raw-pixel net | Frozen Prithvi | Fine-tuned (last 8 of 24 blocks) |
|---|---|---|---|
| Khandwa | 0.569 | 0.657 | 0.679 |
| Dewas | 0.637 | 0.683 | 0.696 |
| South Betul | 0.638 | 0.791 | 0.778 |
| South Chhindwara | 0.644 | 0.703 | 0.712 |
| South Balaghat | 0.406 | 0.595 | 0.701 |
| Dindori | 0.412 | 0.683 | 0.723 |
| Umaria | 0.730 | 0.743 | 0.695 |
| Chhatarpur | 0.677 | 0.736 | 0.763 |
| Panna TR | 0.487 | 0.626 | 0.656 |
| Satpura TR | 0.658 | 0.815 | 0.780 |
| **Mean** | **0.586** | **0.703** | **0.718** |

Fine-tuned beats frozen in 7/10 regions (+0.015). The raw-pixel net is weak (below 0.5 in 3 regions), so the +0.12 Prithvi-over-raw gap here is not comparable to the +0.016 found with a proper model.

**On top of the full cloud model** (`scripts/mp_stack.py`, `results/mp_stack.json`): GPU scores added as one input to LightGBM with controls + Prithvi tokens, region held out (scores are out-of-fold, so no leak):

| Inputs | Mean AUC |
|---|---|
| controls + Prithvi (cloud, before) | 0.736 |
| + GPU frozen score | 0.741 |
| + GPU fine-tuned score | 0.740 |
| controls + GPU fine-tuned score only | 0.728 |
| controls + GPU raw-net score | 0.693 (= controls alone) |

Fine-tuned score adds +0.005 (8/10 regions; region bootstrap CI -0.008 to +0.016), the same as the frozen GPU head (+0.005), and fine-tuned vs frozen is 0.000. **Verdict: fine-tuning gives no gain over frozen Prithvi once the real inputs are in. Not worth a GPU step in the pipeline. Burn-share ranking stays at ~0.74.**

## Lower burn cut-offs and division-by-division (19 Oct 2026)
Akkshay asked: why keep discarding Prithvi, can the "half the square" cut-off go lower (a 500 m square is 25 ha; 4 ha = 16%, 30% = 7.5 ha), and does it help more in some divisions? Region held out, full cloud model (`scripts/mp_thresh.py`, `mp_thresh2.py`; `results/mp_thresh*.json`).

| Burnt if share >= | Squares | Controls | + raw HLS | + Prithvi | + Prithvi + GPU blend |
|---|---|---|---|---|---|
| any (2%) | 31% | 0.632 | 0.656 | 0.673 | 0.676 |
| 10% | 26% | 0.644 | 0.671 | 0.686 | 0.687 |
| 20% | 22% | 0.657 | 0.683 | 0.700 | 0.702 |
| 30% | 19% | 0.671 | 0.698 | 0.713 | 0.716 |
| 50% | 14% | 0.691 | 0.719 | 0.735 | 0.735 |

- Prithvi over controls +0.04 (9/10 regions) and over raw +0.014 to +0.017 at every cut-off. Any cut-off works; pick what officers find meaningful.
- By region, gain over raw (range across cut-offs): Satpura TR +0.03..+0.08 (+0.2 over controls), Dindori +0.02..+0.05, Panna TR +0.03..+0.06, Khandwa/S Chhindwara ~+0.02, Umaria/Chhatarpur/S Balaghat/S Betul ~0, Dewas -0.035 (every cut-off).
- GPU blend (frozen + fine-tuned head ranks, trained at 50%) on top of frozen tokens: +0.001..+0.003, CI spans zero at every cut-off. A GPU retrain at 4 ha is not expected to add more. Frozen Prithvi tokens in the cloud model are the useful form.
