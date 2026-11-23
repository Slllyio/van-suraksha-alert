# Fire size and outline from active-fire points alone, before a clear image (scouting round 12, topic "area", 15 Oct 2026)

## v2 rerun (16 Oct 2026)

Same design as Part A: the same 4,886 VIIRS-seeded scars (Jan-Jun, v1 `grew_into_large_burn` dropped), the same features, each season held out in turn. Only the target changes, from v1 `scar_ha` to **scar outlines v2 (2026-10-16)** `scar_ha` (`fire-alert-scars/reference/v2_2026-10-16/firms_event_scars.geojson`).
- 1,506 of these scars were redrawn and split. Only 155 still touch the chip edge (`still_at_edge`), against 1,659 at the edge in v1.
- The pre/post image dates are unchanged for all but 4 of 15,048 alerts, so the features (built to `post_date`) stay valid.
- Total area rises from 493,012 to 855,928 ha (+74%); the median goes from 70.4 to 72.0 ha.
- Size classes now go above 300 ha: 300-1,000 and ≥1,000 ha.
- Script: `code/area/rerun_v2.py`. Outputs: `code/area/rerun_v2_scalars.csv`, `rerun_v2_lookup.csv`, `rerun_v2.log`.

**What changed, in one line.** Ranking holds or improves slightly, but hectare estimates get worse. v2 shows the big fires are bigger than VIIRS points suggest, so the regression toward the middle is stronger and the spread wider.

| Number | v1 | v2 |
|---|---|---|
| Day-0 LightGBM Spearman | 0.464 | 0.481 |
| All-points LightGBM Spearman | 0.505 | 0.519 |
| Day-0 LightGBM within x2 | 46.6% | 41.5% |
| All-points LightGBM within x2 | 48.4% | 44.1% |
| Training-median (null) within x2 | 36.3% | 32.6% |
| Day-0 median abs log2 error | 1.08 | 1.24 |
| Day-0 within x2, scored without edge scars | 50.6% (v1 edge rule) | 42.4% (`still_at_edge` rule) |
| Day-0 AUC, scar ≥100 ha (base rate) | 0.751 (40.3%) | 0.755 (42.5%) |
| All-points AUC, ≥100 ha | 0.769 | 0.772 |
| Top-10% precision for ≥100 ha (day 0) | 75.8% | 77.9% |
| Day-0 AUC, scar <10 ha | 0.705 | 0.705 |
| Quantile 10-90% coverage / median width factor | 74.7% / 16.8 | 74.6% / 24.7 |
| Power law on day-0 count n | 30.9·n^0.47, resid factor 3.38 | 31.6·n^0.61, resid factor 4.01 |
| Power law on day-0 footprint union | 6.7·x^0.52 (3.36) | 4.4·x^0.67 (3.99) |
| Power law on day-0 FRP sum | 23.8·x^0.32 (3.45) | 22.9·x^0.40 (4.16) |
| Spearman, raw day-0 count / footprint union / FRP sum | 0.445 / 0.447 / 0.391 | 0.460 / 0.462 / 0.403 |
| Median scar ha per MW of summed FRP | 3.24 | 3.83 |
| ha per MW, Mar / Apr | 3.31 / 3.19 | 4.11 / 3.81 |
| Spearman of scar with image gap | 0.08 | 0.07 |

**By true size (day-0 LightGBM: n, within x2, median predicted/true, MAE).** Classes are set on each version's own areas, so their counts differ.

| True scar | v1 | v2 |
|---|---|---|
| <10 ha | 601, 5.5%, 7.7x, 39 ha | 601, 5.0%, 8.3x, 52 ha |
| 10-30 ha | 874, 47.7%, 2.0x, 28 ha | 874, 43.0%, 2.2x, 39 ha |
| 30-100 ha | 1,440, 71.9%, 0.92x, 29 ha | 1,336, 67.6%, 1.03x, 39 ha |
| 100-300 ha | 1,764, 43.9%, 0.46x, 98 ha | 1,265, 48.1%, 0.51x, 94 ha |
| 300-1,000 ha | 207, 8.7%, 0.31x, 228 ha | 708, 15.5%, 0.25x, 401 ha |
| ≥1,000 ha | none (capped) | 102, 2.9%, 0.11x, 1,269 ha |

The raw convex hull of day-0 points is still the least-biased raw guess for the largest fires: 30% of ≥1,000 ha scars are within x2 (0.30x), against 8.8% for the pixel-footprint union. It is still poor overall (40.2% within x2).

Coverage of the 10-90% intervals for 100-300 ha rises from 76% to 90%, and for 300-1,000 ha from 5% to 41%. For ≥1,000 ha it is 5%.

