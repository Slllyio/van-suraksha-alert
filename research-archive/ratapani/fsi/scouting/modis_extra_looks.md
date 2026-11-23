# Do the MODIS looks sharpen fire timing and spread maps? (scouting round 18, 17 Oct 2026)

**Question.** VIIRS sees fires only at about 01:30 and 13:30 IST. Terra MODIS passes at about 10:30 and 22:30 IST, which VIIRS never covers, but its pixels are about 1 km. Do these extra looks sharpen the fire timing and spread maps?

**Data.** The new all-MP MODIS SP file (`fire-alert-scars/alerts_mp/modis_*.csv`, Terra + Aqua, type 0, 152k points). The all-MP VIIRS files are used for the schedule and for the all-MP fires. Ratapani fires, photos and outlines come from the big-fires and continuity threads. Code: `code/modis_looks/` (m0 to m6). Numbers: `code/modis_looks/results/`. Big intermediate files stay in the session scratch.

## Bottom line
1. **Terra rarely sees these fires.** Only 11% of Ratapani multi-look fires get a Terra look between two VIIRS looks (32% of the 146 big fires), and only 4-5% of VIIRS gaps get one. MODIS needs a fire of about 9-15 MW, while the median VIIRS point is 6.5 MW by day and 1.3 MW by night.
2. **When Terra does see a fire, the time it adds is real.** In the hidden-look test, Terra looks cut the timing error from 17 h to 12 h (mean) on the 12% of hidden looks that have one in the gaps next to them. The share timed within 6 h rises from 3% to 31%. Across all hidden looks the gain is only 0.4 h.
3. **For maps of where ground has burned, MODIS does not help.** Drawn as real 1 km blocks, the MODIS looks make the photo score slightly worse: -0.3 to -0.8 points on all 340 photos, and -2 to -3 points on the photos where MODIS adds a look. Drawn as 375 m points at the pixel centre, they make no difference (±0.2 points). This holds for (a) the honest morning setting and for (b) all looks.
4. **Terra at 22:30 is a strong "still alive tonight" signal, but it is rare.** A fire seen at 13:30 is seen again at 01:30 89% of the time if Terra caught it at 22:30, against 19% if not. Only 0.7% of 13:30 fires get that Terra catch. In the held-out stopping model, Terra adds +0.003 AUC overall. For the fires it covers, it fixes the calibration: Brier score 0.35 becomes 0.13.
5. **Pixel against time** [inference from the numbers]. The Terra look sits 3 h from the nearest VIIRS look. At 25 m/h that is about 75 m of spread. Its position error (about 280 m) and block half-width (about 550 m) are 4-7 times larger. So MODIS can date a fire, but it cannot place the front.

## 1. How often does Terra fall between VIIRS looks? (`m1`, `m1b`, `m2`)
- **Ratapani fires** are the big-fires thread's 3,557 v2-event fires. A MODIS SP point belongs to a fire if it lies within the scar + 500 m, inside the big-fires date window.
- **All-MP fires** are built from VIIRS points on forest-department land (MP 500 m beat cells, ≥50% beat cover). Points are linked at 1 km / 48 h, the stopping note's rule. A MODIS point is attached to the forest VIIRS point within 1 km (1.5 km for large pixels) that is nearest in time.
- **A gap** is the time between two consecutive VIIRS looks of the MP-wide schedule, between the fire's first and last VIIRS detection. A "between" MODIS look is more than 1 h from both VIIRS looks.

| set (fires with ≥2 VIIRS looks) | fires | fires with a Terra look between | of which Terra night (22:30) | VIIRS gaps with a Terra look |
|---|---|---|---|---|
| Ratapani v2 fires | 957 | 11.4% | 2.7% | 3.7% |
| Ratapani big fires | 146 | 32% | 6.2% | 4.8% |
| all-MP forest fires | 36,170 | 8.4% | 2.8% | 3.5% |
| all-MP big (≥4 looks, ≥10 points) | 5,921 | 30% | 12% | 6.2% |

