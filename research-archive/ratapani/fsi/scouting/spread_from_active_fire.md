# Predicting the next 1-2 days from today's active fire: persistence, spread kernels and baselines (scouting round 3, topic: activespread)

For the "Rethink the 2-day question" thread and the spread thread (threads 1 and 4). Notes already in the folder are not repeated here: physics models and VIIRS assimilation (`fire_spread_models*.md`), FireSenseNet and the evaluation shortcuts (`fire_spread_models_fullread.md` §9), Hawkes contagion (`short_horizon_prediction*.md` §4), and FSI's large-fire rule plus the persistence and same-window-last-year baselines (`field_alert_systems_fullread.md`, `operational_occurrence_systems.md`).

Each source is marked **FULL**, **PARTIAL** or **ABSTRACT ONLY**. My own reasoning is marked **[inference]**. Section 0 holds new measurements from our own data (FSI LFF archive; VIIRS SNPP 2013-2024 for Ratapani). Scripts are in `scratchpad/r3code/` (persist*.py, momentum.py, share.py). They are quick checks, not a finished analysis.

---

## Headline findings

1. **The field's standard target is "next-day active-fire mask" and its standard baseline is persistence.** Carrying today's mask forward scores AP 0.19 / F1 0.43 on WildfireSpreadTS (year range 0.105-0.287 AP). Best models reach AP 0.37-0.48. On Next Day Wildfire Spread, persistence gets AUC-PR 11.5% and the best CNN gets 28.4%. Almost all of the skill comes from the previous fire mask. Removing it drops AUC-PR from 28.4% to 6.8%. Removing any weather variable changes it by less than 2.5 points.
2. **Our own VIIRS (Ratapani 2013-24, 8,114 vegetation pixels):** a daytime detection has a 17.5% chance of another detection within 1 km in the next 6-30 h. The chance is 34% within 2 km and 4.6% within 500 m. Controls give 3.4-4.0% within 1 km (same time, random other-year fire site, or the same point moved 3-5 km), so the lift is about 4.5x. **A night (01:30) detection is twice as likely to persist: 36% within 1 km, about 9x the control.** Today's detection count matters too. A daytime pixel with 4 or more same-pass neighbours within 1 km gives 51% within 2 km, against 23% for an isolated pixel.
3. **FRP hardly helps at the pixel level.** In daytime FRP quartiles the 1 km persistence is 14.7%, 19.2%, 17.8% and 18.1%. At night it is flat. Night passes have low FRP (median about 1.4 MW), which is why FRP looks "negative" when day and night are pooled. That is a confound, not a signal. Confidence class adds nothing (h 15%, n 16%, l 20%).
4. **Freshness decays fast.** Yesterday's detections (18-30 h) lie within 1 km of 7.7% of today's daytime pixels. Detections from the day before yesterday only (42-54 h) lie within 1 km of 2.5%. A decay time of about 1 day is right **[inference]**.
5. **Spread from known fires can explain at most about a third of tomorrow.** Only 32% of today's daytime pixels lie within 2 km of any detection in the previous 30 h, and 39% within 54 h. The other 61-68% are new ignitions more than 2 km from recent fire. A spread baseline is a component of the 2-day model and cannot replace it.
6. **There is no usable direction kernel at our scale.** Next-day displacement bearings are close to uniform. In each 45° sector the counts run 117-176, with S slightly under-represented. Direction "momentum" is barely detectable: the mean cosine between yesterday's step and today's step is 0.07 (95% CI 0.00-0.15, n = 324). This matches the earlier finding that wind adds nothing at 500 m.
7. **FSI large fires near Ratapani (494 events, 2019-25):** 64% last a single calendar day and 36% last 2 or more days. Once a fire has reached day 2, the chance of continuing is about 0.55 per day. The median bounding box is 1.2 km², with a diagonal of 1.6 km. In March, 45% are multi-day, against 3% in February. Fires first seen on the night pass are multi-day 45% of the time, against 33% for those first seen by day.
8. **Operational practice is probabilistic.** Canada's FireSTARR publishes "probability this cell burns within N days" from thousands of stochastic FBP runs. FEDS tracks fire objects every 12 h, keeps them active for 5 days, buffers them by 5 km (forest) and takes the active front as perimeter within 500 m of new pixels. FSI's rule is 3 or more juxtaposed pixels, tracked until the fire dies plus 3 days.

---

## 0. Our own measurements (new)

### 0.1 FSI Large Forest Fire archive, Ratapani box (lat 22.9-23.4, lon 77.3-78.2). FULL (our data)

File: `/mnt/project-files/ratapani/fsi/fsi_portal/lff_mp.csv`. Duration is counted in calendar days from F_T_D to L_T_D. Box sizes are taken from EXT_* (degrees converted to km at 23°N).