**Day-0 detection-count lookup (final scar, ha: p10 / median / p90; share ≥100 ha).** The p10 and median barely move; the upper tail is now real, not capped at 400 ha.

| Day-0 detections | fires | v1 | v2 |
|---|---|---|---|
| 1 | 1,554 | 5 / 30 / 162; 20% | 5 / 30 / 208; 21% |
| 2 | 831 | 8 / 46 / 204; 26% | 8 / 47 / 261; 28% |
| 3-4 | 757 | 13 / 70 / 224; 39% | 13 / 72 / 317; 40% |
| 5-8 | 708 | 21 / 112 / 250; 55% | 21 / 127 / 467; 58% |
| 9-16 | 505 | 28 / 152 / 303; 72% | 28 / 180 / 626; 75% |
| >16 | 531 | 23 / 178 / 313; 74% | 23 / 306 / 1,045; 78% |

Median ha per VIIRS detection (all points): 1 detection 26.9 (v1) and 26.9 (v2); 5-8 detections 16.1 and 17.6; >16 detections 6.0 and 11.6. In v1, the falling area-per-detection for big clusters was half chip clipping.

**What this means for the actions below.** Action 1 (a size class at alert time) still stands, and is slightly better: AUC 0.755 and 78% top-decile precision. Use the v2 lookup. The p90 for multi-detection fires is now 300-1,000 ha, so tell officials "possibly several hundred ha" when there are ≥5 day-0 detections. Do not quote a hectare point estimate: within x2 dropped to 41-44%.
- The power law steepens to n^0.61. Use 31.6·n^0.61 ha as the central value.
- The FRE consumption estimate in B8 rises ~18%: 3.83 ha/MW implies ~1.0 t/ha at 3 h per detection [inference].
- Two caveats from USE_AND_LIMITS still apply. The "must touch an alert" rule gives point-based models a small head start against these outlines, and the v2 missed-ground share for large fires has not been re-measured.
- Everything below this section is the v1 analysis from 15 Oct, kept for comparison.

Question: can we give officials a burned-area figure (and outline) for an alert from the VIIRS/MODIS points alone, in the ~3 days before our Sentinel-2/Landsat scar arrives? How accurate is it by fire size, especially for small (<100 ha) low-intensity litter fires?

Already covered elsewhere, so not repeated here: Global Fire Atlas and FEDS/alpha shapes (`burn_dating_validation.md` §6, §11; `spread_from_active_fire.md` B1-B2; FEDS constants in `fire_stopping_and_tracking.md` B1); Laurent et al. 2019 FRP vs fire size (`spread_from_active_fire.md` B5); Padilla 2026 and Pinto 2021 Sentinel-2+VIIRS near-real-time burned area (`alert_burn_scars_fullread.md`, `daily_scar_dating.md` B6); PlanetScope (`high_res_imagery.md`); daily Sentinel-3 SYN dating (`daily_scar_dating.md` A5); OPERA DIST-ALERT (`open_datasets.md` B26).

## Headline findings

1. **Tested on our own data (5,375 VIIRS-seeded scars, 2017-2026, every season held out in turn): VIIRS points predict final scar size only roughly.** Spearman 0.46 on day 0 and 0.51 with all points up to the first clear image. The best model is within a factor of 2 for 47-49% of fires; always guessing the training median gets 44% on scars away from the chip edge and 36% on all scars (v1 figures; see the v2 rerun above). The one-sigma error is about a factor of 3.4. Large fires (100-300 ha) come out at about 0.45x their size and fires under 10 ha at 6-8x: everything is pulled toward ~30-50 ha.
2. **What does work is ranking: is this one big?** A day-0 classifier picks out scars ≥100 ha with AUC 0.75 (base rate 40%). Of the top 10% it flags, 76% are ≥100 ha. Small fires (<10 ha) are found with AUC 0.70.
3. **Rule of thumb from our data: one VIIRS detection means a median scar of ~30 ha (IQR 12-79 ha).** Scar area ≈ 31 × n^0.47 ha, where n is the number of day-0 detections. 20% of single-detection fires still reach ≥100 ha. 77.5% of fires get all their VIIRS detections on day 0, so waiting a day adds little.
4. **Hulls and pixel footprints taken as area are no better than the median guess** (within x2: 43-48%). Convex and concave hulls of 1-2 points collapse to one buffered pixel (11 ha). Use hulls as a search footprint, not as the area.
5. **Published numbers agree that small fires are where points fail.** VIIRS cluster perimeters match reference polygons 94% of the time for fires ≥100 ha but 39% for 10-25 ha, with 63% commission (Dastour 2024). Against ground fire records, VIIRS catches 1.3% of fires <1 ha, 7.7% of 1-10 ha and 25.6% of >10 ha (Coşkuner 2022). The best published individual-fire fit, a convex hull at 1,125 m, has R² 0.54 on fires averaging 2,305 ha (Briones-Herrera 2020).
6. **The FRP/FRE route gives the right order of magnitude but adds nothing over a simple count.** Wooster 2005: 0.368 ± 0.015 kg of fuel per MJ of FRE. Our scars hold a median 3.2 ha per MW of summed VIIRS FRP. If each detection stands for ~3 h of burning, that implies ~1.2 t/ha consumed [inference], close to Roberts 2018's FRE-derived 0.14 kg/m² for African savanna and below our 2-3 t/ha litter load. Summed FRP ranks scars worse than the detection count (Spearman 0.39 vs 0.45).
7. **Faster imagery helps more than better point models.** In 2025-26, 27% of our fires had a clear optical image within 1 day, 51% within 2 and 71% within 3 (2017-19: 19/38/53%). Sentinel-1 is no help yet: one descending track (relative orbit 63) with a 12-day revisit over Ratapani through May 2026; S-1D joins in June 2026, which gives 6 days.

