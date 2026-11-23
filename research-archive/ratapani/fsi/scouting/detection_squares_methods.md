# The "squares": what a VIIRS detection block really is, how it moves, and how to get the most out of small moves and short gaps (scouting round 17, topic "squares", 17 Oct 2026)

Asked by Akkshay: treat each VIIRS 375 m (and MODIS 1 km) detection as a real block, study how the blocks move, and squeeze the most out of short gaps and small displacements for the spread model. Standing rules respected throughout: every sensor's detection stays its own row with its own time; nothing is merged into "looks". Where several satellites are used together below, they enter one estimator as separate observations, each with its own time and footprint.

Status tags: **FULL** = whole paper read; **PARTIAL** = the sections that matter read in full text; **ABSTRACT ONLY**. **[DATA]** = computed today on our files. **[inference]** = my reasoning, not from a source.

Not repeated here (see earlier notes): FEDS, Global Fire Atlas, Parks 2014, Briones-Herrera 2020 (`spread_from_active_fire.md`, `area_from_active_fire.md`); FEDS fire states and "fire out" logic (`fire_stopping_and_tracking.md`); geostationary products over India in detail (`geostationary_fire_timing.md`, `fire_detection_sources.md`); Sentinel-2/Landsat active-fire algorithms (`fire_detection_sources.md` §8-9). The big-fires, continuity, spread-review and fuel-from-heat READMEs are the starting point; their numbers are quoted where this note builds on them.

---

## Headline findings

1. **About 90% of the "jitter" between two satellites' squares is plain grid geometry.** [DATA, simulation] Put a single point fire under three VIIRS grids with random offsets, our real scan/track sizes and the published geolocation error. The median distance between two satellites' pixel centres comes out at **263 m**. Our measured same-moment difference is **290-370 m** (big-fires §10, spread review). The small rest is real: fires are lines and several fronts, not points. So the jitter is mostly predictable noise, and it averages out the way geometry says it should.
2. **Geolocation is a small part of it.** Published VIIRS geolocation error is **55-60 m RMSE per axis at nadir** for S-NPP and NOAA-20 (Wolfe 2013; Lin 2019, 2020). It grows with pixel size towards the swath edge. Not knowing where the fire sits inside its square is worth **~134 m per axis**. Geolocation adds **~67 m**. [DATA] Against Sentinel-2/Landsat 30 m fire pixels, each satellite shows a steady offset of **20-65 m**. S-NPP and NOAA-20 differ from each other by about 65 m north-south.
3. **The FRP of neighbouring squares is partly the same number by construction.** VIIRS 375 m FRP comes from the **750 m M13 band**. One M13 value is split evenly among every 375 m fire pixel inside it (VIIRS C2 User Guide §3.1.3; ATBD §2.3.10). [DATA] **31%** of Ratapani VIIRS detections that have a same-pass neighbour within 600 m carry exactly the **same FRP** as that neighbour. Between unrelated pixels 2-10 km apart, the rate is 0.28%. This explains a good part of the fuel-heat thread's 0.93 correlation between adjacent pixels. **FRP cannot place a fire inside a 375 m square, and FRP change between two satellites cannot measure growth below 750 m.**
4. **Short gaps cannot give speed, fire by fire.** [DATA, simulation] Each square's centre has ~150-160 m error per axis, so a speed from one pair has a spread of **~256 m/h at a 50 min gap** (512 m/h at 25 min). True fronts move **~25 m/h**, which is 21 m in 50 min. Seeing 25 m/h at 2σ would take **~420 independent 50-min pairs**, or ~1,700 pairs at 25 min. A 12 h pair needs only 1-2. This is why big-fires found 52% direction agreement for short gaps (random 50%).
5. **What short gaps are good for: sharper placement, not motion.** Fires move only ~20 m in 25-50 min, while the error is ~190 m. So the triplet (NOAA-20 → +~25 min NOAA-21 → +~50 min S-NPP over Ratapani [DATA]) is three nearly-simultaneous looks through three different grids. Combining them cuts the location error of a point fire from **189 m to ~100-110 m** (simulation; averaging the centres and intersecting the footprints both get there). [DATA] On 1,051 real VIIRS detections with a 2.7 h-earlier Sentinel-2/Landsat hot pixel as truth, the joint estimate is closer in **60%** of cases. The median gain is small, **16 m** (95% range 2-33 m), because the 2.7 h gap and multiple fronts blur the truth.
6. **FIRMS points carry more geometry than they seem to.** `scan` and `track` together show the view angle and the onboard **aggregation zone** [DATA: track rises smoothly 0.36→0.78 km, while scan saw-tooths at the zone switches 31.6° and 44.7°]. Detection rates jump at those switches (Csiszar 2014). FIRMS lacks the I-band **line/sample**, the **background temperatures**, and the **view zenith/azimuth**. The free monthly **VNP14IMGML / VJ114IMGML / VJ214IMGML** CSV files have all of them (User Guide §3.2.2). They come from UMD's SFTP server; its public login is printed in the User Guide §4.2 (not repeated here).
7. **Negative evidence ("the satellite looked and saw no fire") is the biggest unused signal.** The L2 VNP14IMG fire mask labels every pixel as fire, clear land, cloud, water, bow-tie or unprocessed. Farguell et al. 2021 used fire *and* clear-ground pixels in an SVM of arrival time on the 10 largest 2020 California fires: **burned-area error 12%, POD 0.86, false-alarm ratio 0.21, Sørensen 0.82** against airborne IR perimeters. It also mapped growth before the first detection. **Needs Earthdata login (LAADS/LP DAAC); not used here.** [inference] Over Ratapani in the dry season, clouds are rare. So "a pass covered the area and FIRMS has no point there" is a fair stand-in for clear-ground evidence until the mask is pulled.
8. **Why blocks scored worse than dots on photos (big-fires §4), and what kernel to use instead.** [inference] A detection is most likely when the fire sits near the pixel centre. The along-scan response is a trapezoid blurred by the optics (Wolfe 2013), not a flat box, and edge fires spill into two pixels. Read as a likelihood, a detection is peaked at the centre, not flat over the block. A flat 375-800 m block spreads probability onto ground that rarely holds the fire. **Test a tent-shaped kernel along scan and a box along track, sized by scan/track**, against the 340 mid-fire photos. This is cheap and can run on FIRMS fields.
9. **Data assimilation (Kalman, particle, EnKF) mostly assumes a physics model and frequent perimeters.** In the studies read (Rochoux 2014, FARSITE-EnKF, Fire-EnSF), what assimilation reliably does well is **estimate a few parameters per fire**, not a full front. For us that is per-fire speed and preferred side, which the robust all-pass fit (25 m/h) and the learned restart already do. The one transferable piece is the **Haley-Mandel detection likelihood**. It turns a fire arrival-time map into a probability of each detection *and* each non-detection, given geolocation error. Our blend map can be scored and tuned with it, with no physics.
10. **Geostationary does not help with the squares.** Pixels over Ratapani are 10-19 km² (GK2A, SEVIRI-IODC, INSAT). They add timing for big fires only (`geostationary_fire_timing.md`). Himawari sits at view zenith ~74° and MTG is beyond the limb. **Sentinel-2/Landsat 30 m hot pixels are the only sub-pixel truth we hold for VIIRS squares**: 43 per big fire, median, at 10:15-10:50 IST. ECOSTRESS 70 m needs Earth Engine on Akkshay's PC.

---

## 1. The square itself: VIIRS I-band geometry (the facts that set every error)

