# Fire "jumps" and new starts near an active fire: embers or people? Literature plus a Knox / near-repeat test on our data (scouting round 13, topic "jump", 16 Oct 2026)

For the spread-review thread (thread 4), which found that its calibrated 6/12/24/48 h burn-chance map misses new fire 1-5 km from an active fire and wants a separate "new fire or jump nearby" chance. It also touches thread 1 (the 2-day model) and thread 5 (patrol).

Not repeated here, because earlier notes cover them:
- Hawkes and self-excitation features, Galicia's arson clustering scales (Marey-Pérez 2023), CrimeRank and the Bogotá ETAS deployment: `short_horizon_prediction*.md`.
- Bowers' prospective hot-spotting: `cold_start_cells.md`.
- Prestemon et al. 2012 supplementary tables: `operational_occurrence_systems.md`.
- FEDS merge distances (1 km sleeper, 2.5-5 km forest connectivity): `fire_stopping_and_tracking.md` B1.
- Controlled and Forest Department burns: `diurnal_and_controlled_burns.md`.
- Mahua and tendu fire-setting: `human_fire_drivers.md`, `mahua_tendu_mapping.md`.

The spread thread's own LightGBM jump model (`research/spread-review/scripts/j1_jumps.py`, `jumps/rows.parquet`) is a different, complementary job. It asks where within 1-5 km the next dot appears. This note asks how much of that is real coupling to the parent fire, and what causes it.

Marks: **FULL** = whole text (or the whole relevant part) read; **PARTIAL**; **ABSTRACT ONLY**. My own reasoning is marked [inference]. "DATA" = computed today on our files.

Code: `code/jumps/` (`prep.py`, `knox.py`, `splits.py`, `knox_sep.py`, `rate_table.py`, `spot.py`). Outputs: `data/jumps/`.

---

## Headline findings

1. **There is real near-repeat clustering, and it is short and local.** New fires appear near an active fire far more often than chance, but only within about 2 km and about 12 hours. Within 0-1 day the observed/expected ratio is:
   - 3.25 at 0-0.5 km, 2.46 at 0.5-1 km, 1.60 at 1-2 km, 1.19 at 2-5 km;
   - about 1.0 at 5-20 km.
   - The ratio is highest when the new fire comes 0-12 h after the parent's detection: 4.8-5.9 at 0-0.5 km and 2.9-3.5 at 0.5-1 km.
   - By 1-2 days it is back to 1.0-1.3, and 2-3 days later it is gone. This holds with a stricter null that shuffles times within the same month (`knox_tables.csv`).
2. **Spotting (embers) explains almost none of it.** Three independent lines of evidence:
   - **Physics.** The Albini 1983 surface-fire model (CFS FBP code) gives a maximum spotting distance of about 60-250 m for 50-500 kW/m litter fires in 10-30 km/h wind. FIRETEC surface-fire firebrands travel 1-7 m on average and at most 9-228 m (Koo 2012). BehavePlus, for open grass with flames up to 2.1 m, gives at most 0.8 km. Long-distance (>500 m) spotting in Australia comes from forest fires of 50 ha and up with bark fuels (Storey 2020).
   - **Wind.** The excess new fires are not downwind. The share of the excess is 24% within 45° of downwind, 34% at 45-90°, 24% at 90-135° and 18% upwind. Spotting would put most of it downwind.
   - **Timing.** A strict "ember-compatible" rule (daytime start, parent seen ≤ 6 h before, downwind ±45°) catches 21 new fires against 15 expected. That is about 6 of the 286 excess fires (**≈2%**).
   - Also, 15% of the excess starts 00:00-06:00 IST and a further 18% at 06:00-09:00, when there is no active front to throw embers [inference].
3. **Within 1 km, the "new fire" is mostly the same burn split in two. Beyond 1-2 km, it is mostly a separate fire.**
   - In 0-1 km, 211 of the 265 excess new fires (80%) have v2 scars within 100 m of the parent's scar. These are spread across an image gap or a merged burn, split by the fire-grouping step.
   - In 1-5 km, 377 of the 643 excess (59%) have scars more than 100 m apart. These are separate ignitions; the share is 40% at 1-2 km, 64% at 2-3 km and 80% at 3-5 km.
   - [inference] The separate ones fit people lighting more than one fire on the same trip or day: they are not downwind, are local to a beat, and are gone after one day. This matches what Florida (Butry & Prestemon) and Galicia found for arson: a lag of 1-2 days and a "same neighbourhood" scale.
4. **A usable jump-chance table (DATA, `jump_rate_table.csv`).** Each fire-day is an issue (5,272 issues). The table gives the chance that at least one new fire starts within the next 24 h, in each distance ring from the fire's detections so far:

   | Ring | Observed | Background (null) | Excess | Ratio |
   |---|---|---|---|---|
   | 0-0.5 km | 2.5% | 0.8% | +1.7 pts | 3.0 |
   | 0.5-1 km | 5.6% | 2.5% | +3.1 pts | 2.3 |
   | 1-2 km | 10.3% | 7.4% | +2.9 pts | 1.4 |
   | 2-3 km | 12.3% | 10.0% | +2.3 pts | 1.2 |
   | 3-5 km | 25.3% | 22.4% | +2.8 pts | 1.1 |

   - Any new fire within 2 km in 24 h: **15.8% observed vs ≈10.1% background**.
   - The 0-1 day excess is positive in all 10 seasons in every ring, holding each season out.