---

## Part A. Our own test (DATA, computed 15 Oct 2026)

Scripts are in `ratapani/fsi/scouting/code/area/`: `build_features.py`, `fit_area.py`, `fit_area_all.py`, `table_lookup.py`, `split_check.py`, and `rerun_v2.py` for v2. `build_features.py` writes `features_750.parquet` to its OUT path; edit OUT before rerunning.

**Setup.** VIIRS points: S-NPP, NOAA-20 and NOAA-21 from `fire-alert-scars/alerts/` (53,259 points). Each event in `event_scars.geojson` whose seed was a VIIRS point (5,375) starts from its own day-0 detections. It then grows FEDS-style, adding VIIRS points within 750 m of any cluster point and within 1 day of that point, from the day before the alert up to the scar's `post_date`. Features: number of detections, distinct overpasses and days; FRP sum and max; union of the true scan × track pixel footprints; convex hull and shapely concave hull (ratio 0.3), each buffered 187.5 m; spatial span. They are computed three ways: day 0 only, days 0-1, and everything up to the first clear image. Target: grown `scar_ha` (also checked against `scar_ha_post` and the split scars in `out/event_scars_split.csv`). Jan-Jun only. Scars flagged `grew_into_large_burn` are dropped, leaving 4,886 scars. Leave-one-season-out over 10 seasons. Models: training median (null), raw geometric areas, a power law on each feature, and LightGBM (300 trees, 15 leaves).

**Caveats on the target.** Part A uses the v1 outlines. In v1, 34% of these scars (1,659) were cut off at the 3 km chip edge, so their areas were lower bounds; see the v2 rerun at the top for the corrected numbers. 19% of v1 scars include ground from neighbouring same-gap fires (split thread). Some of the error is therefore label noise. With the split scars as target, the day-0 count's Spearman rises from 0.45 to 0.50.

**A1. Overall skill (4,886 scars; edge areas used as observed)**

| Model | Spearman | within x2 | median abs log2 error |
|---|---|---|---|
| Training-season median | -0.08 | 0.44 | 1.17 (scored set without edge scars) |
| Raw day-0 footprint union (no fit) | 0.34 | 0.48 | 1.07 (scored set without edge scars) |
| Power law, day-0 footprint union | 0.44 | 0.45 | 1.11 |
| LightGBM, day-0 features + month | 0.46 | 0.47 | 1.08 |
| LightGBM, all points to first image + month | 0.51 | 0.48 | 1.04 |
| LightGBM, day 0, split-scar target | 0.51 | 0.49 | - |

**A2. Error by true scar size (LightGBM, day 0)**

| True scar | n | within x2 | median predicted/true | MAE |
|---|---|---|---|---|
| <10 ha | 601 | 5% | 7.7 | 39 ha |
| 10-30 ha | 874 | 48% | 2.0 | 29 ha |
| 30-100 ha | 1,440 | 72% | 0.92 | 29 ha |
| 100-300 ha | 1,764 | 44% | 0.46 | 98 ha |
| ≥300 ha | 207 | 9% | 0.31 | 228 ha |

On the split-scar target the pattern is the same: <10 ha 10% within x2 (ratio 5.7); 10-30 ha 65% (1.5); 30-100 ha 68% (0.73); 100-300 ha 38% (0.41). Quantile LightGBM 10-90% intervals cover 74% overall, not 80%. Coverage is 94% for 10-30 ha and 92% for 30-100 ha, but only 42% for <10 ha and 35% for 100-300 ha. The median 10-90% interval spans a factor of 14. Intervals are honest only in the middle.