### 1.1 Schroeder, Giglio & Hall 2025, *Collection 2 VIIRS 375-m Active Fire Product User's Guide* v1.2 (June 2025). https://www.earthdata.nasa.gov/s3fs-public/2025-06/VIIRS_C2_AF-375m_User_Guide_1.2.pdf **FULL**

- A granule is 6 min, about 202 scans × 32 detectors × **6,400 samples**, over a swath of about **3,060 km**.
- The **fire mask** has classes 0 not processed, **1 bow-tie deletion**, 2 sun glint, 3 water, **4 cloud**, **5 land (looked, no fire)**, 6 unclassified, 7/8/9 low/nominal/high-confidence fire.
  - The 32-bit **algorithm QA** layer keeps each test's outcome for **every pixel**: background-fire flag, candidate flag, tests 1-4, saturation, glint, and the bit-22 "residual bow-tie" flag.
  - Residual bow-tie duplicates *are* output as fire pixels. **Use bit 22 to avoid counting the same fire twice.** That is FRP double-counting, and for us, double-counting a square.
- **Thresholds that matter for small litter fires** (Table 2):
  - day candidate needs BT4 > 325 K and ΔBT45 > 25 K; night needs BT4 > 295 K and ΔBT45 > 10 K;
  - contextual tests: day ΔBT45 > background + 2 MAD and +10 K; night +3 MAD and +9 K;
  - I4 saturates at **367 K**.
- **FRP** (§3.1.3) is computed from the **750 m M13** radiance. When two 375 m fire pixels share one M13 pixel, **each gets FRP/2**: same value, same MW.
- **Sparse per-fire-pixel fields** in the L2 file:
  - position: FP_line, FP_sample;
  - brightness: FP_T4, FP_T5, **FP_MeanT4, FP_MeanT5, FP_MeanDT, FP_MAD_T4/T5/DT** (the background);
  - FRP and radiance: FP_power, FP_Rad13, FP_MeanRad13;
  - context: FP_AdjCloud, FP_AdjWater, FP_WinSize;
  - angles: FP_SolZen/Az, **FP_ViewZenAng, FP_ViewAzAng**.
- **Monthly ML CSVs** (§3.2.2) carry the same per pixel, plus **Line, Sample, VZA, VAA, Glint, Type and PixArea (km²)**.
  - Server: UMD SFTP at `fuoco.geog.umd.edu`, folder `data/VIIRS/C2/VNP14IMGML` (and VJ114IMGML, VJ214IMGML).
  - The login is a public one printed in §4.2.
  - Files appear 1-2 months after the month ends.
- **L2 swath files**: LP DAAC (`vnp14imgv002`, `vj114imgv002`) and LAADS (`allData/5200/VNP14IMG/`). Both need an Earthdata login.
- **Night plume artefact** (§7): at high scan angle, a tall hot plume can be detected and displaced by parallax toward the swath edge. Not relevant to litter fires [inference].
- **I4 saturation** (§7) is one main reason sub-pixel retrievals from I4 are unreliable. It happens three ways: nominal saturation, DN folding, and mixing during onboard aggregation, which carries no flag.

**Concrete action for us (spread, big-fires, continuity):**
- (a) Pull the three ML CSVs for Jan-Jun 2017-2026 and join them to the FIRMS rows on time + lat/lon. This adds line/sample, background temperatures, view angles and pixel area at no login cost.
- (b) Drop or down-weight residual bow-tie duplicates. They are flagged only in L2; in ML files, look for same-pass pairs ~one scan apart with identical T4 [inference].
- (c) Stop treating FRP of adjacent pixels as independent.

### 1.2 VIIRS 375 m Active Fire ATBD v1.0 (Dec 2016). https://viirsland.gsfc.nasa.gov/PDF/VIIRS_activefire_375m_ATBD.pdf **PARTIAL** (§2.2 inputs and aggregation, §2.3.10 FRP, read in full)

- **Aggregation zones:** 3 native samples per pixel from nadir to **31.59°** scan angle, 2 from 31.59° to **44.68°**, 1 from 44.68° to **56.06°**. Aggregation is done on board for I1-I5.
- M13 is aggregated on the ground; the fire algorithm uses both aggregated (750×750 m) and un-aggregated (**250×750 m**) M13.
- I4's effective saturation is ≈**358 K**, giving ≈**9%** visible fire-pixel saturation. M13 saturates at ≈**659 K**, so it is used for FRP.
- FRP = A·σ/a·(L13 − L13B), with a = 2.88×10⁻⁹ for M13 and A the scan-angle-dependent pixel area.
- "A single pixel 750 m FRP retrieval is divided among the number of coincident 375 m fire pixels, with each sub-pixel receiving the same resulting value in MW."

**Concrete action (big-fires, fuel-heat):**
- Any "FRP per square" analysis should first collapse pixels sharing one M13 pixel. Those are same-pass neighbours with identical FRP; in the ML files, use Line/Sample to find the 2×2 group.
- [inference] The un-aggregated 250 m-wide M13 along-scan samples exist only in the L1 radiance files. They are the only VIIRS data finer than 375 m along scan, and are not worth chasing for litter fires (they would need L1B M13 granules with Earthdata login).

### 1.3 Wolfe, Lin, Nishihama, Tewari, Tilton & Isaacman 2013, "Suomi NPP VIIRS prelaunch and on-orbit geometric calibration and characterization", *JGR Atmos.* 118:11,508-11,521. doi:10.1002/jgrd.50873. NTRS copy https://ntrs.nasa.gov/api/citations/20140010285/downloads/20140010285.pdf **PARTIAL** (§2-3 sensor and spatial response, §5 geolocation, Table 2, read in full; the scan-mechanism maths skimmed)

- I-bands have 32 detectors, rectangular, with the short side along scan. Aggregation (3×1, 2×1, 1×1) limits along-scan growth to about the along-track growth, **≈2× nadir at the scan end**.
- **Bow-tie deletion:** for I-bands, 2 and 4 detectors per scan are not sent in the 2×1 and 1×1 zones. Overlapping scan lines towards the edge are trimmed but not fully removed.
- **Spatial response:**
  - Along track, the line spread function is essentially a square of detector size.
  - Along scan, the telescope rotates during integration. The static spread function is "dragged", giving a **trapezoid-based dynamic LSF with edges blurred by the optics**.
  - "We have **undersampling for all I-bands in all aggregation zones**". As I read Fig. 6 [inference], the I-band half-width footprint is a bit narrower than the sample spacing, so a point source near a pixel edge gives a weaker signal in each of two pixels.
- **Geolocation accuracy (Table 2, nadir-equivalent, after the April 2013 update):**

| | track | scan |
|---|---|---|
| mean bias | 2 m | 2 m |
| RMSE | **70 m (19% of a 375 m pixel)** | **60 m (16%)** |
| Aqua MODIS C6, for comparison | 46 m | 51 m |

  - Errors are quoted "in nadir equivalent units"; they grow towards the scan end at the same rate as the pixel.
  - The first on-orbit update removed biases of 775 m (track) and 1,118 m (scan).
  - A 325 m scan-direction jump came with an electronics switch on 22 Nov 2012 and was fixed on 11 Dec 2012.
- **Terrain:** the I- and M-band products are terrain-corrected with a DEM. The scan-direction error from ignoring terrain is up to **2.75 × elevation** at scan end. [inference] Ratapani relief of ~300 m would be ≤800 m at the edge if uncorrected, but FIRMS uses terrain-corrected geolocation, so this is handled.

