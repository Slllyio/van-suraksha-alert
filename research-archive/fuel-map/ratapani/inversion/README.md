> **WITHDRAWN as fuel-load estimates (Oct 15 2026, after the fuel review `research/fuel-review/README.md`).** Nothing in this file is a fuel measurement.
> - Fuel load cannot be identified from fire size or speed. The same fires fit equally well with more fuel, a looser bed, a light breeze, or a different start time.
> - Everything here was fitted against the research burn-label rasters, which are about 2.4x smaller than the grown scar outlines now used as the project's truth.
> - The class table below does not match `inversion.json`. For grass/scrub/sparse, the code gives 2.7-5.5 t/ha against the 1.0-2.4 in the table.
> - The back-simulation's 1.7-7x speed factor depends on how often VIIRS is assumed to miss a burning fire, and its best fits sat at the top of the search range.
>
> Kept only as a record. Fire timing and ignition work now belongs to the spread thread. The map's loads come from the litter budget in `../README.md`.

# Fuel load per forest class, back-solved from real fires (15 Oct)

Akkshay's idea: if the true fuel loads are unknown, learn them from fires. We run the spread model, compare its burned area with the real burn scar, and use each forest class's share of every scar to back out per-class loads as intervals.

**Data:** the spread thread's 1,398 VIIRS S-NPP fires from 2017-24 that left a mapped scar. Scars come from the same rule as spread/score.py (reproduced exactly: same events, same scar pixels). Each scar is split into 4 classes at 20 m:
1. closed teak: S2 canopy ≥ 0.4, teak probability ≥ 0.5
2. closed other deciduous
3. open forest: canopy 0.1-0.4
4. grass/scrub/sparse

Fires that are at least 60% one class ("pure") number 277 teak, 159 other deciduous, 1 open forest and 263 grass/scrub.