**A3. Lookup table officials could use today (day-0 VIIRS detection count -> final scar, ha)**

| Day-0 detections | fires | p10 | median | p90 | share ≥100 ha |
|---|---|---|---|---|---|
| 1 | 1,554 | 5 | 30 | 162 | 20% |
| 2 | 831 | 8 | 46 | 204 | 26% |
| 3-4 | 757 | 13 | 70 | 224 | 39% |
| 5-8 | 708 | 21 | 112 | 250 | 55% |
| 9-16 | 505 | 28 | 152 | 303 | 72% |
| >16 | 531 | 23 | 178 | 313 | 74% |

(p90 is held down by the ~400 ha chip cap.) Fits: scar_ha = 30.9·n^0.47 (residual factor 3.4); = 6.7·(footprint ha)^0.52; = 23.8·(FRP sum MW)^0.32. At first image: scar_ha_post = 25.8·n^0.49. Area per detection falls with cluster size: median 27 ha for one detection, 20 for two, 16 for 5-8, 6 for >16. Larger fires get revisited more, as Randerson 2012 found for boreal fires (Part B). Window length barely matters: Spearman of scar area with the image gap is only 0.08.

**A4. Ranking skill.** Day-0 LightGBM classifier for ≥100 ha: AUC 0.751 (all points: 0.769); 75.8% precision in the top decile. For <10 ha: AUC 0.705 (base rate 12%). Median scar by month: Jan 16 ha, Feb 27, Mar 42, Apr 35, May 25.

**A5. Time to the first clear optical look after the alert (`post_date` minus alert date)**

| Seasons | median days | ≤1 d | ≤2 d | ≤3 d | ≤5 d |
|---|---|---|---|---|---|
| 2017-19 | 3 | 19% | 38% | 53% | 78% |
| 2020-22 | 3 | 24% | 42% | 59% | 91% |
| 2023-24 | 2 | 32% | 52% | 67% | 90% |
| 2025-26 | 2 | 27% | 51% | 71% | 95% |

**A6. Sentinel-1 GRD over Ratapani (query point 77.6°E, 23.05°N), Planetary Computer STAC, Jan-Jun 2026:** 14 scenes, all descending, relative orbit 63, ~00:45 UTC. They came every 12 days (4 Jan ... 28 May on S-1A), with S-1D first appearing on 28 Jun 2026. Revisit is 6 days from mid-2026 at best.

**Concrete action for us (threads 2 and 5).** Put the A3 table and the p(≥100 ha) score into the live alert ledger (`live.py`) as a provisional "likely size class", with the p10-p90 range. Label it "provisional, replaced by the scar". Do not report a hectare figure from hulls. Expected effect: officials get a size class at alert time that is right about 3 times in 4 for the big ones. Effort: low (half a day).

---

## Part B. Sources

### B1. Giglio, van der Werf, Randerson, Collatz & Kasibhatla 2006, "Global estimation of burned area using MODIS active fire observations", *ACP* 6:957-974. https://acp.copernicus.org/articles/6/957/2006/ **FULL**
- The Terra MODIS fire count is linked to 500 m burned area per 1° cell and month: BA = α × corrected fire count, with α depending on tree cover and **mean fire-pixel cluster size**. Regression trees are fitted per region.
- **South Asia: α = 2.9 km² per Terra fire pixel, r = 0.75 (N = 531), regression tree r = 0.83.** Other regions range from 0.29 (SH South America, r = 0.35) to 6.6 km²/pixel (Central Asia). In savannas α falls as tree cover rises. Of the 60 splits across the regional trees, 68% use vegetation-cover variables and 28% use mean cluster size, but the cluster-size splits cut deviance most.
- One-sigma uncertainties come from regressing squared residuals on fire count. They are 10-40% for regions with large burned area and much larger where burned area is ≤100 km²/yr. Cloud-corrected counts did worse because the correction over-corrects.
- **Concrete action (thread 2/5).** Our α from A3 is ~0.3 km² per VIIRS detection (single detections) falling to 0.06 for big clusters. Cluster size is the strongest single modifier, as Giglio found. Add a cell tree-cover / teak-share feature (fuel thread maps) to the A1 model. Expected gain small [inference].