**Concrete action (spread, continuity):**
- In the error model, use per-axis geolocation σ ≈ 60 m × (pixel size / 375 m). Use a footprint aligned with scan and track, not N-S/E-W boxes.
- Scan direction is perpendicular to the ground track. Over Ratapani that is about 12° off E-W [inference from the 98.7° orbit inclination], and it flips between ascending (day) and descending (night) passes.

### 1.4 Geolocation for NOAA-20 and the latest collections

- **Lin, Wolfe, Tilton, Zhang, Dellomo et al. 2019, "JPSS-1/NOAA-20 VIIRS early on-orbit geometric performance", Proc. SPIE 10764.** NTRS https://ntrs.nasa.gov/api/citations/20190029269/downloads/20190029269.pdf **PARTIAL** (results and Table 2)
  - NOAA-20's initial errors were −897 m (track) and 1,710 m (scan).
  - After revision r2, RMSE is **59.5 m track, 52.7-60 m scan**. Errors stay under ~125 m, meeting the 375 m (3σ) requirement 99.73% of the time.
  - Daily-mean drifts reach **~50 m**, and there is a ~60 m peak-to-peak orbital fluctuation.
- **Lin, Wolfe, Dellomo, Tan et al. 2020, "SNPP and NOAA-20 VIIRS on-orbit geolocation trending and improvements", Proc. SPIE 11501.** https://ntrs.nasa.gov/api/citations/20210026335/downloads/1150112.pdf **PARTIAL**
  - Collection 2 S-NPP: track RMSE **55 m**, scan **49 m**, means ≈0 m.
  - "Daily mean geolocation biases are within ±0.1 I-band pixel."
  - A 10-20 m positive track bias and ±20 m scan wobble remain in mission-to-date data.
- **Blonski, Wang, Ahmad & Cao 2023, "Post-launch evaluation and improvements of NOAA-20 VIIRS SDR geolocation accuracy", J. Appl. Remote Sens.** NOAA repository https://repository.library.noaa.gov/view/noaa/55884 **PARTIAL** (abstract, §1-2)
  - Initial NOAA-20 error was >2 km. It was reduced to **<400 m at nadir (3σ)**, with most errors under 200 m.
  - The requirement is 400 m (3σ) at nadir and **1,500 m at scan edge**.
  - This applies to the operational (NOAA IDPS) SDR. NASA Land SIPS products are better.

**Concrete action:**
- Treat each satellite as having its own slowly varying offset of up to ~50 m, on top of random error.
- [DATA] We measured such offsets against Sentinel-2/Landsat (section 3.3). They are this size, so per-sensor bias terms in the estimator are justified but worth only tens of metres.
- Note: our 2026 Ratapani alerts are **NRT** positions. The archive (SP) moves NOAA-21 points: only 34% match exactly (alerts_mp README). Use SP for research and NRT only live.

### 1.5 Csiszar, Schroeder, Giglio, Ellicott, Vadrevu, Justice & Wind 2014, "Active fires from the Suomi NPP VIIRS: product status and first evaluation results", *JGR Atmos.* 119:803-816. https://directreadout.sci.gsfc.nasa.gov/publications_documents/Csiszar_et_al_2014_JGR.pdf **PARTIAL** (§2 sensor and aggregation, §4 scan-angle evaluation)

- Mostly about the 750 m product. The geometry facts carry over:
  - native pixels ≈ 750 × 250 m for M-bands, half that for I-bands;
  - switchovers at **31.58° and 44.6°**;
  - "a **discontinuity occurs in the VIIRS pixel size at the aggregation switchover angles**", and the lower detection limit jumps with it.
- In the 3-pixel zone VIIRS (750 m) had **26%** more detections than MODIS; outside it, **70%** more.
- Onboard bow-tie handling produces fewer duplicate fire pixels than MODIS.
- Mixed saturated/unsaturated pixels from aggregation are up to ~3% for M15.

**Concrete action (all threads):**
- [DATA] The FIRMS (scan, track) pair already encodes the zone. Track grows smoothly with view angle (0.36 → 0.78 km). Scan saw-tooths: e.g. scan 0.32-0.37 km with track 0.55-0.58 km is a pixel *just past* a switchover, and scan 0.38-0.41 km with track 0.36-0.37 km is near nadir.
- Add "zone" (1/2/3) and view angle (from track) as covariates wherever detection probability matters:
  - the "is it still burning" model;
  - the "44% of passes miss a burning fire" estimate;
  - a per-pass detection probability in the spread scorer.
- Ratapani share by scan size: 33% ≤0.40 km, 40% 0.40-0.50, 23% 0.50-0.60, 4.5% >0.60 [DATA].

### 1.6 Schroeder, Oliva, Giglio & Csiszar 2014, "The new VIIRS 375 m active fire detection data product: algorithm description and initial assessment", *RSE* 143:85-96. https://directreadout.sci.gsfc.nasa.gov/publications_documents/Schroeder_et_al_2014b_RSE.pdf **PARTIAL here** (read FULL in `fire_detection_sources.md` §6; today re-read for simulated detection limits and Landsat-8 comparison)

- Detection curves were simulated for fires of **2-250 m²** at 400-1200 K, inserted into real backgrounds.
- A **1.25 m-radius bonfire (~5 m²) at ~1000 K** was detected at night at a **32.7°** scan angle. It raised I4 by **+10 K**.
- Saturation: nominal I4 saturation in **~8%** of day fire pixels (1% at night); I4 folding 0.2%. Daytime commission error for nominal-confidence pixels: **1.2%**.
- In the Landsat-8 comparison, VIIRS came ~**75 min after** Landsat. Areas of active fire fronts on Landsat-8 overlapped well with the 375 m pixels.

**Concrete action (big-fires):**
- [inference] Litter-fire lines of a few m² are near the night detection limit. They are well inside it by day only when longer or hotter.
- Detection probability therefore depends on where the fire line sits in the pixel and on its length. That is the same PSF-centre peaking that argues for a tent kernel (headline 8).

---

## 2. Fire progression from detections: footprints, negative evidence, arrival-time fields

### 2.1 Farguell, Mandel, Haley, Mallia, Kochanski & Hilburn 2021, "Machine learning estimation of fire arrival time from Level-2 active fires satellite data", *Remote Sens.* 13:2203. https://doi.org/10.3390/rs13112203 **FULL**. Code: https://github.com/openwfm/JPSSdata

- **Idea:** every L2 pixel is a point (lon, lat, time).
  - Fire pixels are labelled +1 and **clear-ground pixels −1**. Missing (cloud) pixels are left out.
  - A weighted soft-margin SVM with a Gaussian RBF kernel separates "burning" from "not burning" in 3-D.
  - At each location, the arrival time is the **smallest t where the decision function crosses 0**, found by cubic-spline roots along t.
- **Weights:**
  - fire pixels use their confidence; those below **70%** are dropped;
  - clear-ground pixels get a fixed **95%**, since 100% overfits;
  - C_i = k_C · c_i³ and γ = k_γ · √n / (p·S_x), tuned by 5-fold grid-search CV that keeps the class ratio;
  - clear ground is undersampled, because the classes are very imbalanced.
