# The "squares" experiments: VIIRS detections as real footprints, small-gap moves, sub-pixel position and "seen, no fire" (scouting round 17, 17 Oct 2026)

Asked by Akkshay: analyse the square blocks of the satellite fire detections and how they move. Get as much as possible out of them, even where the move and the time gap between squares are small, for the fire spread model.

This note holds the **experiments** (run today on our files). The reading and the published error numbers are in [detection_squares_methods.md](detection_squares_methods.md); they are not repeated here.

**How the work was set up**
- Ratapani, 2017-2026.
- Every satellite pass is kept as its own row with its own time. Nothing is merged into "looks".
- Scripts and small outputs: `code/squares/` (results in `code/squares/results/`).
- Terms:
  - **footprint**: the real ground area of one detection pixel (scan × track from FIRMS, turned to the satellite's track).
  - **small-gap pair**: two passes of one fire by different satellites less than 2 h apart (median 49 min).
  - **photo truth**: the 340 mid-fire Sentinel-2/Landsat chips of the fuel thread. Each one shows which ground had burned by that minute. The detections never touch them.
  - **hot pixels**: the 20-30 m Sentinel-2/Landsat fire pixels in `fire-alert-scars/out/af/`.
  - **AUC**: how well a score ranks burned ground above unburned ground. 0.5 is guessing, 1 is perfect.
- Ranges in brackets are 95% bootstrap ranges, resampled over fires.

## Bottom line
1. **The square is real, and its orientation is measurable, but neither changes where the fire is placed.**
   - Adjacent VIIRS pixels line up along the satellite track: 347° by day and 193° by night. This matches orbit geometry.
   - Turning the footprints to that angle changes nothing on photos. The difference from unturned footprints is −0.002 to +0.003 AUC.
   - Treating each pixel as a full square still ranks burned ground slightly *worse* than the plain point: −0.021 to −0.002.
   - The best ranking is still "many dots nearby": a kernel, +0.008 to +0.032 over the nearest point. A kernel over footprint distance ties it.
2. **As an extent map, the union of footprints is right but no better than circles of the same area.**
   - Against 200 m circles it scores +4 to +6 points of pixel accuracy, but only because its area is larger.
   - Against circles of the same area the gain is +0.7 points (+0.1 to +1.3).
   - Both under-map the fire. They mark 26-29% of the scar, while 49% had burned by the photo.
3. **In 94% of small-gap pairs, the two satellites' footprints overlap.** So the two looks never require the fire to have moved at all.
   - The median apparent move is 288 m in 50 min. That is grid geometry (see 4), not spread.
   - Real spread in 50 min is about 20 m.
4. **Error model from non-moving hot sources.** We used 104 industrial sites in MP (FIRMS type 2) and 28,412 pairs of looks by two different VIIRS satellites less than 2 h apart.
   - The apparent move of something that cannot move:
     - median 254 m;
     - 95th percentile 1,083 m when a look has 1 pixel;
     - 95th percentile 489 m when both looks have 4 or more pixels.
   - Pure grid jitter (a fixed point under randomly placed pixel grids) explains the median by itself: 235 m simulated against 247 m measured, plus about 50 m of geolocation error.
   - Fires' small-gap moves have the **same** distribution: median 286 m against 254 m, 95th percentile 1,086 m against 1,002 m.
5. **Small-gap pairs carry almost no spread signal.**
   - Share of pairs beyond the no-movement noise (5% expected by chance):
     - 8.5% for the centre shift;
     - 9% for the FRP-weighted centre shift;
     - 7% for the change in pixel area;
     - 15% for the FRP change;
     - new pixels appear in 68% of pairs, against 63% expected.
   - **Direction:** the shift points the way the fire grows at the next look (6-30 h later) in 54-55% of pairs (51-58). For new pixels it is 55.5% (52-59), and for MODIS–VIIRS pairs 48%. The pairs that are beyond the noise do no better (50-54%).
   - The previous growth direction gets 69% (63-75). Adding the small-gap shift to it changes nothing (69.3% vs 68.9%).
   - **Amount:** after allowing for fire size, new pixels and centre shift relate weakly to next-look growth (partial Spearman 0.07, range 0.01-0.14). FRP change and area change do not. Predicting "any growth at the next look" goes from AUC 0.563 to 0.573.
   - **On photos:** pushing the dot kernel towards the small-gap direction makes it *worse*: −0.07 to −0.01 at strength 0.5.
6. **Minimum detectable speed in a single small gap is 600-1,300 m/h**: the 95% noise divided by the 49 min gap, for 4+ down to 1 pixel. That is 25-50 times the real 25 m/h. A single small gap cannot see Ratapani spread. Only many passes fitted together can, which is what the big-fires 25 m/h front fit already does.
7. **Sub-pixel position: no gain from FRP or brightness weighting inside VIIRS clusters.** Against same-day hot pixels (1.7-3.7 h earlier; 424 clusters of 2+ pixels):

   | estimator | median distance to the hot-pixel centre |
   |---|---|
   | plain centre | 369 m |
   | FRP-weighted | 366 m (closer in 38% of clusters, farther in 52%) |
   | FRP²-weighted | 380 m |
   | brightness-weighted | 392 m |
   | PSF fit | 392 m |

   - 57% of VIIRS clusters are a single pixel, which leaves nothing to weight.
   - For single VIIRS pixels the hot pixels sit *outside* the footprint 65% of the time. The fire has moved, or was on another front, by the time VIIRS looks 2-3 h after Sentinel-2/Landsat.
   - Terra MODIS passes within 15 min of the hot pixels. For single Terra pixels the hot pixels are inside the 1 km footprint 97% of the time, and towards its middle: 75% in the inner half of the area, against 50% if spread evenly. So the centre of a pixel is informative when the look is at the same moment.
   - Moving the dots to their FRP-weighted cluster centre changes the photo score by −0.003 to +0.024. That is not significant.
8. **The overlap of two sensors' footprints concentrates the fire but does not contain it** (coordinator's question).
   - **Terra MODIS + VIIRS:** the overlap has 3.3 times (2.2-4.6) the hot-pixel density of the VIIRS footprints, but it holds only 20% of the hot pixels.
   - **Two VIIRS satellites:** the overlap is no denser than the rest (1.13 times, 0.94-1.32).
   - **On photos:** cutting footprints to their overlaps gives +0.006 AUC (−0.004 to +0.014; n.s.). As an extent map it is worse: IoU −0.065, because the map shrinks further.
   - So use the overlap as a soft weight at most, never as a hard limit.
