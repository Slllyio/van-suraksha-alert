# Fire spread model: a fresh, critical review (15 Oct 2026)

Akkshay asked for a fresh look at the "spread model like C-DAC" because he suspects some claims are made up. I started from the raw satellite fire points and the frozen scar outlines (scar outlines v1, 2026-10-15), not from the READMEs. Every number below that I measured myself comes from `scripts/` and `results/` in this folder, and can be re-run.

**Built (16 Oct): see [IMPLEMENTED.md](IMPLEMENTED.md)** for the arrival-time maps and the calibrated 12/24/48 h chances.

Literature review (36 papers, which ones read in full is marked): [literature.md](literature.md).

## The answer in plain words

1. **The data, not the model, is the main limit.** Satellites look at Ratapani only twice a day (about 01:30 and 13:30). The three VIIRS satellites pass within an hour of each other, so they add second looks, not new times of day. A fire moves about 20-30 m an hour, so in 12 hours it moves about 300 m. The position of a VIIRS point is itself uncertain by about 300 m. So most of the "spread" between two looks is the same size as the measurement error.
2. **The learned model's gain is mostly simple geometry.** A rule with no learning ("the next fire will be about 600 m from the latest points, not on top of the old ones") lifts the next-look hit rate from 51% (persistence) to 67%. The learned model reports 78% on a similar test. So about 60% of its gain is this one rule; the rest (fuel dryness, terrain, timing) is real but smaller.
3. **Physics (Rothermel) cannot be tuned from this data.** Fuel load, spread speed and start time trade off against each other, and the back-fitted numbers sit on the edge of the search grid. The "7x speed" and "6 h start" figures are not reliable.
4. **Shape barely matters; location does.** If we knew a fire's final size and its true centre, a plain circle would score 0.60 against the outline. A circle at the first satellite point scores 0.42. All the clever models score about 0.50. So the useful question is "which way does it go", and one satellite pass cannot answer it.
5. **What would really help** is better observation of the fire while it burns (more timed images, a proper "arrival time" map per fire) and an honest probabilistic forecast ("chance this cell burns in the next 12/24/48 h"), not a sharper physics model. Ranked list in section 4.

Terms used: **persistence** = forecast that the fire stays where it was seen; **look** = one satellite overpass over Ratapani; **Sorensen** = overlap score between a forecast area and the true burned area, 0 (none) to 1 (perfect); **outline** = the scar thread's burned-area polygon from Sentinel-2/Landsat images.

## 1. Which numbers hold, which don't, which can't be checked

| Claim | Verdict | What I found (file) |
|---|---|---|
| "NOAA-20/21 would double the passes, every ~6 h" (spread README section 7) | **Wrong** | NOAA-20 and NOAA-21 pass 25-50 min after S-NPP. Looks over Ratapani come in two slots a day, 11-12.5 h apart, in every season (`r2.json`: 2025 has 3 satellites in 233 of 240 slots, all within ~50 min). |
| 44% of passes miss a burning fire | **Holds** | When one satellite sees a fire, the next satellite ~50 min later sees it only 53% of the time: 39% for one-pixel fires, 90% above 50 MW. Inside a fire's life, 33% of looks are silent. A second satellite raises looks-with-a-detection from 59% to 69%; a third adds nothing (`r2.json`). |
| Ignition to first detection: 3.5 h (FSI) vs ~15 h (fuel timing) vs ~6 h (back-simulation) | **3.5 h holds for afternoon detections; 15 h and 6 h don't** | Mid-fire Sentinel-2/Landsat pictures at 10:30 IST, 3 h before a 13:30 first detection: about half the fires had started (53% over 1 ha burned, 43% show active-fire pixels). So the typical start is about 3 h before an afternoon detection. Fires first seen at 01:30 (29% of fires) mostly had not started by 10:30 the day before (71%), so they started that afternoon or evening. The 15 h comes from fitting a straight line through a median of 3 points per fire, and its mean is -57 h, so it is unstable. The 6 h comes from a fit where 27% of fires hit the top speed of the grid and 22% hit zero lead; it is not identified. |
| Fuel thread update (16:32Z): start time and speed can't be separated; it depends on how often VIIRS misses a burning fire | **Agrees with this review; the missing number is measured here** | Our own data give that detection rate directly: one satellite sees a burning fire 53% of the time (39% for one-pixel fires), and a look with two or three satellites sees it 69% of the time (`r2.json`). The photo check (about half of afternoon-first fires already burning 3 h earlier) sits between the thread's two versions. |
| Front speed ~37 m/h, corrected to 24 m/h | **24-30 m/h is about right** | Independent check: if each outline burned from one point over the fire's detected life plus ~9 h, its radius grows a median 20 m/h (middle half 14-27) for multi-look fires (`r4.json`). Teak-litter burns measured in Ecuador ran 16-43 m/h (literature 5.2). The 37 m/h mixed in pixel jitter. |
| Physics needs ~7x its speed to burn the grown outlines in time | **Not reliable** | Same grid problem as above. Simple geometry says ~20 m/h radial growth over the detected life is enough, which is within the physics model's own range, so the 7x points to how the fit treats nights and silent passes, not to the fuel. |
| Learned restart 86% vs persistence 72% | **Reproduces, but read it carefully** | The earlier audit reproduced it exactly. Half its steps are 50-min satellite-to-satellite gaps where everything scores ~91%. At gaps of 10 h or more, persistence is 51% in my own rebuild (theirs 52%), and a no-learning ring rule gets 67% (`r5.json`). A "hit" counts any forecast pixel within 240 m of the next point, a generous tolerance. |
| Learned footprint 0.50 vs circle 0.45 | **Holds, but it is the "where" ceiling** | Buffering all of a fire's detections to the true area scores 0.51; the learned end footprint scores 0.515. A circle at the true centre scores 0.60 (`r7.json`, 844 fires). |
| Physics only ties a circle | **Holds** (earlier audit) | Expected: wind under canopy is not measured, ERA5 wind does not match fire runs, and slope barely matters for creeping litter fires. |
| "Ratapani fires peak noon-1 pm IST" | **Can't be checked** | VIIRS only looks at 13:30 and 01:30, and no geostationary satellite sees these small fires, so no dataset we have measures the time of day of the peak. |
| C-DAC's validated skill | **No skill score exists** | Their published system is one Sikkim fire, 1.72 km² forecast against 1.07 km² observed, with no baseline (literature 1.1). Our "physics ties a circle" does not contradict any published C-DAC number. |