- **Inputs:** MOD14/MYD14 + MOD03/MYD03 geolocation; VNP14 / VNP14IMG + VNP03 / VNP03IMG. Pixel centres only.
- **Results** (10 largest California fires of 2020, vs NIROPS airborne IR perimeters):
  - **81%** of fire pixels fall between consecutive IR perimeters, so the authors note "an error on every 2 out of 10 pixels";
  - burned-area MAPE **12%** (range 3-20%); total burned-area error **5%**;
  - POD **0.86**, FAR **0.21**, Sørensen **0.82**;
  - **63%** of area errors are over-prediction.
  - The authors blame over-prediction on treating pixels as centre points while the detection used the whole footprint (>1 km² off-nadir). They suggest a non-convex footprint-aware fit as future work.
  - Clear-ground pixels let the method map growth **before the first detection** (LNU, Slater/Devil).
  - Low-confidence isolated pixels are filtered out, while small high-confidence fires survive.

**Concrete action (continuity, spread):**
- This is the cleanest published way to use "looked, saw nothing". Our blend map uses only positives.
- **Recipe A (no new data) [inference]:**
  - For each VIIRS pass over a fire, add pseudo-negative points on a 375 m lattice in the pass's own scan/track frame, within 2 km of the fire, wherever no FIRMS point lies.
  - Weight them less than real negatives (e.g. 0.5), because cloud and smoke can hide fire.
  - Fit Farguell's SVM, or simpler, a logistic GP, in (x, y, t). Score on the 340 mid-fire photos against blend (84%).
- **Recipe B (with Earthdata login):** use the real fire mask (class 5 = clear land, class 4 = cloud excluded). The authors' 63% over-prediction suggests adding the footprint, our tent kernel, to their point treatment.

### 2.2 Haley, Farguell Caus, Kochanski, Schranz & Mandel 2018, "Data likelihood of active fires satellite detection and applications to ignition estimation and data assimilation", *Advances in Forest Fire Research 2018* (Coimbra), arXiv 1808.03318. **FULL**

- **The detection likelihood** given a fire arrival-time map T(x) is built in three steps:
  1. a **heat-release model**: heat fraction decays exponentially after arrival, 1/e in **2 h**;
  2. a **logistic detection probability** in heat fraction: **50% detection at 1% heat fraction**, and a **0.1% false-detection** floor;
  3. **convolution with a Gaussian geolocation kernel.**
  - The result is a log-likelihood that is high for some hours after arrival, steeper on the leading edge, and with quadratic tails.
- Their example uses σ = 2,000 m: "a rounded sum of the diagonal of a 1.1 km pixel plus the standard deviation of 0.5 km geolocation error".
- **Ignition by maximum likelihood:** 1,000 WRF-SFIRE runs (10×10 grid at ~500 m × 10 start times 2 h apart) on the 2013 Patch Springs fire. The estimate was within **~1 h** of the official ignition time, but **~3 km** from the official point.
  - A known bias: earlier ignitions make bigger fires that cover more squares, so maximum likelihood leans early. In the idealised test it returned t = 20 instead of 30.

**Concrete action (spread, continuity, stopping):**
- [inference] Use this likelihood as the **scoring function** for any arrival-time map, physics-free.
  - Each detection square gets log p(detect | T inside its footprint).
  - Each covered-but-empty square gets log p(no detect | T).
  - Kernel: VIIRS σ ≈ 150-160 m per axis (our simulation), not 2 km.
- It lets us tune the blend map's power (now 1/d⁴) and burning clock on *satellite* data, not only on 340 photos. It also gives a proper probability for the "hidden look" test, which today scores everything at ~12 h error.
- **Watch the early-ignition bias** when reading start times off it. The ignition thread's back-third finding (64% of first detections lie in the back third of the scar) is consistent with it.

### 2.3 Haley 2022, *Assimilation of Satellite Active Fires Data*, PhD thesis, Univ. Colorado Denver (arXiv 2204.00686). **PARTIAL** (§2.2 data errors, §3.2 graph method outline, §3.5 ROS uncertainty)

- **Error sources it lists:**
  - geolocation, which grows with scan angle;
  - **arrival-time uncertainty**: a detection says fire was there, not when it arrived;
  - dependence between neighbouring pixels, since "a hot fire near the edge of a nominal pixel may result in two fire detections";
  - resolution mismatch.
- Table 2.1 quotes nadir 3σ error as **200 m for MODIS and 350 m for VIIRS**.
- **ROS between two detections** is treated as a random variable:
  - distance = difference of two Gaussians (σ = 125 m, "a scan angle of approximately 35 degrees");
  - each arrival time is **uniform over the previous 12 h**, so the time difference is triangular;
  - ROS = D/T, with the density of 1/T derived analytically.
- **Graph method:** cluster detections, build a directed graph, take shortest paths from the ignition to every detection, interpolate along paths, smooth iteratively, and use non-fire pixels to cap the outer edge.

**Concrete action (spread, big-fires):**
- [inference] Apply the "arrival uniform over the previous l hours" idea at our scale.
  - At 25 m/h a front needs **~15 h to cross one 375 m square**. A square can therefore stay lit across the next pass, even though the front inside it has moved.
  - The right l for Ratapani is the **pixel residence time** (pixel width / speed), about 12-20 h, not a fixed 12 h.
  - This is another reason "new burning beyond everything seen before" works (68%) while centre-to-centre moves do not.

### 2.4 Veraverbeke, Sedano, Hook, Randerson, Jin & Rogers 2014, "Mapping the daily progression of large wildland fires using MODIS active fire data", *IJWF* 23:655-667. doi:10.1071/WF13015. PDF via https://jin.ucdavis.edu/download_file/view/89/256 **FULL**

- **Method:** ordinary kriging of MODIS detection times inside the final perimeter, on a 500 m grid.
  - A spherical variogram is fitted per fire (R² 0.67-0.99). The nugget is usually 0, the range 4-76 km and the sill 2-857 days².
  - The best number of neighbours n was **4-6**.
- **Geolocation is simulated as sub-pixel location uncertainty:** V = √(S² + T²)/2 (half the pixel diagonal), drawn as V·N(0,1) in x and y, 10 sets per fire. The per-pixel SD of the 10 maps is the "geolocation" error.
- **Errors:** kriging standard error median **0.80-3.56 days**; geolocation-induced **0.34-2.72 days**.
- **Against daily airborne-IR perimeters** (9 SW-US fires, 3,000-240,000 ha):
  - **73%** of pixels within one day, against 33% for MCD45A1 and 53% for MCD64A1;
  - daily burned-area R² **0.64** averaged (others 0.61 and 0.84 for single products).
- **Alaska hold-out** (up to 8 passes/day; four used to map, the rest held out): RMSE **0.70-1.63 days** (1.25 pooled), mean bias 0.01 day.
- MODIS needs only "1-10% of the pixel area" burning to detect a fire, which "can be located at any sub-pixel location".

**Concrete action (continuity):**
- Kriging is the same family as our blend map (inverse-distance^4), with a fitted variogram.
- [inference] Two cheap transfers:
  - (a) fit a per-fire variogram of VIIRS pass times and use its range to set the blend's distance scale per fire, instead of one global power;
  - (b) copy their Monte-Carlo geolocation step, using our scan/track box plus 60 m Gaussian, to put a timing-uncertainty band on each growth-atlas pixel. Band 2 of the GeoTIFFs already holds a bracket width; this would make it a real uncertainty.

### 2.5 Kumar, Picotte & Peterson 2019, "Prototype downscaling algorithm for MODIS satellite 1 km daytime active fire detections", *Fire* 2:29. https://doi.org/10.3390/fire2020029 **PARTIAL** (abstract, method, accuracy section)