### B2. Randerson, Chen, van der Werf, Rogers & Morton 2012, "Global burned area and biomass burning emissions from small fires", *JGR Biogeosciences* 117:G04012. eScholarship PDF. **FULL**
- Small-fire burned area = FC_out × α × γ. FC_out counts MODIS active fires more than 1 km outside MCD64A1 scars. α is burned area per in-scar active fire. γ = (dNBR_out − dNBR_control)/(dNBR_in − dNBR_control) scales for the smaller scars of out-of-scar fires.
- α is <1 km² per active fire in boreal forest (more overpasses, high fuel) and 2-5 km² in tropical savannas (fast, short fires). Across regions FC_out varies 26-fold, α 5-fold and γ 2.8-fold. Out-of-scar fires had lower FRP. The authors did not use FRP to set γ because "it remains uncertain how instantaneous fire behavior may be related to the final size of an individual fire".
- Small fires raised global burned area by 35% (345 to 464 Mha/yr); sensitivity range 24-54%; Southeast Asia +90%. Formal uncertainty was not possible.
- **Concrete action (thread 2).** The γ idea maps directly onto our "none_visible" alerts. Compute dNBR in a 375 m disk around those alerts against control points. The ratio to "yes"-scar dNBR gives the sub-scar burned fraction, which is a cheap area for the 5-11% of alerts with no scar. Effort: low (`eval_chip.py` already makes controls).

### B3. Briones-Herrera, Vega-Nieva, Monjarás-Vega et al. (incl. Parks) 2020, "Near real-time automated early mapping of the perimeter of large forest fires from the aggregation of VIIRS and MODIS active fires in Mexico", *Remote Sens.* 12:2061. **FULL** (upgrades the ABSTRACT ONLY entry in `burn_dating_validation.md` §10)
- Monthly VIIRS+MODIS points are grouped into convex hulls with at least 3 points at an aggregation distance d, and fitted as BA = a·hull to 5,218 MCD64A1 perimeters from 2012-2018 (mean 2,305 ha, SD 3,200).
- Individual fires: d = 750 m: a = 1.73, R² 0.41, RMSE 1,368 ha. d = 1,000 m: a = 1.27, R² 0.50. **d = 1,125 m: a = 1.14, R² 0.54, RMSE 1,185 ha, bias −9 ha (best).** d = 1,500 m: a = 0.82, R² 0.41. Monthly totals: R² 0.94 (750/1,000 m).
- Against Sentinel-2 dNBRcorr > 100 (from 100 field plots) for three fires of 29,329, 12,142 and 2,631 ha, the hulls agreed 93%, 88% and 96%, against 85%, 82% and 80% for MCD64A1. The hull perimeter also seeds the Sentinel-2 scar code, with unburned reference taken 3-5 km out.
- **Concrete action (thread 2).** Even for fires 20x bigger than ours, a hull explains only about half the variance. For us, use the 1,125 m hull, buffered, as the search window for the first post-fire image, and the 3-5 km ring for the chip's unburned reference. Effort: low.

### B4. Dastour, Bhuian, Ahmed & Hassan 2024, "Active fire clustering and spatiotemporal dynamic models for forest fire management", *Fire* 7:355. **FULL**
- Alberta/NWT boreal, 2015-2021, against NBAC perimeters. Points are grouped with DBSCAN (radius 750-3,000 m) and outlined with α-shape concave hulls (α 0.1-0.5).
- **Matching by size (VIIRS):** ≥100 ha 94.2% matched (point commission 8.6%); 50-100 ha 67.3% (37.3%); 25-50 ha 48.4% (61.0%); 10-25 ha 38.8% (63.5%). VIIRS+MODIS: 96.0%, 72.7%, 54.8% and 42.9%.
- Area matching, VIIRS: 72.2% at 750 m/α 0.1 (area commission 21.0%) rising to 84.7% at 1,500 m/α 0.5 (commission 28.8%). Combined sensors: 85.1% at 1,500 m/α 0.1 (commission 28.0%), the recommended setting. A minimum of 4 points changes nothing.
- **Concrete action (thread 4o/2).** Larger radius and α buy area match at the cost of ~1 point of commission per point of match. For burn-probability maps, prefer a pixel-footprint union (our A1 best raw) to α-shapes. Effort: none.