| Statistic | MP (n = 7,536) | Ratapani box (n = 494) |
|---|---|---|
| 1 calendar day | 68.2% | 63.6% |
| ≥2 days | 31.8% | 36.4% |
| ≥3 days | 16.7% | 20.6% |
| ≥5 days | 4.1% | 4.9% |
| P(day ≥3 \| reached day 2) | 0.52 | 0.57 |
| P(day ≥4 \| reached day 3) | 0.55 | 0.55 |
| P(day ≥6 \| reached day 5) | 0.44 | 0.46 |
| Duration in hours, quantiles 50/75/90/95/99 | 0 / 23.7 / 58.5 / 72.7 / 133 | 0 / 23.7 / 68 / 84 / 144 |
| Box diagonal km, quantiles 10/25/50/75/90 | 1.10 / 1.21 / 1.54 / 2.25 / 3.27 | 1.11 / 1.25 / 1.64 / 2.40 / 3.38 |
| Box area km², median (IQR) | 1.10 (0.68-2.31) | 1.23 (0.73-2.58) |
| Multi-day share, first seen by day / by night | 30% / 36% | 33% / 45% |

- **Ratapani by duration:** median box diagonal is 1.35 km for 1-day fires, 2.25 km for 2 days, 3.0 km for 3-4 days, 3.5 km for 5 days and 5.1 km for 7 days. Median box area is 0.84, 2.36, 3.95, 6.1 and 12.4 km².
- **Pass counts:** 295 of 494 events (60%) are seen on a single pass. The rest span 2-17 passes.
- **Box shape:** multi-day boxes are only mildly elongated (aspect ratio median 1.31, IQR 1.16-1.65). E-W and N-S elongation are equally common (47% have width greater than height).
- **By month (Ratapani):** multi-day share is 3% in February (n = 31), 45% in March (n = 253), 34% in April (n = 177) and 20% in May (n = 25).
- **By season:** multi-day share ranges from 24% (2022-23) to 44% (2021-22 and 2023-24).
- **By division:** Obedullahganj 339, Raisen 96, Sehore 32, Bhopal 27. Top ranges are Barkhera 67, Dahod 57, Bineka 56 and Chiklod 53.
- **Recurrence:** only 6.9% of LFFs are followed by another LFF starting within 3 km in the 3 days after the last detection. Once a large fire ends, it rarely restarts next door.
- **Caveat 1:** the "growth rate" read off the box (diagonal / (days-1), median 1.6 km/day) is far above the 100-430 m/day of our litter fronts. Boxes are envelopes of several fronts plus VIIRS pixel spread (about 375-750 m), so they must not be read as rate of spread **[inference]**.
- **Caveat 2:** the archive is conditional on at least 3 juxtaposed pixels, so small fires are excluded.

**Concrete action (threads 1 and 4):**
- A Ratapani large fire has about a 36% chance of being seen on a second day.
- If it is still burning on day 2, the chance of a day 3 is about 55%. A simple geometric survival model, P(still active at day k+1 | active at day k) of 0.36 then 0.55, is a defensible prior for "will this alert still be burning tomorrow".
- Use a March flag and a night-first-seen flag as the two cheapest modifiers.

### 0.2 Persistence of individual VIIRS detections, Ratapani 2013-2024. FULL (our data)

File: `/mnt/project-files/ratapani/viirs_snpp_2013_2024.parquet` (8,114 type-0 pixels: 5,815 day, 2,299 night). For each pixel I took the minimum distance to any detection in absolute-time windows after it: next pass (6-18 h), same pass next day (18-30 h), and the following day (30-54 h).

| Subset | n | ≤0.5 km in 6-30 h | ≤1 km | ≤2 km | ≤1 km in 6-54 h | ≤2 km in 6-54 h |
|---|---|---|---|---|---|---|
| Day pass, all | 5,815 | 4.6% | 17.5% | 34.2% | 19.8% | 40.4% |
| Day, new (no detection ≤2 km in previous 3 d) | 3,411 | 4.2% | 15.0% | 29.1% | 17.2% | 35.5% |
| Night pass, all | 2,299 | 15.2% | 35.9% | 52.1% | 38.7% | 58.2% |
| Night, new | 927 | 14.8% | 32.3% | 47.1% | 34.7% | 52.8% |
| **Control:** same time, random other-year fire site | | 1.0-1.6% | 3.8-4.0% | 10-12% | | |
| **Control:** same point shifted 3-5 km | | 1.0-1.2% | 3.4-3.9% | 11-13.5% | | |

Day-pass detail:
- Next pass (night, 12 h later) within 1 km: 11.3%. Same pass next day within 1 km: 8.2%. 30-54 h: 3.9%.
- Cumulative chance of a next-day (6-30 h) detection, by distance: 2.3% within 375 m, 11.1% within 750 m, 17.5% within 1 km, 27.9% within 1.5 km, 34.2% within 2 km, 42.3% within 3 km, 52.8% within 5 km.
- Among next-day detections within 3 km, the nearest-pixel distance has median 1.44 km and quartiles 0.96 and 2.10 km. This mixes real spread with VIIRS geolocation scatter and multi-pixel clusters.
- Same-pass neighbours within 1 km (0 / 1 / 2-3 / ≥4) give 12.5% / 17.2% / 21.5% / 20.5% within 1 km and 22.8% / 30.7% / 40.3% / 50.8% within 2 km.
- FRP tercile × neighbours (1 km persistence):
  - isolated pixel: low FRP 9.7%, mid and high 14.6%;
  - with neighbours: 18-22% with no FRP trend.
  - FRP is weak and only matters for isolated pixels.