5. **Where and when.** The excess is larger in April:
   - ratio 4.2 at 0-0.5 km, 2.6 at 0.5-1 km and 1.65 at 1-2 km;
   - in March it is 2.8 / 2.05 / 1.30.
   - It is spread across 59 of 64 beats. Borpani, South and North Mathar, Umariya, Malkhar, East Dantkho, Panjhir and Magardha carry the most excess (ratio 2-2.7; `split_beat.csv`).
   - Wind cannot be used to aim the jump kernel. Distance and time since the parent's last detection are the useful inputs.

---

## Part A. Our own measurements (DATA, computed 16 Oct 2026)

### A1. Inputs (`prep.py`)

- **New fires.** From `data/ignition_points.csv`, I took the earliest `first_day_of_fire` event of each `fire_group`. This gives 3,820 new fires, 2017-2026 (258-530 per season).
  - Location: `ign_lat/lon`, which is good to about 300-400 m (`ignition_points.md`).
  - Time: `t_ign_med_ist`, good to a few hours.
- **Active-fire detections.** From the v2 lookup `fire-alert-scars/reference/v2_2026-10-16/firms_alert_scar_lookup.csv`: S-NPP, NOAA-20 and MODIS, 14,011 alerts linked to a fire group. Each alert carries its beat.
- **Scars.** Scar outlines v2 (2026-10-16), `firms_event_scars.geojson`, dissolved by fire group.
- **Wind.** ERA5-Land hourly 10 m wind at 33 points, 0.1° apart (`ratapani/ee/era5/`). I used the mean over the 6 h before the new fire's ignition, at the point nearest the midpoint of the gap.
- **Null model.** A space-time permutation: ignition times are shuffled among new fires of the same season, and locations are kept (199-499 shuffles). A stricter version shuffles only within the same month. The p-values are Monte Carlo values, with 0.002 the smallest possible at 499 shuffles.

### A2. Classic Knox test, new fire against new fire (`knox.py`, test A)

Unordered pairs of new fires.

| distance | lag 0-1 d | lag 1-2 d | lag 2-3 d |
|---|---|---|---|
| 0-0.5 km | 40 vs 12.1 (3.30) | 7 vs 10.7 (0.65) | 6 vs 10.0 (0.60) |
| 0.5-1 km | 146 vs 62.3 (2.34) | 71 vs 56.3 (1.26) | 71 vs 54.3 (1.31) |
| 1-2 km | 494 vs 240.7 (2.05) | 323 vs 214.8 (1.50) | 263 vs 204.6 (1.29) |
| 2-5 km | 1655 vs 1320 (1.25) | 1430 vs 1176 (1.22) | 1276 vs 1132 (1.13) |

- Cells show observed vs expected (ratio); all have p ≤ 0.04 except the 0-0.5 km cells at 1-3 days.
- With the month-block null, the 0-1 day cells keep ratios of 3.29 / 1.98 / 1.71 / 1.15. The 1-3 day cells shrink to 1.04-1.26, and several stop being significant.
- So the one-day coupling is robust, and the longer tail is partly seasonal.

### A3. New fire after another fire's detection (test B)

Each new fire is counted once per cell if any other fire had a detection in that ring before it, within that lag.

| distance | 0-1 d | 1-2 d | 2-3 d |
|---|---|---|---|
| 0-0.5 km | 109 vs 33.6 (3.25) | 31 vs 30.5 (1.02) | 24 vs 28.7 (0.84) |
| 0.5-1 km | 307 vs 124.8 (2.46) | 123 vs 114.7 (1.07) | 127 vs 107.8 (1.18) |
| 1-2 km | 608 vs 379.4 (1.60) | 469 vs 349.2 (1.34) | 371 vs 333.2 (1.11) |
| 2-5 km | 1483 vs 1247 (1.19) | 1333 vs 1173 (1.14) | 1214 vs 1128 (1.08) |

**Finer lags, out to 20 km** (`ratio_by_distance_lag.csv`, observed/expected):

| distance | 0-6 h | 6-12 h | 12-24 h | 1-2 d | 2-3 d |
|---|---|---|---|---|---|
| 0-0.5 km | 4.80 | 5.89 | 1.90 | 1.04 | 0.84 |
| 0.5-1 km | 2.86 | 3.53 | 2.16 | 1.06 | 1.17 |
| 1-2 km | 1.95 | 1.76 | 1.57 | 1.34 | 1.12 |
| 2-3 km | 1.36 | 1.17 | 1.32 | 1.19 | 1.14 |
| 3-5 km | 1.12 | 1.19 | 1.16 | 1.13 | 1.08 |
| 5-10 km | 0.99 | 1.06 | 1.01 | 1.03 | 1.06 |
| 10-20 km | 1.00 | 0.96 | 0.96 | 0.99 | 1.00 |

- The ratio of about 1.0 at 5-20 km matters. If whole-sanctuary "busy days" (weather) drove the clustering, far pairs would also show ratios above 1. They do not, so the near excess is genuinely local coupling and not weather synchrony [inference].
- This fits "weather sets when, not where" in thread 1: the weather signal is sanctuary-wide, while the coupling here is a 0-2 km, half-day effect.