9. **"Seen, no fire" (negative evidence) is real information, but it is already carried by the dot density.**
   - At the same distance from earlier footprints, ground that four or more passes saw clear is less often burned:
     - 400-700 m away: 12% against 25%;
     - 0-200 m away: 60% against 73%.
   - Added to the distance features in a held-out-season model, it gives:
     - forecast AUC ±0.000 (−0.011 to +0.010);
     - reconstruction pixel accuracy +0.6 points (+0.0 to +1.3).
   - The FIRMS files do not hold the pixels that were looked at and found clear. "Seen clear" had to be approximated, so this is a lower bound.
10. **What to do:** see "Next steps" at the end. In short:
    - keep points plus a kernel for placement;
    - use footprints only for "could the fire be here";
    - stop reading direction or speed from small gaps;
    - feed every pass as a separate timed observation into one fit or filter;
    - if negative evidence is used, it belongs as a soft likelihood in that fit, not as a map layer.

## 1. Footprints, not points (`s0_prep.py`, `orient.py`, `s1_footprints.py`)
**Data.**
- 2017-2025: FIRMS standard files in `fire-alert-scars/alerts/`. All fields are present: bright_ti4, bright_ti5, scan, track, frp, confidence, daynight, type.
- 2026: the FIRMS archive (`alerts_mp/`). Its points are the true ones, with scan and track. They replace the Earth Engine centroids, which lack scan/track and sit up to ~190 m off.
- Fires come from the big-fires rule (inside scar + 200 m, day before the first event to 2 days after the last): 16,913 detections. S-NPP 7,953, NOAA-20 6,313, NOAA-21 1,763, Aqua 574, Terra 310.

**Orientation.**
- Within one pass, the vector between adjacent pixels clusters at two angles:
  - day passes (ascending): 167.5° and 77.5°;
  - night passes (descending): 7.5° and 97.5°.