- By month (day pass, within 1 km): January 7.6%, February 10.7%, March 21.5%, April 18.8%, May 16.5%, December 1.6%.
- Scan angle (off-nadir pixels are bigger): within 1 km falls from 18.4% near nadir to 13.6% at the swath edge.

Night-pass detail:
- Within 1 km: 25% for isolated pixels, 33% with 1 neighbour, 44% with 2-3, 51% with ≥4.
- FRP quartiles are flat (33-39%).

Where today's daytime pixels come from (pixel-weighted):
- Previous 6-30 h, within 0.5 / 1 / 2 / 3 / 5 km: 7% / 19% / 32% / 39% / 52%.
- Previous 6-54 h: 8% / 21% / 39% / 48% / 63%.
- Previous 7 days: 4% / 19% / 47% / 62% / 79%. The 7-day window starts at 18 h.

Direction:
- Bearings of next-day displacement (n = 1,246 pairs within 2 km), by sector N to NW: 154, 168, 170, 136, 117, 152, 173, 176.
- Momentum: mean cosine 0.073 (CI 0.001-0.146). Only 23% of steps fall within 45° of the previous step, against 25% expected at random.

**Concrete action (threads 1 and 4):**
- This is the "fire neighbourhood" surface for Ratapani, in numbers. Build it as a feature family and as a stand-alone baseline (recipes in Part C).
- Night pixels deserve about twice the weight of day pixels.
- Count same-pass neighbours rather than FRP.
- Drop direction kernels.
- Expect the spread component to cover about a third of next-day detections at 2 km, and to need a separate ignition model for the rest.

---

## Part A. Next-day spread benchmarks and their baselines

### A1. Huot, Hu, Goyal, Sankar, Ihme & Chen 2022, "Next Day Wildfire Spread: a machine learning dataset to predict wildfire spreading from remote-sensing data", IEEE TGRS 60:4412513. arXiv 2112.02447. FULL

What it is:
- US 2012-2020, 64 × 64 km patches at 1 km, 18,545 samples. The target is the MODIS fire mask at t+1, with "uncertain" pixels masked from the loss.
- From t to t+1, 58% of fires grow, 39% shrink and the rest stay the same size.

Results (test set):

| Model | AUC-PR | Precision | Recall |
|---|---|---|---|
| CNN autoencoder | 28.4 | 33.6 | 43.1 |
| Random forest (3 × 3 neighbourhood features) | 22.5 | 26.3 | 46.9 |
| Logistic regression | 19.8 | 32.5 | 35.3 |
| Persistence | 11.5 | 35.7 | 27.3 |

- **Persistence has the highest precision of all (35.7%).** The models win on recall and ranking.
- Ablations (AUC-PR):
  - removing the previous fire mask: 6.8;
  - removing humidity: 26.1;
  - removing wind speed: 27.2;
  - removing wind direction: about 25.5 when kept as the only extra feature.
  - The top 9 RF Gini importances are all previous-fire-mask neighbourhood pixels (0.05-0.09 each). ERC is the best non-fire feature at 0.017.
- Previous fire mask alone: recall 49.6%, precision 29.2%, AUC-PR 22.9.
- Coarser targets (AUC-PR):

| Target cell | Model | Persistence |
|---|---|---|
| 2 km | 39.8 | 19.5 |
| 4 km | 53.5 | 30.6 |
| 8 km | 66.3 | 41.3 |

**Concrete action (thread 1, evaluation):**
- Report our spread baseline at 500 m and also aggregated to 1, 2 and 4 km, because score depends heavily on cell size.
- State persistence's precision next to our model's, since persistence can win on precision.
- The ablation independently supports our "wind adds nothing" result: weather moves AUC-PR by 1-2 points.

### A2. Gerard, Zhao & Sullivan 2023, "WildfireSpreadTS: a dataset of multi-modal time series for wildfire spread prediction", NeurIPS Datasets & Benchmarks. FULL. Data on Zenodo 8006177, CC-BY-4.0

What it is:
- 607 US fires (2018-21), 13,607 daily images at 375 m, 23 channels.
- The target is the VIIRS active-fire mask of the next day. All detections in a 24 h window are pooled, so still-burning pixels count as positives.
- 35-49% of images have no detection at all, because of cloud, smoke or quiet days.

Persistence:

| Year | AP | F1 |
|---|---|---|
| 2018 | 0.187 | 0.432 |
| 2019 | 0.105 | 0.323 |
| 2020 | 0.194 | 0.439 |
| 2021 | 0.287 | 0.535 |
| Mean | 0.193 | 0.432 |

- Using only the **last** detection of the day is **worse** (mean AP 0.135, F1 0.333), because noisy and view-angle-dependent detections make the pooled mask more reliable.
- Model results (mean AP):

| Model | AP |
|---|---|
| Logistic regression (one 3 × 3 convolution, 361 parameters) | 0.279-0.288 |
| Res18 U-Net | 0.328-0.344 |
| ConvLSTM | 0.29-0.31 |
| UTAE (vegetation features) | 0.372 |

- Adding all features lowered UTAE to 0.321.
- Topography plus fire mask gave 0.29-0.31. The VIIRS reflectance bands were the best single extra group.

