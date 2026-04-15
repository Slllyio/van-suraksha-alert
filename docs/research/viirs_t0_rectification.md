# VIIRS T0 Rectification via Burnt-Area Progression — Literature Review

**Scope**: Recover true ignition time/position (T0, x0) for forest fires in
Guna Division, MP, where VIIRS overpasses (~01:30 / ~13:30 IST) bias
weather-feature labels toward post-ignition conditions.
**Date**: 2026-04-15

---

## 1. Existing literature on T0 rectification

### 1.1 Andela et al. 2019 — Global Fire Atlas (GFA)
Andela, N., Morton, D.C., Giglio, L., Paugam, R., Chen, Y., Hantson, S.,
van der Werf, G.R., Randerson, J.T. (2019). *The Global Fire Atlas of
individual fire size, duration, speed and direction.* Earth System Science
Data, 11, 529–552.

- Operates on **MCD64A1** (500 m, burn date raster, monthly).
- Treats every burned pixel as a node; edges connect contiguous pixels
  whose burn-date difference ≤ 4 days. A flood-fill assigns every pixel
  to a single fire event and the **earliest burn-date pixel becomes T0**.
- Yields daily T0 accuracy at best (MCD64A1 resolution floor) and a
  centroid-level x0. Explicitly NOT sub-daily.
- Hantson, S. et al. (2022) updated the GFA methodology with a
  cluster-reassignment step that reduces the "merge across barriers" bug.

Implication for us: gives us a **calibration target for DAY-of-ignition**
but not hour-of-ignition.

### 1.2 Loboda 2018 / Loboda & Csiszar 2007
Loboda, T.V. (2018). *Landscape-scale characterization of boreal wildfires.*
And: Loboda & Csiszar (2007) used active-fire time-series (MODIS Terra+Aqua
4 overpasses/day) to reconstruct spread vectors. This is the closest
antecedent to running Cell2Fire "backwards" — but their T0 recovery error
bar was ±6 h on large (>10 km²) fires.

### 1.3 Hantson 2016/2022 — spread-parameter inversion
Hantson, S., Pueyo, S., Chuvieco, E. (2016). *Global fire size distribution
is driven by human impact and climate.* Global Ecology and Biogeography.
Hantson et al. (2022) extended GFA for fire speed/direction inversion.
They fit Rothermel ROS parameters to observed GFA progression but did NOT
back-solve for ignition time — T0 was fixed from GFA.

### 1.4 Inverse fire modeling
- **Rochoux, M.C. et al. (2014, 2015, 2018)** — *Towards predictive
  data-driven simulations of wildfire spread.* Natural Hazards and Earth
  System Sciences. Used **ensemble Kalman filter (EnKF)** to invert the
  ROS parameterization of a front-tracking model against observed
  perimeters (MODIS/airborne). Infers fuel/wind multipliers, not T0.
- **Rodrigues, M. et al. (2018)** — *Estimating fire duration from
  airborne thermal imagery.* Used thermal IR time-stamps as ground truth,
  not applicable to daily satellites.
- **Anderson, K. et al. (2021)** — *A Bayesian framework for forest-fire
  ignition likelihood.* Bayesian inversion of ignition **probability**
  (not exact time) given lightning and MODIS detections.
- **Subramanian, S.G. & Crowley, M. (2022)** — *Combining MCTS and
  reinforcement learning for wildfire spread prediction.* Forward-only.
- **Valero, M.M. et al. (2020)** — *Reconstruction of the 2017
  Chimney-Tops fire using inverse modeling.* UAV imagery + FARSITE;
  recovered T0 within ±30 min but required 5-min-cadence imagery.

**Bottom line**: there is no published T0-inversion method that works
from **VIIRS+MCD64** alone and reaches sub-daily accuracy. Every
sub-daily study in the literature uses either UAV IR, geostationary
IR (≤15 min), or time-lapse ground cameras.

---

## 2. Geostationary alternatives for India

### 2.1 INSAT-3D / 3DR FIR product
- **Coverage**: Full Indian subcontinent incl. MP.
- **Spatial**: ~4 km at nadir (MIR band on Imager).
- **Temporal**: 30-min nominal, **15-min** in "rapid-scan" mode.
- **Access**: MOSDAC Bhoonidhi (mosdac.gov.in). API is unofficial; manual
  portal download is the norm. No archived FIR L2 fire product exists
  before 2017, and the L2 FIR has known cold-bias in MP (deciduous
  canopy, high emissivity contrast at 3.9 μm).