### A4. What the excess looks like (`splits.py`)

The sample is the new fires with another fire's detection 0.5-2 km away in the previous 24 h: 710 observed vs 424 expected, so an excess of 286 (40% of these fires).

| split | categories: observed vs expected (ratio) |
|---|---|
| Angle of the gap against the 6 h mean wind | downwind <45°: 176 vs 106 (1.65); 45-90°: 203 vs 106 (1.91); 90-135°: 173 vs 104 (1.67); upwind >135°: 157 vs 107 (1.47) |
| Time since the parent's latest detection | 0-3 h: 126 vs 68 (1.86); 3-6 h: 51 vs 21 (2.46); 6-12 h: 223 vs 112 (1.99); 12-18 h: 50 vs 40 (1.26); 18-24 h: 260 vs 183 (1.42) |
| Hour of the parent's latest detection (IST) | 00-06 (the 01:30 pass): 305 vs 144 (2.12), 56% of the excess; 12-18: 397 vs 272 (1.46), 44% |
| Hour of the new fire's ignition (IST, posterior median) | 00-06: 72 vs 30 (2.41); 06-09: 114 vs 63 (1.82); 09-12: 335 vs 212 (1.58); 12-15: 128 vs 86 (1.49); 15-18: 44 vs 24 (1.86); 18-24: 17 vs 10 (1.62) |
| Month | Jan 21 vs 7; Feb 78 vs 39 (2.0); Mar 449 vs 291 (1.54); Apr 152 vs 82 (1.85); May 3 vs 2 |
| Distance | 0.5-1 km 2.54; 1-1.5 km 1.69; 1.5-2 km 1.37 |
| Strict ember-compatible rule (start 10-18 h, parent seen ≤ 6 h before, downwind ±45°) | 21 vs 15 (excess about 6 of 286) |
| Scars | 34% of these new fires have their ignition inside, or within 100 m of, the parent's v2 scar; 42% of their scars touch the parent's scar, against 25% for a control (same distance, lag 3-10 days) |

How to read this [inference]:
- **The wind gives no direction preference.** All four sectors carry 18-34% of the excess. With an ember source, the downwind sector should carry most of it.
- **Many new fires follow a parent last seen at 01:30.** The new fire then starts 6-12 h later, in the morning. This could be a fire that crept overnight and was split into a separate "fire" (see A5), or people going back into the same area the next morning.
- **10% of these new fires (72) "ignite" at 00-06 IST**, against 4.7% of all new fires. This is consistent with a slow front grouped as a new fire, not with spotting.

### A5. Same burn split in two, or a separate fire? (`knox_sep.py`)

Each pair of new fire j and other fire g in the same season is flagged "joined" if their v2 scars lie within 100 m of each other. That is true of 9.7% of the 129,277 pairs within 5 km.

Test B, lag 0-1 day:

| ring | separate scars: observed vs expected (ratio, excess) | joined scars: observed vs expected (ratio, excess) | share of the excess that is separate |
|---|---|---|---|
| 0-0.5 km | 11 vs 4.0 (2.73, +7) | 99 vs 29.3 (3.38, +70) | 9% |
| 0.5-1 km | 91 vs 43.8 (2.08, +47) | 224 vs 82.9 (2.70, +141) | 25% |
| 1-2 km | 367 vs 260.8 (1.41, +106) | 297 vs 137.5 (2.16, +160) | 40% |
| 2-3 km | 599 vs 483.6 (1.24, +115) | 161 vs 94.9 (1.70, +66) | 64% |
| 3-5 km | 1181 vs 1025 (1.15, +156) | 101 vs 60.9 (1.66, +40) | 80% |

All cells have p = 0.005, the smallest possible with 199 shuffles.

**For the spread thread.**
- **Joined pairs.** These are burn complexes that the grouping split, mostly within 1 km. The spread or restart model should capture them, because the ground is continuous.
- **Separate new fires.** These are what a spread model cannot capture. They dominate beyond 2 km.
- **The excess is roughly flat across rings.** Between +1.7 and +3.1 pts of "any new fire in 24 h" per ring, so per km² it falls steeply with distance:
  - with the ring area round a single point: about 0.021 at 0-0.5 km, 0.013 at 0.5-1 km, 0.003 at 1-2 km, 0.0015 at 2-3 km and 0.0006 at 3-5 km (excess chance per km² per fire-day);
  - real footprints are larger, so treat these as upper values [inference].

### A6. Jump-chance table with seasons held out (`rate_table.py`)

- **Issue.** Each fire group on each IST day it is detected (5,272 issues). The issue time is the fire's last detection that day, and the footprint is all its detections up to then.
- **Event.** Another fire group's new ignition in the ring within (0, 1], (1, 2] or (2, 3] days.

**Full table** (`jump_rate_table.csv`; "any new fire" chance per issue; lags 1-2 and 2-3 days are in the file):