**Concrete action (thread 1):**
- A 3 × 3-neighbourhood logistic model already gets about 1.5x persistence AP. That is our "kernel + logistic" baseline (Part C, B2).
- Pool all passes of the day into the input mask rather than using only the latest pass. This agrees with our night-pass finding.

### A3. Lahrichi, Bova, Johnson & Malof 2025, "Improved wildfire spread prediction with time-series data and the WSTS+ benchmark", arXiv 2502.12003 v3. FULL

- With focal loss, pretraining and AP used for model selection, Res18-UNet reaches AP 0.455-0.468 for one input day and UTAE(Res18) 0.478 for five days. The original paper's numbers were 0.33-0.37.
- Removing focal loss costs 24% AP. Selecting checkpoints without AP costs 29%.
- WSTS+ adds 4 years (2016-17, 2022-23). Per-year AP across models sits around 0.25-0.58. The extra data did not raise accuracy.

**Concrete action (thread 1):** loss and model-selection choices moved AP more than any feature set did. If we revisit a CNN, use focal loss and select on AP. Do not add channels. Low priority for us.

### A4. Gopakumar & Pannozzo 2026, "WildfireSpreadBench: the metric decides the model in wildfire spread prediction", arXiv 2609.22191 v2 (NeurIPS 2026 CCAI workshop). FULL

- On the WSTS 2021 test year, persistence gets AP 0.287 and F1 0.535.
- Only ResNet18 U-Net, ConvLSTM and logistic regression beat persistence on F1 at threshold 0.5. BCE U-Net, UTAE and flow matching fall below it.
- The highest-AP model flags 4-5 times the observed fire area. UTAE flags 16-23 times.
- Going from 7 to 23 channels changes AP by 0.03, while AP differs by 0.21-0.24 across models.
- Recommendation: report AP together with F1, precision and recall at a threshold chosen on a validation year, the predicted-to-observed area ratio, and the same metrics for persistence. An agency with a fixed budget should fix the flagged area and compare recall.

**Concrete action (threads 1 and 5):**
- Our "5 picks per beat per day" is exactly the fixed-area comparison they recommend. Add **predicted area / observed area** and **persistence at the same budget** to every results table.

### A5. Zhao, Gerard & Ban 2024, "TS-SatFire", arXiv 2412.11555. FULL

- The progression label is defined as **newly burned area**: tomorrow's burned-area mask minus the burned area already seen. The raw next-day mask would let a model "detect" rather than "predict".
- 3D models reach F1 0.35-0.375 (IoU 0.31-0.34) on this harder target. Active-fire detection reaches F1 about 0.8.

**Concrete action (threads 1 and 4):**
- Report two targets:
  - (a) "any detection in the cell tomorrow", which is easy and includes still-burning cells;
  - (b) "**new** cell burned or detected tomorrow", which excludes cells detected in the past k days or inside the existing scar.
- Persistence scores zero on (b) by construction. The distance-decay kernel is the real baseline for it.
- This is the FireSenseNet shortcut noted earlier, now with a published label definition to copy.

### A6. Karlsson, Xu, Berg & Haglund 2025, "Comparing next-day wildfire predictability of MODIS and VIIRS satellite data", arXiv 2503.08580 v4. FULL

- Australia: 2019-20 season for training, 2023-24 for testing, on a 0.75° grid.
- Persistence F1 is 19.6% with the VIIRS VNP14 mask and only 6.6% with MODIS MOD14 (IoU 10.9% and 3.4%).
- Models scored on their own mask: VIIRS 28.6% F1, MODIS 12.0%. A model with MODIS inputs and a VIIRS target gets 27.2%.
- MOD14 is "stochastic" from day to day and is a poor target.

**Concrete action (thread 1):** keep VIIRS (SNPP + NOAA-20 + NOAA-21) as the target and the input mask. Do not mix in MODIS detections as targets. A MODIS-only Ratapani persistence will look about 3x worse for reasons that have nothing to do with fire.

### A7. Radke, Hessler & Ellsworth 2019, "FireCast: leveraging deep learning to predict wildfire spread", IJCAI 2019:4575. FULL

- A CNN on 30 m Landsat-8, terrain, fuel and 24 h weather, trained on GeoMAC daily perimeters.
- Evaluated on one test fire (Beaver Creek 2016): recall 91.1%, against 50.4% for random pixels and 74.8-81.1% for FARSITE (wet and dry runs).
- **Concrete action:** none. The test set is a single fire and the target is perimeters, which we do not have. This is the shortcoming to avoid.

---

## Part B. Fire-event tracking, duration and spread rate from satellites

### B1. Chen, Hantson, Andela, Coffield, Graff, Morton, Ott, Foufoula-Georgiou, Smyth, Goulden & Randerson 2022, "California wildfire spread derived using VIIRS satellite observations and an object-based tracking system" (FEDS), Scientific Data 9:249. FULL. Data on Figshare; Python code; NRT layers on gis.earthdata.nasa.gov (FireTracking)