- Each 1 km MODIS fire pixel is split into its four 500 m sub-pixels, ranked by contextual 2.13 µm SWIR reflectance tests against neighbours (windows 9×9 up to 31×31).
- More than **84%** of 500 m cells with real fire were put in high/medium probability classes. Checked with gas flares and ASTER (which flies on Terra with MODIS).
- Limits: fire size and temperature, smoke, **PSF and geolocation errors**. "A downscaled 500 m product … can potentially reduce the location and area uncertainty by one half and one quarter."

**Concrete action (big-fires):**
- [inference] VIIRS has no band finer than 375 m. But the same trick works across sensors: use **day-of-pass Sentinel-2/Landsat SWIR** to say which part of a VIIRS square is burning or burnt. Our hot-pixel layer is exactly that.
- For **MODIS** squares (1 km+), which big-fires found make placement worse, split them with the 500 m MODIS SWIR (MOD09GA) before use, or drop them for placement and keep them for timing only.

### 2.6 Other progression sources

- **Scaduto, Chen & Jin 2020**, "Satellite-based fire progression mapping: a comprehensive assessment for large fires in northern California", *IEEE JSTARS* 13:5102-5114. **ABSTRACT ONLY** (paywalled).
  - 42 fires over 5,000 acres, 2017-18, vs NIROPS.
  - Best: natural-neighbour interpolation of combined MODIS+VIIRS, daily R² **0.70**, **0.83** with a 2-day window.
  - VIIRS alone: kappa 0.55, overall accuracy 0.59.
  - 61% of pixels on the right day, plus 25% within ±1 day.
  - **Action:** natural neighbour is a third interpolator to add to the continuity photo table (blend vs nearest-look vs natural neighbour). It costs about an hour.
- **Sá et al. 2017**, "Evaluating fire growth simulations using satellite active fire data", *RSE* 190:302-317. **ABSTRACT ONLY** (IDL page has no reachable PDF).
  - 9 large Portuguese fires; two discrepancy measures, absolute and relative, between FARSITE output and MODIS detections. The relative one is flagged as not independent across evaluations.
  - **Action:** none beyond what HONEST_TESTS already does with photos.
- **Benali et al. 2016**, *Remote Sens.* 8:326. **ABSTRACT ONLY** here (covered in `ignition_points.md`). MODIS ignitions within **12 h and 2 km** of reported ones.
- **Chen et al. 2022 FEDS** (*Sci. Data* 9:249). **PARTIAL here** (FULL in `spread_from_active_fire.md`). Re-checked: the active front is the perimeter segment near new pixels. The tracking buffer is 5 km for forest and 1 km otherwise. It works on pixel centres; footprints are not used.
- **Liu et al. 2024 GOFER** (*ESSD* 16:1395). **PARTIAL** (methods). Hourly GOES perimeters:
  - max detection confidence over time, smoothed with a dynamic square kernel, thresholded at an **optimised confidence (0.75-0.99)**, vectorised at 200 m;
  - **terrain-parallax correction** of GOES pixels from a 10 m DEM;
  - IoU **0.77** vs FEDS-FRAP's 0.83.
  - **Action:** the "smoothed max-confidence over a time stack, then threshold" step is a simple way to build our per-pass burning masks from blocks. Parallax does not matter for VIIRS, which is terrain-corrected, but would for GK2A (view zenith 62°, about 300 m relief × tan 62° ≈ 560 m, negligible against its 3 km pixel) [inference].
- **Coen & Schroeder 2013/2018-20 VIIRS fire-front papers**: no full text found today. Earlier notes have the 2013 abstract. A 2019 MODIS/VIIRS science-team slide says 375 m VIIRS perimeters are used to start the CAWFE model, and shows a perimeter 12 h later.
- **Johnston et al. 2018**, "Flame-front rate of spread estimates … strongly influenced by measurement approach", *Fire* 1:16. **PARTIAL** (abstract, methods).
  - On 27 lab burns, eight ROS methods gave significantly different answers. "Failing to fully account for directionality of the RoS may result in significant error."
  - The best method (Paugam 2013) computes **rate and direction from arrival times at triangles of points**.
  - **Action:** compute speed as 1/|∇T| of the arrival map, along the gradient direction, not as distance between detections. Our Theil-Sen front distance is a 1-D version of this.

---

## 3. Extracting signal from tiny displacements and short gaps

### 3.1 The pass order over Ratapani [DATA, `alerts/` 2017-2025, VIIRS, consecutive passes <3 h apart]

| from → to | n | median gap | 10-90% |
|---|---|---|---|
| NOAA-20 → NOAA-21 | 229 | 51 min | 24-54 |
| NOAA-21 → S-NPP | 299 | **26 min** | 23-28 |
| NOAA-20 → S-NPP | 807 | **50 min** | 49-75 |
| S-NPP → NOAA-20 (next orbit) | 976 | 50 min | 23-51 |

- Typical day order: **NOAA-20, then NOAA-21 ~25 min later, then S-NPP ~50 min after NOAA-20.** The night triplet is the same.
- Pixel sizes are statistically identical across satellites (median scan 0.45 km). But each pass has its own grid phase and its own view angle.

### 3.2 Error model [DATA: Monte Carlo on our scan/track sizes; geolocation from §1.3-1.4]

A point fire is observed by a pixel whose grid is offset at random. That gives uniform error over the pixel, plus Gaussian geolocation of 55-58 m × (pixel size / 375 m).

| quantity | value |
|---|---|
| per-axis error of one detection centre | **151 m (scan), 161 m (track)** |
| of which grid ("where in the square") | ~134 m |
| of which geolocation | ~67 m |
| single-centre radial error, median | **189 m** |
| two satellites, same moment: median centre separation | **263 m** (p90 470 m); observed on our fires 290-370 m |
| speed spread from one pair, 25 / 50 / 75 min gap | 512 / **256** / 171 m/h |
| same, 12 h / 24 h gap | **18 / 9 m/h** |
| independent pairs needed to see 25 m/h at 2σ, at 25 / 50 / 75 min | ~1,700 / **~420** / ~190 |
| at 12 h | ~2 |

- **Minimum detectable speed from one 50-min pair is ~500 m/h (2σ)**, twenty times the real front speed.
- **Within-pixel persistence instead of centres.** A square is lit while any front is inside it. At 25 m/h the chance that a front crosses a 375 m pixel edge within 50 min is about 21/375 ≈ **6%** per front-edge [inference]. And the three grids differ, so "a new pixel" is mostly a new grid, not new ground.
- **New-pixel counts and footprint area** are therefore also grid noise at 25-50 min. FRP over 50 min is worse:
  - two satellites on the same look agree only at **0.51** (factor 1.9 typical), per the fuel-from-heat thread;
  - FRP is at 750 m resolution, and is the same number in 31% of neighbour pairs;
  - [inference] the real diurnal change over 50 min near the 12-13 h peak is <20%, well under the 2× noise.
- **Conclusion:** at 25-75 min, nothing about motion survives per fire. Summed over hundreds of pairs it can (big-fires: 52.2%, range 50.1-54.2, so barely). Use short gaps for **placement and "still burning"**, and 12-24 h gaps for motion.

### 3.3 What the triplet *does* give: sharper placement [DATA]

**Simulation** (point fire, three satellites with their own grids, ±8° axis rotation, PSF spill into the neighbour when the fire is within 15% of the edge):

