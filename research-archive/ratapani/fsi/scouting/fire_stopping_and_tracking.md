# When fires stop, and how to make burn-probability maps people can trust (scouting round 11, topic "stopping", 15 Oct 2026)

Threads served: (4) the spread model, mainly the calibrated 6/12/24/48 h maps (`spread/README.md` 4o) and the fire-stopping model (4p); (5) live alerts and patrols ("is this fire still going?").

Not repeated here, because earlier notes already cover them: Huot 2022 NDWS, WildfireSpreadTS, WSTS+, WildfireSpreadBench, TS-SatFire, Karlsson 2025, FireCast, FEDS paper (Chen 2022), Global Fire Atlas (Andela 2019), Parks 2014, Wang 2014/2017, Laurent 2019 FRP-size, FireSTARR (`spread_from_active_fire.md`); Dayan 2026 conformal risk control (`small_data_models.md` D6); GlobFire, FRY, Andela 2022 Amazon NRT, FIRED, Haley/Farguell 2018 detection likelihood (`ignition_points.md`); Parks 2015 previous burns as barriers (`fire_regime_ecology.md`); barrier stop probabilities (`fire_barrier_maps.md`); ELMFIRE and FARSITE (`fire_spread_models*.md`); FSI LFF abstract (Vikram et al.).

Reading status: **FULL 8** (FEDS source code; Ray, Nepstad & Moutinho 2005; Finney et al. 2011 FSim; Finney et al. 2011 FSPro ensembles; Luo et al. 2024 overnight fires, the preprint; Kanmani et al. 2026 FireGraphNet, main text; Funk 2026; Chakravarty 2025). **PARTIAL 5** (GOFER, Liu et al. 2024, methods; Esparza et al. 2026; Kumar et al. ICLR 2025; Yu et al. 2026 diffusion surrogate; Balch et al. 2022, from the Earth Lab summary only). **ABSTRACT or SNIPPET ONLY 3** (Podur & Wotton 2011; Allaire et al. 2020/2021; Canadian stage-of-control definitions). Plus **one new analysis of our own** (Part A). Blocked: the Balch 2022 PDF (OSU mirror DNS failure, no OA copy), the Podur 2011 full text (CSIRO paywall), Allaire 2020 (HAL bot wall), the University of Coimbra repository (TLS chain failure; I did not disable verification), the FSI FAQ and LFF pages (connection reset).

---

## Headline findings