- Orbit geometry for a 98.7° sun-synchronous orbit at 23° N gives a track heading of 346.9° by day and 193.1° by night.
- So each footprint is a scan × track rectangle tilted about 13° from north, the opposite way by day and by night (26° apart).
- Median pixel: 450 m (scan) × 476 m (track); 0.32-0.80 km across.

**How footprints change the apparent move** (2,572 small-gap VIIRS pairs, median gap 50 min)

| | value |
|---|---|
| median centre-to-centre move | 288 m (165 m along scan, 171 m along track) |
| median move by pixel size: 300-420 / 420-520 / 520-650 m | 218 / 290 / 355 m |
| pairs whose two footprint sets overlap | **94%** |
| move the two looks *require* (gap between the footprint sets) | median 0 m, 90th percentile 0 m |
| overlap as a share of the smaller footprint set | median 54% |

- Bigger pixels make bigger apparent moves.
- In almost every pair the second look is consistent with no movement at all.
- [inference] The "300 m in 50 min" seen in big-fires §10 is the footprint itself, not the fire.

**Photo test, forecast** (203 photos, 171 fires; VIIRS seen ≥1 h before, within 4 days and 4 km; same set-up as big-fires b6b)

| score | AUC | new ground only (188) | vs nearest point |
|---|---|---|---|
| nearest point | 0.782 | 0.746 | |
| nearest footprint, unturned (old) | 0.771 | 0.743 | −0.021 to −0.001 |
| nearest footprint, turned to track | 0.772 | 0.743 | −0.021 to −0.002 |
| nearest half-size footprint | 0.782 | 0.745 | −0.004 to +0.003 |
| footprints cut to near-time overlaps (VIIRS) | 0.777 | 0.747 | −0.018 to +0.008 |
| same, with MODIS | 0.772 | 0.743 | −0.028 to +0.005 |
| **kernel of points, exp(−d/400 m)** | **0.802** | **0.762** | **+0.008 to +0.032** |
| kernel of footprint distance, 200 m | 0.800 | 0.761 | +0.004 to +0.030 |
| kernel of footprint distance, 400 m | 0.801 | 0.763 | +0.003 to +0.033 |

- Turned minus unturned: −0.002 to +0.003. The tilt does not matter at this scale.

**Extent: "burned by the photo" as a map** (same 203 photos; truth: 49% of the scar had burned)

| map | marks this share of the scar | pixel accuracy | IoU (overlap with truth) |
|---|---|---|---|
| inside 200 m circles | 21% | 0.686 | 0.320 |
| inside circles of the footprint's own area | 28% | 0.731 | 0.408 |
| inside the union of footprints, unturned | 29% | 0.739 | 0.420 |
| **inside the union of footprints, turned** | 29% | **0.739** | **0.418** |
| inside half-size footprints | 11% | 0.606 | 0.169 |
| footprints cut to overlaps | 24% | 0.705 | 0.353 |