- The median longest gap of Ratapani fires stays at 23.7 h (24.5 h for big fires) with Terra added.
- Aqua passes with VIIRS: in Ratapani, 39% of Aqua points on these fires are within 1 h of a VIIRS look, and the rest are only 1-2 h off. So Aqua adds almost no new time.
- **New SP file against the old one.** The SP file puts 1,150 MODIS points on 636 Ratapani fires. The big-fires thread's `detections.csv` has 861 points on 485 fires, from the Ratapani-box file (mixed NRT/SP).
- **Did big-fires use MODIS?** Yes. `passes.csv` has 222 Terra and 404 Aqua passes (53 and 99 on big fires), and they entered its direction, front-speed and photo-block tests.

**Does Terra night catch fires that VIIRS 01:30 then also sees?**

| set | Terra-night fire passes | VIIRS sees it at 01:30 after | VIIRS saw it at 13:30 before | seen by neither |
|---|---|---|---|---|
| Ratapani v2 fires | 44 | 80% | 61% | 14% |
| all-MP forest fires | 1,976 | 87% | 54% | 7% |
| all-MP big | 917 | 97% | 83% | 1% |

So a Terra night catch is nearly always confirmed by VIIRS 3 h later. It is almost never a fire that VIIRS misses.

## 2. Adding MODIS looks to the arrival maps (`m3`, `m4`, `m6`)
**Method.**
- The continuity code (`c0_lib.py`) is imported read-only, and the photo/fire matching of `c1_photos.py` is copied.
- Each MODIS pass on the fire is one extra look. Its footprint is either the real scan × track box (median 1.2 km², against 0.2 km² for VIIRS) or a 375 m box at the pixel centre ("point").
- The scores are pixels right at photo time and the photo-level AUC. The 95% ranges come from resampling fires.

**Mid-fire photos, reconstruction maps (all VIIRS looks, before and after the photo; blend = the continuity choice).** VIIRS-only baseline: 84.4% right on 340 photos and 82.7% on the 171 photos with a look before and after. These numbers reproduce the continuity thread.

| MODIS added | photos where it adds a look | all 340, real blocks | all 340, as points | photos where it adds a look, real / points |
|---|---|---|---|---|
| **(a)** looks ≥3 h before the photo (up to the night before) | 91 | -0.7 pts (-1.2 to -0.3) | 0.0 (-0.1 to +0.0) | -2.7 / -0.1 |
| (a, Terra only) | 45 | -0.3 (-0.6 to -0.0) | | -2.1 / |
| all except ±3 h of the photo | 130 | -0.8 (-1.6 to -0.0) | -0.2 (-0.9 to +0.2) | -2.0 / -0.6 |
| **(b)** all looks, incl. Terra-day at the photo minute | 165 | -0.8 (-1.6 to -0.1) | -0.2 (-0.9 to +0.2) | -1.5 / -0.4 |

- **AUC.** The ranking within a photo improves a little in every variant (0.723 → 0.729-0.741), but the burned/unburned call at photo time gets worse. [inference] The extra looks pull pixel times towards the morning, which helps the order but moves the 0-hour line in the wrong direction about as often as the right one.
- **The "nearest look" map** behaves the same way: real blocks -0.2 to -0.5 points, points ±0.0.
- **(b) is a different question: "what is burning now".** Terra-day passes within ~15 min of the photo. On the 25 photos with a Terra-day footprint at the photo minute, 40% of the ground inside it (outside earlier VIIRS blocks) had burned. Elsewhere outside those blocks the figure was 29%. So even a same-minute 1 km block marks burned ground only weakly. It locates the fire, not the burned area.

**Honest morning forecast** (only what was seen before the photo; 245 photos with a VIIRS look before; spread-review rule `t + distance/15 m/h`, plus the ranking of the honest distance table):