Algorithm settings:
- 12-hour steps using VNP14IMGTDL (nominal and high confidence only).
- New pixels are clustered, then joined to an existing fire if they fall within its perimeter plus a buffer: **5 km for forest, 1 km for shrub, grass and crop.**
- A fire stays **active while it has a detection in the past 5 days**.
- Perimeter: **alpha shape with α = 1 km** (tuned on 2018 fires over 4 km²), with a 187.5 m buffer per pixel. Convex hull for 3 pixels, 187.5 m circles for 1-2 pixels.
- **Active front:** perimeter segments within **500 m of newly detected pixels.**
- Static-source filter: a fire under 20 km² with cumulative pixel density above 20 per km² is labelled static.
- Areas between consecutive perimeters are assumed burned. Unburned islands make up about 9% of the area.

Results:
- 35,337 fire objects in California 2012-20; 735 large fires (over 4 km²) with 12,801 half-day growth records.
- Against FRAP final perimeters: precision 0.85, recall 0.93, IoU 0.79, F1 0.88.
- Against NIFC daily polygons (7 fires): per-fire metrics 0.72-0.95.
- Mean positional uncertainty of a perimeter is about 375 m **[stated as approximate in the paper]**.

**Concrete action (threads 2 and 4):**
- Implement the FEDS logic on our VIIRS with Ratapani-scale settings: 12 h steps, join buffer 750 m to 1 km (litter fires move 0.1-0.43 km/day, so 5 km would merge separate ignitions), active for 3 days (FSI uses +3 days), alpha 500-750 m, front = within 500 m of new pixels.
- Its outputs give every alert an event ID, an "active front" line and an age. These are the inputs for both the distance-to-front feature and the per-alert scar.
- Expected effect: cleaner "front distance" and "freshness" features than nearest-pixel distance, because a pixel inside an old burned patch stops counting as front **[inference]**.

### B2. Andela, Morton, Giglio, Paugam, Chen, Hantson, van der Werf & Randerson 2019, "The Global Fire Atlas of individual fire size, duration, speed and direction", ESSD 11:529-552. FULL

Method:
- MCD64A1 at 500 m, 2003-16, 13.3 million fires.
- **Fire persistence threshold** (the time a fire may take to spread from one 500 m cell to the next):
  - 4 days in cells that burned more than three times;
  - 6, 8 and 10 days in cells that burned 3, 2 and 1 times.
- Minimum fire size is 0.21 km² (one MODIS cell).
- Burn-date accuracy against VIIRS: in forests and woody savannas, 24% and 35% of pixels match on the same day, and 54% and 67% within ±1 day.

GFED region results:

| Region | Mean size km² | Mean duration d | Expansion km²/d | Speed km/d |
|---|---|---|---|---|
| Southeast Asia (includes India) | 2.2 | 4.1 | 0.4 | 0.7 |
| World | 4.4 | 4.5 | 0.6 | 0.9 |
| Australia | 17.9 | 5.0 | 1.7 | 1.2 |

Values are per-fire means; size-weighted values are higher.

- Agricultural fires: 1.4 km², 3.4 d, 0.7 km/d.
- Fire direction showed **no clear dominant direction** in most of the humid tropics. Direction was more consistent in the arid tropics.

**Concrete action (threads 1 and 4):**
- The GFA dataset (direction and speed layers) for Ratapani could cross-check our 100-430 m/day. Expect GFA speeds of 0.5-1 km/d, biased high by 500 m cells and missing small fires **[inference]**.
- Our frequently burned cells match GFA's 4-day persistence rule. Use **4 days** as the maximum gap that still links two detections into one fire.

### B3. Parks 2014, "Mapping day-of-burning with coarse-resolution satellite fire-detection data", IJWF 23:215-223. FULL (Treesearch)

- Ten interpolations of MODIS detections to day-of-burning were tested on 21 fires against progression maps.
- **WMD** was best: weighted average of the 5 nearest detections, with weight w = 1/(|day_i − mean day| + 1) × 1/d_i.
- Agreement: 46.1% exact, 75.8% within 1 date, 85.8% within 2.
- Nearest-date was worst (42.8%, 69.4%, 80.7%).
- Residual (smouldering) detections are removed by keeping only the earliest detection per pixel. Interpolated islands of 25 ha or less are merged.

**Concrete action (threads 2 and 4):**
- Use WMD with the 5 nearest VIIRS pixels to date each 20 m scar pixel. Expect about 75% within ±1 overpass-day **[inference from MODIS result]**.
- Keep only the earliest detection per pixel before computing spread rate, so smouldering does not look like a stalled front.

### B4. Wang, Parisien, Flannigan, Parks, Anderson, Little & Taylor 2014, "The potential and realized spread of wildfires across Canada", Global Change Biology 20:2518-2530. FULL (Treesearch)

- A **spread day** is a day on which day-of-burning progression is at least **240 m**. That equals a rate of spread of at least 1 m/min over a 4 h burning period with circular growth.
- Potential spread days need FWI ≥ 19 and are interrupted by rain.
- Most large-fire growth happens on 1-15 days, which need not be consecutive.
- The ratio of realized to potential spread days varies regionally and correlates with conifer share (r = 0.60).

**Concrete action (thread 4):**
- Ratapani's 100-430 m/day straddles the 240 m threshold. Label each fire-day as **spread day yes/no** (progression of at least 240 m, or one 500 m cell) and model that binary outcome. Do not regress rate.
- Tally spread days per event against FWI or VPD. This is cheap and tests whether the weather "sets when" result also holds for spread.