## 2. What really limits spread prediction here

**Observation (the biggest limit)**
- **Two looks a day.** Every satellite we have passes at ~13:30 or ~01:30. MODIS Terra (10:30 / 22:30) would add new times, but it saw only 13% of the multi-look VIIRS fires: too coarse for litter fires.
- **Position error equals 12 h of spread.** The same fire seen by two satellites 50 min apart: points sit a median 290 m apart (90th percentile 780 m) (`r2.json`). At 12 h, new points sit a median 660 m from all earlier points (`r3.json`), so there is a real signal, but only about twice the noise.
- **Most fires have no track.** 76% of fires are seen at only one look; only 10% at three or more (`r2.json`). For three in four fires there is nothing to "spread" from.
- **Silent looks are common.** A third of the looks during a fire's life miss it.

**Truth (the outlines)**
- **Outlines are dated only to a window.** The image pair around a fire is a median 10 days apart (middle half 8-13). So the outline is "everything burned in those ~10 days connected to the alert", not "what burned by tomorrow".
- **Outlines are built from the alerts themselves.** A burned patch only counts if it touches a 200 m circle around an alert point. A model that is fed the same alert points has a built-in head start, so footprint scores flatter distance-to-alert methods. Only 2-5% of a fire's points fall more than 400 m outside its outline (`r6.json`), partly by construction.
- **Big fires are cut at the image chip edge.** Outlines are drawn inside a 3 x 3 km chip; 64% of fires seen on 3-4 looks and 91% of fires seen on 5+ looks touch the edge (`r4.json`). Exactly the fires where spread matters most are under-drawn.
- **Error bands.** Per the scar thread's own blind check, about 9% false edge and a median 22% missed ground. So a difference of ~0.05 Sorensen between two models is near the limit of what this truth can show.

**Method and evaluation**
- **Physics is not identifiable.** Speed, fuel load and start time can be traded against each other and still fit the same few points. Calibrating Rothermel on these data gives numbers that look precise but are not.
- **Some headline tests mix easy and hard steps.** The 50-min satellite-to-satellite steps inflate the average; only gaps of 10 h or more test spread.
- **The baseline was weak.** Persistence over all earlier points wastes area on the burnt-out middle. The fair baseline is "a ring around the latest points" (here 67%), and the literature says the same (Gerard et al. 2023; Gopakumar & Pannozzo 2026, literature section 4).

## 3. Quick experiments run for this review