| estimator | median error | p90 |
|---|---|---|
| one satellite's centre | 189 m (140 m with spill, which gives two-pixel hits) | 320 m |
| mean of three satellites' centres (each kept as its own row; motion ~20 m ignored) | **109 m** (82 m with spill) | 194 m |
| footprint intersection of the three (union of lit pixels per satellite, padded 60 m) | **101 m** (97 m) | 184 m |
| intersection + "unlit neighbour" rule | 101 m (100 m) | 184 m |

**Real-data check:**
- 508 fire-days in the big-fires table where a VIIRS day pass came 1-5 h (median 2.7 h) after Sentinel-2/Landsat 30 m hot pixels. 1,878 VIIRS detections.
- Truth = nearest hot pixel.
  - Single centre: median **290 m** (p75 493 m).
  - For 1,051 detections with another satellite's detection within 400 m in the same pass window, the joint estimate (own centre averaged with the other satellites' centres within 400 m) is closer in **60.2%** of cases.
  - Median error 292 → **276 m**. Joint minus single, bootstrap over fires: **−33 to −2 m**.
- The gain is real but small on this truth. The hot pixels are 2.7 h older and fires have several fronts, so the truth itself is ~250 m "noisy".
- Only **43%** of nearest hot pixels sit inside the nominal VIIRS square (sd of offset 0.85 pixel along scan, 1.06 along track). So this truth cannot measure the PSF shape.

**Per-sensor offset against Sentinel-2/Landsat** (mean of hot-pixel minus VIIRS centre, nearest within 600 m, bootstrap over fires):

| sensor | n | east (m) | north (m) |
|---|---|---|---|
| S-NPP | 711 | **−50** (−69 to −31) | −17 (−36 to +4) |
| NOAA-20 | 674 | **−41** (−61 to −23) | **+48** (+30 to +64) |
| NOAA-21 | 174 | +20 (−10 to +52) | +34 (+1 to +69) |

- [inference] Fire motion over 2.7 h has no common direction across fires (big-fires: wind/slope ≈ random). So a shared drift is unlikely, and the **NOAA-20 vs S-NPP north offset of ~65 m** looks like registration.
- This agrees with the published ~50 m daily drifts. The correction is worth tens of metres at most.

**Concrete action (spread, continuity, big-fires):**
- (a) In the arrival/blend map and the robust front-speed fit, give each detection a **location uncertainty**, and let near-simultaneous detections from other satellites (|Δt| < 60 min) **pull each other** by their inverse variances. Rows, times and sensors stay separate; only the location estimate is shared, and a 25 m/h × Δt motion allowance is included.
- (b) Fit per-sensor, per-season offsets against Sentinel-2/Landsat hot pixels and subtract them.
- (c) Re-score on the 340 photos. Expected gain [inference]: +0.005 to +0.01 AUC on "closest dot".
  - The bigger effect should be on **front-speed fits**: per-look position σ falls from ~155 to ~90-100 m per axis, so 12 h speed σ falls from ~18 to ~11 m/h. That could raise the share of fires with speed clearly above zero (61% now) by ~5-10 points.

### 3.4 Sub-pixel position from brightness of adjacent squares [inference, no paper found that does this for VIIRS]

- The search found PSF-impact work for SEVIRI (Calle et al.) and MODIS (consecutive-scan double counting). No published VIIRS fire-centroid method from neighbouring radiances turned up.
- Principle: when two adjacent pixels along scan are lit by one fire line, the ratio of their **I4 radiance excess** (I4 radiance minus background) places the fire between their centres, through the trapezoid/tent response.
  - FIRMS gives bright_ti4 for each lit pixel but **no background**.
  - The ML CSVs give **MeanT4**, which removes the fuel-heat thread's "one background per pass" artefact.
- **Do not use FRP for this.** It is the shared M13 value (§1.2).
- **Limits:**
  - I4 saturates at 367 K (3.8-4.6% of our detections);
  - an unlit neighbour reads as "below threshold", not "zero signal";
  - real fires are lines several hundred metres long, so the "position" is the line's centre of brightness.
- **Test:** on two-pixel same-pass clusters with an S2/Landsat hot pixel the same morning, see whether the I4-ratio position beats the midpoint. Expected gain is small; ~30-50 m at best on the ~40% of detections that come in pairs.

### 3.5 Dozier two-channel fraction (where in the pixel)

- The two-channel solution gives burning **fraction and temperature, not position**.
- The big-fires thread found it solvable for 77% of detections, giving 0.8% of the block at ~537 K, and of no use for placement.
- The fuel thread showed I5 mostly reads the canopy-shaded background.
- With ML-file MeanT4/MeanT5 the fraction becomes better posed, but it still says nothing about *where*. **Not ranked for spread.**

---

## 4. Kalman, particle and ensemble tracking of fire fronts

### 4.1 Rochoux, Ricci, Lucor, Cuenot & Trouvé 2014, "Towards predictive data-driven simulations of wildfire spread - Part I: reduced-cost EnKF based on a polynomial chaos surrogate", *NHESS* 14:2951-2973. **PARTIAL** (abstract, §1-2 observation model)

- A level-set front solver (FIREFLY) with Rothermel ROS. Observations are **front markers** with independent Gaussian error σ_o.
- An EnKF estimates **ROS parameters** (fuel depth, moisture, wind factor), not the front itself. A polynomial-chaos surrogate makes it cheap.
- Tested on synthetic cases and a controlled grassland burn. Skill "strongly relate[s] to the spatial and temporal variability of the errors in the ROS model parameters".
- **Action:** the parameter-estimation framing fits us: one speed, one preferred side and one stop chance per fire, updated each pass. Their front-marker Gaussian observation model is wrong for squares (§3.2 is uniform-plus-Gaussian, plus non-detections).

### 4.2 FARSITE-EnKF (Theodori 2016, MS thesis, Univ. Maryland, https://drum.lib.umd.edu/handle/1903/18625) and Srivas et al. 2016

- **Theodori 2016**: **PARTIAL** (framework chapters). FARSITE coupled to an EnKF through OpenPALM, with **60 ensemble members** perturbed in wind and moisture, on 30 m grids. Tested on synthetic and experimental fires.
- **Srivas, Artés, de Callafon & Altintas 2016**, "Wildfire spread prediction and assimilation for FARSITE using ensemble Kalman filtering", *Procedia Comput. Sci.* (ICCS 2016): **ABSTRACT ONLY**. Hourly perimeter assimilation on a simulated 2014 Cocos fire. A 2017 follow-up also adjusts fuel factors.

### 4.3 Shi, Wang & Liu 2025, "Fire-EnSF: wildfire spread data assimilation using ensemble score filter", arXiv 2510.15954. **PARTIAL** (abstract, §1, §4 set-up and results)

- A diffusion-model-based filter on FARSITE perimeter states. Observations are VIIRS-derived perimeters (FEDS-type) with noise.
- EnSF has lower RMSE than EnKF in the authors' tests. The EnKF only slightly beats no assimilation in their high-dimensional set-up. Code public.
- **Action:** none directly. It confirms that a full perimeter state is hard for an EnKF.

### 4.4 What this means for us [inference]