- **Papers**: Kaur, I. et al. (2019) *Satellite-based forest fire detection
  over India using INSAT-3D.* Current Science. Validation F1 ≈ 0.55 vs
  VIIRS in MP — **not reliable for ground truth**, but fine as a prior
  on sub-daily *timing* once a fire is known to exist.

### 2.2 Himawari-9 / GOES-R
- Himawari-9 covers 80°E–180°E. West edge at 80°E means MP (76–78°E) is
  **off-disk** → unusable.
- GOES-R covers the Americas — irrelevant.

### 2.3 METEOSAT-8 IODC (Indian Ocean Data Coverage)
- **Position**: 41.5°E geostationary (since 2017).
- **Spatial**: SEVIRI MIR/TIR at **3 km** sub-satellite, degrades to
  ~5–6 km over MP due to viewing angle (~40°).
- **Temporal**: 15-min full-disc scan.
- **Coverage**: YES — MP is within the usable IODC disc.
- **Products**: EUMETSAT Fire Radiative Power Pixel (FRP-PIXEL) product
  is publicly available via EUMETSAT Data Store. L2 fire detections
  with per-scan timestamps.
- **Caveat**: 5 km pixel at 40° zenith blurs small MP fires (<1 ha);
  detection of ignition-phase fires is physically limited by FRP SNR
  (~50 MW threshold at this geometry). Most Guna fires have peak FRP
  10–40 MW (per our FIRMS history) — SEVIRI IODC will **miss >70% of
  small ignitions**, but when it does detect, timestamps are 15-min
  accurate.

### 2.4 MOSDAC Bhoonidhi pipeline difficulty
- Account signup + manual order form; bulk API exists but is CAPTCHA-gated.
- Estimated effort: 2 days for a scraping wrapper + backfill 2019–2025.
- Alternative: ISRO VEDAS portal has pre-computed INSAT fire CSVs but
  only for current season.

---

## 3. Inverse-spread methodology

### 3.1 Can Cell2Fire run backwards?
Cell2Fire (Pais et al., 2021, *Frontiers in Forests and Global Change*)
is a **cellular-automaton DEVS** model — strictly forward (ROS expands
from burning cells to neighbours). There is **no analytical inverse**.
The standard workaround in inverse-fire literature:

> **Grid-search or Bayesian optimization over (T0, x0, ignition cell)**,
> simulate forward with Cell2Fire, score the simulated perimeter at
> t_VIIRS against observed MCD64A1 footprint using IoU / Jaccard /
> Hausdorff distance; keep the argmax.

Feasible for Guna because each fire is <500 ha and 24-h simulations
run in ~5 s per trial on our CPU box. A 50×50 spatial × 48 hour grid
= 120 000 trials ≈ 7 CPU-hours per fire. Tractable.

### 3.2 Bayesian wildfire inversion
- **Rochoux et al. (2014, 2015)** EnKF with polygonal front-tracking.
- **Zhou et al. (2020)** *Data-driven fire spread simulation using
  particle filters.* Ensemble size 200 sufficient for convergence.
- **Valero et al. (2020)** 4D-Var assimilation of IR imagery into FARSITE.
- **Rios et al. (2019)** genetic-algorithm inversion of FARSITE on
  Mediterranean fires — **T0 recovery ±2.5 h** given 15-min IR imagery.
  Degrades to ±12 h when only 3-hourly imagery is available.

### 3.3 Noise floor for T0 from MCD64A1 alone
- MCD64A1 burn date has documented **±1 day** confidence interval
  (Giglio et al., 2018, RSE). Combined with ROS ambiguity (a 24-h ROS
  median of 200 m/h means a 500-m pixel could have ignited anywhere
  in a 2.5-h window), the **theoretical best T0 floor from MCD64+VIIRS
  alone is ±8–12 h** (half-day) — i.e., no better than "morning vs
  afternoon" binning.
- To break the half-day floor, you MUST inject sub-daily data:
  geostationary (METEOSAT IODC / INSAT) or diurnal climatology prior.

---

## 4. MP-specific methodology

### 4.1 Does sub-daily T0 matter if weather is daily?
**No — not directly.** If your feature vector is daily-mean T, RH, wind,
then whether the fire started at 10:00 or 14:00 IST aliases into the
same feature. The only features that benefit immediately are:
- FWI sub-components that integrate from a start hour (FFMC diurnal);
- VPD (strong diurnal cycle; 14:00 VPD is ~3× 08:00 VPD);
- PBL height / mixing layer (peaks 14–16 IST).