### B5. Su & Yu 2026, "A global dataset of individual fire events (2012-2025) derived from VIIRS active fire product", *ESSD Discuss.* essd-2026-387. **FULL** (preprint). Data: https://zenodo.org/records/21807914 (834 MB zip, CSV/Parquet, CC BY 4.0)
- S-NPP VIIRS on a 0.005° grid, monthly patches merged across months when they overlap by ≥2 cells and are ≤5 days apart. Clusters of <3 unique pixels are dropped. The released area is **pixel accumulation**. They found convex hulls overestimate by taking in unburned land; concave hulls preserve fronts but need tuning.
- Against MTBS (1,392 matched fires): log-R² 0.78, median bias −4.23 km², MedAE 5.49 km², mean bias −32.4 km². FPA-FOD: log-R² 0.64 (N 1,461). CNFDB: 0.50 (N 737). Australia: 0.22 (N 707), rising to 0.66 when split events are summed. Precision is ~0.1 for small fires (<4 km²) and climbs to 0.55-0.8 above 10 km². Duration is underestimated by a median of 24 days. Fields include ignition, start/end, area_km2, expansion rate, FRP and GFED5 fire type, plus US-calibrated area_ref_km2 with p90 bounds.
- **Concrete action (threads 1, 4).** Of limited use for Ratapani: the ≥3-pixel filter would drop ~45% of our fires (1-2 detections). It could give a uniform all-India event table for the all-MP model's "fire size" covariate. Effort: medium (834 MB).

### B6. Coşkuner 2022, "Assessing the performance of MODIS and VIIRS active fire products in the monitoring of wildfires: a case study in Turkey", *iForest* 15:85-94. https://iforest.sisef.org/contents/?id=ifor3754-015 **FULL** (journal HTML via fetch)
- Turkish Forest Service ground records, 2015-2019 (10,966 fires: 78.5% <1 ha, mean 0.18 ha; 17.5% 1-10 ha, mean 3.2 ha; 4.0% >10 ha, mean 70.6 ha). Matched within one pixel.
- **VIIRS detection rate: <1 ha 1.3% (closed forest 0.8%), 1-10 ha 7.7% (closed forest 9.8%), >10 ha 25.6% (closed forest 42.9%).** MODIS: 0.6%, 3.2% and 16.6%.
- **Concrete action (threads 1, 5).** The field-alert thread's ~0.15 ha guard-confirmed fires are almost all invisible to VIIRS. Every point-based area is conditional on detection. When reporting VIIRS-derived totals to officials, show that a VIIRS-free beat-day is not proof of no fire.

### B7. Fornacca, Ren & Xiao 2017, "Performance of three MODIS fire products (MCD45A1, MCD64A1, MCD14ML) and ESA Fire_CCI in a mountainous area of northwest Yunnan, China, characterized by frequent small fires", *Remote Sens.* 9:1131. **FULL**
- About 99% of fires are human-caused and often <50 ha; Landsat reference fires for 2006 and 2009. MCD14ML active fires had the best producer's accuracy: 43% and 47% overall, **61% and 66% for fires >50 ha**, but only 13.3% (2006) for 12.5-25 ha. F1 was 0.26 and 0.24. Burned-area products did worse: MCD64A1 detected 0-2.9% of fires <25 ha. Merging active fires and MCD45A1 raised producer's accuracy to 55-59%.
- **Concrete action.** Confirms that point products beat coarse burned-area products for small human fires. Do not add MCD64A1/VNP64A1 as an early-area input.

### B8. Wooster, Roberts, Perry & Kaufman 2005, "Retrieval of biomass combustion rates and totals from fire radiative power observations", *JGR* 110:D24311. EPA mirror PDF. **FULL**
- **Fuel consumed (kg) = 0.368 (±0.015) × FRE (MJ)**, and combustion rate (kg/s) = 0.368 × FRP (MW). FRE vs mass gives r² 0.98 (n = 29); FRP vs rate r² 0.90 (n = 178). There is no significant difference by fuel type, mostly Miscanthus plus others. During combustion the instantaneous factor is 0.464 (±0.018) kg/MJ; the 0.368 includes radiation from the cooling bed after flaming. Fires radiate 14 ± 3% of their heat yield in a form a MIR imager sees.
- **Our numbers [inference].** Litter consumption of ~2 t/ha needs ~5,400 MJ of FRE per ha. A front burning 1 ha per hour radiates ~1.5 MW, which matches the 2-6 MW VIIRS FRP of our detections. Our median 3.2 ha per MW of summed FRP implies ~4.9 h of burning per MW-snapshot at 2 t/ha, or ~1.2 t/ha consumed if each detection represents 3 h.
- **Concrete action (thread 3, fuel map).** Compute a proper FRE per scar by integrating FRP over all overpass times (S-NPP, NOAA-20, NOAA-21, MODIS, and the geostationary FRP in `fire_detection_sources.md` §2). Then FRE×0.368/scar area = consumed fuel per ha, a satellite-only check on the 2-3 t/ha litter map: expect 1-2 t/ha if the map is right [inference]. Effort: medium.