- Footprints vs circles of the same area: accuracy +0.7 points (+0.1 to +1.3), IoU +0.9 (−0.1 to +2.0).
- **So the union of footprints is the right extent rule (the fuel thread found the same: the front sits at the footprint's far edge), but its gain over circles is mostly area.** Every rule here under-maps.
- [inference] Ground burned before the first look, and fronts no satellite flagged, are missing from any map built from detections.

**Reconstruction** (continuity's nearest-look rule, every VIIRS pass of the fire before and after the photo; 212 photos, 126 with passes on both sides). The arrival time of a pixel is the time of the nearest point or footprint. Pixel accuracy:

| shape | all | passes on both sides |
|---|---|---|
| point | 0.782 | 0.806 |
| footprint, unturned | 0.781 | 0.803 |
| footprint, turned | 0.781 | 0.803 |
| half-size footprint | 0.783 | 0.807 |

- Footprint minus point: −0.005 to +0.002.

## 2. Small-gap pairs: error model and signal (`s2b_smallgap.py`, `s2c_jitter.py`, `s2d_photo.py`)
**Error model.** It uses things that cannot move. These are 104 MP industrial hot sources (FIRMS type 2 in the 2018-2026 archive, grouped by 3 km cell), each seen in at least 20 passes. A pair is two looks by different VIIRS satellites less than 2 h apart. There are 28,412 such pairs, almost all ~50 min apart.

| pixels in the smaller look | pairs | median apparent move | 95th percentile |
|---|---|---|---|
| 1 | 21,584 | 262 m | 1,083 m |
| 2 | 5,325 | 235 m | 804 m |
| 3 | 1,191 | 211 m | 612 m |
| 4+ | 312 | 204 m | 489 m |
| fires, all VIIRS small-gap pairs | 2,420 | 286 m | 1,086 m |

Other noise figures from the static sites:
- the FRP-weighted centre has the same noise (95th percentile 957 m);
- pixel area and FRP change by up to ×3.6-4.0 (95th percentile |log ratio| 1.27 and 1.38) with no change at the source;
- a "new pixel" (outside every footprint of the earlier look) appears in 55% of pairs with 1 pixel and 85% with 4+, with nothing moving.

**Grid jitter alone** (a fixed point, each look's grid at a random offset and turned to its track, matched pixel sizes):
- simulated median 235 m and 95th percentile 443 m, against 247 m and 764 m measured on single-pixel static pairs;
- adding 50 m of geolocation error (per axis) matches the median; 100 m gives 285 m.
- [inference] The median is grid geometry. The heavy tail is a few large geolocation errors, or sites with more than one hot stack.
- This agrees with the methods note: 263 m simulated, and 55-60 m published geolocation error.

**Signal tests** (2,420 VIIRS–VIIRS pairs on fires; 865 have a next look with new burning to point at).

| signal in the small gap | beyond the 95% noise | same way as next-look growth | vs next-look new area (partial on size) |
|---|---|---|---|
| (d) centre shift | 8.5% | 54.2% (51.1-57.3) | 0.07 (0.01-0.12) |
| (d) FRP-weighted shift | 9.0% | 54.6% (51.3-57.7) | 0.07 (0.01-0.12) |
| (d) same, only pairs beyond the noise | | 54.3% (44.7-63.6), n 138 | |
| (a) new pixels, bearing | 68% (63% expected) | 55.5% (51.7-59.1), n 638 | 0.07 (0.02-0.14) |
| (b) change in pixel area (duplicates counted once) | 6.8% | | 0.00 (−0.06 to +0.05) |
| (c) FRP change | 15% | | 0.06 (−0.01 to +0.11) |
| MODIS–VIIRS pairs, centre shift | | 47.9% (43.3-52.2), n 309 | |
| *previous growth direction (persistence), for comparison* | | **68.9% (63.2-74.6)**, n 492 | |
| persistence + significant FRP shift | | 69.3% (64.3-74.5) | |

Notes on the table:
- **Held-out-season model of "any growth at the next look":** AUC 0.563 from size, FRP so far and day/night; 0.573 with (a)-(c) added.
- **Fraction of small-gap pairs that carry signal:** about 3-4% above chance for position, about 10% for FRP. Even those do not point the way the fire grows next.
- [inference] The FRP change is real: fires flicker more than chimneys. But it reflects how hard the fire is burning at that minute, not where it is going.
- **Minimum detectable speed** (95% noise ÷ 49 min): 1,326 m/h with 1 pixel, 985 with 2, 749 with 3, 598 with 4+.

**On photos** (98 photos with a small-gap pair in the 24 h before):
- Weighting the dot kernel towards the pair's direction lowers the AUC:
  - FRP shift: −0.022 to +0.002 at strength 0.25, −0.066 to −0.014 at 0.5;
  - new pixels: −0.025 to −0.004 at 0.25, −0.074 to −0.021 at 0.5.
- Even the persistence direction lowers it on photos (−0.073 to −0.003 at 0.5), as the spread review found.
- [inference] Burned-by-now ground hugs the dots. Direction is about where the *next* new burning appears, not about which nearby ground has burned.

## 3. Sub-pixel position (`s3_subpixel.py`, `s3c_overlap.py`)
**Set-up.**
- Clusters are pixels of one pass that touch: within 1.3 pixels along both scan and track.
- Truth is the centre of the same-day hot pixels within the cluster's footprints + 300 m.
- VIIRS day passes come 1.7-3.7 h after Sentinel-2/Landsat (median 2.7 h). There are no closer pairs: Sentinel-2/Landsat cross at ~10:45 IST, VIIRS at 12:00-14:30 IST.
- Terra MODIS crosses within 15 min.

| clusters | n | plain centre | FRP | FRP² | brightness | PSF fit |
|---|---|---|---|---|---|---|
| VIIRS, 2+ pixels | 424 | 369 m | 366 | 380 | 392 | 392 |
| VIIRS, 2+ pixels, gap ≤2 h | 41 | 373 | 373 | 380 | 357 | 382 |
| VIIRS, 3+ pixels | 206 | 425 | 425 | 424 | 442 | 465 |
| Terra MODIS, 2+ pixels | 15 | 283 | 237 | 250 | 286 | 328 |

- The figures are median distances to the hot-pixel centre.
- Distance to the nearest hot pixel tells the same story: 242 m plain, 240 m FRP-weighted.
- The PSF fit is worse by a median 46 m (21-71) on 3+ pixel clusters.
- [inference] The weights fail because neighbouring FRP values are nearly equal: the heat thread found a correlation of 0.93, and pixels overlap near the swath edge. A real sub-pixel fit would need the radiances of the non-fire neighbours, which FIRMS does not give.

**Where the hot pixels sit inside a single footprint.**

| | n | hot centre inside the footprint | share of those in the inner half of the area (even spread = 50%) |
|---|---|---|---|
| VIIRS (2-3 h later) | 572 | 35% | 47% |
| Terra MODIS (≤15 min) | 29 | 97% | 75% |

- At the same moment, the pixel centre is a fair guess (MODIS).
- 2-3 h later, the VIIRS pixel no longer covers where Sentinel-2/Landsat saw the fire in two cases of three.
- [inference] This is the same lag the fuel thread found: the true front sits at the far edge of the footprints.

**Overlap of near-time footprints** (day passes, footprint sets of two sensors).

| pair | pass pairs | overlap / union area | hot pixels in the overlap | density vs the VIIRS footprints alone |
|---|---|---|---|---|
| Terra MODIS + VIIRS (<3 h) | 46 | 6% | 20% | **3.3× (2.2-4.6)** |
| VIIRS + VIIRS (<2 h) | 252 | 14% | 16% | 1.13× (0.94-1.32) |

**Photos with sub-pixel dots** (203 photos), moving each dot to its FRP-weighted cluster centre:

| score | AUC |
|---|---|
| nearest point, pixel centres | 0.782 |
| nearest point, FRP-weighted centres | 0.793 (−0.003 to +0.024) |
| kernel, pixel centres | 0.802 |
| kernel, halfway to the FRP-weighted centre | 0.804 (−0.001 to +0.006) |

- [inference] The small gain for the nearest point comes from pulling clusters together, which mimics the kernel. It is not better placement.

## 4. Negative evidence: "the satellite looked and saw no fire" (`s4_negative.py`)
**What FIRMS can and cannot say.** The FIRMS files list only fire pixels. Pixels that were viewed and found clear, or hidden by cloud, are not in them. That information is in the VNP14IMG fire-mask granules, which need an Earthdata login, so it was not used here. The approximation:
- **Pass looked at Ratapani:** the satellite has MP archive detections within 250 km of Ratapani in that pass, or detections on both sides of it.
- **Pass was active on this fire:** the same pass flagged at least one pixel of the fire. This proves the fire area was in view and not cloud-hidden.
- **Seen clear:** a 20 m spot is "seen clear" at an active pass if it lies outside every footprint of that pass and within 1.5 km of one.
- Cloud is unknown and assumed clear (Feb-May is mostly dry). Detection chance is only ~53% per satellite, so one "seen clear" is weak evidence.

**Burned-by-photo share** (forecast setting: passes ≥1 h before the photo; 165 photos, 319k pixels)

| distance from earlier footprints | seen clear by 0-1 passes | 2-3 | 4+ |
|---|---|---|---|
| inside a footprint | 89% | 89% | 89% |
| 0-200 m | 73% | 59% | 60% |
| 200-400 m | 43% | 34% | 34% |
| 400-700 m | 25% | 21% | 12% |
| 700-1,500 m | 16% | 12% | 10% |

**Held-out-season logistic models** (every season predicted by a model fitted on the others):

| setting | distance features only | + negative evidence | difference (range) |
|---|---|---|---|
| forecast, AUC | 0.795 | 0.795 | −0.011 to +0.010 |
| forecast, pixel accuracy | 0.766 | 0.769 | −0.002 to +0.008 |
| reconstruction, AUC | 0.820 | 0.819 | −0.009 to +0.010 |
| reconstruction, pixel accuracy | 0.790 | 0.797 | **+0.000 to +0.013** |

- The distance features are distance to footprints, the dot kernel and, for reconstruction, distance to later footprints and the nearest-look time.
- For reference, the plain nearest-look rule on the same 165 photos scores 0.776.
- The model's weights say "more clear looks, less likely burned" (−0.44 standardised). Ground seen clear *after* it was inside a footprint is also less likely burned (−0.14 to −0.22).
- [inference] Pixels seen clear by many passes are the same pixels with few dots nearby, so the dot kernel already holds most of this.

## Limits
- Static industrial sites stand in for "non-spreading fires". They are hotter and steadier than litter fires, so their FRP noise is a lower bound for fires.
  - Fires whose later scar shows no growth were not used. Our scars are grown from 200 m circles round the detections, so "no growth" cannot be judged independently of the detections.
- Hot pixels are 1.7-3.7 h before the VIIRS day pass. Sub-pixel tests for VIIRS therefore mix placement error with real movement. The only near-simultaneous truth is Terra MODIS (n = 15-29).
- Photos are mostly morning photos after a night pass (6-12 h lead), as in every earlier test.
- 2026 uses the FIRMS archive points. The photos are 2017-24, so none of the photo numbers depend on 2026.
- Negative evidence is approximated (no fire-mask granules, no cloud mask).

## Next steps
**Spread thread**
- Stop using any single small-gap move, pixel-count change or FRP change as a direction or speed signal.
- Put every pass in as its own timed observation inside one likelihood or filter. The fit should treat each footprint as "fire somewhere inside, P(detect) ≈ 0.5", and "seen clear at an active pass" as a soft likelihood. This is the Farguell / Haley arrival-time approach in the methods note.
- Use the 95% noise table above (by pixel count) as the observation error.

**Big-fires thread**
- In section 10, replace the "short gap = 300 m apparent move" reading with "94% of short-gap footprints overlap; required move 0 m".
- Keep the 25 m/h multi-pass front fit; it is the only speed estimate that beats the noise. It can be given proper per-pass errors from the noise table: 1-pixel looks ~2× the error of 4-pixel looks.
- Use the turned footprints from `s_lib.foot_dist` for any atlas drawing.

**Continuity thread**
- Keep points plus kernel (or nearest look) for the arrival map. Footprints, turning, overlaps and FRP weighting do not improve it on photos.
- The one small honest gain is +0.6 points of pixel accuracy from adding "seen clear" counts to a held-out-season model. Worth adding only if the map is ever refitted.

**Data that would actually help**
- The VNP14IMG fire-mask granules: real "clear / cloud / fire" for every pixel. This needs an Earthdata login on Akkshay's PC, and no credentials are stored here. They would turn the negative evidence from an approximation into a measurement.
- Same-time 30 m truth for VIIRS: Landsat/Sentinel-2 never cross at the VIIRS times. ECOSTRESS passes at other hours (lead in the big-fires README).

## Files (`code/squares/`)
- `s0_prep.py`: detections with all fields, turned footprints, passes, fire assignment.
- `orient.py`: footprint orientation check (`results/orientation.txt`).
- `s_lib.py`: footprint distance, photo truth cache, scoring.
- `s1_footprints.py`: experiment 1 (`results/e1_*`).
- `s2b_smallgap.py`, `s2c_jitter.py`, `s2d_photo.py`: experiment 2 (`results/e2_*`).
- `s3_subpixel.py`, `s3c_overlap.py`: experiment 3 (`results/e3_*`).
- `s4_negative.py`: experiment 4 (`results/e4_*`).
- Rerun: `SQ_SCRATCH=<dir> python3 s0_prep.py`, then the s1-s4 scripts in order. The big intermediates (`det_all.parquet`, `photos.pkl`, static pairs) stay in the scratch dir.