### B4b. Wang, Parisien, Taylor et al. 2017, "Projected changes in daily fire spread across Canada over the twenty-first century", ERL 12:025005. PARTIAL (publisher HTML, methods and results)

- Potential spread days are days with FWI > 19 inside burning periods set by DMC > 20.
- Realized spread days come from daily MODIS-hotspot progression of fires of 200 ha or more (2001-14), constrained to the National Fire Database perimeters.
- Potential days are converted to realized days with a linear conversion per fire zone (exponential distributions). There is no per-day logistic model and no accuracy metric.
- About 50% of the variation is residual (fuel, topography, ignitions), not weather.
- **Use:** confirms that the operational "spread day" approach is a weather-threshold count calibrated per zone, with no day-level skill reported. For our thread 4, a per-day logistic model of spread-day yes/no would go beyond the published practice **[inference]**.

### B5. Laurent, Mouillot, Moreno, Yue & Ciais 2019, "Varying relationships between fire radiative power and fire size at a global scale", Biogeosciences 16:275-288. FULL

- FRY patches from MCD64A1 with MCD14ML FRP.
- In South-East Asia (SEAS), fire size rises with FRP only up to a **threshold of about 45 MW for savanna fires and about 10 MW for forest fires**, with a slope of about 3.9 ha/MW. Above that it flattens or falls.
- The most intense fires happen late in the season.

**Concrete action (thread 1):** this matches our flat FRP result. Do not expect patch-level FRP to predict which detections grow. At most add log(FRP) for isolated pixels, and test cluster-summed FRP instead **[inference]**.

### B6. Coen & Schroeder 2013, "Use of spatially refined satellite remote sensing fire detection data to initialize and evaluate coupled weather-wildfire growth model simulations", GRL 40:5536. ABSTRACT ONLY

- WRF-SFIRE initialized from 375 m VIIRS tracked the 2012 Little Bear fire well for **12-24 h** after each initialization, then drifted. Re-initializing on each pass fixed the drift.
- **Use:** independent support for daily re-initialization (already in `fire_spread_models.md` §4). The skill horizon of physics growth is about one day, the same as our 2-day window.

### B7. FSI, Vikram et al. (ICMBio 7th International Wildfire Conference abstracts), "Automated monitoring of large forest fires using near-real time satellite data: experience from India". ABSTRACT ONLY

- Candidate events need 3 or more juxtaposed SNPP-VIIRS pixels. Events are tracked across passes with a predefined buffer, and the boundary is redrawn on each pass.
- A 3-pixel threshold gives 7,882 events lasting more than 24 h in 2018 (8,755 in 2016). A 5-pixel threshold gives far fewer, especially early in an event. FSI does not publish the buffer distance.

---

## Part C. Operational neighbourhood probability surfaces

### C1. CFS FireSTARR and the Fire Growth Model comparison (CWFIS infographics, information current to 1 April 2026). FULL (2 pp each)

- FireSTARR is a daily probabilistic growth model for **all** fires in Canada, built on FBP fuel types, topography, detected fire location and size, and forecast weather.
- It runs thousands of stochastic simulations. A cell's burn probability is the share of runs in which it burned (900 of 1,000 gives 90%).
- Output: contours of equal relative risk, "not a projected fire boundary".
- Limitations: weather is applied to the whole scene with no elevation adjustment; there is no suppression, spotting or extinguishment; fuel breaks must be in the fuel grid.
- Uses: initial containment objectives, prioritizing new fires, inspection needs.
- Prometheus is deterministic and no longer updated. Bigfoot automates Prometheus nationally ("very coarse").

**Concrete action (threads 4 and 5):**
- The product we should copy is FireSTARR's **form**: "probability this cell burns within 1 day and within 2 days, around each active alert", shown as 2-3 contour bands.
- We can get it empirically without simulation, from section 0.2 and the kernel in recipe B2 below.
- If the physics spread model is kept, run it as a stochastic ensemble over ROS multiplier, burning hours and ignition jitter, and report burn probability. Do not report a single perimeter **[inference]**.

### C2. Dehkordi 2025, "Wildfire propagation modeling using satellite-derived parameters and generalized elliptical frames", arXiv 2512.10189. FULL (no validation)

- Huygens-principle elliptical spread with rate of spread driven only by satellite LFMC, ERA5 wind and NDVI. It gives formula tables but no validation against observed fires.
- **Use:** none beyond the idea of satellite-only ellipses. Our data show near-isotropic spread, so a circle is the right first shape.

---

## Part D. Recipes: target definition, baselines, expected skill

### D1. Target definitions

- **T1, "fire tomorrow":** the 500 m cell has a VIIRS detection (any satellite, both passes) in the 24 h fire-day starting at 06:00 local on day t+1 (or t+2). This is comparable to NDWS and WSTS, and persistence is meaningful.
- **T2, "new fire tomorrow":** as T1, but excluding cells with a detection in days t-2..t or inside an already-mapped scar. This is the TS-SatFire definition and the operationally useful one: where should a guard go that is not already known.
- **T3, "burns tomorrow":** the dated scar (WMD-dated, B3) assigns the cell to day t+1. This is the spread-thread target; 17.7% of cells within 500 m burn next day, against 0.8% at 2-3 km (`fire_spread_models.md`).
- Score every target:
  - at the fixed budget (5 picks per beat per day), with recall and precision;
  - with AP;
  - with the predicted/observed area ratio;
  - at 500 m and 1 km;
  - against both persistence and the kernel baseline.