| ring | 0-1 d obs / bg | 1-2 d obs / bg | 2-3 d obs / bg |
|---|---|---|---|
| 0-0.5 km | 2.48% / 0.84% | 0.66% / 0.73% | 0.57% / 0.72% |
| 0.5-1 km | 5.58% / 2.45% | 2.52% / 2.23% | 2.45% / 2.09% |
| 1-2 km | 10.26% / 7.37% | 8.74% / 6.71% | 7.26% / 6.43% |
| 2-3 km | 12.33% / 10.02% | 10.53% / 9.08% | 9.71% / 8.65% |
| 3-5 km | 25.25% / 22.44% | 22.33% / 20.66% | 20.09% / 19.83% |

**By month and by parent size, 0-1 day (excess, pts):**

| group | 0-0.5 km | 0.5-1 km | 1-2 km | 2-3 km | 3-5 km |
|---|---|---|---|---|---|
| Jan-Feb (n = 1,019) | +0.4 | +2.9 | +2.1 | +0.1 | +2.5 |
| Mar (2,692) | +2.1 | +3.6 | +3.1 | +2.7 | +3.1 |
| Apr (1,221) | +2.1 | +3.0 | +3.7 | +3.7 | +3.2 |
| May-Jun (159) | +0.6 | +0.3 | -0.2 | -0.1 | +1.0 |
| Parent ≥ 3 detections that day (1,687) | +2.6 | +4.6 | +3.2 | +2.6 | +4.0 |
| Parent 1-2 detections (3,585) | +1.2 | +2.4 | +2.8 | +2.2 | +2.3 |

**Held-out seasons** (`jump_rate_heldout_summary.csv`).
- The 0-1 day excess is positive in 10 of 10 seasons in every ring. The mean excess and its SD across seasons:
  - 0-0.5 km: +1.55 ± 1.0 pts;
  - 0.5-1 km: +3.18 ± 1.25;
  - 1-2 km: +3.08 ± 1.11;
  - 2-3 km: +2.36 ± 1.43;
  - 3-5 km: +2.88 ± 1.89.
- At 1-2 days, the excess is positive in 9 of 10 seasons at 1-3 km, but only 4-5 of 10 within 1 km.
- Season-to-season count errors from a pooled rate are 20-45% of the season total, so use the pooled rate with a season-level spread.

---

## Part B. Sources

### B1. Albini 1983 (INT-309) and Albini 1979 (INT-56), as coded by the Canadian Forest Service in `fbp97spot.c`. **FULL** (the code, 194 lines; the reports themselves were not found online)
https://cwfis.cfs.nrcan.gc.ca/downloads/fwi_obs/fbp97/fbp97spot.c

What it shows:
- **Wind-driven surface fires (Albini 1983, with the Chase 1981 pocket-calculator form).**
  - f(U) = A·U^B, with tall grass A = 129, B = −1.238; light-fuel A = 162, B = −1.465; slash A = 69.6, B = −0.818.
  - E = I·f(U); lofting height H = 0.173·√E; h_c = H^0.337 − 1.22.
  - Downwind drift X = 2.78·U_H·√H, with winds scaled by a 1/7 power law.
- **Torching trees (Albini 1979)** are a separate branch, with flame height √(I/300) (Byram).

My port (`spot.py`, tall-grass coefficients) gives the following "SpotCalc" output. I read the units as metres; the code does not label them [inference].

| fireline intensity | 10 km/h | 20 km/h | 30 km/h |
|---|---|---|---|
| 50 kW/m | 62 | 98 | 131 |
| 125 kW/m | 81 | 125 | 163 |
| 250 kW/m | 100 | 154 | 199 |
| 500 kW/m | 125 | 190 | 245 |
| 1,000 kW/m | 156 | 237 | 303 |

- Ratapani litter fires: ROS 30-160 m/h (`fire_behaviour_field_data.md`) × 0.2-0.3 kg/m² consumed × 18 MJ/kg gives about 30-240 kW/m [inference].

**Concrete action for us (thread 4).** Add no ember kernel beyond about 300 m. Ember spotting is physically capped at a few hundred metres for our fires, so the 1-5 km "jump chance" must be a human-ignition term, not an ember term. Expected effect: it avoids a wind-aligned jump kernel that our data say has no skill (A4).

### B2. Koo, Linn, Pagni & Edminster 2012, "Modelling firebrand transport in wildfires using HIGRAD/FIRETEC", *IJWF* 21:396-417. **FULL**
https://fs.usda.gov/rm/pubs_other/rmrs_2012_koo_e001.pdf

What it shows:
- The surface-fire case is a line fire in tall-grass-like fuel, with wind of 6 m/s at mid-flame height.
- **Effective firebrands from surface fires are tiny:** discs average 0.09 g (1.65 mm thick) and cylinders 0.003 g.
- **Travel distance (Table 2).**
  - Mean 1.07-1.7 m with the terminal-velocity assumption and 6.4-7.4 m without it.
  - Maximum 9.3-41 m with it and 26-228 m without it.
  - Flight times are 1-26 s.
- Vertical velocities at launch are below 4 m/s, because "there is not enough space below the firebrands for the entrained wind to accelerate and launch firebrands". Crown fires launch bigger brands much further.

**Concrete action (thread 4).** As B1: cap ember spread at a few hundred metres, and treat everything at 0.5-5 km as a separate ignition. Large flat teak leaves are disc-like, and discs travel furthest. Even so, the maximum in this model is around 0.2 km [inference].