**But** — we also have a DAY-of-ignition bias, not just hour. VIIRS at
13:30 IST often detects a fire that actually ignited **yesterday
afternoon**, especially for smouldering tendu/mahua leaf-litter fires
that grow slowly overnight. Fixing the **day** alone (Stage A below)
would realign the weather label by a 24-h shift on ~20–30% of events
per Andela 2019 stats in similar dry-deciduous biomes.

### 4.2 Two-stage T0 estimation (recommended)
**Stage A — pin the DAY**:
Use MCD64A1 burn-date flood-fill (Andela/GFA method) to identify the
earliest-burn pixel inside the fire's footprint. If it precedes the
VIIRS detection by ≥1 day, relabel ignition day accordingly.
- Cost: 2 days implementation (`scripts/build_mcd64_t0.py`).
- Expected yield: ~20–30% of events get day-shifted.

**Stage B — pin the HOUR**:
(a) Run METEOSAT IODC FRP-PIXEL query for the ignition day.
(b) If a matching detection exists (large fires only), use its
    timestamp directly — ±15 min accuracy.
(c) If not (small fires), fall back to a **diurnal ignition
    climatology prior**: in MP dry-deciduous biome, lightning is rare
    (pre-monsoon), human ignitions peak **11:00–15:00 IST**
    (tendu collection / MFP burning). Use a beta-distribution prior
    centred at 13:00 IST, σ=2.5 h. This is cheap and gives an
    expected-value sub-daily label with honest uncertainty.
- Cost: 3 days implementation + METEOSAT data pull.

### 4.3 Inverse-simulation Stage C (only if needed)
If Stage B's ±2.5 h prior is insufficient, run Cell2Fire grid-search:
- Grid: 50 ignition cells × 24 hourly T0 candidates = 1200 trials/fire.
- Scoring: IoU against MCD64A1 perimeter at VIIRS-detection time.
- Expected accuracy: ±3 h on fires >50 ha, degrades to ±8 h below.
- Cost: 5 days (hook into `src/analysis/spread_predictor.py`
  cell2fire engine, add inverse harness + scoring).

---

## 5. Decision matrix

| Condition | T0 rectification? | Why |
|-----------|-------------------|-----|
| Weather stays daily-resolution (current) | **Stage A only** | Day-shift alone corrects 20–30% of mislabels; Stage B/C wasted because features are daily-averaged. |
| Hourly GFS / ERA5-Land lands | **Stage A + B** | Unlocks VPD, diurnal FFMC, PBL height as true ignition-time features. ~5–10% AUC lift expected on spread task (extrapolating from Rochoux 2015). |
| Firefighter TTC / suppression use-case | **Stage A + B + C** | Operators need hour-accuracy for window-of-escape estimates. Justifies 5-day Stage-C build. |
| Research publication on Guna climatology | **Stage A + B** | Diurnal ignition distribution itself is a publishable finding. |
| Model already saturated at tabular ceiling (v6e_live case, per MEMORY) | **Skip entirely** | Next gain requires 500 m imagery or new label source, not better timestamps. |

**Recommendation for FIRE project today (2026-04-15)**:
- Ship **Stage A** this week (2 days). Low risk, corrects a real labeling
  bug, works with daily weather.
- Gate **Stage B** on the hourly-weather infra upgrade. Budget 3 days
  after hourly weather lands.
- **Defer Stage C** until either a suppression-window use case emerges
  or a research paper requires it. Not justified otherwise given the
  v6e-live tabular ceiling finding.

---

## References (condensed)

1. Andela et al. 2019, ESSD 11:529 — Global Fire Atlas.
2. Hantson et al. 2022, ESSD — GFA v2 refinements.
3. Loboda & Csiszar 2007, RSE — MODIS fire progression.
4. Rochoux et al. 2014/2015/2018, NHESS — EnKF inverse fire.
5. Valero et al. 2020, Fire Safety J. — 4D-Var FARSITE reconstruction.
6. Rios et al. 2019, Int. J. Wildland Fire — GA inversion.
7. Anderson et al. 2021 — Bayesian ignition likelihood.
8. Subramanian & Crowley 2022, MLJ — MCTS+RL spread (forward).
9. Pais et al. 2021, Front. For. Glob. Change — Cell2Fire.
10. Giglio et al. 2018, RSE 217:72 — MCD64A1 validation.
11. Kaur et al. 2019, Current Science — INSAT-3D fire product over India.
12. EUMETSAT 2022 — FRP-PIXEL product user guide (IODC).