| | right at photo time | ranking AUC, distance table |
|---|---|---|
| VIIRS ≥1 h before | 78.2% | 0.775 |
| **(a)** + MODIS ≥3 h before, real blocks | 76.6% (-1.6, -2.8 to -0.5) | 0.765 |
| (a) + MODIS as points | 78.0% (-0.2, -0.5 to +0.2) | 0.775 |
| **(b)** + Terra-day at the photo minute, real blocks | 76.3% (-1.9, -3.3 to -0.6) | 0.755 |
| (b) as points | 78.0% (-0.2) | 0.774 |

**Hidden-look test** (1,044 middle VIIRS looks of 457 fires; hide one look and predict its points' time from the other looks). MODIS looks within 2 h of the hidden look are always dropped, because Aqua would hand over the answer. Numbers are the mean error in hours, VIIRS only → with MODIS (95% range of the change).

| added | all hidden looks | the 124 looks with a Terra look in the gaps next to them | share within 6 h (those 124) |
|---|---|---|---|
| Terra, real blocks (blend) | 20.0 → 19.6 (-0.7 to -0.2) | **16.9 → 12.2 (-6.2 to -3.5)** | 3% → 31% |
| Terra, as points (blend) | 20.0 → 19.8 | 16.9 → 14.7 | 3% → 19% |
| Terra + Aqua, real (blend) | 20.0 → 20.1 (-0.4 to +0.7) | 16.9 → 12.3 | 3% → 25% |
| Terra, real (nearest look) | 23.5 → 23.1 | 19.9 → 14.2 | 0% → 25% |

- The median error stays at about 12 h overall, which is the continuity thread's figure.
- Aqua adds noise, not time.
- Real blocks beat points here because the question is "when", and the block covers the hidden points.

## 3. Does Terra 22:30 tell whether a fire is still alive at night? (`m5`)
**Set-up** (the stopping note's Part A idea, with label = "seen at the next VIIRS look"). There are 849k states: every all-MP forest fire at every VIIRS slot, from its first detection to 3 slots after its last.
- VIIRS features: silent slots, FRP now / last / max, slots seen, age, points, hour.
- MODIS features: only what is known more than 1 h before the next VIIRS look.
- Model: HistGradientBoosting, seasons held out one at a time.

| states | n | seen next | AUC VIIRS | + Terra only | + all MODIS | Brier VIIRS → + Terra |
|---|---|---|---|---|---|---|
| all | 849k | 8.6% | 0.814 | 0.817 | 0.818 (+0.004 to +0.005) | 0.0646 → 0.0635 |
| at 13:30 (next = 01:30) | 425k | 7.7% | 0.819 | 0.821 | 0.823 | 0.0591 → 0.0583 |
| silent (VIIRS missed it last look) | 591k | 4.4% | 0.749 | 0.753 | 0.755 | 0.0394 → 0.0389 |
| Ratapani box | 36k | 8.9% | 0.822 | 0.825 | 0.827 | 0.0675 → 0.0666 |
| **Terra look in the gap** | 4.4k | 83% | 0.689 | 0.729 | 0.731 | **0.351 → 0.131** |

**Plain table** (fire seen at 13:30, seen again at 01:30?):

| 13:30 FRP | no Terra 22:30 | Terra 22:30 caught it |
|---|---|---|
| ≤5 MW | 8% (n 61,608) | 81% (n 98) |
| 5-15 MW | 14% | 88% (n 568) |
| 15-50 MW | 20% | 91% (n 348) |
| >50 MW | 26% | 89% (n 61) |

- When VIIRS missed the fire at 13:30 (seen at 01:30 before), it is seen at the next 01:30 11% of the time. With a Terra 22:30 catch, the figure is 71% (n 143).
- **Reading.** Terra 22:30 is a near-certain "still burning tonight" when it fires, and it is almost silent otherwise. Its absence says little, because MODIS misses most small fires. For "declare out" (p < 0.10), MODIS changes nothing: 3.9% vs 3.8% seen next.

## 4. 1 km pixels against the time they add [mostly inference, from the numbers above]
| quantity | value |
|---|---|
| time from a Terra look to the nearest VIIRS look | ~3 h (22:30 vs 01:30; 10:30 vs 13:30) |
| spread in that time at 25 m/h | ~75 m |
| spread over a full VIIRS gap (12 h) | ~300 m |
| Terra pixel centre to same-minute hot pixels (squares thread, n 15) | ~280 m |
| MODIS point to the nearest same-fire VIIRS point (all MP, median) | 400-460 m |
| MODIS block half-width | ~550 m (1.2 km², 6× a VIIRS block) |

- A MODIS look could sharpen **where** the front is only if the time it fills, times 25 m/h, exceeded its placement error. That would need about 11 h or more, but Terra always sits 3 h from a VIIRS look. So spatially it carries less than it blurs, as the photo tests show (-2 to -3 points as blocks, 0 as points).
- For **when**, the pixel size matters less. The fire is somewhere in the block at 22:30 or 10:30, and that time stamp cuts the hidden-look error by ~5 h where it exists.
- **What wins.** For timing labels, use Terra as a time stamp. For burned-ground maps, keep VIIRS dots, and if MODIS is added at all, add it only as a point.

## Next steps
- **Continuity.** Keep the VIIRS-only blend for the atlas, since MODIS does not raise the photo score. Optionally add Terra passes, as points, to each page's look table and timing bracket. For the ~30% of big fires that have one, they narrow the arrival time near the Terra pixel. Don't use them as 1 km blocks.
- **Big fires.**
  - Swap in the SP MODIS file: 1,150 vs 861 points, 636 vs 485 fires.
  - Treat MODIS as a point (or a down-weighted pass) in the pass-by-pass front-speed fit, never as a 1 km block.
  - For timing between passes, the Terra pass is the one that adds time; Aqua duplicates VIIRS.
- **Spread / alerts.**
  - Don't add MODIS to the "chance burned by morning" table; it lowers the morning forecast by 1.6 points as blocks.
  - Add one feature, "Terra 22:30 saw it", to the stopping / still-alive model (4p). It is cheap and it fixes calibration for the fires it covers (Brier 0.35 → 0.13). Show it on the alert as "seen burning at 22:30" for the night shift.
  - In the live feed this needs the MODIS NRT stream, which has a different position processing from SP [inference: check the match rate first, as the README did for NOAA-21].

## Limits
- The all-MP fires are VIIRS clusters on forest-department land, not v2 scar outlines. Farm fires on beat land are still included.
- MODIS-to-fire matching uses distance and time only. A MODIS point between two close fires may go to the wrong one.
- Terra's swath has small gaps at 23°N, so "Terra silent" is not always "Terra looked" [inference: a small effect on the no-Terra rows].
- Few photos have a Terra night look before them (3 with a footprint outside VIIRS blocks), so the night-look part of (a) rests on few cases. Most of what MODIS adds before the photo comes from Aqua and Terra-day looks of earlier days.

## Files (`code/modis_looks/`)
- `m0_prep.py`: loads the all-MP VIIRS and MODIS points into the scratch folder (schedule, passes).
- `m1_fires_mp.py`: builds the all-MP forest fires and attaches MODIS.
- `m1b_ratapani.py`: attaches MODIS SP to the Ratapani v2 fires. It needs `fire_scars.pkl` from continuity `c0b_scars.py`.
- `m2_coverage.py`: test 1.
- `m3_photos.py`: test 2, photo scores.
- `m4_hidden.py`: test 2, hidden looks.
- `m5_alive.py`: test 3.
- `m6_photo_summary.py`: summaries.
- Results: `coverage.csv`, `terra_night_catch.csv`, `photo_modis.parquet`, `photo_summary.csv`, `inside_footprint.csv`, `hidden_modis.parquet`, `hidden_summary.csv`, `alive.csv`, `alive_table_*.csv`.
- Rerun: `ML_SCRATCH=<dir> FC_SCRATCH=<dir>`, then m0, m1, continuity c0b_scars.py, m1b, m2, m5, m3, m4, m6. Total under 30 min on 4 cores.