### B3. Storey, Price, Sharples & Bradstock 2020, "Drivers of long-distance spotting during wildfires in south-eastern Australia", *IJWF* 29:459-472. **FULL** (main text; reference list not read)
https://connectsci.au/wf/article-split/29/6/459/21517/Drivers-of-long-distance-spotting-during-wildfires

What it shows:
- **Data.** 338 source fires from aircraft line scans, 2002-2018. 151 had at least one spot fire more than 500 m away.
- **Maximum spotting distance.**
  - Range 5 m to 13.9 km; mean 0.9 km; 95th percentile 3.9 km. Only 11 fires spotted beyond 5 km.
  - The distribution is roughly exponential.
- **Spot fires per source fire.** Mean 13 at any distance. Beyond 500 m: mean 2.3, 95th percentile 10.2.
- **Predictors.** Source-fire area is the strongest (LR 55), then foliage cover (13.6), wind speed (8.9), slope, wind exposure and upper-level wind.
- **Modelled maxima.**
  - About 4 km at about 1,000 ha and about 8 km at about 5,000 ha, in dense, steep, windy forest.
  - Only 0.4 km at 1,000 ha and 0.9 km at 5,000 ha in sparse plains.
- The smallest fires that spotted beyond 500 m were six fires of 50-100 ha. Recently burnt source fires spotted far less (0.2 vs 2.3 long spots).
- Vegetation: 76% forest, 3% grass.

**Concrete action (thread 4).**
- Even in eucalypt forest, a fire must be large and intense before spotting beyond 500 m is common.
- Our median scar is about 62 ha (v2), in sparse leafless canopy and litter.
- If the spread thread wants any ember term, gate it on source size above about 200 ha and a dry, windy day, with a maximum of about 0.4-0.9 km (the sparse-plain values) [inference].
- Expected effect: negligible for over 95% of fires.

### B4. Ellis 2015 via CSIRO PyroPage no. 2 (Aug 2015), "Predicting spotfire ignition in dry eucalypt litter". **FULL** (2-page summary of Ellis 2015, *IJWF* 24:225-235; the paper itself was not read)
https://research.csiro.au/pyropage/wp-content/uploads/sites/17/2015/08/CSIRO-PyroPage-Issue-2-Spotfires.pdf

What it shows:
- **Flaming brands** (bamboo, 0.6-0.9 g, 9 s flame):
  - With no wind, the litter must be at 14% moisture or less to ignite, and 50% ignite below about 9%.
  - With wind, the limits are about 21% and 50% below about 13%.
  - Below about 7%, ignition is "essentially guaranteed".
- **Glowing bark brands** (0.2 g): at 2 m/s wind they need 10% moisture or less, with 50% ignition below about 4%. With no wind, ignition is unlikely.

**Concrete action (threads 4 and 1).**
- Ratapani litter is very dry in Mar-Apr afternoons [inference: dead fine fuel moisture is probably 5-8%, see `fine_scale_weather.md`]. So ignition by any brand that lands is near-certain.
- The bottleneck is lofting distance (B1, B2), not ignition. No action beyond B1.

### B5. Pyretechnics (pyregence.github.io/pyretechnics), §7 "Spot fire" (ELMFIRE's model). **FULL** (the spot-fire chapter)
https://pyregence.github.io/pyretechnics/

What it shows:
- **Landing distance.** Downwind distance is lognormal with E[Δx] = Δ₁·I^e_I·U^e_U and Var = r·E.
  - Example configuration: Δ₁ = 10 m, e_I = 0.3, e_U = 0.55, r = 425 m.
  - Crosswind SD is 100 m.
  - Flight survival is exp(−d/200 m).
  - Firebrands: 1e-6 per kJ.
- **Ignition.** Schroeder 1969: P(I) from temperature and fine fuel moisture. Spot ignition delay: Albini 1979 plus 20 min.
- The authors warn that Sardoy 2008 parameters give "nonsensical σ_Y > E[Δx]".

My numbers (`spot.py`):
- A 25 ha fire at 125 kW/m, wind 2-4 m/s, T 35 °C, fuel moisture 5-8%:
  - mean landing distance 62-91 m; P(beyond 1 km) 0.4-0.7%; about 1,125 brands;
  - **0.003-0.009 expected spot fires 1-5 km away** with the survival term, or 1.8-4.6 without it.
- A 60 ha fire at 500 kW/m and 6 m/s gives 0.04-0.06 (or 18-28 without survival).

**Concrete action (thread 4).**
- The result swings by 500× with one uncalibrated parameter (the 200 m survival scale), so physics spotting models cannot settle the question. Our data can (A4, A5).
- With the survival term, embers give fewer than 1 jump per 100 fires. We observe about 6 pts excess of new fire within 2 km per fire-day.
- Do not use ELMFIRE-style spotting to explain the 1-5 km starts.

### B6. FARSITE / FlamMap technical documentation, "Spotting". **FULL** (single page)
https://owfflammaphelp62.firenet.gov/LegacyFARSITE/Tech_Spotting.htm

What it shows:
- "Spotting in FlamMap and FARSITE is only simulated from torching trees (Albini 1979)." Surface-fire spotting is "calculated in BehavePlus, but [is] not present in FlamMap or FARSITE".
- 16 embers are lofted per torching vertex. An "ember spot probability" setting is applied, and "all embers burning at impact ignite". There is a minimum spotting distance setting.