| # | Question | Result | Script |
|---|---|---|---|
| E1 | Do the three satellites give more times of day? | No: two slots a day, satellites ~50 min apart | `r1_tracks.py`, `r2_revisit.py` |
| E2 | How often does a second satellite see a fire the first one saw? | 53% (39% one-pixel, 90% > 50 MW) | `r2_revisit.py` |
| E3 | Is 12 h spread bigger than position noise? | Yes, about 2x: 660 m vs 290 m median | `r3_spread_signal.py` |
| E4 | Do outlines match the VIIRS record? | Mostly, partly by construction; big fires truncated at chip edge | `r4_outline_vs_viirs.py`, `r6_dets_outside.py` |
| E5 | How much of the learned restart's gain is plain geometry? | Ring at 600 m around the latest look: 67% vs persistence 51%, same radius chosen in every held-out season (2017-2026), 1,901 steps of 10 h+ | `r5_geometry_rules.py`, `r5b_summary.py` |
| E6 | Is shape or location the problem? | Circle at true centre 0.60, at first point 0.42, all detections buffered 0.51 | `r7_shape_ceiling.py` |
| E7 | Does MODIS Terra fill the gaps? | Only 13% of multi-look fires get a Terra point | inline check, noted in E1 |

Caveat for E5: my fires are linked from all three satellites with the spread thread's 1.2 km / 30 h rule, on a 40 m grid; the spread thread's 78% is on its own fire set, so the comparison is close but not exact.

## 4. Ranked improvements, with the evidence for each

1. **Change the product to calibrated chances, scored fairly.** Issue at each 13:30 and 01:30 look: "chance each 40 m cell has fire by the next look / in 24 h / 48 h", with the chance a fire is still alive built in. Score with reliability plots and Brier score (how close the chances are to what happened) against the ring baseline, on 10 h+ gaps only. *Evidence:* E5 shows the old baseline was too weak; the literature shows half of published ML spread models fail against a fair persistence (literature section 4). This is also what Akkshay asked for (calibrated % per cell). The spread thread's 4o is heading this way; it needs the ring baseline added.
2. **Build one arrival-time map per fire, and make that the truth.** Combine every clear Sentinel-2/Landsat image during the fire (exact burned-so-far at 10:30, plus hot pixels), every VIIRS look as a pixel footprint, and silent looks as "probably not yet" evidence. Fit a smooth "time the fire reached here" surface. *Evidence:* Farguell et al. 2021 and Mandel et al. 2014 reached Sorensen 0.82 this way (literature section 3); our 331 mid-fire snapshots already show this works locally (fuel thread). It replaces the 10-day outline window with real timing.
3. **Fix the outlines for big fires.** Redraw any outline that touches the chip edge with a larger chip, and stop requiring burned patches to touch an alert circle when scoring spread (use a fire-independent burned-area map for the truth). *Evidence:* E4, 64-91% of multi-look fires touch the edge; the 200 m rule makes the truth depend on the input.
4. **Treat each look as evidence, not a fact (a "hidden fire state" model).** Keep a probability map of where fire is, update it at each look with how likely each satellite is to see a fire of that strength, day or night, near or far from nadir. *Evidence:* E2 (detection 39-90% by strength); FEDS (Chen et al. 2022) and data-assimilation papers (literature section 3). This also gives honest start times instead of the three conflicting numbers.
5. **Spend learning on direction, using the second look.** One pass says nothing about direction (spread README 4l: cues at 35-51%, near random); the move from the first to the second look predicts the run 63-65%. So the forecast should widen into a ring after one look and narrow toward the observed move after two. Keep the learned inputs that earned their place (dryness, earlier burns, barriers) on top of the ring.
6. **Demote physics to a helper.** Use Rothermel only for intensity and flame length (crew safety), not for where the fire goes, until item 2 gives arrival times good enough to calibrate it. *Evidence:* ties a circle; parameters not identifiable (section 1).
7. **More timed images.** Add Sentinel-2C and Landsat 9 scenes (more 10:30 snapshots), and Sentinel-3 SLSTR night/morning fire points for the larger fires. New small-satellite fire constellations may help later; I have not checked their access over India. *Evidence:* E1/E7: nothing else free fills the gaps.

What not to spend time on: wind (no measurable effect, several threads agree), finer grids than 40 m (point error is ~300 m), more physics fuel tuning.

## Files
- `scripts/r1_tracks.py` ... `r7_shape_ceiling.py`, `r5b_summary.py`: all experiments (inputs: `fire-alert-scars/alerts/`, `alerts_mp/`, scar outlines v1).
- `results/r2.json` ... `r7.json` plus per-step and per-fire tables.
- `literature.md`: the paper review.

Truth = scar outlines v1 (2026-10-15), error bands per USE_AND_LIMITS.md.