### D2. Baselines (all parameter-light)

- **B0, persistence:** the cells detected on day t, all passes pooled. Expected on T1:
  - detection-level next-day hit within the same 375 m pixel: about 2-5%;
  - within the 3 × 3 neighbourhood at 500 m: on the order of 10-15% precision **[inference from 0.2: 11% within 750 m]**.
  - For comparison, WSTS persistence F1 is 0.43 on large US fires, where fires are large and persistent. Expect much lower for our small fires.
- **B1, buffered persistence:** cells within r of any detection in the last 24 h, with r = 0.5, 1 and 2 km. From 0.2:
  - a daytime pixel "captures" a next-day detection within 1 km 17.5% of the time and within 2 km 34% of the time;
  - pixel-weighted, 19% (1 km) and 32% (2 km) of next-day detections are within reach of the previous 30 h.
- **B2, distance-decay kernel (recommended):**
  - Score(cell) = Σ over detections j in the last 72 h of w_j · exp(−d_j / λ) · exp(−age_j / τ).
  - Starting values: λ = 0.7 km (fit range 0.4-1.5), τ = 1 day (yesterday-only gives 7.7% within 1 km against 2.5% for the day before).
  - Weights: w_j = 2 for night-pass pixels and 1 for day; × (1 + 0.15 · same-pass neighbours within 1 km), capped at 4 neighbours.
  - Months: March and April × 1, February × 0.5.
  - Better: fit it as a logistic regression on log(d_min), age of nearest detection, night flag, neighbour count and month. That is the "logistic regression on a 3 × 3 mask" of WSTS, which reached about 1.5x persistence AP.
- **B3, event-survival layer:**
  - For each FEDS-style event, P(alive tomorrow) = 0.36 on day 1 and 0.55 from day 2 on (0.1), × 1.25 if first seen at night, × 1.2 in March **[inference: crude ratios from 0.1]**.
  - Spread the event's probability over cells within 1 km of its active front (500 m around new pixels) with the B2 kernel.
- **B4, climatology:** same 15 days in past years per cell (already proposed in `operational_occurrence_systems.md`). Combine B2 + B4 + the LightGBM ignition model as the operational surface.

### D3. Expected skill [inference unless stated]

- Lift of the spread surface over a random or "fire-site" control within 1 km: about 4.5x for day pixels and about 9x for night pixels (measured, 0.2).
- Ceiling: the spread surface cannot reach more than about 32-39% of next-day detections within 2 km. With a 1 km radius it reaches about 19-21% (measured, 0.2).
- So on T1 the spread kernel will dominate precision in a few beats with active fires, while recall across 94 beats still depends on the ignition side. Expect the combined model to gain most on days that follow active fire.
- Published ML over persistence: +0.10-0.28 AP (WSTS 0.19 → 0.29-0.48; NDWS 0.115 → 0.284), almost all from better use of the fire mask. A gain of that size from adding weather or fuel is not expected (NDWS ablations: weather variables moved AUC-PR by 1-2 points).

---

## Datasets

| Name | Link | Resolution | Years | Licence | Access |
|---|---|---|---|---|---|
| WildfireSpreadTS | https://zenodo.org/records/8006177 | 375 m, daily | 2018-21 (WSTS+ 2016-23) | CC-BY-4.0 | Zenodo (about 48 GB HDF5); code on GitHub (SebastianGer/WildfireSpreadTS) |
| Next Day Wildfire Spread | https://www.kaggle.com/datasets/fantineh/next-day-wildfire-spread | 1 km, 64 × 64 patches | 2012-20 | CC-BY | Kaggle TFRecords; GEE export code in the paper |
| TS-SatFire | arXiv 2412.11555 (links in the paper) | 375 m | 2017-21 | see paper | Download per paper |
| FEDS (California) and FEDS NRT (CONUS/Canada) | https://springernature.figshare.com/collections/5601537 ; https://gis.earthdata.nasa.gov/image/rest/services/FireTracking | VIIRS 375 m, 12 h | 2012-20 (FEDS2.5 to 2023), NRT | open (Figshare CC-BY) | Figshare plus Python code; OGC API for NRT. Code to re-implement for India |
| Global Fire Atlas | https://doi.org/10.3334/ORNLDAAC/1642 | 500 m | 2003-16 (later extensions exist) | NASA open | ORNL DAAC; per-fire ignition, size, duration, speed and direction shapefiles plus daily rasters |
| FSI Large Forest Fire archive (MP) | `fsi_portal/lff_mp.csv`; https://fsiforestfire.gov.in | event bbox | 2019-25 | Government of India open portal | Already pulled |
| Ratapani VIIRS SNPP | `/mnt/project-files/ratapani/viirs_snpp_2013_2024.parquet` | 375 m | 2013-24 | FIRMS open | Local; add NOAA-20 (2018-) and NOAA-21 (2023-) from FIRMS to roughly double passes |
| CWFIS FireSTARR / M3 hotspots | https://cwfis.cfs.nrcan.gc.ca | 100 m-1 km | NRT | Open Government Licence Canada | Infographics; code is public on GitHub (CWFMF/firestarr) **[not opened this round]** |

