# Fresh review of the Ratapani fuel load map (15 Oct 2026)

Reviewer: a separate Claude thread, asked by Akkshay to check the "High-resolution fuel load map" thread with fresh eyes. Every number below was either re-computed from the files in `fuel-map/ratapani/` (marked **re-checked**), read from code (marked **from code**), or taken from the thread's own text without a way to re-run it (marked **not re-runnable**). Nothing in `fuel-map/ratapani/` was edited.

A few words used throughout:
- **Fuel load**: dry weight of burnable material lying on the forest floor (fallen leaves, twigs, dry grass), in tonnes per hectare (t/ha). FSI uses g/ft²; 1 t/ha = 9.29 g/ft². FSI's "Low" class is under 20 g/ft² = under 2.15 t/ha.
- **Raster**: a map made of square pixels, each holding one number.
- **Rothermel**: the standard physics formula that turns fuel, moisture, wind and slope into a fire's forward speed.
- **Inversion / back-solving**: guessing the fuel by asking "what fuel would make the simulated fire match the real one?"

## The answer in five lines

1. **There is a 10 m fuel map, but it is mostly a canopy-cover map multiplied by one borrowed number.** 86% of the pixel-to-pixel variation is explained by canopy cover alone (re-checked). Its absolute level comes from ten hand-picked constants, none measured in Ratapani.
2. **The headline map numbers reproduce** (mean 1.46 t/ha, 78% Low / 22% Moderate). **The fire-based fuel numbers mostly do not hold up**: one table in the README does not match what its own code wrote, the fires used were the burn-label rasters that the project later found are 2-3x too small, and fuel cannot be separated from wind, bed looseness and model error using fire speed alone.
3. **The thread drifted.** The map was done in about two hours on 14 Oct. The most recent ~10 hours went into fire timing, VIIRS geometry and ignition back-simulation, which belong to the spread work. The map itself was never updated with anything learned: it still says 1.46 t/ha while the spread model runs at 3.0 t/ha.
4. **Most drift was asked for**, by Akkshay or the coordinator, one step at a time. Each step was reasonable; together they moved the thread off its aim and no one pulled it back.
5. **A credible 10 m map without field plots is not possible as an absolute number.** What is possible is an honest *relative* map (more vs less fuel, ±40-50% absolute), built from litterfall physics with stated uncertainty, plus a cheap path to calibration (FSI's plot data, or 30-60 floor samples) when it opens. The ranked plan is in section 5.

## 1. What the fuel map actually is today

All files are in `fuel-map/ratapani/`. Rasters are 10 m (or 20 m for the Rothermel stacks), 7,544 x 3,348 pixels, covering the 775 km² of WorldCover tree, shrub and grass land inside the Ratapani AOI.

### 1a. The files

| File | What is in it | How it was made |
|---|---|---|
| `fuel_continuous_peak_10m.tif` | April-peak fuel per pixel, g/ft² (x0.1) | Formula in `scripts/build_v2.py` (below), burn history from all seasons 2017-26. Says itself: not for model training. |
| `fuel_season_<2018..2026>_peak_10m.tif` | Same, using only seasons before each year | Same formula. The only version safe as a model input. |
| `fuel_fsi_strata_10m.tif` | FSI-style 16 groups (canopy class x slope class), one value each | **Each group's value is the average of the continuous map inside it.** Not independent. |
| `fuel_fsi_strata_fsicanopy_10m.tif` | Same groups on FSI's own 2023 canopy map | Group values again from our continuous map. |
| `canopy_cover_10m.tif`, `canopy_density_1ha_10m.tif` | Tree canopy % | Sentinel-2 model trained on Meta 1 m tree heights (bad strip in the west replaced). Per-pixel R² 0.46, 1 ha R² 0.76 (thread's figures, not re-runnable). |
| `burn_frequency_2017_2026_10m.tif` | Share of seasons burned, smoothed to 60 m and shrunk toward 20% | From `research/ratapani-burn-labels/rasters/`, the burn rasters the project later found are 2-3x too small. |
| `leaf_fall_fraction_10m.tif` | Share of leaf drop done by end of Dec..Apr | Sentinel-2 NDVI time series, one season. |
| `teak_probability_10m.tif`, `teak_share_cells.csv` | Chance a pixel is teak-mixed | LightGBM on Sentinel-2 phenology, trained on a 2005-10 national vegetation map (60 m polygons). |
| `cover_phenology_10m.tif` | 5 rule-based cover classes | NDVI thresholds; photo check showed the "shrub" class was a wheat field. |
| `fsi_fcm_2023_10m.tif`, `fsi_ftm_2021_10m.tif`, `fsi_fire_prone_2021_10m.tif` | FSI's canopy, forest type and fire-prone maps | Decoded from coloured map images on the Van Agni portal. Legend names are inferred from colours. |
| `rothermel/`, `rothermel/loosebed/`, `rothermel/teakmix/` | 8-band fuel stacks for the spread model | Same loads, different assumed bed looseness. Loose bed is the spread default. |
| `fuel_cells_static.csv`, `fuel_cells_season.csv` | Map averaged to the 3,614 x 500 m scoring cells | |
| `inversion/` | Fuel back-solved from fire size, fire energy and pass-to-pass speed | See section 2. |
| `timing/` | Mid-fire snapshots, VIIRS footprint test, per-fire speed fits | Fire behaviour, not fuel mapping. |
| `ignition/ignition_fits.csv` | Back-simulated start time and place for 788 fires | Fire behaviour. **The script that made it is not in the shared folder.** |

### 1b. The formula behind the map (from code)

```
floor (t/ha) = 0.5 x 5.0 x cover_eff x shed_rel x freq_factor x slope_mult
grass (t/ha) = grass_by_years_since_burn x (1 - cover) x greenness_vigour x slope_mult
```

| Ingredient | Value | Source type |
|---|---|---|
| Floor = 0.5 x annual litterfall | 0.5 | **Literature ratio** (Jhariya 2017, Bhoramdeo, Chhattisgarh; ratio 0.48-0.57 in its tables) |
| Annual litterfall, closed forest | 5.0 t/ha/yr | **Judgement call** between literature values 3.3 (Satpura teak, leaf only, abstract only), 4.2 (Achanakmar) and 7.6 (Bhoramdeo unburnt) |
| cover_eff = canopy / 0.7, capped at 1 | 0.7 | **Assumption** |
| shed_rel = this pixel's NDVI drop / Ratapani mean, clipped 0.5-1.5 | | **Satellite-measured**, relative only |
| Burn-frequency factor 1.0 / 0.88 / 0.76 / 0.63 | | **Literature** (Jhariya Table 2), applied to burn counts from the undersized rasters |
| Slope multipliers 1 / 0.95 / 0.85 / 0.75 | | **Assumption**, no source |
| Grass 0.6 t/ha first year, +0.9 t/ha per year, cap 2.5 | | **Literature** from Mudumalai, Tamil Nadu (Mondal & Sukumar 2016), 1,000 km away |
| Monthly build-up Jan 0.5 / Feb 0.7 / Mar 0.88 / Apr 1.0 | | **Literature** (Saha 2002, Gadchiroli, fresh weight); January is a guess |
| Rothermel bed density, moisture of extinction, size split | 2.5-6 kg/m³, 0.25, 75/25 | Literature defaults plus one fitted choice (loose bed) |

So: **canopy cover and leaf drop are measured from space; every number that turns them into tonnes is borrowed or assumed.** Nothing in the map was measured on Ratapani's floor.

### 1c. What the map says (re-checked)

| Measure | Thread's claim | Re-checked | Verdict |
|---|---|---|---|
| Mean fuel | 1.46 t/ha | 1.465 t/ha | Holds |
| FSI classes | 78% Low / 22% Moderate | 78.0% / 22.0%, 0% High | Holds |
| FSI-strata version | 95.5% Low | 95.5% | Holds, but **circular**: the strata take their values from this same map |
| FSI-canopy strata | 100% Low | 100% | Holds, same circularity |
| Highest value anywhere | (not stated) | **3.08 t/ha** | The formula caps out here. It can never show "High" (over 4.3 t/ha), by construction. |
| By canopy class | (not stated) | under 10% cover: 0.38 t/ha (21% of area); 10-40%: 1.22; 40-70%: 2.02; over 70%: 2.14 | |
| How much is canopy cover | (not stated) | **86%** of pixel variance explained by canopy cover alone; 88% with burn frequency added | It is a canopy map in disguise |
| Real detail | "30 m holds 98%, 100 m 88%" | 30 m blocks keep 95%, 100 m 82%, 300 m 65% | Roughly holds. True detail is ~30 m, not 10 m. |
| Spread model's load | 3.0 t/ha | Published `rothermel/loosebed` layers still average **1.47 t/ha** | The map was never updated to what the spread model actually uses |

Two internal contradictions stand out:
- **The map sits below its own sources.** Jhariya's measured summer floor is 2.30 t/ha in a stand that burns every year and 3.95 t/ha in one that never burns. The map gives dense forest 2.0-2.1 t/ha on average, because it picked 5.0 rather than Jhariya's 7.6 t/ha litterfall and then also applied the burn-frequency cut. The later "discovery" from fires that real loads are ~3 t/ha largely re-finds the literature value the map chose not to use.
- **Unit mixing.** FSI weighs oven-dry litter. Saha 2002 and Mondal & Sukumar 2016 weighed litter fresh. The thread used both without a conversion (Saha's own note suggests ~10-15% lower when dry).

## 2. Which claims hold, which don't, which can't be checked

| Claim | Status | Why |
|---|---|---|
| Mean 1.46 t/ha, 78% Low | **Holds** (re-checked) | But it is the output of borrowed constants, so "holds" means "the arithmetic is right", not "the fuel is right". |
| FSI-strata map matches FSI's ~96-99% Low | **Holds but means nothing** | The strata values are averages of our own map. Agreement with FSI is built in, not tested. |
| Effective detail ~30 m | **Holds roughly** (95% kept at 30 m vs 98% claimed) | |
| Fuel adds nothing to the 2-day model (29.0 / 28.8 vs 29.1 control) | **Plausible, not re-run** | Test design is sound (season maps use prior burns only). It needs the pipeline's scoring code. |
| Teak map AUC 0.81 | **Number is real-looking but means less than it sounds; not re-runnable** | The inputs live in a `/tmp` folder that no longer exists. The 0.81 measures agreement with a 2005-10 map drawn as coarse 60 m polygons, not with real teak. Cell-level agreement with that map is only r = 0.52. "Teak vs other" is not a validated map. |
| Inversion loads per class (teak 1.1-2.5, other deciduous 1.1-2.9, grass 1.0-2.4 t/ha) | **Does not hold** | (1) The README table cannot be regenerated: `invert.py` uses one starting load of 1.5 t/ha for every class, and its own output `inversion.json` gives grass/scrub **2.7-5.5 t/ha**, not 1.0-2.4. The README was computed by hand with class-specific loads. (2) Every fire size came from the burn-label rasters, which undercount scar area by a median 2.4x (spread README 4k). (3) The spread runs started on the mapped scar (spread audit). (4) It assumes burned area grows as speed², which roads and old burns break. All four push the answer in unknown directions. |
| "Map underloads grass/scrub 2-4x" | **Does not hold as stated** | Same undersized scars. Grass plots also carry the map's grass formula from Mudumalai. It may be true, but this analysis cannot show it. |
| Fire-energy (FRP) consumption ~2.5-3 t/ha | **Weak** | Two satellite looks a day, a fixed "6 h per look" guess, and scar areas from the undersized rasters (smaller area inflates t/ha). Its own spread is 3-8x. It cannot confirm anything to better than a factor of ~3. |
| Front speed 37 m/h | **Reproduces, but withdrawn by the thread itself** | 281 intervals, median 36.9 m/h (re-checked). Treating VIIRS as a point adds ~380 m of jitter; the thread corrected this. |
| Front speed 24 m/h | **Reproduces with a caveat** | Median 23.7 m/h over the 169 fires with a positive fit (re-checked). Over all 221 fitted fires the median is **17 m/h**: 52 fires with zero or negative fits were dropped before taking the median. |
| "ROS x2 is mostly fuel; real load ~2.5-3.5 t/ha" | **Not supported** | In Rothermel at a fixed bed density, speed is proportional to load, so load and any other speed factor are interchangeable. The thread's own table shows a 0.3 m/s breeze under the canopy halves the load needed (3.6 → 2.1 t/ha). Published field-to-Rothermel speed ratios already run 0.7-2.6 (median 1.4), so a x2 is ordinary model error. The plume test (wind direction doesn't predict direction) says nothing about wind *speed* or bed looseness. Fuel was picked by preference, not identified. |
| Back-simulation needs ~7x faster spread | **Not a usable number** | In `ignition_fits.csv`, the fitted speed factor only took 6 values (1, 1.7, 2.8, 4.5, 7, 11), and **27% of fires hit the top value 11**, so their real optimum may be higher. If 7x were fuel it would mean 10-21 t/ha, which is impossible for a litter floor (literature 2-4 t/ha). The spread thread's README says the grown outlines "do not call for a faster fire, only a longer one". The two threads disagree, and neither has settled it. The code that made the fits is not in the shared folder. |
| Ignition ~15 h before first VIIRS (timing README) vs ~6 h (ignition fits) | **Conflict** | Two methods in the same thread give medians 2.5x apart. Both may be right for different fire subsets; neither is validated against an independent start time. |
| Ground burned last year runs slower (17 m/h) | **Too thin** | 9 intervals. |

**Reproducibility.** Almost every script reads intermediate files from `/tmp/claude-0/fuel/`, which existed only inside the thread's own container. From the shared folder alone, none of the map, the teak classifier or the inversion can be rebuilt. The ignition back-simulation code is not saved at all.

**Was there hallucination?** I found no invented files or invented numbers: every figure I re-ran came out as stated. The problems are of a different kind: a table that doesn't match its code, conclusions stated more firmly than the method allows ("the x2 is mostly fuel"), truth data that was later shown to be wrong but never re-run, and medians taken after dropping awkward cases. Those are the habits that make results drift away from what the data can carry.

## 3. How far the thread drifted, and what it cost

**The aim (14 Oct, Akkshay's item 2):** a high-resolution (10-30 m) surface fuel load map for Ratapani, following FSI's method, tested as an input to the 2-day model, published to `fuel-map/ratapani/`.

**Timeline (from the thread):**

| When (UTC) | Work | On aim? |
|---|---|---|
| 14 Oct 14:35-16:35 | v1 and v2 maps, Rothermel layers, 2-day test | Yes. Aim met in ~2 h. |
| 14 Oct 17:15-17:43 | Honest critique, FSI data search, Van Agni layers | Yes |
| 14 Oct 17:47-21:32 | Shrub/grass classes from time series (Akkshay's ask) | Yes, ended correctly in "can't confirm, not added" |
| 14 Oct 22:19-15 Oct 00:14 | Teak vs other classifier (Akkshay's ask) | Partly. Useful layer, but it did not change the fuel. |
| 15 Oct 05:11-05:57 | Fuel from fire size, energy and speed (Akkshay's idea) | In intent yes (calibrate fuel from fires). In method, built on scars later found wrong. |
| 15 Oct 06:00-now (~10 h) | Fire timing, VIIRS footprints, ignition back-simulation for the spread thread | **No.** This is spread-model work. |

**Who steered it there.** Every turn was requested: Akkshay asked for the inversion, pass-to-pass speeds, precise timing, the 375 m footprint and the ignition sweep; the coordinator asked for Rothermel layers and start points for the spread thread. Each step followed sensibly from the last. What was missing was anyone (thread, coordinator or reviewer) asking "is the fuel map better now?" The answer since 06:00 on 15 Oct is no.

**What it cost.**
1. **The map is stale and inconsistent.** It still says 1.46 t/ha; the spread model runs at 3.0 t/ha; the inversion README says grass is under-loaded but the map was never changed; burn history inside the map still comes from the undersized rasters.
2. **Weak findings were promoted.** "Real litter is ~3 t/ha" moved into project memory and the spread model as if measured. It is one of several equally good fits.
3. **Nothing can be rebuilt.** Intermediate data never reached the shared folder.
4. **The FSI-method part was never pushed further.** FSI's own canopy and type maps were downloaded but the obvious next steps (proper 272-stratum structure, all-MP, request for FSI plot data actually sent) stopped. The email to FSI was drafted; the thread has no record of it being sent.
5. **Roughly 10 hours of the most recent effort produced fire-behaviour results** (useful to the spread thread) instead of fuel-map results.

## 4. How good can a 10 m fuel load map be with no field plots?

Full notes with page and table references: [literature.md](literature.md). Papers marked [abstract] there were not read in full.

**Short answer: not good as an absolute number at 10 m. Honest as a relative map at about 1 ha.**

What the published evidence says:

1. **Satellites cannot see litter directly.** Leaf litter lies under the canopy. Every published method predicts it through stand properties (canopy, forest type, time since fire), not by seeing it.
2. **Even the best methods explain little.** Labenski et al. 2023 (full text, US forests, dense lidar plus Sentinel-2) reached R² 0.27 for litter load (RMSE 2.57 t/ha). Simply using the forest-type average gave RMSE 2.83 t/ha, only 9% worse. Other studies report surface-fuel R² of about 0.12-0.57.
3. **National fuel maps match the ground poorly.** Keane 2013 (full text, 13,138 US plots): mapped LANDFIRE fuel classes matched plots 25% of the time, and mapped vs measured loadings had R² below 0.1.
4. **Litter varies over metres, not tens of metres.** Keane 2012 (full text): litter variograms level off within 0.5-2.5 m. In Mudumalai, 135 one-m² quadrats ranged 0.6-10.8 t/ha (Mondal & Sukumar). Between-quadrat variation is CV 54-89% in several studies. So a single 10 m pixel value is a stand average dressed up as a pixel.
5. **FSI's own map is a lookup table, not a measured map.** 15,114 samples, 272 strata (17 forest type groups x 4 canopy x 4 slope), each stratum given its sample mean. No per-stratum values, no accuracy assessment published. FSI's fire risk zonation does not even use it as an input.
6. **Ratapani's literature range is narrow and usable.** Pre-fire (Mar-Apr) floor fuel in central Indian dry deciduous forest is about **2.3-4.5 t/ha** (Jhariya 2017: 2.3 frequently burnt, 3.95 unburnt; Saha 2002: 3.7-4.5 in Mar-Apr, fresh weight; Kittur 2014 [abstract]: 2.2-3.4). Carry-over between years is about zero: the monsoon rots last year's litter. Repeated burning cuts floor fuel by about 40%.
7. **Fire behaviour cannot pin fuel down.** In Rothermel at fixed bed density, spread speed is proportional to load, so load trades one-for-one with wind, moisture and bed looseness (algebra checked; Rochoux 2014 lumps them into one factor for that reason). In 15 measured teak burns in Ecuador (Ramos-Rodríguez 2026, full text), fuel load vs spread speed gave r = -0.05: heavier beds did not burn faster. Load did predict intensity (r = 0.80).
8. **Fire energy (FRP) gives fuel consumed within about a factor of 2, over km², not pre-fire load at 10 m.** Combustion factors differ (0.368 vs 0.453 kg/MJ), polar orbiters see 2-4 times a day, and canopy can block 6-92% of a surface fire's radiation (Roberts 2018).
9. **Coarse products exist only as rough bounds.** ECMWF/CAMS fuel characteristics (~9 km, daily), FCCS global fuelbeds (~300 m), GFED (500 m). None can check a 10 m map.

**What this means for Ratapani.** Without plots, the honest product is:
- a map computed at 10 m but **read at about 1 ha or by stand**,
- driven by things satellites do measure well (canopy cover, leaf-fall timing, date of last fire),
- with absolute loads **bounded by the literature range** and an uncertainty of **about ±40-60%**,
- and labelled as such.

It cannot claim validated t/ha per pixel, teak-specific loads, or grass loads under trees. The current map is actually close to this in structure. Its problems are the stale burn history, a litterfall constant below its own source, circular FSI comparisons, missing uncertainty, and conclusions from fires stated as measurements.

## 5. Plan back to a credible high-resolution fuel load map (ranked)

Ranked by how much each step improves credibility per unit of effort. None needs field staff except step 8.

| # | Step | Why (evidence) | Effort |
|---|---|---|---|
| 1 | **Freeze and label what exists.** Mark the map v2 "relative fuel index, absolute ±50%", state in the README that the inversion, speed and back-simulation numbers are not fuel measurements, and fix the inversion table to match `inversion.json` or withdraw it. | Sections 2-3. Stops weak numbers spreading into other threads. | Hours |
| 2 | **Save every intermediate to the shared folder** so the map rebuilds from `fuel-map/ratapani/` alone (canopy, NDVI composites, teak features, ignition-fit code). | Nothing is re-runnable today. | Hours |
| 3 | **Rebuild burn history from the grown scar outlines**, not the undersized rasters: per pixel, date of last fire and number of fires 2017-26, using the scar thread's frozen v1 outlines plus VIIRS. | Burn history drives both the burn-frequency cut and grass regrowth; the rasters miss ~2/3 of burned ground (spread README 4k). Literature: fire history is the strongest known control on litter (Jhariya: -40%). | 1 day |
| 4 | **Rebuild the litter model as a one-season budget with ranges**: litter at date *d* = annual litterfall (range 4.75-7.6 t/ha/yr closed, Jhariya) x canopy share x leaf-fall fraction by *d* (per pixel, Sentinel-2) x burn-history factor, reset to zero at the monsoon and at each fire's date. Carry a low / central / high map instead of one number. | Litterfall x phenology x time-since-fire is the most defensible plot-free method (Brandis & Jacobson 2003 [abstract]; zero carry-over: Saha 2002, Jhariya 2017). Uses the full Jhariya range instead of picking 5.0. | 1-2 days |
| 5 | **Publish at two grains**: 10 m for the spread model, and a 1 ha / per-compartment summary as the official map. Drop the slope multipliers unless a source is found. | Litter varies over metres (Keane 2012); 95% of the map's variation already sits at 30 m and 65% at 300 m. | Hours |
| 6 | **Add a dry-season exposed-litter index** from Sentinel-2 SWIR (non-photosynthetic cover) under leafless teak, kept as an index, and check that it agrees in rank with step 4. | Teak is leafless Feb-May, so the floor is partly visible; SWIR dry-matter indices worked in open savanna (Labenski review). Independent of the litterfall constants. | 1 day |
| 7 | **Compare openly, don't calibrate**: our map vs FSI's class areas for Raisen/Sehore, CAMS fuel and FCCS at their own scale, and VIIRS fire energy per km² as a consistency check. Report disagreements. | These are the only independent numbers available; none is accurate enough to calibrate a 10 m map. | 1 day |
| 8 | **Get real numbers when possible.** Send the drafted FSI request (MP plot weights or the 272 stratum means); ask MP FD divisions around Ratapani for FSI plot sheets or working-plan crop composition. When field access opens: about 36 litter quadrats (0.25-1 m², oven-dried) per main stratum in late March-April gives a stratum mean within ±20%. | Any measured data beats every other step combined (CV ~60% means ~36 quadrats for ±20%). | Email now; field later |
| 9 | **Stop using fires to estimate fuel load**, and hand fire timing, footprint and ignition work formally to the spread thread. Keep only one fire-based check: does the step 4 map, unchanged, make the spread model's sizes better or worse on held-out years? | Load is not identifiable from speed or size (section 4, point 7). Ends the drift. | Decision |
| 10 | **All of MP** only after steps 1-7, using the same budget model on Earth Engine, with Group 3 sal forests (Balaghat, Mandla) given their own litterfall range. | Scaling an unchecked map multiplies its errors. | Later |

**What "done" looks like:** a versioned map (low / central / high), rebuildable from the shared folder, built on the frozen scar outlines, with a one-page note saying what is measured, what is borrowed, what is assumed, and how it compares with FSI and CAMS.
