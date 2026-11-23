# Fire spread models for Ratapani: what exists, what it needs, how it is checked

Literature and software scan, 14 Oct 2026. It builds on `../cdac_spread_details.md` (the C-DAC deck) and on the spread section of `research/ratapani-ignition/README.md`, and does not repeat them. Every item below has a link. Lines marked **[inference]** are my judgement, not something a source states.

**Our starting point.** In Ratapani the next-day burn depends on distance to the front: 17.7 % of cells within 500 m of a VIIRS front burn the next day, against 0.8 % at 2-3 km. How fresh the front is matters too. Wind direction adds nothing at 500 m. So a physics model has to beat a "distance plus freshness" baseline on our own dated fires before it earns its keep.

Target PC: i7-14700F (20 cores, 28 threads), 64 GB RAM, AMD GPU, Windows. Alternative: a Linux container.

---

## 1. What C-DAC actually published (new detail beyond the deck)

- **Kale et al. 2024, "Operational Forest-Fire Spread Forecasting Using the WRF-SFIRE Model", *Remote Sensing* 16:2480.** [mdpi](https://www.mdpi.com/2072-4292/16/13/2480), [PDF](https://mdpi-res.com/d_attachment/remotesensing/remotesensing-16-02480/article_deploy/remotesensing-16-02480.pdf). Read in full.
  - **Grids:** GFS 0.25° drives three WRF domains at 7.2 km, 2.4 km and 800 m. The fire mesh is 40 m, a 1:20 refinement of the 800 m domain.
  - **Fuel map:** the 1:10,000 LULC map is converted to a 40 m fuel raster. The classes map to Anderson models as follows:
    - Grassland → Short Grass (FBFM 1)
    - Dense Scrub → Timber with grass and understory (FBFM 2)
    - Open Scrub → Tall Grass (FBFM 3)
    - Forest → Closed Timber Litter (FBFM 8)
  - **Fuel values:** loads come from 23 field plots of 0.1 ha. The Forest class has load 0.270 kg/m² (2.7 t/ha; 24 % of the WRF-SFIRE FBFM 8 default), depth 0.061 m (the FBFM 8 default, not a field value) and SAV 1224 ft⁻¹ (from the literature). The moisture of extinction, windrf and heat values below are also WRF-SFIRE `namelist.fire` defaults (see `fire_spread_models_fullread.md`). Moisture of extinction is 0.12 for grass, 0.15 for dense scrub, 0.25 for open scrub and 0.30 for forest. The wind reduction factor is 0.36-0.44 (Baughman & Albini). Heat content is 17.433 MJ/kg.
  - **Compute:** a 24 h forecast took **2 h 11 min on 240 cores** of PARAM Seva. The deck's later figure is 17 min on 16 nodes.
  - **Validation:** forecast burnt area 1.72 km² against 1.07 km² mapped from Sentinel-2. "Shapes matched well." No overlap score is reported, so the forecast overpredicted area by about 60 %.
- **Chavan, Labade, Kale et al. 2025, ISPRS Annals X-5-W2-2025:103.** [PDF](https://isprs-annals.copernicus.org/articles/X-5-W2-2025/103/2025/isprs-annals-X-5-W2-2025-103-2025.pdf).
  - C-DAC also ran **NIST FDS** in level-set mode 4 (fire front coupled to the CFD flow) on 1-5 m grids in South Sikkim on HPC, with field SAV values.
  - Validation was an overlay on post-fire Sentinel-2 (a 9.5 ha burn), reported only as "70 % agreement" for the first fire point, with the metric undefined.
  - The paper says FARSITE and FlamMap use constant environmental conditions and have "limited questionable accuracy" (their view).
- **Project page:** the [Sikkim Wildfire Spread Forecasting and Monitoring System](https://nsmindia.in/applications/projects/sikkim-wildfire-spread-forecasting-and-monitoring-system-swfms/) gives 48 h forecasts. The Sikkim Forest Department used them on 27 Jan 2023 and 12 Mar 2024.
- **Other Indian work:**
  - Khadke, Mukherjee & Ghosh 2026, *J. Earth Syst. Sci.*: WRF-Fire on the May 2018 Western Himalaya fires. Low RH, more than temperature, drove faster spread ([EBSCO record](https://www.ebsco.com/articles/earth-and-atmospheric-sciences/23c0dfeb-96ab-5c42-8afc-b06297a04d08/simulating-forest-fires-in-uttarakhand-uncovering-the-role-of-meteorological-variables); full text not seen).
  - Singh et al. 2017: FARSITE at Taradevi, Himachal Pradesh, with no quantitative validation ([Consensus](https://consensus.app/papers/details/b4cdc001914d54a18559ea03d44a0fdf/)).
  - No IIRS spread-simulation paper and no FARSITE or FlamMap study of Uttarakhand chir pine turned up.

---

## 2. Models

### WRF-SFIRE (OpenWFM), the C-DAC system
- **Links:** [code](https://github.com/openwfm/WRF-SFIRE), [wiki and user guide](https://wiki.openwfm.org/wiki/User_guide), [compile guide](https://wiki.openwfm.org/wiki/How_to_compile_WRF-Fire), [WRFx real-data pipeline](https://wiki.openwfm.org/wiki/How_to_set_up_the_WRFx_system). Model paper: [Mandel et al. 2011, GMD 4:591](https://gmd.copernicus.org/articles/4/591/2011/).
- **Licence:** public domain, under the WRF notice ([EESSI listing](https://gitlab.com/eessi/support/-/issues/230); no LICENSE file was seen).
- **What it does:** WRF weather coupled two-way to Rothermel spread on a level-set front. A fuel moisture model is built in ([Vejmelka 2016, IJWF 25:558](https://publish.csiro.au/wf/WF14085), [arXiv](https://arxiv.org/pdf/1406.4480)).
- **What it needs:** Fortran and C compilers, NetCDF, MPI and WPS, plus GFS boundary data, a DEM, a fuel-category raster and an ignition point or time.
- **Run time:** 240 cores for 2 h 11 min per 24 h forecast in Sikkim.
  - **[inference]** On the 20-core PC at a 40 m fire grid, expect several hours to more than 10 h per forecast day. A coarser 2-3 km WRF domain with a 60 m fire mesh would be much quicker but is untested here.
- **Windows PC:** Linux only. It builds under WSL2 or Docker with gfortran **[inference]**. The GPU is unused.
- **Validation found:**
  - Perimeter or area checks only: Santa Ana 2007 ([arXiv 1202.3209](https://arxiv.org/pdf/1202.3209)), Split, Croatia ([record](https://researchers.mq.edu.au/en/publications/coupled-fireatmosphere-simulations-of-the-split-croatia-wildfire/)) and Camp Fire against NEXRAD perimeters ([NSF PAR](https://par.nsf.gov/biblio/10461797)).
  - FireFlux, against in-situ flow and plume measurements ([Kochanski 2013, GMD 6:1109](https://gmd.copernicus.org/articles/6/1109/2013/)).
  - In most cases it simulated areas slightly too small or spread rates off. None of the WRF-SFIRE papers I found scores with Sørensen or Jaccard.
- **Use for us:** low. The coupled atmosphere matters for intense, plume-driven fires. Ratapani fires are low-intensity litter fires, and wind direction does not steer them at our scale. Running it is a big build and compute job for little expected gain. Better: give C-DAC our dated validation set and let them run it.

### ForeFire (Université de Corse / CNRS)
- **Links:** [GitHub](https://github.com/forefireAPI/forefire), [docs](https://forefire.readthedocs.io/en/stable/getting_started/introduction.html), [JOSS 2025, doi:10.21105/joss.08680](https://doi.org/10.21105/joss.08680).
- **Licence:** GPL-3.0.
- **What it does:** a C++ front-tracking engine with Python bindings, several rate-of-spread models, and optional coupling to the MesoNH weather model.
- **What it needs:** NetCDF layers for elevation, fuel and wind.
- **Run time:** designed to run faster than real time. No figure was found.
- **Windows PC:** through WSL or Docker only. A Docker quick-start with a web console exists ([quickstart](https://forefire.readthedocs.io/en/docs/getting_started/quickstart.html)).
- **Validation:** [Filippi et al. 2014, NHESS 14:3077](https://nhess.copernicus.org/articles/14/3077/2014/). They ran 80 Mediterranean fires × 4 spread models, fully automatic and untuned, given only burned area and ignition. The more physical models ranked higher.
- **Use for us:** medium. It is good for an automated many-fires test like Filippi's, but its fuel set is Mediterranean, so we would have to supply Rothermel-type fuels ourselves.

### FARSITE / FlamMap 6 (USFS Missoula Fire Lab)
- **Links:** [FlamMap](https://firelab.org/project/flammap), [applications page](https://firelab.org/applications). FARSITE4 is retired and FARSITE now ships inside FlamMap 6. Model paper: [Finney 1998](https://consensus.app/papers/details/b5fb446769615acd99e89a1f09217a47/).
- **Licence:** free (freeware), closed source.
- **What it needs:** a landscape (.lcp) file (elevation, slope, aspect, fuel model, canopy), a weather and wind stream, fuel moistures, and an ignition.
- **Run time:** minutes per fire on a PC **[inference, typical use]**.
- **Windows PC:** yes, it runs on 64-bit Windows only.
- **Validation found:**
  - [Jahdi 2015, northern Iran](https://consensus.app/papers/details/fa4de8dadf9752e0b7271c3b2c19e5a6/): Scott-Burgan fuel models beat Anderson models.
  - [Jahdi 2014](https://consensus.app/papers/details/2541597c176c59909c4c88c08b97d9d2/): Kappa 0.5 with uniform wind and 0.8 with WindNinja winds.
  - [Price 2022, sagebrush](https://consensus.app/papers/details/48d184e4b9c55168b0516ad9adbf9c54/): Sørensen 0.38 with LANDFIRE fuels, rising to 0.70-0.80 with a fuel map classified from RAP satellite vegetation cover. The fuel map was the main lever.
  - [Xu 2022, Inner Mongolia](https://consensus.app/papers/details/6de15bb8a3c25c0bb4924dd923ffaa34/): re-initialising FARSITE from each VIIRS pass raised the final Sørensen from 0.54 to 0.79.
- **Use for us:** high as a calibration and teaching tool. It is free, runs on the PC, and lets FSI and Forest Department staff test fuel models by eye. It is not scriptable at scale.

### ELMFIRE (Lautenberger / CloudFire)
- **Links:** [GitHub](https://github.com/lautenberger/elmfire), [docs at elmfire.io](https://elmfire.io), [Berkeley Fire Lab](https://firelab.berkeley.edu/software). Model paper: [doi:10.1016/j.firesaf.2013.08.014](https://doi.org/10.1016/j.firesaf.2013.08.014).
- **Licence:** the current LICENSE.md is **AGPL-3.0 plus the Commons Clause**: free to use, but not to sell as a product or service. Older listings say EPL-2.0.
- **What it does:** Eulerian level set with Rothermel surface spread, crown fire and spotting. It is built for many-fire ensembles and burn probability. It drives the Pyrecast forecasts of most large US fires.
- **What it needs:** GeoTIFFs for fuel, topography, weather and moisture, plus Fortran namelists. Dependencies are gfortran, OpenMPI and GDAL.
- **Run time:** no published benchmark found. **[inference]** Seconds to minutes per fire at 30 m on 20 cores, given its operational ensemble use.
- **Windows PC:** through Docker (`docker compose up`) or WSL2. The documented build is Ubuntu 24.04.
- **Use for us:** high for burn-probability and Monte Carlo runs over the whole sanctuary once fuels are calibrated.

### Pyretechnics (Spatial Informatics Group / Pyregence)
- **Links:** [GitHub](https://github.com/pyregence/pyretechnics), [docs](https://pyregence.github.io/pyretechnics/), [PyPI](https://pypi.org/project/pyretechnics).
- **Licence:** dual licence since 2026 (LICENSE.md): a free Community License for noncommercial, research, governmental and nonprofit use, and a paid Commercial License otherwise. The older EPL-2.0 listing is out of date.
- **What it does:** a pure Python and Cython library holding Rothermel surface spread, crown fire, spotting, fuel models with dynamic loading, and ELMFIRE's Eulerian level set. Inputs go in a "space-time cube", so rasters can vary hour by hour.
- **What it needs:** numpy and rasterio, our fuel and DEM rasters, and hourly weather and moisture.
- **Run time:** no figure found. **[inference]** Fine for single fires at 20-30 m on the PC.
- **Windows PC:** should work with pip, since it is plain Python with Cython **[inference; OS support not stated]**. It works in any Linux container.
- **Use for us:** **highest**. It is the same physics as WRF-SFIRE's spread and ELMFIRE, inside our Python pipeline. We can calibrate the fuel models against our dated fires directly.
- **pyrothermel:** no package of that name was found. Nearest equivalents:
  - Pyretechnics
  - R package [firebehavioR](https://github.com/EcoFire/firebehavioR) (Rothermel and BehavePlus-like)
  - JS port of BehavePlus 6 [fire-behavior-simulator](https://github.com/cbevins/fire-behavior-simulator)
  - C [firelib](https://pkgsrc.se/branch=pkgsrc-2016Q2/misc/firelib)

### Cell2Fire / C2F-W / C2FK
- **Links:** [Cell2Fire](https://github.com/cell2fire/cell2fire) (GPL-3.0; its readme says research use, no warranty), [paper, arXiv 1905.09317](https://ar5iv.labs.arxiv.org/html/1905.09317), [docs](https://cell2fire.readthedocs.io/). Maintained forks: [C2FK](https://github.com/fire2a/C2FK) and [C2F-W](https://github.com/fire2a/C2F-W), with a QGIS toolbox via [fire2a-lib](https://pypi.org/project/fire2a-lib/0.2.11).
- **What it does:** a cell-based model with elliptical spread inside each cell, using the Canadian Fire Behaviour Prediction (FBP) system by default, and parallel for large landscapes.
- **Validation:** checked against Prometheus scars on real and hypothetical fires.
- **Windows PC:** Docker, or the QGIS plugin (C2F-W) **[Windows support of the plugin inferred]**.
- **Use for us:** medium-low. It is mainly for firebreak and landscape planning. Support for Scott-Burgan fuels was not confirmed.

### Prometheus (Canada)
- **Links:** [model description](https://www.math.ualberta.ca/~thillen/paper/prometheus-final.pdf), [UVic record](https://dspace.library.uvic.ca/handle/1828/2242).
- **What it does:** wave (Huygens) propagation using the Canadian FBP fuel types. It is now also wrapped in [BurnP3+](https://apexrms.com/burnp3plus/).
- **Licence:** unclear.
- **Use for us:** low. FBP fuel types are boreal and do not fit teak litter.

### Phoenix RapidFire (Univ. Melbourne / Bushfire CRC)
- **Links:** [Pursuit article](https://pursuit.unimelb.edu.au/articles/the-computer-program-that-saved-a-town), [Bushfire CRC](https://bushfirecrc.com/news/news-item/bushfire-predicting-computer-program-gets-21-million-boost).
- **Status:** used operationally in Victoria. No public licence or download was found.
- **Use for us:** none (not obtainable).

### SPARK (CSIRO Data61)
- **Links:** [about](https://research.csiro.au/spark/about), [FAQ](https://research.csiro.au/spark/about/faq), [access page](https://research.csiro.au/spark/), [v0.9 docs](https://research.csiro.au/static/spark/docs/docspark.html).
- **What it does:** a raster level-set solver in OpenCL, where you write your own speed function.
- **Licence:** Spark 1 commercial licensing has ended and a non-commercial demo remains. Spark 2 licensing was "expected 2025", with status unknown.
- **Windows PC:** OpenCL drivers are required. **[inference]** The AMD GPU should run OpenCL.
- **Use for us:** low, because of the licensing uncertainty. Its idea of a user-defined speed function is worth copying, though: our empirical distance kernel could serve as one.

### NIST FDS / WFDS (CFD)
- **What it is:** used by C-DAC at 1 m (above). Run time is about 10 h on HPC for a small area.
- **Use for us:** none operationally.

### Wind downscaling: WindNinja
- **Links:** [Fire Lab](https://research.fs.usda.gov/firelab/products/dataandtools/windninja), [site](https://ninjastorm.firelab.org/windninja/about.html), code at github.com/firelab/windninja.
- **Platforms:** Windows installer; Linux build from source.
- **Use for us:** only if a physics model later shows wind sensitivity. Our data say it does not at 500 m.

---

## 3. Machine-learning spread emulators

| Work | What | Score reported | Use for us |
|---|---|---|---|
| [FireCast, Radke 2019 IJCAI](https://www.ijcai.org/proceedings/2019/636) | CNN on 24 h perimeters | Beat FARSITE and random on accuracy, recall and F1 | Idea only |
| [Next Day Wildfire Spread, Huot 2022 IEEE TGRS](https://arxiv.org/abs/2112.02447v2) | US dataset, 1 km, 1-day lead | Benchmark for CNN, logistic and RF models | US data, no transfer |
| [WildfireSpreadTS, Gerard 2023 NeurIPS](https://neurips.cc/virtual/2023/poster/73593), [Zenodo](https://zenodo.org/records/8006177) | 607 US fires, 375 m VIIRS, 23 channels, daily series | U-Net baselines; the authors flag noisy labels from smoke and cloud | Template for a Ratapani-style dataset |
| [FireSenseNet 2026](https://consensus.app/papers/details/4ec03e1408f655c48194aa328b36e8cb/) | Dual-branch CNN on NDWS | F1 0.42; **previous-day fire mask dominates, wind speed acts as noise at coarse time resolution**; common evaluation shortcuts inflate F1 by more than 44 % | Independent support for our wind result |
| [CNN-BiLSTM, Marjani 2024](https://consensus.app/papers/details/16d7054eb92155e39c02ff91aa294b2e/) | VIIRS daily spread | F1 0.58 on validation | — |
| [Shadrin 2024, Sci. Rep.](https://consensus.app/papers/details/c8ac97311fc35b439f3368bb212b4eaa/) | 1-5 day spread, Russia | F1 0.64-0.68 | — |

Two points about all of these:
- They learn the same thing our LightGBM already learned: spread from yesterday's fire mask. **[inference]** A CNN is unlikely to beat our model on 500 m cells, with roughly 1,700 held-out spread patches.
- On the AMD GPU, PyTorch on Windows is awkward **[inference]**. These models are small enough to run on the CPU.

---

## 4. Data assimilation of VIIRS

- [Mandel et al. 2014, arXiv 1410.6948](https://arxiv.org/pdf/1410.6948): shifts the fire arrival-time field to fit the detections (Tikhonov / Bayesian), then re-runs WRF-SFIRE from that state.
- Haley, Farguell et al. ([UC record](https://ap1.sib.uc.pt/handle/10316.2/34301)): a detection likelihood that is a function of arrival time, including a model of geolocation error.
- [Farguell 2019 WRF workshop](https://www2.mmm.ucar.edu/wrf/users/workshops/WS2019/short_abstracts/p2.html): uses an SVM to separate "burning" from "not yet" detections and recover the arrival time.
- [Generative (cGAN) arrival time from VIIRS, arXiv 2309.02615](https://arxiv.org/pdf/2309.02615): mean Sørensen 0.82 on 2020 California fires, and 0.81 on five Pacific fires in a 2025 follow-up.
- [Xu 2022](https://consensus.app/papers/details/6de15bb8a3c25c0bb4924dd923ffaa34/): restarting FARSITE at each VIIRS pass gave Sørensen 0.54 → 0.79. This is the cheap version of assimilation.
- [Rios 2019, data-driven simulator](https://consensus.app/papers/details/a6698193466d5f8eaac3a8ce58b60dad/): estimates effective fuel and wind from observed front positions instead of measuring them.
- **Use for us:** restarting the model every day from the newest VIIRS front is the same insight as our "freshness dominates" result. Any physics model we run should be restarted each day, not run free for 48 h. Fitting the effective spread rate from observed fronts (Rios) can stand in for unknown fuel loads.

---

## 5. Fuel moisture and fuel models for dry teak litter

### Dead fuel moisture
- **The model:** Nelson (2000), *Can. J. For. Res.* 30:1071 ([FAO record](https://agris.fao.org/search/ar/records/65df77300f3e94b9e5d8b47a)). It simulates a stick with radial nodes and needs temperature, RH, solar radiation and rain.
- **Code:** the reference code is NFDRS4 `deadfuelmoisture.cpp`. A Go port exists ([pkg.go.dev](https://pkg.go.dev/alpineworks.io/firewx/nfdrs/nelson)). No Python package was found.
- **Other fuel classes:** [Carlson, AMS](https://ams.confex.com/ams/pdfpapers/65884.pdf) gives stick parameters for the 1, 100 and 1000 h classes.
- **WRF-SFIRE's own approach:** a simpler time-lag model with Kalman assimilation of station data (Vejmelka 2016, above).
- **Use for us:** drive a Nelson or time-lag 1 h and 10 h moisture with ERA5-Land hourly data. Weather is effectively one value per day across the sanctuary, so one moisture series is enough.

### Ratapani fire character
- **Saha 2002, central India deciduous forest (Gadchiroli)** ([Curr. Sci.](https://consensus.app/papers/details/f162b252fedd5cfba7a0459a9a7f8e53/)):
  - fires in March, after about 75 % of leaf fall
  - mean flame height 55-60 cm
  - residence time about 12 s
  - fire return interval of 1 year
  - These are low-intensity ground fires, the closest published analogue to Ratapani.
- **Behera 2023, tropical dry forest, eastern India** ([Trop. Ecol.](https://consensus.app/papers/details/59f0d7cead0a53e5a2890983ac978072/)): teak is more flammable than sal (low moisture, high volatiles).

### Standard fuel models
From [Scott & Burgan 2005, RMRS-GTR-153](https://gacc.nifc.gov/oncc/docs/40-Standard%20Fire%20Behavior%20Fuel%20Models.pdf), Table 7 (read from the PDF), and [Anderson 1982, INT-122](https://www.fs.usda.gov/rm/pubs_int/int_gtr122.pdf).

| Model | 1h / 10h / 100h load (t/ac) | Live herb / woody | 1h SAV (ft⁻¹) | Depth (ft) | Mx (%) | Fits |
|---|---|---|---|---|---|---|
| FBFM 8 closed timber litter | 1.50 / 1.00 / 2.50 | 0 / 0 | 2000 | 0.2 | 30 | C-DAC "Forest" choice; compact, slow |
| FBFM 9 hardwood litter | 2.92 / 0.41 / 0.15 | 0 / 0 | 2500 | 0.2 | 25 | Loose broadleaf litter; faster than 8 |
| TL2 low-load broadleaf litter | 1.40 / 2.30 / 2.20 | 0 / 0 | 2000 | 0.2 | 25 | Teak litter early in the season |
| TL6 moderate broadleaf litter | 2.40 / 1.20 / 1.20 | 0 / 0 | 2000 | 0.3 | 25 | Teak litter after full leaf-fall (March-April) |
| TL9 very high broadleaf litter | 6.65 / 3.30 / 4.15 | 0 / 0 | 1800 | 0.6 | 35 | Probably too heavy |
| TU1 low-load timber-grass-shrub | 0.20 / 0.90 / 1.50 | 0.20 / 0.90 | 2000 | 0.6 | 20 | Open teak with grass |
| GR1 / GR2 short / low-load grass | 0.10 / 0 / 0 | 0.30 or 1.00 / 0 | 2200 / 2000 | 0.4 / 1.0 | 15 | Grassy blanks and edges |

- FBFM 9 SAV and Mx are as given in Anderson's tables. The FBFM 8 and 9 values come from secondary tables ([NWCG S-290](https://training.nwcg.gov/dl/s290/s-290-usfs-aids-to-determining-fuel-models.pdf)); loads, depth and Mx are now verified against INT-122 Table 1, and SAV 2000/2500 matches Albini 1976 as coded in Pyretechnics and WRF-SFIRE.
- 1 t/ac ≈ 2.24 t/ha. FSI's "< 20 g/ft²" low class is about 2.2 t/ha (about 1 t/ac), which sits between TL2 and TL6.
- **[inference]** Start with TL6 for teak after leaf-fall, TL2 for January-February, and GR2 or TU1 for open patches. Then scale the 1 h load and depth to fit observed day-to-day front advance.

### Local calibration is standard practice
- [Ascoli 2015](https://consensus.app/papers/details/cf1b745a2f4d52f0b8a5e79e37c13bea/): a genetic algorithm fits the fuel-model parameters to observed spread rates, with no fuel sampling. Errors fell 19-39 %.
- Several Chinese litter studies found that uncalibrated Rothermel errs by 35-135 % and needs local fitting ([Xu 2025](https://consensus.app/papers/details/d3b358766e165de08fcca361055cc0d9/), [Xu 2025 mixed fuels](https://consensus.app/papers/details/571ca59d615e51faa85c8379b4103cdb/), [Zhang 2023](https://consensus.app/papers/details/8da8f0c4d11f5273a77cfea5bd99e2c9/)).

---

## 6. Validation metrics

Notation: A = observed burned area, B = simulated burned area.

| Metric | Formula | Notes and sources |
|---|---|---|
| Sørensen (Dice, F1) | 2\|A∩B\| / (\|A\|+\|B\|) | Most-used fire score: [Price 2022](https://consensus.app/papers/details/48d184e4b9c55168b0516ad9adbf9c54/), [Xu 2022](https://consensus.app/papers/details/6de15bb8a3c25c0bb4924dd923ffaa34/), [Ning 2024](https://consensus.app/papers/details/fcb8e09024195b168cf05f059d5ee755/) (>0.8 rated "high accuracy"), [cGAN](https://arxiv.org/pdf/2309.02615) |
| Jaccard (IoU) | \|A∩B\| / \|A∪B\| | Equals S/(2−S). Common in ML papers |
| Cohen's Kappa | agreement beyond chance | [Jahdi 2014](https://consensus.app/papers/details/2541597c176c59909c4c88c08b97d9d2/) |
| POD and false alarm ratio | TP/(TP+FN), FP/(TP+FP) | Separates under-forecast from over-forecast. C-DAC's 1.72 vs 1.07 km² is a false-alarm problem |
| Area ratio | \|B\|/\|A\| | C-DAC's only number, 1.6 |
| Arrival-time agreement | compare simulated and observed burn time per cell, e.g. mean absolute error in hours or days | [Filippi et al. 2014, IJWF 23:46 "Representation and evaluation of wildfire propagation simulations"](https://www.publish.csiro.au/WF/fulltext/WF12202) proposes arrival-time and shape agreement and argues that scoring dynamics beats snapshots. See also [FARSITE vs HFire, Portugal](https://dl.uc.pt/handle/10316.2/34307) |
| Hausdorff and maximum distance error | largest gap between perimeters | [arXiv 2609.01675 appendix](https://arxiv.org/pdf/2609.01675) |

**Our recipe [inference]:**
1. Use VIIRS dates for arrival time (the 375 m pixel day) and the 20 m scar patch as the final shape.
2. For each fire, score Sørensen, POD and FAR on the final scar, plus arrival-day error at VIIRS pixels.
3. Always report the same scores for two baselines:
   - a **distance-only kernel**: a circle growing at the observed median speed
   - our **LightGBM spread model**
4. Use [Filippi 2014](https://nhess.copernicus.org/articles/14/3077/2014/)-style automatic, untuned first runs over many fires, not a few hand-picked ones.

---

## 7. Ranked plan (top 5)

1. **Build the scoring set first** (days, no new software).
   - Contents: about 50-200 dated Ratapani fires, 2017-2026. Each has VIIRS pixel days, the scar perimeter, an ignition guess (first VIIRS pixel) and hourly ERA5-Land weather.
   - Score the two baselines with the metrics in section 6.
   - Offer this set to C-DAC and FSI: it is the validation their WRF-SFIRE runs lack.
2. **Pyretechnics on our Python stack**, run in the Linux container or on the PC.
   - Inputs: 30 m fuel map with TL2 or TL6 for teak by date, TU1 or GR2 for open areas, non-fuel for water, roads and fields. Add the SRTM or ALOS DEM and a Nelson or time-lag 1 h and 10 h moisture from ERA5-Land.
   - Restart each day from the latest VIIRS front.
   - Calibrate 1 h load and depth (Ascoli-style search) on 2017-2022 fires and test on 2023-2026.
   - Success means beating the distance kernel on Sørensen and arrival-day error **[inference that it may not]**.
3. **ELMFIRE in Docker** with the calibrated fuels.
   - Monte Carlo burn probability and 24-48 h "reach" envelopes for each new VIIRS alert across the sanctuary.
   - Licence check: AGPL plus Commons Clause is fine for government or non-commercial use, but not for a paid service.
4. **FlamMap 6 on the Windows PC** for staff-facing checks.
   - Run the same calibrated fuels as a custom fuel-model file, as a sanity check, for training, and for fire-line intensity or flame length for crew safety.
   - Saha's 55-60 cm flames are a quick plausibility check.
5. **WRF-SFIRE only through C-DAC.**
   - Do not build it locally. Ask C-DAC to run their Deccan or Ratapani setup on our scoring set and report Sørensen and arrival error against our baselines.
   - Given our wind finding, expect little gain over item 2 for litter fires **[inference]**.

**Not recommended:** ML emulators (US-trained; they relearn "yesterday's mask", which we already have), Prometheus or Cell2Fire with FBP fuels, Phoenix (not available), SPARK (licence unclear) and FDS (cost).