---

## Reading status

- **FULL (13):**
  - Huot 2022 (NDWS)
  - Gerard 2023 (WSTS)
  - Lahrichi 2025 (WSTS+)
  - Gopakumar & Pannozzo 2026 (WildfireSpreadBench)
  - Zhao 2024 (TS-SatFire)
  - Karlsson 2025 (MODIS vs VIIRS)
  - Radke 2019 (FireCast)
  - Chen 2022 (FEDS)
  - Andela 2019 (GFA)
  - Parks 2014
  - Wang 2014
  - Laurent 2019
  - Dehkordi 2025
  - plus the two CWFIS infographics (FireSTARR, FGM comparison)
- **PARTIAL:** Wang et al. 2017 (ERL, publisher HTML).
- **ABSTRACT ONLY:** Coen & Schroeder 2013 (Unpaywall lists it as open access, but Wiley returned 403); FSI Vikram et al. LFF abstract; Wang et al. 2020 (search level).
- **Searched, not found:** a published "probability that a VIIRS detection is followed next day" for small fires (none found, so section 0.2 is our own); INPE neighbourhood propagation rules (INPE risk is weather-only, see `operational_occurrence_systems.md` D1); empirical slope-anisotropy kernels from VIIRS (only a non-peer-reviewed Thai symposium paper).

---

## Ranked action list

| Rank | Action | Thread | Inputs and settings | Expected gain | Effort |
|---|---|---|---|---|---|
| 1 | **Fix the targets.** Score T1 (any detection), T2 (new cell, excluding cells detected in t-2..t or inside a scar) and T3 (dated burn) separately. Add persistence and kernel baselines, predicted/observed area ratio, and 500 m plus 1 km views to every table | 1, 4 | Existing VIIRS, scars, grid | Honest comparison; prevents "detecting not predicting" inflation (TS-SatFire, FireSenseNet) | 0.5-1 day |
| 2 | **Kernel baseline B2 as a fitted logistic model:** log d_min to last-72 h detections, age of nearest detection, night flag, same-pass neighbour count, month. Start λ = 0.7 km, τ = 1 day | 1, 4 | `viirs_snpp_2013_2024.parquet` + NOAA-20/21 | Measured lift about 4.5x (day) and 9x (night) within 1 km; WSTS analogue gave about 1.5x persistence AP | 1 day |
| 3 | **Add these as LightGBM features** if not already present: night-pass detection flag, same-pass neighbour count, age of nearest detection in hours, count of fire-days in the 1 km neighbourhood over the past 3 days. Drop FRP and confidence unless they survive ablation | 1 | Same | Night detections persist twice as often; a likely gain on fire-adjacent days only | 0.5 day |
| 4 | **Add NOAA-20 and NOAA-21 VIIRS** to inputs and targets | 1, 4, 5 | FIRMS archive | Up to 3 passes per half-day; fewer "no detection" days (WSTS: 35-49% of images empty) | 0.5 day |
| 5 | **FEDS-style event tracker for Ratapani:** 12 h steps, join buffer 750 m-1 km, active 3-4 days, alpha 500-750 m, front within 500 m of new pixels; event ID, age and front line per alert | 2, 4, 5 | VIIRS; FEDS code as template | Cleaner front-distance and freshness features; per-alert scar seeds; event survival (B3) | 2-3 days |
| 6 | **Event-survival prior on alerts:** P(still burning tomorrow) 0.36 on day 1, 0.55 after; × night-first-seen and March modifiers. Show it on the alert card | 5 | `lff_mp.csv` + tracker | Lets guards triage which alerts to visit first; cheap | 0.5 day |
| 7 | **Spread-day labels** (progression ≥240 m, or one cell): model spread-day yes/no against VPD, FWI and dryness | 4 | Dated scars, ERA5-Land | Tests whether weather "sets when" for spread too; replaces noisy rate-of-spread regression | 1 day |
| 8 | **WMD day-of-burning interpolation** (5 nearest VIIRS, weight 1/(\|Δday\|+1)·1/d) to date scar pixels; keep the earliest detection per pixel | 2, 4 | Scars + VIIRS | About 75% within ±1 day (MODIS analogue); a better T3 | 1 day |
| 9 | **FireSTARR-style output:** 1-day and 2-day burn-probability bands around each active alert from the fitted kernel (or a stochastic ensemble if the physics model is kept) | 4, 5 | Results of 2 and 5 | Adoption; matches Canadian operational practice | 1 day |
| 10 | **Drop direction kernels and wind anisotropy** from the spread model unless a scar-level test shows otherwise (bearings uniform, momentum cosine 0.07) | 4 | — | Saves effort | 0 |
| 11 | Cross-check speeds against Global Fire Atlas Ratapani fires (expect 0.5-1 km/d, biased high) | 4 | GFA download | Sanity check only | 0.5 day |