1. **A season-held-out "fire still alive?" model is cheap and already well calibrated** (our data, Part A). Every state is "k passes silent since the last detection". The label is "the fire is detected again". The inputs are k, FRP so far, day/night, hour and passes so far. LightGBM-style boosting scores AUC 0.796, against 0.679 for k alone. Brier is 0.163, against 0.195 for k alone and 0.215 for climatology. The reliability bins sit within 1-2 points of the diagonal up to p = 0.8. Daily weather adds only +0.012 AUC (0.807).
2. **What a silent pass means depends on the time of day.** After a *night* detection and one silent pass, 40% (under 5 MW), 68% (5-15 MW) and 75% (15-50 MW) of fires are seen again. After a *day* detection, the figures are 20%, 38% and 58%. A night-detected fire is very likely still smouldering and flares at noon. [inference: the Ratapani diurnal cycle, `geostationary_fire_timing.md`]
3. **Our durations are short and depend on how events are linked.** With 1 km / 48 h linking: 3,694 fires, 58% seen on one pass only, median duration among multi-pass fires 12.1 h, p90 49 h. With 750 m / 24 h: 4,591 fires, 62% single-pass, multi-pass median 1.7 h, p90 25 h. The linking rule sets the tail, as 4p already warned. FEDS uses 0.7 km clustering, a 1 km link to the previous fire line, "inactive after 5 days" and "dead after 20 days". Those values are built for western-US megafires and would merge separate Ratapani fires. [inference]
4. **Fires end on wetter, later days, but the signal is weak.** On a fire's last day, next-day RH is 21.6% against 19.5% on continuing days; AUC 0.57 for daily RH. Rain of 2 mm or more the next day drops the chance of being seen again from 49% to 31% (n = 93). Within 3 days of rain it is 25%, against 49-55% for 4-30 dry days. Fires in March are seen again 62% of the time, in January 25% and in May 31%. **Fuel and patchiness ("runs out of litter"), not weather, likely stop most Ratapani fires.** [inference, consistent with 4j's finding that weather adds nothing]
5. **The physics of night extinction in litter fires:** experimental understorey fires in the Amazon (Ray 2005) stopped spreading below about **0.75 kPa VPD** or above about **23% litter moisture**. No spreading fire crossed both thresholds, and 93% of the fires that needed manual extinction burned at moisture below 23%. Luo 2024 finds that whether a fire burns overnight is set by slow drought codes (DMC, BUI), not by the night's humidity, and that it is predictable from daytime indices (≥70% of overnight events caught).
6. **How others verify a burn-probability map.** FSPro (Finney 2011) intersects the observed final perimeter with the probability field: 10% of fires should just reach the 0.1 contour, 60% the 0.6 contour. Its ensemble mean sizes were too large and its farthest extent too short (91 fires). FireGraphNet: raw learned 12 h probabilities are badly calibrated for most architectures (ECE 0.09-0.33). Skill is reported as a lift over a ring-distance null: 1.7-1.9× in state, 1.62× out of state, and **below the null (0.86×) in the first 12 h of a fire**. WildfireSpreadTS UQ papers report ECE 0.51 for MC-dropout, BNN and deep ensembles: none is usable without post-hoc recalibration.
7. **What this means for 4o** [inference]: fit isotonic regression per lead bucket (6/12/24/48 h) on held-out-season out-of-fold scores. Score Brier, reliability and ECE only inside a fire-centred ring (Funk's FCER, e.g. 2.5 km), plus the FSPro perimeter-contour test on the grown outlines. Report lift over persistence and over the distance ranking separately for fire age < 12 h and ≥ 12 h.

---

## Part A. Our own data: how long Ratapani fires last, and when silence means "out"

**Data.** `fire-alert-scars/alerts/viirs-*.csv`: S-NPP 2017-26, NOAA-20 2018-26, NOAA-21 2024-26, type 0 only, clipped to `ratapani_aoi.geojson`, January-June. That leaves 15,561 detections. **FULL (our data).**

**Method** (scripts in the session scratchpad, `stop_code/duration.py`, `outmodel.py`, `outmodel2.py`; the logic is short enough to redo):
- Detections are joined into one fire (union-find) when they lie within LINK m and GAP h of each other. Runs: 1,000 m / 48 h and 750 m / 24 h.
- An "overpass" is a satellite plus its acquisition time rounded to 20 min. The schedule is every pass that detected anything in the AOI.
- For every detection pass of every fire, I counted the schedule passes in the next 48 h and how many of them passed before the fire's next detection.
- State (k) means "k passes so far without seeing it"; label = the fire is seen again later.
- Model: sklearn HistGradientBoosting (200 iterations, learning rate 0.05, 15 leaves), leave-one-season-out. 33,465 state rows; base rate 0.313.
- Weather: NASA POWER daily, `ratapani/weather_power_daily.parquet` (one sanctuary-wide series).

**Durations**

| Linking rule | Fires | Single-pass | Multi-pass median dur | p90 (all) | p95 | p99 |
|---|---|---|---|---|---|---|
| 1,000 m / 48 h | 3,694 | 58.4% | 12.1 h | 25.4 h | 48.2 h | 86.4 h |
| 750 m / 24 h | 4,591 | 62.4% | 1.7 h | 13.3 h | 24.5 h | 48.2 h |

By the strongest detection (1 km / 48 h):

| Max FRP | Fires | Single-pass | Median duration | Over 24 h | Over 48 h |
|---|---|---|---|---|---|
| < 5 MW | 1,680 | 78% | 0 h | 4% | 1.0% |
| 5-15 MW | 1,661 | 46% | 0.5 h | 18% | 7.6% |
| 15-50 MW | 332 | 24% | 12.1 h | 38% | 19.6% |
| > 50 MW | 21 | 5% | 35.7 h | 76% | 38% |

**Chance the fire is seen again after k silent passes (1 km / 48 h; the 750 m / 24 h figure in brackets)**

| k silent passes | All | FRP so far < 5 MW | 5-15 MW | ≥ 15 MW |
|---|---|---|---|---|
| 0 (just seen) | 54.3% (46.3) | 42.5 | 58.0 | 73.7 |
| 1 | 41.4% (29.7) | 30.0 | 44.3 | 64.4 |
| 2 | 32.6% (20.8) | 21.5 | 35.7 | 55.3 |
| 3 | 25.4% (13.0) | 17.9 | 27.7 | 42.4 |
| 4 | 20.2% (7.8) | 15.4 | 21.6 | 33.1 |
| 6 | 14.3% (3.5) | 11.5 | 14.3 | 24.7 |

With three satellites there are about 6 passes a day in the AOI, so k = 6 is about one day. Seen again rises with the passes already seen: 42% after one pass, 52% after two, 61% after three, 69% after four, 76% after five or more. The last detection of a multi-pass fire falls at night 29.4% of the time, the same as the night share of all detections (29.5%). So fires do not visibly "end at night" any more than they burn at night.

**Held-out model (seasons left out one at a time)**

| Model | AUC | Brier |
|---|---|---|
| Climatology | 0.5 | 0.2151 |
| k only (lookup table) | 0.679 | 0.1947 |
| Fire state (k, FRP last and max, day/night, hour, passes so far) | 0.796 | 0.1630 |
| + daily weather (RH, T, wind, rain today and tomorrow, days since 2 mm rain, day of year) | 0.807 | 0.1606 |

Reliability of the fire-state model: predicted 0.066, observed 0.072; 0.145, 0.156; 0.245, 0.245; 0.448, 0.444; 0.649, 0.653; 0.745, 0.744; 0.844, 0.801; 0.926, 0.871. It is slightly over-confident only at the very top. **As a "declare out" rule:** at p < 0.05, 1,791 states are flagged and 4.6% of them were seen again; at p < 0.10, 7,588 and 7.2%; at p < 0.20, 15,029 and 11.4%.

**Caveats.** "Seen again" is not the same as "still burning": a fire can creep on undetected and die unseen, and 4p's 44% miss rate means small fires are often invisible. The label is cut off by the linking gap. The overpass schedule is built from passes that saw *something*, so quiet passes early in the season are missing [inference: this inflates the silent-pass counts a little in January]. Weather is a single daily series for the whole sanctuary.

**Concrete action for us.**
- *Thread 4 (4p stopping model) and 5 (alerts).* Ship this as the "still alive" probability attached to each alert, refreshed after every pass. Inputs: passes silent since last detection, FRP max and last, day/night of the last detection, hour, passes seen. Setting: train on 2017-24 and freeze, as 4s does. Use 750 m / 24 h linking for alerts (closer to 4j's 48 h restart window) and keep 1 km / 48 h as a sensitivity run.
- Rule for the patrol pilot: send no follow-up visit when p < 0.10 [inference: about 7% of those would still flare]; hold "monitor" between 0.10 and 0.4. Expected effect: removes about a quarter of the states from the "still burning" list at about 7% risk. [inference]
- *Thread 4 (4o).* Multiply the learned restart's "where" map by this "whether" probability. The calibrated 6/12/24/48 h burn probability is P(alive at t + h) × P(pixel | alive). This splits "where next" (4j, already strong) from "whether at all" (this model). [inference]

---

## Part B. When and why fires stop: sources

### B1. FEDS / fireatlas source code (Earth-Information-System/fireatlas, `FireConsts.py`, `FireObj.py`, main branch, fetched 15 Oct 2026). **FULL** (the constants and state logic)
https://github.com/Earth-Information-System/fireatlas

What it shows (exact defaults):
- `maxoffdays = 5`: "fire becomes inactive after this number of consecutive days without active fire detection".
- `limoffdays = 20`: a fire inactive for more than 5 but at most 20 days is a "sleeper" that may reactivate; after 20 days it is "dead" (`isdead`).
- `isburning` means a detection in the current 12 h step.
- `CONNECTIVITY_CLUSTER_KM = 0.7` (initial clustering); `CONNECTIVITY_SLEEPER_KM = 1` (a new pixel within 1 km of a sleeper's last fire line wakes it). The California fire-type table sets connectivity at 1 km (other, urban, agriculture), 2.5 km (wild forest) and 5 km (managed forest, shrub).
- Shape parameters: `VIIRSbuf = 187.5` m (half a pixel), alpha hull `valpha = 1000` m, fire-line pixel buffer `fpbuffer = 200` m, `flbuffer = 500` m, interior/exterior `extbuffer = 1000` m, VIIRS pixel area 0.141 km².
- Static flaring sources are masked with a 1 km buffer.

So operational FEDS declares nothing "out". It has three states (burning, active, sleeper) and kills a fire only after 20 days of silence.

Concrete action for us (thread 4/5): copy the three-state design, with times scaled to our fires. [inference from Part A: at 750 m / 24 h, 96% of silences of 6 passes (about 1 day) are final]
- Burning: seen this pass.
- Active: p_alive ≥ 0.1 from the Part A model.
- Sleeper: p_alive < 0.1 but less than 48 h since the last detection; a new detection within 1 km re-attaches it to the same fire, as FEDS does.
- Dead: more than 48 h silent.

Expected effect: no double-counted "new" fires when a sleeper flares, and the restart model (4j) keeps its history. [inference]

### B2. Ray, Nepstad & Moutinho 2005, "Micrometeorological and canopy controls of fire susceptibility in a forested Amazon landscape", *Ecological Applications* 15(5):1664-1678. **FULL**
https://www.woodwellclimate.org/wp-content/uploads/2015/09/RayetalEcolAppl.05.pdf

What it shows:
- 300 experimental 1 m litter fires (152 spreading, 148 dying), lit at 13:00-16:00 in an 8-year regrowth forest, a logged and burned forest, and a mature forest, Sept-Nov 2002.
- Spread rate (FSR) is fit by VPD, recent rain, wind and LAI, which explain 57%. The single fits are ln(FSR + 1) = 0.018 + 0.087·VPD (R² 0.50) and FSR = 0.043 + 0.838·exp(-0.107·LMC) (R² 0.45).
- **Break points: VPD about 0.75 kPa and litter moisture (LMC) about 23%.** No spreading fire was below 0.75 kPa and above 23% at once. 93% (141/152) of the fires that needed manual extinction burned at LMC under 23%.
- Mean FSR is 0.20 m/min at VPD 0.76-3.0 kPa, against 0.05 m/min at 0-0.75 kPa. It is 5× higher at LMC 5-23% than above 23%.
- Mean FSR by forest: 0.257 (regrowth), 0.185 (logged/burned), 0.067 m/min (mature); maximum 0.93 m/min. Flame heights 20-38 cm.
- Reduced logistic model from canopy height, LAI and weighted rain (Eq. 2) predicts 73% of spread/die outcomes; the full model (VPD, LMC, litter mass, height) about 78%. Litter mass mattered as a proxy for fuel continuity.
- Earlier Amazon work: 15% litter moisture used as the flammability threshold. Moist forest stays resistant about 2 weeks after 1-2 cm of rain, large gaps 4-5 days.

Concrete action for us (thread 4, stopping and night survival):
- Build an hourly "below threshold" feature from ERA5-Land hourly T and dewpoint: hours with VPD under 0.75 kPa in the night after a detection, and the minimum night VPD.
- Ratapani in March-April rarely drops below about 1 kPa at night [inference from NASA POWER daily RH of about 20% and 29 °C; check hourly]. If so, the feature will be near-constant in peak season, which would explain why weather adds little in Part A and 4j. Its value is in January-February and after rain.
- Also take 23% litter moisture as the extinction cut in the fuel-moisture code the spread model uses (Rothermel litter Mx is often 25-30%).

### B3. Luo, Wang, de Jong & Flannigan 2024, "Drought triggers and sustains overnight fires in North America", *Nature* (2024, doi 10.1038/s41586-024-07028-5). **FULL** (Research Square preprint rs-2774294)

What it shows:
- GOES-R hourly detections plus Canadian and US perimeter records, 2017-2020, fires ≥ 1,000 ha (about 1,600 fires).
- An **overnight burning event (OBE)** = fire detected in *every* night-time hour of a day.
- 20% (n = 330) of large fires had one; 1,084 OBEs, 2.2% of all fire-nights.
- 13% of OBE fires held over half the OBEs, and 67% of OBEs were followed by another the next night (persistence).
- 52% of OBE fires had one within 2 days of ignition, 31% on the ignition day.
- OBE fires were 6.6× larger (31,071 ha against 4,682 ha).
- The drivers are slow drought codes, DMC or BUI, top in every biome-season random forest. In temperate-mountain fall, DMC was 255.8 against 101.6 (+152%) and BUI 279.3 against 129.1 (+116%). Fast weather (night RH, T) ranked low, and the day-night *range* was no smaller on OBE nights.
- Daytime logistic models caught at least 70% of OBEs (82.6% best).

Concrete action for us (thread 4 stopping model; thread 1 weather features):
- Add slow dryness to the Part A model: ERA5-derived DMC and DC (or KBDI) and days since rain, not just same-day RH. The analogue of an OBE for us is a fire detected on a night pass *and* the next day pass.
- Settings: label = "detected at night and again within 12 h"; inputs = noon DMC/BUI/days since rain, day of season, FRP. Expected effect: small but real for the 12 h and 24 h survival heads [inference]; Part A's +0.012 AUC from crude daily weather is a floor.

### B4. Balch et al. 2022, "Warming weakens the night-time barrier to global fire", *Nature* 602:442-448. **PARTIAL** (Earth Lab summary and abstract; the PDF was not reachable)
https://earthlab.colorado.edu/blog/warming-weakens-night-time-barrier-global-fire

What it shows:
- Per land cover, a VPD threshold (VPDt) below which fire detections are very rare. It was fit on 81,809 FIRED events (2017-2020) with GOES-16 detections about every 15 min.
- Thresholds are highest in croplands and lowest in temperate forests.
- 16.3% of burnable area worldwide had at least 25% of detections at night (2003-2020); temperate evergreen needleleaf forest reached 38%.
- Flammable night hours rose 110 h a year (36%); night FRP rose 7.2%.

Concrete action for us (thread 4/5):
- Ratapani has **29.5% night detections** (our data). That puts it in the top sixth of burnable land and confirms night burning is normal here, not an exception. A night silent pass is therefore informative (Part A).
- Fit our own VPDt: logistic of "pixel-pass has a detection" against hourly VPD at pass time, using every pass over known-burning fires (4p's 2,045 passes).
- Expected use: one more input for the alive model, plus a sanity check that night VPD rarely crosses the threshold in peak season. [inference]

### B5. Finney, McHugh, Grenfell, Riley & Short 2011, "A simulation of probabilistic wildfire risk components for the continental United States" (FSim), *SERRA* 25:973-1000. **FULL**
https://research.fs.usda.gov/download/treesearch/39312.pdf

What it shows, on how a burn-probability system decides when fires stop:
- Fires stop by **two mechanisms only**: a statistical *containment probability*, and a *season-ending event* (consecutive days below the lowest spread percentile of ERC).
- Containment was more likely (1) during slow growth relative to the average daily change, (2) as duration increases, and (3) in non-timber fuels. It is applied as a probability per interval of daily growth rate that stochastically ends growth.
- Spread is not simulated on days with ERC(G) below the 80th percentile. The burn period is fixed at **1, 3 and 5 h** for the 80th, 90th and 97th ERC percentiles.
- 10,000-50,000 simulated seasons; burn probability at 270 m spans 10⁻⁵ to 10⁻².
- Validation: bootstrap confidence intervals on mean burn probability per planning unit, plus fire-size distributions per region.
- Containment "reduc[ed] the sizes of fires by censoring growth after quiescent periods", which steepened the size distribution toward observed.

Concrete action for us (thread 4):
- The stopping model should be a **hazard on recent growth**: P(stop in next step | growth in last step, age, fuel type). A slow step means likely to stop; Ratapani's "suppression" is fuel running out. Inputs: grown area in the last pass interval (from 4j's footprints), fire age, fuel load and teak share, FRP trend.
- Also take FSim's "no spread below the 80th percentile dryness" as a gate in the physics restart. Expected effect: shorter, right-sized simulated fires; it reproduces the observed size distribution in FSim. [inference that it transfers]

### B6. Podur & Wotton 2011, "Defining fire spread event days for fire-growth modelling", *IJWF* 20:497-507. **ABSTRACT ONLY** (CSIRO paywall; the 2010 slide deck returned 403)
https://doi.org/10.1071/WF09001

What it shows:
- Most growth happens on a few "spread event" days. Fires otherwise creep or stop.
- FBP-based models over-predicted spread on non-spread days.
- Spread-event probability comes from a logistic on ISI (from the 2010 slides, via a search snippet). Extinguishment was tied to rain; MODIS hotspots were the data.

Concrete action for us (thread 4): a per-fire-day classifier, "spread day" against "creep/stop day", with the label from 4j's grown area per day (top tercile = spread day). It would gate the restart model's area (calibration of the expected area). Gain: probably modest, since 4j says weather adds little [inference].

### B7. Operational "fire out" definitions. **PARTIAL / SNIPPETS**
- **Canada (CIFFC, CWFIS):** stage of control OC (Out of Control), BH (Being Held), UC (Under Control), EX (Out). BC Wildfire Service: "Only when the fire has been completely extinguished can it be declared that the fire is Out". Being Held = "not likely to spread beyond existent or predetermined boundaries" (https://glossary.ciffc.ca, BCWS outlook PDF).
- **US (NIFC/NWCG):** contained, controlled and out are ground declarations by incident staff. The NWCG glossary page returned 503 from here.
- **Satellite systems:** FEDS (B1) uses 5-day inactive and 20-day dead. FSI LFF (abstract): a buffer around the pixel clump is "redrawn ... until it is active", with no published silence rule. GOFER (B8) ends a fire at "the last GOES detection within a few days of previous detections", near the official final size.

Concrete action for us (thread 5): no agency declares "out" from satellites. Our alert should therefore say "likely out (p = x)", never "out". It should map onto FSI's own field step: a guard visit closes the alert. That is the one place a ground "out" exists, and those closures, when the field-check thread gets them, are the only labels that can recalibrate the Part A model to "really out". [inference]

### B8. Liu et al. 2024, "Systematically tracking the hourly progression of large wildfires using GOES satellite observations" (GOFER), *ESSD* 16:1395-1424. **PARTIAL** (methods and evaluation read)
https://essd.copernicus.org/articles/16/1395/2024/ · data https://doi.org/10.5281/zenodo.8327264

What it shows:
- Hourly perimeters for 28 large California fires (2019-2021) from GOES-16/17.
- GOES confidence is smoothed with a dynamic kernel. The confidence threshold was optimised at **0.95** and the parallax factor at 0.85, from IoU with MTBS on the 10 largest 2020 fires.
- Early perimeters are rescaled, with the minimum scaling at 0.1.
- IoU 0.77 against FRAP (FEDS against FRAP: 0.83).
- Two fire-line definitions:
  - *Concurrent* line: perimeter segments touching this hour's detections, output at confidence 0.05-0.9.
  - *Retrospective* line: segments that grew by the next hour.
- An hour with no line is "dormant", filled from the nearest active lines.

Concrete action for us (thread 4): use the retrospective-line idea to label stopping per *segment*. For each grown-outline edge at pass t, did the next pass's growth start from it? That gives "edge stops" against "edge runs" labels for a fire-stopping model at 20 m, with barriers, fuel and slope as inputs. GOES does not see India; GK2A (`geostationary_fire_timing.md`) could play the hourly role at 2 km for large fires only. [inference]

---

## Part C. Calibrated probabilistic spread forecasts: sources

### C1. Finney, Grenfell, McHugh, Seli, Trethewey, Stratton & Brittain 2011, "A method for ensemble wildland fire simulation" (FSPro), *Environ. Model. Assess.* 16:153-167. **FULL**
https://www.fs.usda.gov/rm/pubs_other/rmrs_2011_finney_m001.pdf

What it shows:
- Ensembles come from an ERC time-series model (seasonal trend + AR residuals), forecasts for days 1-7 appended, and climatological wind joint distributions. A 7-day run has 2,457 possible sequences: 5 moisture categories × 49 wind states.
- The season-end date is the day ERC falls below z* and does not rise again. Its distribution gives P(season over by day d).
- **Verification on 91 operational fires (2007-09)**:
  - (i) Observed size against mean member size.
  - (ii) Overlay the final perimeter on the probability grid and read the probability at every vertex. The *minimum* (100th percentile) and the 90th-percentile vertex probabilities are tallied in deciles: ideally, 10% of fires just reach the 0.1 contour.
- Result: **ensemble average sizes were consistently larger than actual, yet the farthest extent burned was underestimated** (100th-percentile test). Agreement was better at the 90th percentile.
- 256, 1,024 and 4,096 members were compared by pixel CV: it is lowest above p 0.9 and highest in the tails below 0.1. 2D spread beats 1D transects (1D always lower).
- The sample excluded fires extinguished early, which is a known bias.

Concrete action for us (thread 4, 4o):
- Add the FSPro perimeter-contour reliability test to the fair table. For each fire and each lead (6/12/24/48 h), take the grown-outline (4k) vertices of the new growth, read the forecast probability at each, and tally the minimum and 90th-percentile vertex probability by decile. Plot against the diagonal.
- It complements pixel reliability: it checks whether the *extent* is right, the failure FSPro had. Effort: half a day on top of `calib.py`. Expected: it will show 4j's learned map under-predicting rare long runs, like FSPro. [inference]

### C2. Kanmani, Esparza & Mostafavi 2026, "FireGraphNet: sub-daily wildfire spread prediction with directed graph neural networks", arXiv 2610.19191. **FULL** (main text, tables)

What it shows:
- 12 h growth posed as node classification on H3 resolution-8 cells (0.74 km²) within 5 rings of the FEDS front.
- Directed edges carry wind alignment cos(θ − θwind), elevation difference, fuel continuity and barrier flags. Cells carry 82 features: 64 AlphaEarth embedding dimensions, terrain, HRRR weather, LANDFIRE fuels, fire history, day/night flag.
- In-state sealed test: 512,742 candidates, 8,455 positives (prevalence 0.0165).
  - GINE: PR-AUC 0.0710, Brier 0.035, ECE 0.093.
  - Other graph variants: PR-AUC 0.062-0.068, ECE 0.147-0.220.
  - Cell-only MLP: 0.0394, equal to the **ring-distance null 0.0369**.
  - Wind-slope heuristic: 0.018.
  - ResU-Net trained on the same candidates: PR-AUC 0.077 but ECE 0.33, Brier 6.9× worse.
  - ResU-Net trained on the full burned mask: 0.023.
- **Out of state: lift 1.62× over the ring null (MLP 1.06×).**
- By fire age: lift 1.95× at 0-48 h of track age, 1.02× at 240-480 h, 1.46× beyond. **The initial window (< 12 h) is 0.86×, worse than distance.**
- Skill falls with track age (ρ -0.41 to -0.47). All probabilities were raw (uncalibrated), and the authors say they should be calibrated before operational trials.

Concrete action for us (thread 4):
- (a) Score 4j and 4o against a **ring-distance null** and report **lift** as well as hits. Stratify by fire age under 12 h and over 12 h. FireGraphNet's sub-12 h loss to distance matches our "first pass" case (4i/4j after pass 1: 72.5 → 86.0 is already better than that).
- (b) Train only on candidate cells outside the current footprint ("new growth"). The full-mask target collapses skill (0.023 against 0.077).
- (c) Expect learned rankers to be miscalibrated even when they rank well, so recalibrate (C5).
- An edge-based graph is a possible later upgrade; our 4j already gets the "distances and lead" gain that FireGraphNet credits to message passing. [inference]

### C3. Funk 2026, "Boundary-aware uncertainty quantification for wildfire spread prediction", arXiv 2605.03148. **FULL** (short paper). Code: https://github.com/jonasvilhofunk/WildfireUQ-FCER

What it shows:
- **Fire-Centred Evaluation Region (FCER)**: score only inside the true fire mask dilated by radius r, and sweep r. The anchor is r = average surface distance (ASD).
- WildfireSpreadTS, UTAE, 3-member ensemble: AP 0.50 ± 0.08, ASD 1.39 km, Brier 0.161, NLL 0.512 at the anchor.
- A distilled single-pass student (DUDES) keeps Brier and NLL and ranks errors better: AUROC 0.629 against 0.558, AUPRC 0.307 against 0.249 (random 0.205). The ensemble is better only within 750 m of the edge.
- It criticises Chakravarty's sub-pixel "20-60 m" buffers at 375 m resolution.

Concrete action for us (thread 4, 4o): report Brier, ECE and reliability inside rings of 0.5, 1, 2.5 and 5 km around the known fire, not over the whole 2.5 km lattice. Whole-domain scores are dominated by easy far-away zeros. Settings: the same lattice as `calib.py`, with masks by distance to the last detection. Effort: low.

### C4. Chakravarty 2025, "Spatial uncertainty quantification in wildfire forecasting for climate-resilient emergency planning", arXiv 2510.09666 (NeurIPS 2025 CCAI workshop). **FULL**

What it shows:
- WildfireSpreadTS (607 fires, 13,607 daily images), UTAE (about 1.1 M parameters), 12 folds.
- **Persistence AP 0.191 ± 0.063.** Vegetation + active fire AP 0.378; weather + fire 0.323; all features 0.319 (adding weather lowered skill).
- Calibration (ECE / Brier / NLL): MC-dropout 0.536 / 0.294 / 0.805; BNN 0.525 / 0.283 / 0.794; deep ensemble 0.512 / 0.265 / 0.731.
- An ECE above 0.5 is grossly miscalibrated [inference: from weighted BCE training], whatever the UQ method.

Concrete action for us (thread 4): if 4o's lattice model is trained with class weights or focal loss, its raw output will be biased the same way. Train unweighted for the probability head, or recalibrate. Also, "weather hurts" replicates our 4j ablation on another continent.

### C5. Esparza, Ayanzadeh, Mousavi & Mostafavi 2026, "Modular deep learning mechanisms for auditable next-day wildfire spread prediction", arXiv 2609.17763. **PARTIAL** (related work, protocol, calibration table)

What it shows:
- NDWS best F1 is about 0.42 (FireSenseNet 0.4176 / AUC-PR 0.3435; Huot's original 0.359 / 0.284; this paper's ensemble F1 0.4292 / AUC-PR 0.3790).
- **Protocol traps**:
  - The "Both Days" target, which copies the previous-day mask into the label, inflated F1 by 44-50% with no model change (a claimed 0.702).
  - FireSenseNet chose its threshold on the test set.
- Calibration on NDWS is fine at the pixel level (ECE 0.023-0.034, Brier 0.013-0.016), because prevalence is low. Retrieval and ensembles move ECE by ±0.003.

Concrete action for us (thread 4, the audit): add both traps to the fair-table checklist. Never let the current footprint into the target; pick thresholds on the training seasons only. Pixel ECE near 0.03 on a low-prevalence lattice says little, so use the rings (C3) and the perimeter test (C1).

### C6. Kumar, Kang, Chakraborty & Mukhopadhyay 2025, "Has the deep neural network learned the stochastic process? An evaluation viewpoint", ICLR 2025, arXiv 2402.15163. **PARTIAL** (abstract, sections 1-2). Code: https://github.com/harshitk11/evaluate_stochastic_process

What it shows: with one observed realisation of a stochastic spread, threshold metrics and MSE reward copying that realisation. The authors argue that **ECE is the metric that tests whether the model learned the process probabilities**, shown on a synthetic forest-fire cellular automaton and on NDWS.

Concrete action for us (thread 4): it argues for reporting ECE next to hits and Sorensen when choosing between the learned restart and the physics ensemble. A model can lose on Sorensen and still be the better probability map.

### C7. Yu, Ghosh, Finn, Arcucci, Bocquet & Cheng 2026, "A probabilistic approach to wildfire spread prediction using a denoising diffusion surrogate model", arXiv 2507.00761 v2. **PARTIAL** (abstract, method, headline results)

What it shows:
- A conditional diffusion model trained on a probabilistic cellular automaton (Chimney 2016 and Ferguson 2018 landscapes).
- The ensemble of samples beats the deterministic regression surrogate: MSE cut by 69.3%, FID 49.0 against 165.9, higher "hit rate".
- Synthetic truth only.

Concrete action for us: none now. It is relevant only if we later want sample-based ensembles (many plausible scars) instead of a marginal probability map. The marginal map is what 4o needs. [inference]

### C8. Allaire, Filippi & Mallet 2020/2021 (IJWF 29:160, "Generation and evaluation of an ensemble of wildland fire simulations"; Appl. Math. Modelling 2021, posterior UQ). **ABSTRACT ONLY** (HAL bot wall)

What it shows:
- Monte Carlo ForeFire ensembles on 7 Corsican fires (2017-18), scored with meteorological probabilistic scores.
- 2021: calibrated inputs drawn from a posterior; the pseudo-likelihood is the Wasserstein distance between simulated and observed burned areas, with a GP emulator and MCMC (about 1 day on 8 cores).
- The calibrated ensembles favour lower rate of spread and narrower wind direction. They reduce over-prediction while still covering the observed area.

Concrete action for us (thread 4): if the physics ensemble stays in the comparison, calibrate its spread-rate multiplier and wind spread by a Wasserstein or Sorensen distance to the 2017-24 grown outlines, rather than by hand (4b did a grid search). The learned restart already wins, so this is low priority.

---

## Part D. Recipe for 4o and 4p, combining the above [inference unless stated]

1. **Two factors.** P(pixel burns within h) = P(fire alive through h) × P(pixel reached | alive, h). The first is the Part A model (one row per fire and pass). The second is 4j's next-pass and end heads, conditioned on lead.
2. **Calibration.**
   - Fit isotonic regression per lead bucket (≤ 6, 6-12, 12-24, 24-48 h) on leave-one-season-out out-of-fold scores. Platt (logistic) is the fallback when a bucket has fewer than about 500 positives.
   - Freeze the calibration on 2017-24 and check it once on 2025-26 (the 4s protocol).
   - Conformal risk control (Dayan, `small_data_models.md` D6) is optional, for a guaranteed miss rate on patrol maps: for example, the smallest area holding 90% of next-pass detections.
3. **Scores.**
   - Brier with its reliability/resolution decomposition, ECE with 10 equal-count bins, reliability diagrams.
   - All of these inside rings of 0.5/1/2.5/5 km (C3).
   - The FSPro perimeter-vertex decile test on new growth of the grown outlines (C1).
   - Lift over (i) persistence (475 m disc), (ii) the distance ranking, and (iii) the latest-pass circle; stratified by fire age under and over 12 h (C2) and by day/night of the last pass (Part A).
4. **Labels.** New growth only (C2, C5). Thresholds and isotonic maps fit on training seasons only (C5).
5. **The stop model** (4p) as a hazard. Inputs:
   - Silent passes, FRP max and last, day/night, hour, passes seen (Part A).
   - Grown area in the last interval (FSim containment logic, B5).
   - Fuel left inside 500 m (fuel-map thread), the share of ring pixels already burned this season, distance to the nearest barrier (`fire_barrier_maps.md`).
   - Days since rain and DMC/BUI (B3); hours below 0.75 kPa VPD that night (B2).
   - Expected: AUC 0.80 from the fire state alone, perhaps 0.82-0.85 with fuel and edge features [inference: weather gave +0.01; fuel exhaustion is the more likely cause of stopping].

---

## Datasets and code

| Item | What | Where | Access | Use for us |
|---|---|---|---|---|
| fireatlas (FEDS) code | VIIRS 12 h fire tracking, active/sleeper/dead states | github.com/Earth-Information-System/fireatlas | Open (pip/GitHub) | Copy the state machine (B1); run on our points as a cross-check of event linking |
| FEDS NRT layers | Perimeters, active segments, new pixels (US/Canada) | gis.earthdata.nasa.gov/image/rest/services/FireTracking | Open | Format template only |
| GOFER | Hourly perimeters, fire lines, spread rates, 28 CA fires | doi 10.5281/zenodo.8327264 | Open | Concurrent/retrospective line definitions (B8) |
| WildfireUQ-FCER | Ring-based UQ evaluation code | github.com/jonasvilhofunk/WildfireUQ-FCER | Open | Scoring masks for 4o (C3) |
| evaluate_stochastic_process | ECE for stochastic-process fidelity | github.com/harshitk11/evaluate_stochastic_process | Open | Metric code (C6) |
| WildfireSpreadTS | 607 US fires, daily 375 m | github.com/SebastianGer/WildfireSpreadTS, Zenodo 8006177 | CC-BY | Already noted; persistence AP 0.191 for reference |
| FSim/FSPro outputs | US burn probability 270 m | fs.usda.gov/rds RDS-2016-0034 | Open | Method template only |
| Our alive-model scripts | `duration.py` (linking, durations, silent-pass table), `outmodel.py` / `outmodel2.py` (season-held-out model, reliability, weather) | session scratchpad `stop_code/` (not copied to the project, per this round's write rule) | n/a | Re-run in `fsi/scouting/code/stopping/` if adopted |
| ERA5-Land hourly T and dewpoint | Night VPD, DMC/BUI inputs | Earth Engine, `ratapani/EE_EXPORT_BRIEF_ERA5LAND.md` | Open | B2/B3 features |

---

## Ranked action list (gain, effort)

1. **Ship the "still alive" probability with each alert and in 4p** (Part A model). Inputs: silent passes, FRP, day/night, hour, passes seen. Linking 750 m / 24 h; isotonic on top; freeze on 2017-24. *Gain: high* for patrols: a calibrated "likely out" with about 7% flare-back at p < 0.1, held-out AUC 0.80. *Effort: low* (1 day; the code exists).
2. **Make 4o two-factor and isotonic per lead bucket** (Part D 1-2): P(alive) × P(reached | alive). *Gain: high*: calibrated 6-48 h maps that shrink correctly as fires die, which the restart model alone cannot do. *Effort: medium* (2 days).
3. **Score 4o in rings plus the FSPro perimeter-vertex test, with lift over the ring-distance null by fire age** (C1, C2, C3). *Gain: medium-high* (honest, comparable numbers; shows the extent bias). *Effort: low* (half a day).
4. **Add slow dryness (DMC/BUI, days since rain) and night-VPD hours to the alive/stop model** (B2, B3, B4). *Gain: low-medium* (+0.01-0.03 AUC expected; larger in January-February and after rain). *Effort: medium* (ERA5-Land hourly export, then FWI codes).
5. **Stop model as a hazard on recent growth, fuel left and barrier distance, with labels from segment-level "edge stopped / edge ran"** (B5, B8). *Gain: medium* (the stopping map the patrol pilot needs for "where to cut a line"). *Effort: medium-high* (3 days; needs per-pass grown footprints from 4j/4k).
6. **Three-state tracking (burning, active, sleeper, then dead at 48 h) for the live ledger** (B1). *Gain: medium* (fewer duplicate "new fire" alerts, continuous history for 4j). *Effort: low.*
7. **Audit checklist additions**: no previous footprint in targets; thresholds from training seasons only; ECE next to hits (C5, C6). *Gain: protects every number. Effort: trivial.*
8. Physics-ensemble calibration by Wasserstein/Sorensen (C8) and diffusion ensembles (C7). *Gain: low* (the learned restart already wins). *Effort: high.* Defer.