**Concrete action (thread 4).** This supports leaving the ember term out of the physics comparator. US operational simulators do not spot from surface litter fires at all. State this in the spread thread's comparison so the physics model is not unfairly penalised for missing jumps.

### B7. Butry & Prestemon 2005, "Spatio-temporal wildland arson crime functions", AAEA annual meeting paper. **FULL**
https://research.fs.usda.gov/download/treesearch/9537.pdf

What it shows:
- **Data.** Daily wildland-arson counts for six high-arson Florida Census tracts, 1994-2001; means of 0.03-0.11 arson ignitions per day.
- **Model.** A Poisson autoregression, PAR(p), with dummies for an arson in a neighbouring tract (local) or in the county and surrounding counties (regional) on t−1, t−2 and t−3 to t−11.
- **Results.**
  - Own-tract autoregression p1 = 0.23-0.52 (p < 0.01 in 4 of 6 tracts), p2 = 0.12-0.32.
  - Pooled model: lags p1-p10 significant at 5%.
  - Regional neighbours at t−1: 0.93-1.10 (p < 0.05) in Sarasota, Taylor and Volusia. At t−2: 0.76 in Charlotte; local t−2 1.62 in Sarasota.
  - "Spatio-temporal lags longer than two days were not significant." The authors read this as serial or copycat firesetting.
- **Other variables.** The drought index (KBDI) is positive everywhere (0.10-0.50). Saturdays are mixed. Socioeconomic variables are weak.

**Concrete action (threads 1 and 4).**
- The same shape as ours: one to two days and "the tract next door", with the own-place effect lasting longer.
- Make the jump term a 0-1 day kernel (≤ 12 h strongest) on new fires in the same and adjacent beats, and let it decay to nothing by day 2-3. A5 gives the values.
- Expected: it adds about 2-3 pts of "new fire within 2 km in 24 h" above background where the spread model currently has zero.

### B8. Genton, Butry, Gumpertz & Prestemon 2006, "Spatio-temporal analysis of wildfire ignitions in the St Johns River Water Management District, Florida", *IJWF* 15:87-97. **FULL**
https://research.fs.usda.gov/download/treesearch/22039.pdf

What it shows:
- 21 years of ignitions over 31,681 km², located to cadastral sections of 1.6 km.
- The homogeneous L-function shows clustering from the smallest distance up to tens of km.
- "Ignitions by railroad, lightning, and arson are spatially more clustered than ignitions by other accidental causes". Arson clusters "around major cities", attributed to "a common firesetter with a limited spatial domain".
- The location precision (1.6 km) is too coarse for sub-2 km structure.

**Concrete action.** None beyond B9. It is an example of how a homogeneous test overstates clustering; we used a permutation null instead.

### B9. Hering, Bell & Genton 2009, "Modeling spatio-temporal wildfire ignition point patterns", *Environ. Ecol. Stat.* 16:225-250. **FULL**
https://research.fs.usda.gov/download/treesearch/36264.pdf

What it shows:
- Re-analysing B8 with an inhomogeneous K-function, "clustering is less important than initially thought".
- **Arson.** In 1996 the homogeneous L shows clustering to 25 km; the inhomogeneous L "flirts with the upper bound through 15 km". In 1997 it is clearly clustered through 10 km.
- **Lightning clustering disappears** once the trend is modelled.
- **Arson and accident fires cross-cluster to about 35 km.**
- Prescribed burns show no significant interaction with wildfires in the same or next year.

**Concrete action (thread 4 and our Knox test).** Spatial clustering alone is mostly "where people are". Only the space-time interaction is coupling. That is why our null keeps locations and shuffles times; it already removes the fixed "fire-prone place" effect. The A3 ratio of about 1.0 at 5-20 km confirms the null is not leaking a trend.

### B10. Comas, Costafreda-Aumedes & Vega-Garcia 2014, "Characterizing configurations of fire ignition points through spatiotemporal point processes", *NHESS Discuss.* 2:2891-2911. **FULL** (discussion paper)
https://nhess.copernicus.org/preprints/2/2891/2014/nhessd-2-2891-2014.pdf

What it shows:
- 984 ignitions, 2007-2011, in a 30 × 30 km square of SW Galicia (110 in 2007, 138 in 2008, ...). Inhomogeneous space-time K with 199 simulations.
- Space-time **interaction at lags < 100 days and distances < 10 km**, still visible at 180 days within 4 km, and none at 365 days.
- The finest time lag tested is 30 days.
- It quotes August 2006: "1900 fires set in just 12 days".

**Concrete action.** None directly: its lags are 30× coarser than ours. It shows that a seasonal-scale K-function would call our sanctuary "clustered" for reasons that are only seasonal. Use day-level permutation tests, as here.

### B11. Holbrook, Ji & Suchard 2021, "Bayesian mitigation of spatial coarsening for a Hawkes model applied to gunfire, wildfire and viral contagion", arXiv 2010.02994. **FULL**
https://arxiv.org/pdf/2010.02994