### B9. Roberts, Wooster, Xu & He 2018, "Fire activity and fuel consumption dynamics in Sub-Saharan Africa", *Remote Sens.* 10:1591. **FULL**
- SEVIRI FRP-PIXEL FRE (0.37 kg/MJ) is compared with MODIS burned area and pre-fire fuel load (accumulated MODIS PSN). Per-fire FRE fuel consumption tracks fuel load (r = 0.96), but **mean FRE-derived fuel consumption per unit area is only 0.14 kg DM/m²**, "far lower" than expected. They read this as SEVIRI missing low-intensity FRE or the coefficient needing revision.
- **Concrete action (thread 3).** Expect FRE-based consumption to read low for our litter fires (polar-orbiter sampling misses most of the burn). Use it as a relative fuel index across beats, not an absolute load.

### B10. Ramo, Roteta, Bistinas, van Wees, Bastarrika, Chuvieco & van der Werf 2021, "African burned area and fire carbon emissions are strongly impacted by small fires undetected by coarse resolution satellite data", *PNAS* 118:e2011160118 (PMC7936338). **FULL**
- Sentinel-2 FireCCISFD11 (20 m) found 4.9 Mkm² burned in Africa in 2016, against MCD64A1's 2.7. **87% of the difference comes from fires <100 ha**, which are 41% of Sentinel-2 burned area but ~5% in coarse products. Sentinel-2/MODIS ratio for <100 ha fires is 23x in croplands; for >100 ha it is ~1.1x.
- **Concrete action.** Supports keeping the 20 m scar as truth and treating any point-derived area as provisional for the <100 ha majority (61% of our scars).

### B11. Liu, Marlier, Karambelas, Jain, Singh, Singh, Gautam & DeFries 2019, "Missing emissions from post-monsoon agricultural fires in northwestern India", *Environ. Res. Commun.* 1:011007 (EarthArXiv postprint). **FULL**
- Punjab/Haryana crop fires: MCD64A1 omission is 33-46% against VIIRS-located fires, and Landsat-hybrid ModL2T 1-8%. Burned area is 44 ± 21% higher than MCD64A1. VIIRS detected fires in 68% of 0.02° cells vs 54% for MODIS. Same-day omission against fine imagery was 95%, falling to 75% for the season. Aqua fire counts are 647% higher than Terra's because of afternoon timing.
- **Concrete action.** An Indian small-fire case where overpass timing dominates detection. Our NOAA-21/S-NPP/NOAA-20 ~13:30 passes are the right ones; no change.

### B12. Ban, Zhang, Nascetti, Bevington & Wulder 2020, "Near real-time wildfire progression monitoring with Sentinel-1 SAR time series and deep learning", *Sci. Rep.* 10:1322 (PMC6987169). **FULL**
- Three large crown fires (Elephant Hill, Camp, Chuckegg Creek). VH backscatter drops 2-3 dB in burned forest, while grassland VH is unchanged. A CNN on VV+VH change reached F1 ~0.87-0.89 and kappa ~0.76 at one site, against log-ratio Otsu ~0.6-0.77. Agricultural change gives VV false alarms.
- **Concrete action.** Not for us now. Over Ratapani it is one track with a 12-day revisit (A6), and our >99% low-severity litter fires leave the teak canopy, which dominates C-band, intact [inference]. Revisit once S-1D gives 6 days.

### B13. Belenguer-Plomer, Tanase, Fernandez-Carrillo & Chuvieco 2019, "Burned area detection and mapping using Sentinel-1 backscatter coefficient and thermal anomalies", *RSE* 233:111345. **PARTIAL** (published abstract and summaries; the gofcgold PDF failed TLS/503, ebuah is bot-blocked)
- MODIS/VIIRS hotspots seed a Reed-Xiaoli change detector on Sentinel-1, with random forests where there are no hotspots. 18 sites, 21 Mha, Landsat/Sentinel-2 reference: **mean Dice 0.59 ± 0.06, omission 0.43, commission 0.37**, which is +0.13 Dice over MCD64A1. Best in forests, worst in grasslands.
- **Concrete action.** Same as B12; hotspot seeding is already what our optical chip does.

### B14. Oliva & Schroeder 2015, "Assessment of VIIRS 375 m active fire detection product for direct burned area mapping", *RSE* 160:144-155. **ABSTRACT ONLY** (closed; no repository copy found)
- Consecutive VIIRS 375 m detections were aggregated into burned area at 10 sites and checked against Landsat-8. Accuracy is best for large, long-duration forest fires and worst (highest omission and commission) in grassland, savanna and agriculture. The Rim Fire agreed well with airborne data.
- **Concrete action.** None beyond A1; our litter fires behave like their "worst" class (short, low intensity).

