> **WITHDRAWN as fuel-load estimates (Oct 15 2026, after the fuel review `research/fuel-review/README.md`).** Nothing in this file is a fuel measurement.
> - Fuel load cannot be identified from fire size or speed. The same fires fit equally well with more fuel, a looser bed, a light breeze, or a different start time.
> - Speeds and loads here were measured against the research burn-label rasters, which are about 2.4x smaller than the grown scar outlines now used as the project's truth.
> - The class table below does not match `inversion.json`. For grass/scrub/sparse, the code gives 2.7-5.5 t/ha against the 1.0-2.4 in the table.
> - The back-simulation's 1.7-7x speed factor depends on how often VIIRS is assumed to miss a burning fire, and its best fits sat at the top of the search range.
>
> Kept only as a record. Fire timing and ignition work now belongs to the spread thread. The map's loads come from the litter budget in `../README.md`.

# Timing fire growth precisely (Oct 15)

Akkshay asked for accurate detection times and burn-scar growth. He also asked how to handle VIIRS's 375 m pixel, since the alert point is a pixel centre and the fire can be anywhere inside it.

## 1. Snapshots of burned-so-far at an exact minute (`midscar.py`, `midscar.parquet`, `chips/`)

The spread thread's `midevent_scenes.parquet` lists 352 Sentinel-2/Landsat scenes taken while a scarred fire was burning (334 fires, 10:15-10:50 IST).

For each scene:
- **Scar and clear looks.** The final scar comes from the same rule as passfront. The pre-fire look is the last clear look before first detection. The post-fire look is the first clear look after the last detection.
- **Burned by scene time.** A pixel counts as burned when its NBR drop from the pre look to the mid-fire scene is at least max(0.10, half its pre-to-post drop). Hot pixels in the scene also count.

This gives 331 usable scenes (at least 70% of the scar clear). Each is a 20 m picture of how much had burned, timed to the minute.

| scene time vs first VIIRS detection | n | share of final scar already burned (median, IQR) | ha |
|---|---|---|---|
| 6-24 h before | 41 | 0% (0-9%) | 0 |
| 0-6 h before | 90 | 3% (0-19%) | 2.4 |
| 6-12 h after | 81 | 61% (37-86%) | 17 |
| 12-24 h after | 80 | 87% (55-100%) | 23 |
| 24-48 h after | 29 | 75% (61-98%) | 37 |

- **Fires burn most of their area within about a day of first detection.**
- **Fires often start before VIIRS sees them.** In 41% of scenes taken before the first detection, more than 5% of the scar had already burned (median 9 ha).
- **Measurement repeatability.** Where S2 and Landsat imaged the same fire within minutes, burned area agrees within about 1-2 ha.
- **Fires imaged on consecutive days (5 cases)** grew 0.4-0.9 ha/h.

## 2. A VIIRS detection is a footprint, not a point (`footprint_check.py`)

Each detection is drawn as its real pixel footprint. FIRMS gives the scan x track size in km: 0.35-0.8 km a side, median 0.2 km². The footprint is clipped to the scar. Walking distance inside the scar is measured from the first-pass detections. The result is checked against the burned-so-far front in 194 scenes:

| front estimate at scene time | median error vs the 20 m snapshot | bias |
|---|---|---|
| pixel centre point (used so far) | 387 m | front is 379 m further on than the point says |
| far edge of the footprints seen so far | 128 m | -22 m (unbiased) |

| burned-so-far fraction | median error | correlation |
|---|---|---|
| from the point front | 0.59 | 0.10 |
| from the footprint far edge | 0.19 | 0.42 |

The true front sits at the far edge of the pixel footprint, not the centre. So the right way to use a VIIRS alert is "fire reached somewhere in this footprint by this minute, most likely its far side".

## 3. Speeds redone with footprints (`passfront_fp.py`, `passfront_fp.parquet`)

- **Most pass-to-pass intervals show no measurable advance at this resolution.** The first pixel footprint already reaches 374 m of a median 791 m scar extent. In 67% of intervals the new footprints fall inside ground already covered.
- **Where advance is measurable** (223 intervals), the median is 30 m/h (IQR 12-62), about 1 ha/h. Speed by class: teak 33, other deciduous 24, grass 28 m/h. Afternoon-to-night intervals run at 33 m/h and night-to-afternoon at 28.
- **Earlier point-based figure.** The 37 m/h from `inversion/passfront.py` mixes real spread with jitter inside the pixel. The fuel conclusion (about 2.5-3.5 t/ha of loose litter) holds roughly: 30 m/h with no wind gives about 2.9 t/ha.

## Next

Build a per-fire arrival-time map at 20 m. It would combine:
- the exact snapshots (burned and not yet burned at minute T)
- VIIRS footprints (some pixel in the footprint is burning at time t)
- S2/Landsat hot pixels (burning at T, 20-30 m)
- optionally Sentinel-3 SLSTR (1 km, 10:00/22:00 IST, from the FSI thread)

Speed per fuel class would then come from the arrival-time gradient rather than from pixel centres.

## 4. Per-fire speed from exact snapshot plus footprints (`arrival.py`, `arrival_fit.parquet`)

Each fire is described by its front distance (walking distance inside the scar) at every timed observation:
- the snapshot (exact, ±40 m)
- each VIIRS pass (footprint far edge, ±130 m, running max)

A straight line front = v x (t - t_ignition) is fitted by weighted least squares. Only observations before the front reaches 90% of the scar extent are used.

**Results** (169 fires with a positive fit):
- **Speed:** median 24 m/h (IQR 10-56, 90th percentile 136).
- **By forest class:** teak 27, other deciduous 28, grass/scrub 20 m/h. Still no class difference.
- **By month:** Feb 57 m/h (n = 12), Mar 24, Apr 19.
- **By first detection:** fires first seen by day run 31 m/h, fires first seen at night 20 m/h.
- **Start time:** extrapolated ignition is a median 15 h before the first VIIRS alert (IQR 5-38 h). Fires first seen at the 01:30 IST pass have mostly been burning since the previous afternoon.

**Fuel.** With no wind, 24 m/h needs about 2.4 t/ha of loose litter, against 2.9 t/ha from 30 m/h. The defensible range is 2-3.5 t/ha.

**Caveat.** A constant speed is a simplification. Fires are faster early and slow at the scar edge, so start times are rough.