What it shows:
- A space-time Hawkes model of 2,925 Alaska wildfire ignitions, 2015-2019. Ignition locations are inferred from discovery point plus size.
- **Fitted values (full model, posterior median):**
  - background: spatial scale 34.8 km, temporal 25.9 days;
  - self-excitation: spatial 11.1 km (10.1-12.0), temporal **1.1 days** (0.9-1.4);
  - normalised self-excitation weight 0.34.
- The naive model is bimodal. One mode has 6.5 km / 10 days; the other has an "unreasonable" background of 3,244 days.
- Self-excitation and background scales trade off, and fixing them equal is a common workaround.

**Concrete action (thread 4).**
- Alaska's lightning-dominated fires also show about a 1-day trigger time. Our 0-1 day window is the right one.
- If the spread thread fits a Hawkes jump term, fix the trigger time near 0.5 day (our A3 peak is 0-12 h). Use a two-scale spatial kernel (σ ≈ 0.5 km for joined burns, σ ≈ 2-3 km for separate fires), so it does not fall into the multimodality the paper reports [inference].
- About 1 day of work. It would replace the step table in A6 with a smooth kernel; expect a similar score [inference].

### B12. Nebraska BehavePlus study: "Spot-fire distance increases disproportionately for wildfires compared to prescribed fires as grasslands transition to *Juniperus* woodlands" (2023, PMC10089345). **PARTIAL** (first 100k of 144k characters: methods and results)
https://pmc.ncbi.nlm.nih.gov/articles/PMC10089345/

What it shows:
- BehavePlus surface-fire spotting for open grass (FBFM1, 1-h moisture 7%, flat, flames up to 2.1 m) gives a maximum of **0.8 km** at prescribed-fire winds (20 ft wind ≤ 32 km/h) and 1.4 km at wildfire winds.
- Encroached grass reaches 1.3 / 4.3 km, and juniper torching 2.6 / 6.6 km.
- These are modelled values; no field spotting distances are given.

**Concrete action.** These are open-terrain upper bounds. Ratapani fires burn under canopy with flames of about 0.3-0.7 m [inference], so 0.8 km is a ceiling. Same action as B1.

### B13. Grubb & Nobles 2016, "A spatiotemporal analysis of arson", *Journal of Research in Crime and Delinquency*. **ABSTRACT ONLY** (plus a secondary summary)
https://doi.org/10.1177/0022427815590858

What it shows:
- Los Angeles County Sheriff arson data, 2005-2012, with the Monte Carlo Knox test. There is "enhanced likelihood of near repeat follow-up incidents in close spatial and temporal proximity". Patterns differ by residential vs non-residential, day vs night and weekday vs weekend.
- Secondary summary (not verified): the excess lasts up to 14 days within about two blocks; night arsons generate more near-repeats.

**Concrete action (thread 5).** Copy the "day vs night" split for patrol. Our A4 shows night-detected parents (01:30 pass) carry 56% of the excess. A parent seen at 01:30 is the strongest trigger for a morning check within 1-2 km [inference].

### B14. Other leads read only as snippets or abstracts

- **Australian Institute of Criminology, BushFIRE Arson Bulletin no. 56 (2009).** **ABSTRACT ONLY**; the PDF returned 403.
  - Bushfire arson "clustering" over short periods; cites the Florida 11-day window.
  - Serial offending and copycats cannot be told apart, because offenders are rarely caught.
  - One firefighter lit at least 25 fires in 2001-02.
- **Briz-Redón, Martínez-Ruiz & Montes 2022**, "Adjusting the Knox test by accounting for spatio-temporal crime risk heterogeneity to analyse near-repeats", *Eur. J. Criminology* 19:586-611. **ABSTRACT ONLY**; not open access.
  - The classic Knox test assumes uniform risk; they add space and time effects.
  - Our month-block null and the 5-20 km control are a simple version of this.
- **NOAA/CIMSS NGFS alert reports**, e.g. https://cimss.ssec.wisc.edu/ngfs/alert/report/648443. **PARTIAL**: one report read; the documentation was not found.
  - Each geostationary detection is tagged "New Feature" or "Known Incident: <name> (…, tdiff = 0.37 days, Perimeter)".
  - So an operational system does label "new start vs known fire" by time since the incident and by perimeter. The thresholds are not published on the page.
  - This is the closest operational "new start near an active fire" product found. No operational system was found that publishes a calibrated jump probability.
- **Flint, Michigan arson near-repeat chains** (Security Journal 2019). **ABSTRACT ONLY**: mean risk window about 5 days; some chains last up to 2 months.

Searched and not found:
- A wildfire paper using a Knox test or near-repeat calculator on ignitions at sub-2 km / sub-day resolution. Our A2-A5 may be the first such numbers for a dry deciduous forest [inference].
- Any measurement of teak or other broadleaf litter firebrand flight.
- Corcoran et al. wildfire work: their papers are on South Wales urban and secondary fires, not wildland.

---

## Datasets and code