### B15. Other sources checked
- "Active fire-based dating accuracy for Landsat burned area maps is high in boreal and Mediterranean biomes and low in grasslands and savannas", *ISPRS J.* 2024 (doi 10.1016/j.isprsjprs.2024.02.014). **ABSTRACT/SNIPPET ONLY**. Snippet: for VIIRS the lowest agreement starts at 31.4% for burned areas <100 ha, against 80.3% for >5,000 ha.
- "Enhancing burned area monitoring with VIIRS dataset: a case study in Sub-Saharan Africa", *Science of Remote Sensing* 2024 (doi 10.1016/j.srs.2024.100165). **NOT READ** (403).
- Consensus search quota was exhausted (no results).

---

## Datasets and code

| Item | What | Access | Use |
|---|---|---|---|
| `fire-alert-scars/alerts/viirs-*.csv` | VIIRS S-NPP/NOAA-20/NOAA-21 points with scan/track | local | features for A1-A4 |
| `fire-alert-scars/event_scars.geojson`, `out/event_scars_split.csv` | grown and split event scars | local | targets |
| Our scripts (`build_features.py`, `fit_area*.py`, `table_lookup.py`, `split_check.py`, `rerun_v2.py`) | area-from-points features, LOYO models, lookup, v1 vs v2 | `ratapani/fsi/scouting/code/area/` | port to `live.py` |
| Su & Yu 2026 VIIRS fire events | global events 2012-2025, pixel-accumulated area, FRP, durations | https://zenodo.org/records/21807914 | all-MP size covariate |
| Sentinel-1 GRD calendar | relative orbit 63 desc., 12 d (6 d from Jun 2026) | Planetary Computer STAC `sentinel-1-grd` (keyless) | recheck 2027 |
| Giglio 2006 α table | burned km² per MODIS fire pixel by region (South Asia 2.9) | ACP OA | prior / sanity check |
| Wooster 2005 coefficient | 0.368 ± 0.015 kg/MJ | JGR | FRE -> consumed fuel |

## Reading status
FULL: 12 (Giglio 2006, Randerson 2012, Briones-Herrera 2020, Dastour 2024, Su & Yu 2026, Coşkuner 2022, Fornacca 2017, Wooster 2005, Roberts 2018, Ramo 2021, Liu 2019, Ban 2020). PARTIAL: 1 (Belenguer-Plomer 2019). ABSTRACT/SNIPPET ONLY: 2 (Oliva & Schroeder 2015; ISPRS 2024 dating). Not read: 1.

## Ranked action list (gain, effort)

1. **Size class at alert time in `live.py` (threads 5, 2).** Add the A3 lookup (detections -> median and p10-p90 scar) plus the day-0 p(≥100 ha) classifier (AUC 0.75; 76% precision in the top decile). Label it provisional and replace it with the scar when one exists. Gain: medium (the only thing officials get in days 0-3 for ~50% of fires). Effort: low.
2. **Use the earliest image even when partial (thread 2).** 27% of 2025-26 fires have a clear look within 1 day and 51% within 2. Issue a first-image scar marked provisional (we already keep `scar_ha_post`), seeded and windowed by a 1,125 m hull of the points (B3). Gain: medium. Effort: low.
3. **Retrain on the split scars and drop chip-edge lower bounds or treat them as censored (thread 2 model).** The split target already lifts Spearman 0.45 -> 0.50. Add tree cover/teak share, last-year burn, distance to fire lines, time of first detection and scan angle. Expect within-x2 to go from ~49% to the mid-50s at best [inference]. Gain: small. Effort: low-medium.
4. **FRE per scar as a satellite-only fuel check (thread 3).** Integrate FRP over all polar and geostationary passes. FRE×0.368/area should give 1-2 t/ha if the litter map is right; use it as a relative index (B8, B9). Gain: small-medium. Effort: medium.
5. **Area for "none_visible" alerts via Randerson's γ (thread 2).** Use dNBR in the 375 m disk vs controls vs "yes" scars to give a sub-20 m burned fraction instead of zero. Gain: small. Effort: low.
6. **Use the conditional size distribution as the prior in the 24/48 h burn-probability maps (thread 4o).** Calibrate the total burned mass of the map to the A3 median for that detection count. Gain: small. Effort: low.
7. **Do not invest in hull or α-shape areas or Sentinel-1 for Ratapani now.** Hulls are no better than the median (A1; B4 commission 63% at 10-25 ha). S-1 has a 12-day single track and litter fires barely change C-band (B12, B13). Revisit S-1 when the 6-day S-1A+S-1D calendar is in place.
8. **Su & Yu 2026 events for the all-MP model (thread 1).** Pixel-accumulated fire size per event as a division-level covariate. Note that their ≥3-pixel filter drops ~45% of small fires. Gain: small. Effort: medium (834 MB).