- Physics lost to a learned restart model (86% vs 72% persistence), and terrain/wind do not steer these fires. A physics-state filter has nothing to correct.
- The tracking problem that remains is **"where are the active fronts now, between passes"**. A small particle filter suits it:
  - **State:** a few front points per fire, each with a heading drawn from the learned direction model (28.6% top-of-8, 60% within one sector) and a speed from the 25 m/h prior (IQR 16-36).
  - **Transition:** advance on the burning clock.
  - **Weights:** the Haley likelihood of each pass's lit squares *and* covered-but-unlit squares, using the §3.2 error model.
  - **Output:** the particle cloud is the 6/12/24/48 h burn-probability map, with calibration built in.
  - It also handles "44% of passes miss a burning fire": a missed look lowers but does not kill the particles, because p(no detect | burning) ≈ 0.44 rather than 0.
- Effort is moderate; expected gain is uncertain. Make it a challenger to the restart model, scored on photos and held-out passes.

---

## 5. Geostationary time density over India (short; see earlier notes)

- All geostationary pixels over Ratapani are **10-19 km²**: GK2A ~2.4 × 4.0 km at view zenith 61.8°; SEVIRI-IODC ~14 km²; INSAT-3D/3DR/3DS ~19 km² at view zenith 27°.
- That is 70-135 VIIRS squares per pixel. **They cannot resolve square-to-square motion.**
- Measured GK2A detection probability for Ratapani-size fires is **0.1% by day under 10 MW**, and 12-14% at night for 10-30 MW clusters (`geostationary_fire_timing.md`).
- Their use is timing and "still burning at night" for the few big fires. The stacked diurnal curve peaks 12:10-13:30 IST, which sets the burning clock.
- Himawari: view zenith ~74°, not useful. FY-4A: tested once for South Asia (`fire_detection_sources.md` §4). LSA SAF FRP-PIXEL (IODC): needs free registration, still not pulled.
- **Action:** none new for the squares. The burning clock already uses the measured curve.

## 6. Landsat / Sentinel-2 / ECOSTRESS as sub-pixel truth for the squares

- We hold **S2/Landsat 30 m hot pixels on 112 of the 146 big fires** (median 43 per fire; 45,166 S2 + 12,346 Landsat rows in `big-fires/results/detections.csv`). They come at 10:15-10:50 IST, 2.7 h (median) before the 13:00-13:30 VIIRS triplet. At 25 m/h that is ~70 m of motion, well under the ~190 m square error.
- **Uses:**
  - (1) per-sensor registration offsets (§3.3, done);
  - (2) scoring sub-pixel estimators (§3.3-3.4);
  - (3) a direct, empirical **"where is fire inside a lit square" distribution** in scan/track coordinates, but only for the ~10% of cases where the Terra-MODIS / S2 pairing is same-time. Terra comes within ~30 min of S2/Landsat; the big-fires thread found 64 such Terra detections.
- ECOSTRESS (70 m, variable hours) is the only source for other hours. It needs Earth Engine on Akkshay's PC, and only 7 of 209 photos have a usable pass (spread review), so it is a placement test, not a photo-truth extension.

---

## 7. The recipe (squares → spread model)

**Data fields to pull**

| source | fields | access | why |
|---|---|---|---|
| FIRMS (have) | lat, lon, scan, track, acq_time (minute), bright_ti4/ti5, frp, confidence, daynight, satellite | have, SP archive | baseline. Missing: line/sample, background, view angles |
| **VNP14IMGML / VJ114IMGML / VJ214IMGML** monthly CSV | **Line, Sample**, T4, T5, **MeanT4, MeanT5, MeanDT, MADT4/5/DT**, FRP, Rad13, Mean13, AdjCloud, WinS, **SZA, SAA, VZA, VAA**, Glint, Type, **PixArea** | UMD SFTP, public login (User Guide §4.2). SFTP is not HTTPS, so it likely runs from Akkshay's PC [inference] | exact view geometry and axis orientation, aggregation zone, M13 sharing groups (Line/Sample 2×2), real background for I4-ratio and Dozier |
| **VNP14IMG / VJ114IMG / VJ214IMG** L2 swath (NetCDF) | 'fire mask' (all classes), 'algorithm QA' (bit 22 bow-tie), sparse FP_* arrays | LAADS `allData/5200/` or LP DAAC. **Needs Earthdata login (not used here)** | true negative evidence (class 5), cloud (class 4), bow-tie |
| VNP03IMG / VJ103IMG geolocation | per-pixel lat/lon of the whole swath | LAADS, **Earthdata login**; files are large [inference: hundreds of MB per granule] | to place the non-fire mask pixels. [inference] Cheaper: fit a local affine line/sample → lat/lon from the granule's own fire pixels near Ratapani (dozens per granule in season). Check on a few granules against VNP03IMG |
| S2/Landsat hot pixels (have) | 30 m fire pixels with time | have | truth for placement and registration |

**Error model** (per detection; every detection its own row and time):
- True fire location inside the footprint, weighted by a **tent along scan** (half-width = scan size) × **box along track** (track size). Axes are rotated to the pass's scan direction (VAA from the ML file, or ~12° off E-W, flipped day/night).
- Plus geolocation N(0, 60 m × pixel/375 m) per axis, plus a per-sensor-season bias (20-65 m, fitted on S2/Landsat).
- Detection probability depends on zone, view angle, day/night and fire size. Non-detection of a burning fire happens at ~44% per pass.
- Arrival time is uniform over the previous **pixel residence time** (pixel size / ~25 m/h ≈ 12-20 h), not "at the pass".

**Estimator** (in order of effort):
1. *Joint placement.* For each detection, a location posterior that combines its own footprint with other satellites' footprints within ±60 min, allowing 25 m/h × Δt of motion. Feed the posterior means and σ into the blend map, the robust front-speed fit and the restart model.
2. *Likelihood-scored arrival map.* Keep the blend map. Tune its distance power and burning clock by maximising the Haley-type likelihood of all lit squares **and** covered-unlit squares (pseudo-negatives from FIRMS now, the real mask later).
3. *Farguell SVM / logistic GP in (x, y, t)* with positives and negatives, as a challenger map.
4. *Particle front filter* (§4.4) for the 6-48 h maps.

**Validation:**
- the 340 mid-fire photos (84% blend baseline; 82% for photos with a look before and after);
- the closest-dot AUC 0.84 table in HONEST_TESTS;
- S2/Landsat hot pixels for placement;
- the hidden-look test, rescored by likelihood instead of hours.
- Seasons held out as before. The front-speed share "clearly above zero" (61%) and its interval width (38 m/h median 95% range) are secondary targets.

**Expected gain (honest):**
- Placement improves ~10-40 m on a ~190-290 m error, and photo AUC by +0.005-0.01.
- Speed intervals narrow ~30-40%.
- Negative evidence is the one likely to move the arrival map more than a point. Farguell's clear-ground pixels were what let them map growth before the first detection and cap the outer edge. [inference]
- None of this changes the 2-day occurrence ceiling (weather sets when, not where).

---

## 8. Method ranking by what our data supports (coordinator's list)

