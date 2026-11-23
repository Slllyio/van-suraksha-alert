# Three honest tests of the spread chance map (16 Oct 2026)

Figure: [figures/6_honest_tests.png](figures/6_honest_tests.png). Scripts: `scripts/h1_loso_models.py`, `h2_photo_test.py`, `j1_jumps.py`, `b1_beat_checklist.py`.

## Bottom line
- **The chance model's big win was mostly self-graded.** On mid-fire photos, which never touch the satellite dots, the plain rule "ground closest to any dot seen so far burns first" beats it. The claim "70% vs 39% for persistence" in [IMPLEMENTED.md](IMPLEMENTED.md) does not hold on independent truth.
- **What survives:**
  - The arrival map: 82% of photo pixels right. It is basically the "closest to any dot" rule with a speed.
  - The chance model beats the 600 m ring on photos too.
  - On new ground at least 450 m from every dot, the chance model and "closest to any dot" are roughly level.
- **Jumps:** new fire 1-2 km from a burning fire is about 4 times more likely than on a normal day. But the chance is still only about 1.4% per 300 m square.
- **Beat check list:** using the chance model to pick 3 spots per beat gives a small gain over simpler picks: 26% of lists hit a burning spot, against 24% and 22%.

## 1. Mid-fire photos as truth (`photo_test*/`)
**Setup.**
- The truth is 20 m Sentinel-2/Landsat pictures of burned-so-far ground at an exact minute: the fuel thread's chips, 2017-24.
- The forecast is issued at the last satellite look at least 1 h before the photo. In practice that is the night look about 9 h before a morning photo.
- Each forecast uses only the dots seen by then, and a model trained without that season. These models are lighter: 35% of rows and 200 trees.
- Pixels already inside a seen dot's footprint are removed.

**Score.** The score is AUC, which measures how well a method ranks burned ground above unburned (0.5 = guessing, 1 = perfect).

| truth set | photos | closest to any dot | chance model | 600 m ring |
|---|---|---|---|---|
| pixels inside the final scar | 151 | **0.78** | 0.57 | 0.51 |
| whole photo box (outside scar = unburned) | 209 | **0.84** | 0.63 | 0.58 |
| new ground only, 450 m+ from every dot | 155 | **0.82** | 0.78 | 0.70 |

**Model compared with "closest to any dot"** (95% bootstrap range):
- AUC difference: −0.26 to −0.16 inside the scar, −0.25 to −0.17 in the whole box, and −0.06 to −0.02 on new ground.
- Equal-area "found" (pick as much ground as truly burned) on new ground: the model finds 11.2% and the closest-dot rule 9.0%, a difference of +0.2 to +4.7 points. Per photo, though, the closest-dot rule wins more often (39% of photos against 32%).

**Model compared with the ring:** the model is better in every set, by +0.01 to +0.11 AUC.

**Why.** The model was trained on labels built from the dots plus a fixed speed. Those labels treat ground near a footprint as "already burned" and drop it from training. They also reward the 600 m distance where the next dot tends to appear.

The photos show something different: burned ground hugs the dots. New dots do land about 600 m away, which is what the review found, but the ground in between burns first.

**Grid check (17:45Z).** The chips' i0/j0 index the unpadded burn raster. `midscar.py` uses `rowcol` on the burn_2017 transform with no pad, and every year's raster has the same transform. `h2_photo_test.py` converts with that same transform. Across 118 chips, the scar centre sits a median 89 m from a VIIRS dot (90th percentile 168 m, none beyond 1.5 km). So there is no 2 km offset here, and these scores stand.

**Limits.**
- Nearly every photo is a morning one after a night look, so the lead time is 6-12 h.
- Ground outside the final scar is counted as unburned.
- The truth includes ground that burned unseen before the forecast time. That is what a user needs, but the model was never asked to predict it.

## 2. New fire near a burning fire (`jumps/`)
**Setup.** Every 300 m square 1-5 km from a fire's dots, at half of the satellite looks of 2017-26, in fire season. The question: does a new dot appear within 300 m in the next 24 h?

| distance | chance per square | normal-day chance | times normal | looks with any new dot in this band |
|---|---|---|---|---|
| 1-2 km | 1.4% | 0.36% | 3.9x | 28% |
| 2-3 km | 0.8% | 0.33% | 2.4x | 27% |
| 3-5 km | 0.7% | 0.30% | 2.4x | 44% |

- **It is not embers.** The FSI thread checked this ([fire_jumps_and_nearby_starts.md](../../ratapani/fsi/scouting/fire_jumps_and_nearby_starts.md), 17:34Z), using a stricter background in which locations are fixed and times are shuffled, including within the same month:
  - The real excess is smaller than the "times normal" column above. My normal-day chance is a season average, and that overstates the excess. Their figures are 1.6x at 1-2 km and 1.2x at 2-5 km.
  - The excess is not explained by shared weather, it is not downwind, and embers explain about 2% of it.
  - Within 1 km, most of it is the same burn split in two, so it counts as spread. At 1-5 km, most of it is separate human starts.
  - It peaks 6-12 h after a night (01:30) detection, which points to a morning check within 1-2 km of night dots.