| Item | What | Where |
|---|---|---|
| `data/jumps/knox_tables.csv` | Knox tests A and B, year- and month-block nulls | ours |
| `data/jumps/ratio_by_distance_lag.csv` | observed/expected, 0-20 km × 0-6 h to 2-3 d | ours |
| `data/jumps/knox_joined_vs_separate.csv` | excess split by v2 scar adjacency | ours |
| `data/jumps/split_*.csv`, `splits_summary.json`, `children_0.5-2km_0-1d.csv` | wind angle, hour, lag, month, beat, division splits; per-new-fire rows | ours |
| `data/jumps/jump_rate_table.csv`, `jump_rate_heldout*.csv`, `jump_rate_summary.json` | per-issue jump-chance table (ring × lag × month / parent size) with background; season hold-out | ours |
| `data/jumps/spot_out.txt` | Albini 1983 and ELMFIRE-style spotting numbers for our intensities | ours |
| `code/jumps/*.py` | prep, knox, splits, knox_sep, rate_table, spot | ours |
| CFS `fbp97spot.c` | Albini 1979/1983 spotting code | https://cwfis.cfs.nrcan.gc.ca/downloads/fwi_obs/fbp97/fbp97spot.c |
| Pyretechnics spot-fire module | ELMFIRE spotting, Schroeder ignition probability | https://pyregence.github.io/pyretechnics/ (GitHub pyregence/pyretechnics) |
| Alaska ignitions (Holbrook) | discovery points and sizes, 2015-19 | https://fire.ak.blm.gov |

---

## Ranked action list (gain, effort)

1. **Add a separate "new fire nearby" layer to the burn-probability maps (thread 4), using `jump_rate_table.csv`, not an ember kernel.**
   - Inputs: each fire's detections so far; time since its last detection; month; parent detections that day.
   - Settings: the 0-1 day chance per ring is 2.5% / 5.6% / 10.3% / 12.3% / 25.3% for 0-0.5 / 0.5-1 / 1-2 / 2-3 / 3-5 km; spread it over ring area; ×1.2-1.5 in April and for parents with 3 or more detections that day; zero after day 2.
   - Gain: it covers the misses the spread thread found. The excess of about 3 pts per ring is about 40% of what the burn map currently misses within 2 km [inference]. Effort: half a day.
2. **Re-score the spread model after removing joined pairs** (A5).
   - Count a "new fire" within 1 km whose v2 scar touches the parent scar as spread, not a jump. That is 80% of the 0-1 km excess.
   - Gain: a fairer "jump" target and a better calibration check. Effort: 1-2 h.
3. **Do not use wind direction to aim the jump term** (A4). The excess is isotropic, and the ember-compatible rule explains about 2% of it.
   - Gain: it avoids a wrong model. Effort: none.
4. **Patrol rule (thread 5): a morning re-check within 1-2 km of any fire seen on the 01:30 pass.** About 56% of the 0.5-2 km excess follows a night-detected parent, with the new start 6-12 h later.
   - Gain: in hit rate per km walked, likely the best single rule [inference; test it in the patrol pilot]. Effort: low.
5. **Thread 1: add a "new fire within 2 km in the last 12-24 h" feature.** Restrict it to separate-scar fires and to the issue day only. The excess lasts less than a day, so it mostly helps the day-1 part of the 2-day window.
   - Expected: +0.5-1 pt on new ignitions [inference]. It overlaps the Hawkes features already planned in `short_horizon_prediction_fullread.md`, so test it as their τ = 0.5 d, σ = 1-2 km member. Effort: 1 h.
6. **Optional: fit a two-scale Hawkes jump kernel** (B11), with trigger time fixed at about 0.5 day and σ of 0.5 km (joined) and 2.5 km (separate). Fit on 2017-24 and test on 2025-26 against the step table.
   - Gain: a smooth map, small skill gain [inference]. Effort: 1 day.
7. **Beat focus for patrol staffing.** Borpani, Mathar North/South, Umariya, Malkhar, East Dantkho, Panjhir and Magardha carry the most near-repeat excess (ratio 2-2.7).
   - Gain: small. Check against beat fire counts first; these are also high-fire beats. Effort: low.
8. **Not worth doing:** ember models (Albini, ELMFIRE) for jumps; a seasonal-scale K-function. The physics caps embers at a few hundred metres, and the K-function cannot resolve the 0-12 h scale that matters here.

---

## Reading status

- **FULL (11):**
  - Albini 1979/1983 via CFS `fbp97spot.c` (code);
  - Koo et al. 2012;
  - Storey et al. 2020 (main text);
  - CSIRO PyroPage on Ellis 2015;
  - Pyretechnics spot-fire chapter;
  - FARSITE spotting documentation;
  - Butry & Prestemon 2005;
  - Genton et al. 2006;
  - Hering, Bell & Genton 2009;
  - Comas et al. 2014;
  - Holbrook, Ji & Suchard 2021.
- **PARTIAL (2):** the Nebraska BehavePlus paper (2023); one NOAA/CIMSS NGFS alert report.
- **ABSTRACT or snippets only (4):** Grubb & Nobles 2016; AIC bulletin 56; Briz-Redón et al. 2022; the Flint arson chains paper.

**Limits of the data analysis.**
- Ignition points are good to about 300-800 m and times to a few hours, so the 0-0.5 km and 0-6 h cells are smeared.
- FIRMS misses many small fires (59% of fire-pixel clusters had no alert; `USE_AND_LIMITS.md`). Real jump rates are probably higher, but the excess ratios should hold if misses are independent of parents [inference].
- MODIS-only fires carry coarse footprints.
- ERA5-Land wind is 9 km and hourly, too coarse for valley winds. A weak downwind effect could hide in that noise, but not a dominant one.