| method | runs on FIRMS points (scan/track/FRP, no mask)? | extra data needed | verdict |
|---|---|---|---|
| **Cross-sensor registration error model** | **yes**, done today against S2/Landsat | none | per-sensor offsets 20-65 m. Use in the error model. Small but free |
| **Overlap geometry of two or three sensors' footprints as a constraint** | **yes** (scan/track size; orientation approximated) | VAA/Line from ML CSV for exact axes | simulated 189 → ~100 m. Real check: joint closer 60%, −16 m median. **Best value for effort** |
| **Sub-pixel localisation from adjacent-square brightness** | partly (bright_ti4 yes, background no; FRP unusable because M13 is shared) | ML CSV MeanT4, Line/Sample | worth a small test. Saturation and lines limit it |
| **Negative evidence (unlit squares)** | approximated: pseudo-negatives where a pass covered and FIRMS has no point | L2 fire mask + geolocation (**Earthdata login**) for the real thing | largest potential gain for arrival maps. Pseudo-negative version can start now |
| **Kalman / particle tracking of fronts** | yes (likelihood from §3.2) | none (mask improves it) | moderate effort, uncertain gain. A challenger to the restart model, not physics |
| **GOES/VIIRS front-tracking papers (GOFER, FEDS, Coen)** | FEDS-style yes; GOFER-style needs geostationary | geostationary L1/L2 (registration) | GOFER pixels are too coarse for Ratapani squares. Borrow only the "smoothed max-confidence stack + threshold" idea |
| **Dozier fire fraction and position within the pixel** | fraction only, badly posed without background | ML CSV background | gives no position. Not useful for spread (big-fires and fuel-heat agree) |
| FRP change over 25-50 min as growth | yes | — | **no**: 2× repeat noise, M13 sharing, true change <20% |
| Centroid moves over 25-75 min | yes | — | **no** per fire. Needs ~420 pairs per 25 m/h estimate |

---

## Datasets and code

| item | link / path | access | use |
|---|---|---|---|
| VIIRS C2 375 m User Guide v1.2 | earthdata.nasa.gov/s3fs-public/2025-06/VIIRS_C2_AF-375m_User_Guide_1.2.pdf | open | field definitions, mask classes, QA bits |
| VNP14IMGML / VJ114IMGML / VJ214IMGML (C2 v03) | fuoco.geog.umd.edu, data/VIIRS/C2/… | SFTP with public login (guide §4.2) | line/sample, background, view angles, pixel area |
| VNP14IMG / VJ114IMG L2 | ladsweb.modaps.eosdis.nasa.gov/archive/allData/5200/ ; lpdaac.usgs.gov/products/vnp14imgv002 | **Earthdata login** | full fire mask (negative evidence), QA bow-tie bit |
| VNP03IMG / VJ103IMG | LAADS | **Earthdata login** | geolocation of mask pixels |
| openwfm/JPSSdata (Farguell 2021) | https://github.com/openwfm/JPSSdata | open | L2 download + SVM arrival-time code (Python, libsvm) |
| WRF-SFIRE / wrfxpy likelihood code (Haley, Mandel) | github.com/openwfm | open | detection likelihood (physics part not needed) |
| Fire-EnSF code | linked from arXiv 2510.15954 | open | reference only |
| Our scripts today | `/tmp/claude-0/-home-user/be9b8f54-cc26-52cb-bdbb-9c8008a24baf/scratchpad/r17_work/q1.py`-`q5.py` (container scratch, not on the shared mount) | — | FRP-sharing check, pass gaps, error-model Monte Carlo, footprint-intersection simulation, S2/Landsat placement and registration test |
| Our inputs | `fire-alert-scars/alerts/viirs-*_2017-2025.csv`; `research/big-fires/results/detections.csv` | have | |

---

## Ranked actions (gain, effort) [inference unless stated]

| # | action | thread | gain | effort |
|---|---|---|---|---|
| 1 | **Joint placement**: give each VIIRS detection a location σ from scan/track (§3.2), let same-±60 min detections from other satellites pull each other (rows stay separate), subtract per-sensor offsets (§3.3). Refit front speed and the blend map; rescore on photos | spread, continuity, big-fires | speed intervals −30-40%; photo AUC +0.005-0.01; placement −10-40 m | 0.5-1 day |
| 2 | **Pseudo-negative squares from FIRMS** (covered pass, no point, dry season) + Haley likelihood to tune the blend map's power and clock; rescore the hidden-look test by likelihood | continuity, stopping | possibly +1-3 points on photos for "look after" cases; better "is it out" | 1 day |
| 3 | **Tent-along-scan × box-along-track kernel** in place of dots/blocks in the "many dots nearby" placement; photo test | big-fires, spread | resolves why blocks lost; +0-0.01 AUC | 2 h |
| 4 | **Pull the ML CSVs** (2017-2026, MP box) on Akkshay's PC. Join to FIRMS; derive zone, VZA, scan azimuth, M13 groups and backgrounds | all | enables 1-3 exactly; fixes FRP double counting and the background artefact | 2-3 h + download |
| 5 | Collapse M13-shared FRP before any FRP-per-square or cluster-FRP analysis (31% of neighbour pairs share FRP) | fuel-heat, big-fires | removes a built-in correlation | 1 h |
| 6 | Add aggregation zone and view angle as covariates to the still-burning model and the per-pass detection probability (the 44% miss) | stopping, spread | better calibrated "missed vs out" | 2 h |
| 7 | Farguell-type SVM / logistic-GP arrival map with positives + negatives as a challenger to blend; add natural-neighbour (Scaduto) to the photo table | continuity | unknown; Farguell got Sørensen 0.82 on big CA fires | 1 day |
| 8 | Get Earthdata login on Akkshay's side and pull L2 fire masks for the 146 big fires' passes only (~1,600 passes); test the affine-from-fire-pixels geolocation shortcut on a few granules | continuity | real negatives (cloud separated) | 1-2 days |
| 9 | Small particle front filter (§4.4) as a challenger for the 6-48 h maps | spread | uncertain | 3-5 days |
| 10 | I4-ratio sub-pixel position for two-pixel clusters, scored on S2/Landsat | big-fires | ≤30-50 m on ~40% of detections | 0.5 day |
| — | Not worth doing: centroid moves or FRP change over 25-75 min per fire; Dozier for position; geostationary for square motion; MODIS 1 km squares for placement (unless split with 500 m SWIR) | | | |

---

## Reading status

- **FULL (4):**
  - VIIRS C2 375 m User Guide v1.2 (2025);
  - Farguell et al. 2021 *Remote Sens.*;
  - Haley et al. 2018 (AFFR / arXiv);
  - Veraverbeke et al. 2014 *IJWF*.
- **PARTIAL (14):**
  - VIIRS 375 m ATBD 2016;
  - Wolfe et al. 2013 *JGR*;
  - Lin et al. 2019 SPIE (NOAA-20);
  - Lin et al. 2020 SPIE;
  - Blonski et al. 2023 *JARS*;
  - Csiszar et al. 2014 *JGR*;
  - Schroeder et al. 2014 *RSE* (FULL in an earlier note);
  - Haley 2022 thesis;
  - Kumar et al. 2019 *Fire*;
  - Rochoux et al. 2014 *NHESS*;
  - Theodori 2016 thesis;
  - Shi et al. 2025 Fire-EnSF;
  - Johnston et al. 2018 *Fire*;
  - Liu et al. 2024 GOFER *ESSD*.
  - Chen et al. 2022 FEDS was re-checked here, FULL in an earlier note.
- **ABSTRACT ONLY (4):**
  - Scaduto et al. 2020 *JSTARS*;
  - Sá et al. 2017 *RSE*;
  - Benali et al. 2016 *Remote Sens.*;
  - Srivas et al. 2016 *Procedia*.
- **Not found:** Coen VIIRS fire-front 2018/2020 full text; a published VIIRS sub-pixel fire-centroid method; Johnston GOES ROS.
- Not re-read (covered in earlier notes): Andela 2019, Parks 2014, Briones-Herrera 2020, Lizundia-Loiola (FireCCI), Wooster 2015 SEVIRI FRP-PIXEL, Xu 2017 Himawari, INSAT/FY-4 sources.
