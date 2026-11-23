# Why the forecast fronts don't match the real burn scars (17 Oct 2026)

Akkshay asked for a critical look, and then pasted an outside audit. This note measures where the gap comes from on the 146 big fires
in the C-DAC fronts atlas (`../cdac_fronts/`). Script `../scripts/gap_analysis.py`; one row per fire in `gap_classified.csv`.
The "real" burn state at each hour is the fire-continuity blend map inside scar outline v2 (84% of pixels right on 340 mid-fire photos).

## 1. The answer in plain words
- **Most of a big scar is not reachable from the first alert.** At the measured speed of 20-30 m an hour, a fire covers about 600 m in
  a day. But 49% of the ground burned in the first 24 h lies more than 600 m from the first alert's dots, and 20% lies more than 1 km
  away. Over the whole scar, 77% lies more than 600 m away and 58% more than 1 km. That ground burned from new fronts that later
  satellite looks reveal. Many are separate human starts (FSI check, spread review). A forecast grown from the first alert cannot
  draw them, however good its physics.
- **No single speed fits.** The forecast is about the right size on the median fire (0.93x at 24 h), but 38% of fires are too small
  (under two-thirds of the real size) and 27% too big (over 1.5x). Fuel, weather and terrain inputs have not explained which is which.
- **Even a perfect blob reaches only about 0.6.** A disc at the true burned ground's own centre, with the true size, scores 0.63 at
  24 h and 0.61 for the whole scar. The rest is patchy shape plus label error: outlines miss ~22% at the edges and are ~9% wrong inside.
- **Staff put fires out.** Edges and stops partly reflect crews, which no model sees.

## 2. How much each fix recovers (overlap with the real burned ground, median of 146 fires, 1 = perfect)
| What the forecast is given | By +24 h | Whole scar |
|---|---|---|
| First alert only (the atlas) | 0.44 | 0.39 |
| + the exact right size (perfect speed) | 0.51 | 0.44 |
| A plain disc at the first alert, right size (no physics) | 0.49 | 0.42 |
| Every satellite look so far, physics restarted from each (uses later looks) | 0.53 | 0.41 |
| + the exact right size | 0.58 | 0.51 |
| Just the 375 m blocks of every look, no model | 0.53 | 0.56 |
| Best possible single blob (true centre, true size) | 0.63 | 0.61 |

Physics adds about 0.02 over a plain disc of the same size. Restarting from each new look and getting the size right together recover
most of the reachable gap; the new fronts recover the rest only once a satellite has seen them. Caveat: the "real" timing is itself
rebuilt from the dots, which flatters the dot-based rows.

## 3. Main failure type per fire (at +24 h)
| Failure type | Fires | Median overlap | Rule |
|---|---|---|---|
| Good | 52 (36%) | 0.59 | overlap 0.5+ |
| New fronts far from the first alert | 49 (34%) | 0.29 | over 30% of the 24 h burn is more than 1 km from the first dots |
| Too big (too fast) | 21 (14%) | 0.36 | forecast over 1.5x the real area |
| Too small (too slow) | 12 (8%) | 0.41 | forecast under 0.67x the real area |
| Right size, wrong place or shape | 9 (6%) | 0.44 | the rest |
| Scar label doubtful | 3 (2%) | 0.02 | under 20 ha burned by 24 h, or over 30% of the outline more than 1 km from any dot |

Rules applied in the order listed. These are crude cut-offs, so read the counts as rough shares.

## 4. The audit, point by point
| Audit point | Status | Where |
|---|---|---|
| Score each horizon against the burn state at that hour, not the final scar | **Done in the atlas already**: the 6/12/24/48 h scores are against the burn state at that hour. The "48 h vs whole scar" line is a separate, extra score. | `../cdac_fronts/cdac_fronts_scores.csv` |
| Baselines (persistence, equal-area distance, physics) and failure classes on the same rows | **New, done now** | sections 2-3 above |
| The first detection is not the ignition | **Done before (4l)**: a back-fitted start lands right only 21% of the time (first look catches a flank); the first look covers 18% of the outline. Move from pass 1 to 2 gives direction 63% (the audit's ~70%). | README 4l, fire-continuity |
| Next-front model from sequential looks | **Done (4j, learned restart)**: best at the next satellite dots (77% vs ring 64% on 2025-26). On photos it beats closest-to-dots only beyond 450 m (+5); near the fire it loses. | README 4j, 4s, 4t |
| Final-footprint model | **Done (4i)**: 0.53 with barrier inputs vs circle 0.46 | README 4i, 4m |
| Physics as an input, not the authority | **Done**: physics features add ~0 to the learned models; physics alone ties a disc | README 4n, section 2 above |
| Update the state on every new look | **Partly**: the learned restart and the spread review's chance maps re-issue at every look. The row "restarted from each look" above shows the gain. No explicit compare-then-correct loop yet. | `research/spread-review/forecast/` |
| Time-stamped targets, "unknown" where no look fell | **Partly**: detection targets only count a horizon when a look fell in it. Pixel targets with an "unknown" class are **new**. They belong to the spread-review thread's chance model. | `research/spread-review/` |
| Treat 375 m pixels as blocks, not points | **Done in the maps** (blend and arrival maps use real footprints); finer sub-pixel work is the research thread's | fire-continuity, research thread |
| Probability map + expected area + uncertainty | **Done for burned-by-morning** (photo-calibrated chances by distance); expected area isn't done | `research/spread-review/HONEST_TESTS.md` |

## 5. What would actually change the picture
1. **Report the forecast as "where next, given what we've seen so far", re-issued at each look.** Don't promise the final scar from the
   first alert. The table above says this is where most recoverable skill is.
   The research thread's square-block notes (`ratapani/fsi/scouting/detection_squares_methods.md`) give the method for that loop. Treat
   each pass as "fire somewhere in this 375 m block, seen about half the time", using a measured position noise of median 254 m. Treat a
   covered pass with no fire as a weak "no". Don't read direction from 50-minute satellite pairs.
2. **Staff suppression logs from the 2027 field app** would separate where fires stopped from where they were put out.
3. **A satellite that sees between the 01:30 and 13:30 passes** (geostationary INSAT-3D/3DR, or ECOSTRESS-type passes) would time the
   new fronts.
4. **About 200 hand-checked outlines on high-resolution photos** would firm up the truth, which currently caps every score.