## Method 1: spread model against scar size
- **Model run:** the spread thread's final configuration (loose teak bed, leaf fall interpolated to the fire date, ROS ×2, roads as barriers, no wind). Area is compared at the last detection + 12 h.
- **Regression:** a median regression of log(scar area / forecast area) on the class shares gives a per-class area correction. Intervals are 90% bootstraps.
- **Area to rate of spread:** area grows as ROS² (shape ≈ a disc, per the spread thread's tests).
- **Rate of spread to load:** on our loose litter bed, Rothermel ROS is proportional to load, since doubling the load doubles the ROS (checked).
- **Two scenarios for the ×2:**
  - Keep the fitted ×2 as a non-fuel factor (wind gusts, spotting, unmapped fuel).
  - Put all of the ×2 on the load.

  The truth lies between them, so together they bound the interval.

| Class | Load the model used (t/ha, at fire time) | Scar ÷ forecast area | Load, ×2 kept as non-fuel (t/ha) | Load, ×2 on load (t/ha) | Interval to use (t/ha) |
|---|---|---|---|---|---|
| Closed teak | 1.65 | 0.47 (0.41-0.55) | 1.13 (1.06-1.22) | 2.26 (2.11-2.45) | **1.1-2.5** |
| Closed other deciduous | 1.65 | 0.60 (0.47-0.78) | 1.28 (1.13-1.46) | 2.56 (2.26-2.91) | **1.1-2.9** |
| Open forest | 1.18 | 1.7 (0.63-3.35), 1 pure fire | 1.54 (0.94-2.16) | 3.08 (1.87-4.32) | **0.9-4.3** (weak) |
| Grass/scrub/sparse | 0.59 | 3.35 (2.82-4.11) | 1.08 (0.99-1.20) | 2.16 (1.98-2.39) | **1.0-2.4** |

## Method 2: fire radiative energy (independent of the spread model)
- **Energy estimate:** fuel burned per m² = 0.368 kg per MJ of fire radiative energy (Wooster 2005), divided by scar area. Energy is the mean S-NPP overpass FRP times duration ("mid"), or times 6 h per overpass ("low").
- **Results for pure fires** (median, with IQR in brackets):

  | Class | Low (t/ha) | Mid (t/ha) |
  |---|---|---|
  | Teak | 3.1 (1.2-9.1) | 6.2 (2.4-17.8) |
  | Other deciduous | 2.5 (1.2-6.3) | 5.1 (2.5-12.5) |
  | Grass/scrub | 3.2 (1.2-9.4) | 6.4 (2.5-18.7) |

- **Interpretation:** the scatter is 3-8x, and two looks a day cannot pin down the energy. This method does not separate the classes. It does say that the fuel burned is not far below the 2-3 t/ha the spread method gives.

## What it tells us
1. **Closed forest litter at fire time is about 1-3 t/ha.** The spread method's central range (2.1-2.9 if the ×2 is load) matches the literature for teak floors (2.4-3.9 t/ha) and the low FRP numbers.
2. **Teak and other deciduous cannot be told apart by fire.** Their intervals overlap, and other deciduous is, if anything, slightly heavier. This agrees with the teak-mix bed test.
3. **The map underloads grass/scrub/sparse land by about 2-4x.** Real fires there burn 3.4x the area the model predicts. The map gives 0.6 t/ha; fires behave as if it is 1-2.4 t/ha. This is the one clear correction the fires ask for.
4. **Caveats:**
   - Mapped scars can stop short of the true front (makes loads look lower), and neighbouring fires can merge into one scar (makes loads look higher).
   - The area ∝ ROS² assumption breaks where roads or old burns cap a fire.
   - Only S-NPP passes are used.
   - The ROS ×2 is confounded with load, which is why each class gets an interval, not a number.

## From pass-to-pass speed (Oct 15)

Akkshay's idea: put each fire's VIIRS detections on its own scar and measure how far the fire moved between two passes. Script `passfront.py`, table `passfront.parquet`, examples `passfront_examples.png`.

Method: S-NPP + NOAA-20 + NOAA-21 detections (Jan-Jun 2017-24), fires seen on 2 or more passes. Each detection is snapped to its scar (kept if within 400 m). Distance is measured inside the scar (walking only over burned pixels) from the first-pass pixels. The front at each later pass is the farthest detection so far. For each interval of 3 h or more: front advance (m/h), area newly enclosed (ha/h), and the fuel-class mix of that band. Result: 281 intervals from 221 fires, mostly ~12.5 h apart (afternoon pass to night pass and back).

| | intervals | front speed, median (m/h) | 90% CI (bootstrap by fire) | area per hour (ha) |
|---|---|---|---|---|
| all | 281 | 37 | | 1.3 |
| closed teak | 150 | 32 | 29-41 | 1.3 |
| closed other deciduous | 73 | 38 | 33-46 | 1.4 |
| grass / scrub / sparse | 56 | 38 | 31-53 | 1.4 |
| open forest | 2 | too few | | |
| afternoon -> night | 156 | 43 | | 1.9 |
| night -> next afternoon | 125 | 31 | | 0.8 |
| moves of 375 m or more only (beyond VIIRS position error) | 180 | 54 | | |

- **Speed is the same in every class** (median regression on class shares: teak 43, other deciduous 35, grass 47 m/h, standard errors 6-9). Speed cannot tell the classes apart, which matches the scar-size result that teak and other deciduous are indistinguishable.
- Fires keep moving overnight. The interval that holds the afternoon peak is about 40% faster than the one that holds the night.
- About 1 km a day at the front, about 30 ha a day burned.

### Load from speed (Rothermel, loose litter, moisture averaged over 3 / 5 / 7%)

| bed density | under-canopy wind | load for 37 m/h (t/ha) | for the 29-46 m/h class range |
|---|---|---|---|
| 2.5 kg/m³ (loose teak litter) | none | 3.6 | 2.8-4.5 |
| 2.5 | 0.3 m/s | 2.1 | 1.7-2.6 |
| 2.5 | 0.6 m/s | 1.2 | 0.9-1.5 |
| 4 | none | 5.3 | 4.1-6.5 |
| 4 | 0.3 m/s | 3.3 | 2.5-4.1 |

The current 1.5 t/ha loose bed with no wind runs at 15 m/h against the observed 37. That is the spread model's ROS x2 seen directly, from speed rather than final size. Speed alone cannot say whether the missing x2.4 is more fuel or a light breeze under the canopy: 3.6 t/ha with no wind and 2.1 t/ha with 0.3 m/s give the same speed.

Two independent checks break the tie towards fuel:
- FRP-based consumption is about 2.5-3 t/ha (median).
- Published teak floor litter is 2.4-3.9 t/ha.

The consistent reading is **about 2.5-3.5 t/ha of loose litter in every forest class, with little or no wind needed**. In other words, the ROS x2 factor is mostly fuel load: the map's literature values are about half of what actually burns. This is an inference and has not been measured on the ground.

Caveats:
- VIIRS positions carry ~375 m error, which is about ±30 m/h on one 12 h interval. Medians over many intervals are fine; single intervals are not.
- Front advance is a lower bound when a fire paused inside the interval. Mid-fire intervals give the same median (36 m/h), so pauses are not dominant.

Spread thread's reply (Oct 15):
- In their engine, ROS is linear in load at a fixed bulk density. So 1.5 t/ha with ROS x2 is identical to 3.0 t/ha with no factor: same front, same area, same outline. They now state the factor as fuel, 3.0 t/ha at fire time.
- Their smoke plumes in 273 mid-fire Sentinel-2 scenes show that wind direction does not predict where the fire goes next. This supports reading the x2 as load rather than a breeze.

### What else the speeds say (Oct 15, `passfront2.py` / `passfront2.parquet`)

**Intensity.** Byram fireline intensity = 18,000 kJ/kg x fuel consumed x speed. With 0.25-0.3 kg/m² consumed:

| front speed | intensity | flame length |
|---|---|---|
| 37 m/h (typical) | 46-56 kW/m | about 0.5 m |
| 116 m/h (fast) | 145-175 kW/m | about 0.8 m |

This is far below the ~350 kW/m limit for hand-crew direct attack. Beaters can stop the head, and a 2-3 m bare line (1.5-2x flame length) should hold, which fits roads acting as barriers in the spread model.

**Inputs that do not change speed** (median regression, all p > 0.4):
- leaf-fall stage at fire date (the median is already 95% fallen)
- slope
- teak share

Once the litter is down, how much has fallen matters less than whether it is dry.

**Ground burned the year before is slow.** Intervals crossing such ground run at 17 m/h (only 9 intervals). Ground burned 2-3 years ago runs at 36 m/h, and older ground at 42 m/h. This is weak evidence that litter needs about 2 years to rebuild fully, consistent with the burn-frequency factor in v2.

**Season to season.** 2018-19 ran at about 48 m/h, and 2021-24 at 25-31 m/h. This is unexplained. It could be dryness, or the extra NOAA-20/21 passes making intervals shorter and moves smaller. Not resolved.

**Correction (Oct 15, later):** the pass-to-pass speeds above treat each VIIRS point as the fire's position. Checked against 194 mid-fire Sentinel-2/Landsat snapshots, the pixel-centre point lags the true front by about 380 m, while the far edge of the pixel footprint is unbiased. Redone with footprints (`../timing/README.md`), two-thirds of intervals show no resolvable advance. Where advance is measurable, the median is 30 m/h, which still gives about 2.9 t/ha. The 2.5-3.5 t/ha conclusion stands, but the 37 m/h figure and the class-by-class speeds should be read as rough.