- **Can a model say where?** It picks the riskiest tenth of squares. That tenth catches 34% of the new dots in 2025-26 (30% in held-out seasons). Past fire history alone catches 21%, and distance alone 18%. AUC is 0.78, against 0.71 for history and 0.55 for distance.
- **Use.** This could be a separate faint "watch zone" layer. It should not be merged into the spread chance, because the chances are too small to change a decision.

## 3. Three spots per beat each afternoon, 2025-26 replay (`beat_checklist/`)
**Setup.**
- At each 13:30 look, every beat with an active fire gets 3 spots, 150 m squares at least 450 m apart.
- The models were trained on 2017-24 only.
- The test is whether a spot burns in the next 24 h.

| how spots are picked | lists with a burning spot (dated truth) | spots that burn | lists hit by a new dot (raw dots) |
|---|---|---|---|
| chance model | **26%** | 15% | 6.5% |
| 600 m ring | 24% | 14% | 5.8% |
| next to latest dot | 22% | 13% | 4.6% |

The gain is small. Also, the "dated truth" here is built from the same dots (see section 1), so the real difference is probably smaller still.

## What to do with this
1. For "where is it burning / will be burned by next morning", use the arrival map, which ranks ground by closeness to every dot. Don't use the chance model's ranking for this.
2. If the chance map is kept, re-rank it so ground next to any dot comes first. The calibrated % is only trustworthy against dot-based labels.
3. Jumps: a faint separate layer at most.
4. The real limit is still the data: two looks a day at 375 m. More timed images (item 7) is the only way to test spread properly.

## Next step, done 16 Oct 18:00Z: the honest map and a morning check list
Figure: [figures/7_honest_map_and_morning_list.png](figures/7_honest_map_and_morning_list.png). Scripts: `scripts/h3_photo_calibrated.py`, `scripts/b2_morning_list.py`.

**Honest map (`photo_calibrated/`).** The chance that a 20 m spot is burned by the next-morning photo, fitted only on photos with each season held out. There were 209 photos and 1.06 M pixels, at a lead of 6-12 h.

| where | inside a seen satellite pixel | 0-200 m | 200-300 | 300-400 | 400-500 | 500-700 | 700 m-3 km |
|---|---|---|---|---|---|---|---|
| burned by morning | 19% | 16% | 13% | 9% | 6% | 3% | ~1.5% |

- **This plain distance table ranks as well as a small model fitted on the photos.** On the 0.5-1 scale it scores 0.83 against 0.84 (the gain has a 95% range of −0.004 to +0.014). The table is better calibrated: the photo-fitted model is overconfident above 10%.
  - Where the table says 1.7%, 1.7% came true.
  - Where it says 5.9%, 5.9% came true.
  - Where it says 12%, 11.5% came true.
- **The old chance model loses** (0.64), even after re-calibrating it on the photos.
- **Inside a seen satellite pixel, only about 1 in 5 spots has burned by morning.** These fires are much smaller than the 375 m pixel.

**Morning check list (`morning_list/`).**
- The setup: after each 01:30 look in 2025-26, every beat gets 3 spots, 300 m squares at least 450 m apart. A spot counts if a satellite dot lands within 300 m by the next night.
- These figures are for the 561 beat-mornings where the beat itself had a night dot. Results for all beats within 5 km of a night dot (3,332 lists) are in `morning_list/summary.json`.

| spots chosen | lists with any fire | lists with a NEW fire (>1 km from the last 2 days' dots) |
|---|---|---|
| **next to the night dots** | **24%** | 0% |
| 2 next to dots + 1 at 1-2 km | 21% | 3% |
| most fire-prone squares | 14% | 4% |
| 1-2 km ring | 8% | 6% |
| random | 9% | 5% |

- **Go back to the night dots.** That is where fire is next day: 24% of lists, against 9% for random spots.
- **A 1-2 km ring does not find new fires better than random spots** (6% vs 5%). The real 1-2 km excess (FSI thread) is too thin to aim a check at.

**ECOSTRESS lead (checked 18:25Z, not run).** The idea was to add ECOSTRESS 70 m hot pixels as extra dots and rescore the honest map on the photos. That test can't measure anything. Only 7 of the 209 photos have an ECOSTRESS pass between the night forecast and the morning photo, because the photos are taken ~10:30 IST and most passes come at 10-12 or 15-17 IST. Earth Engine also isn't reachable from this cloud session. A useful first check would be whether ECOSTRESS sees litter fires at all (hot 70 m pixels inside the 81 passes of 2019-24 with VIIRS within ±3 h). That check belongs with whoever has EE access, which is the PC or the big-fires thread.

**Dot-density and direction variants (checked 19:20Z on the same 209 photos, all fires).** These ideas came from the big-fires thread. Neither changes the plain closest-dot table, so it stays.
- **"Many dots nearby" kernel** (sum of exp(−d/400 m) over all dots so far): it ties the closest-dot rule, 0.842 against 0.839. The 95% range of the difference is −0.005 to +0.010.
- **Growth direction** (from the centre of earlier dots to the latest look, with weight 1 + a·cos(angle)): it makes things worse on the 130 photos where a direction exists. At a = 0.25 the score is 0.831, at a = 0.5 it is 0.819, and at a = 1 it is 0.774, against 0.836 without direction. At a = 0.5 the 95% range of the change is −0.028 to −0.007.
- **Scope.** This holds for the morning-after-night setting on all fires. Direction may still help on big fires, which is the big-fires thread's subject.
