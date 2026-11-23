# How fires differ across MP forest types, and what must change when Ratapani rules go state-wide (scouting round 14, topic "types", 16 Oct 2026)

Scope: sal forests in the east, the teak belts, mixed dry deciduous and thorn forest in the north and west, and bamboo. For each I cover leaf-fall timing, season peak, return interval, fire size, human causes, how well burn scars can be seen, and VIIRS density. I also flag the divisions where Ratapani-calibrated rules are likely to fail: the 15 Feb-15 Jun window, the leaf-fall curve and the scar method.

Most of the evidence is our own data, computed today. Published studies of fire by forest type for MP are thin. Most are MODIS hotspot summaries or abstracts behind paywalls. Reading status for each source is given in its heading. **[inference]** marks my own reasoning.

Code and outputs: `code/mp_types/` (scripts `t1`-`t7`, `un7z.py`; tables in `code/mp_types/out/`). The master table is `code/mp_types/out/division_types_final.csv`: one row per division, 46 columns plus a `flags` column.

---

## Headline findings

1. **We now have an MP-wide forest-type layer, and it can be used today.** Roy et al. 2015 Vegetation Type Map (Zenodo 11615011, 60 m) was decoded with a 20-line stdlib LZMA2 script (`un7z.py`; no 7-Zip needed) and joined to all 8,973 beats (`out/beat_vtm.csv`: hectares of each class in each beat).
   - Inside beats the classes are: dry deciduous 20.5%, agriculture 19.1%, degraded 11.4%, teak-mixed moist deciduous 11.2%, sal 10.2%, moist deciduous 8.7%, scrub 5.7%, teak 3.5%, bamboo 1.8%, and a long tail of *Anogeissus pendula*, *Acacia catechu*, *Boswellia*, *Hardwickia* and grassland.
   - 19% of beat area is mapped as farmland.
2. **Fire density by type (S-NPP, 2014-26, points inside beats, per 100 km² per year):**
   - Bamboo 55, teak 42, sal 41, moist mixed 37, dry mixed 27, degraded 28.
   - Thorn, scrub, grass and the northern dry types: 13.5. Farmland inside beats: 13.
   - Across divisions density runs from **75 (Obedullahganj, i.e. Ratapani) down to 0.3 (Morena)**. Ratapani is the second-highest of 87 divisions, so it is not a typical division.
3. **Ratapani sits at the early end of MP's fire season.**
   - Ratapani: median fire 27 Mar (DOY 86), peak week 13.
   - Sal belt: median DOY 95 (5 Apr). North and thorn divisions: DOY 104 (14 Apr), peak weeks 15-16.
   - Gwalior, Shivpuri, Datiya, Tikamgarh and Bhind run 3-5 weeks later than Ratapani, with 10-38% of points after 15 May.
   - Sal forest has almost no fire before 15 Feb (0.7% of points, Singrauli excluded). Teak has 5.2% and Ratapani 7.8%.
4. **Leaf fall differs a lot by type, but it barely sets the fire date.** I measured MODIS NDVI curves at 5,220 random forest pixels, seasons 2022-23.
   - The date by which half the season's greenness loss is done:
     - north-dry and degraded: about 28 Dec
     - dry mixed: 3 Jan
     - teak: 17 Jan
     - moist mixed: 24 Jan
     - bamboo: 31 Jan
     - **sal: 7 Feb**
   - By 15 Feb sal has lost only 58% of its greenness; teak and degraded forest have lost 70-76%.
   - Sal keeps the greenest dry-season canopy (NDVI 0.39 against 0.27-0.30) and re-flushes from late April.
   - Across 77 divisions, Spearman between the leaf-fall half-date and the median fire date is only **0.14**. The fire peak lands in late March to mid-April whatever the leaf timing.
   - The leaf-fall date does predict **early fires**: earlier leaf fall goes with a larger share of fires before 15 Feb (ρ = −0.47).
   - The 2023 leaf fall came about 3 weeks earlier than 2022 in every type. The year-to-year shift is as large as the shift between types.
5. **The scar method transfers well. Sal is only a few points worse.** I joined the existing 15 Oct all-MP scar run (2,905 sampled fires + 12,586 tiger-reserve fires) to forest type.

   | Forest type | Scar found (sample) | Scar found (tiger reserves) | Median scar (sample) | Median scar (tiger reserves) |
   |---|---|---|---|---|
   | Sal | 82% | 83% | 39 ha | 33 ha |
   | Teak | 88% | 80% | 47 ha | 63 ha |
   | Dry mixed | 83% | 84% | 43 ha | 77 ha |
   | North-dry | 82% | 82% | 30 ha | 64 ha |

   - Controls (no fire) show a scar 2-6% of the time in every type.
   - The real weak spots are elsewhere: **February in moist mixed (55%) and sal (64%)**, and June in teak (57%).
   - Thorn divisions with farm mosaic also do badly: Shajapur 33%, Morena 50%, Kuno, Rewa and Satna about 68%. Kanha is 72%.
6. **Three divisions have fire regimes Ratapani rules will mis-handle outright.**
   - (a) **Singrauli:** 22% of S-NPP points are FIRMS `type = 2` (static land source). 63% are at night, with FRP about 1 MW. These are coal-mine and industrial heat inside sal beats. **Mask these before training.**
   - (b) **Kuno-Palpur:** the share of fires before 15 Feb rose from 7% (2014-22) to 29% (2023-26): 69% in 2023, 27% in 2025, 59% in 2026. These are daytime fires in *Anogeissus*/dry deciduous after the cheetah project began. This looks like a new early-burning regime **[inference: management burns; not confirmed in any source I could open]**.
   - (c) **Satpura TR:** the same jump, 4% to 23% (40-42% in 2023, 2024 and 2026).
   - Kanha shows early burning every year (10-37% before 15 Feb). This matches the reported routine winter "early/cool burning" of meadows in Kanha, Bandhavgarh and other tiger reserves.
   - A 2019-21-train / 2022-24-test per-division model will miss these shifts.
7. **The weather-year signal does not carry north.**
   - The correlation of a division's yearly fire count with Ratapani's is 0.83 (median) in the teak belt, 0.75 in the sal belt and **0.39 in the north**. It is 0.04 in Sheopur, 0.23 in Shivpuri and 0.27 in Gwalior.
   - Ratapani's "which years are bad" learning does not transfer to the north and west. **[inference]** Those divisions need their own weather terms, or a pooled model with region-specific weather interactions.
8. **Fire return interval and repeat burning follow density almost one-for-one (ρ = 0.90).**
   - Repeat-burn share (cells burning in year Y that also burned in Y−1): Ratapani 22%, teak belt 14%, sal belt 15%, north 5%.
   - Mean interval between burns, among cells that burn at all: Ratapani 4.9 yr, teak and sal 6.7 yr, north 10 yr.
   - The "burned last year" feature that drives the Ratapani model will be much weaker in the north.
9. **North and west divisions are data-starved for a per-division model.** 14 divisions have under 10 S-NPP points per 100 km² per year (Morena 0.3, FDCM Vidisha 0.1, Rajgarh, Barwani, Shajapur, Tikamgarh, Mandsaur, Sheopur, Datiya, Jhabua). In 8 of them over 35% of points fall on VTM farmland inside beats.
10. **Sal and bamboo fires look different from orbit.**
    - Sal: night share 35%, median FRP 3.65 MW (Singrauli excluded).
    - Bamboo: night share 49%, median FRP 3.0 MW.
    - Dry mixed and north-dry: night share 25-26%, FRP about 5 MW.
    - **[inference]** These are lower-intensity, longer-lasting fires under canopy. That fits the 44%-missed-pass problem in thread 4: such fires keep burning between detections.

---

## Part A. Our own analyses (DATA, computed 16 Oct 2026)

### A1. Inputs and method
- **VIIRS:** `fire-alert-scars/alerts_mp/` (FIRMS SP archive, Jan-Jun). Three satellites; 657,897 points fall inside a beat polygon (`t1_join.py`). Times were converted to IST.
- **Main statistics** use **S-NPP only, 2014-26 (13 seasons)**, so all divisions have the same sensor and years. NOAA-20 2019-26 is the cross-check (`t6_checks.py`).
- **Forest area:** the sum of `Beat_Ar` per division, 91,283 km² in total.
- **Forest type:** VTM class at each point and the class mix of each beat (`t2_vtm.py`).
  - Groups: sal = classes 24/27/36; teak = 25/28/37; dry_mixed = 26; moist_mixed = 23; degraded = 106; bamboo = 30/40; north_dry = thorn, scrub, grass, *Anogeissus*, *Acacia*, *Boswellia*, *Hardwickia*, *Ziziphus* and savannah (29, 46, 49, 53-55, 116, 120-124, 132, 135).
- **Per-division metrics** (`t3_division.py`):
  - peak week: 7-day bins from 1 Jan, 3-bin smoothed
  - percentiles of the fire date
  - shares before 15 Feb, after 15 May and after 15 Jun
  - night share and median FRP
  - repeat-burn share on a 0.005° grid (about 500 m)
  - mean interval between burns among burnt cells
  - events: DBSCAN with eps 0.8 km in (km, km, 0.75 × days), so points within about 0.8 km and about 1 day join
  - annual CV, and the correlation of yearly counts with Obedullahganj
- **Leaf-fall curve** (`t4_ndvi.py`, `t4b_leaf_curve.py`):
  - MOD13A1 + MYD13A1 NDVI at 500 m, an effective 8-day series, filtered to pixel_reliability ≤ 1.
  - Read from Planetary Computer COGs; the public SAS token is fetched at run time and never stored.
  - 60 random VTM forest pixels per division, seasons 2022 and 2023.
  - Loss fraction = (Oct-Dec max − NDVI) / (Oct-Dec max − Mar-May 10th percentile).
  - **Caveat:** MODIS 500 m mixes canopy, understorey and grass. The curve is a canopy-plus-floor greenness loss, not litterfall.

### A2. Fire regime by forest type (S-NPP 2014-26; `out/type_regime.csv`)

| Group | km² in beats | pts/100 km²/yr | median date | 10th-90th pct date | peak wk | before 15 Feb | after 15 May | night | FRP median | repeat-burn |
|---|---|---|---|---|---|---|---|---|---|---|
| Teak | 14,248 | **42.2** | 30 Mar (89) | 1 Mar-25 Apr | 13 | 5.2% | 3.0% | 33% | 4.1 | 13.0% |
| Sal | 10,006 | **41.4** | 5 Apr (95) | 22 Mar-3 May | 14 | 2.3% (0.7% without Singrauli) | 5.9% | 39% (35%) | 3.4 (3.65) | 14.4% |
| Bamboo | 1,636 | **55.2** | 3 Apr (93) | 14 Mar-27 Apr | 13 | 3.1% | 3.7% | 51% | 2.8 | 13.9% |
| Moist mixed | 8,083 | 36.7 | 3 Apr | 14 Mar-27 Apr | 14 | 1.8% | 3.3% | 31% | 4.3 | 10.0% |
| Dry mixed | 19,133 | 27.2 | 31 Mar | 4 Mar-28 Apr | 13 | 4.5% | 3.7% | 26% | 5.0 | 10.4% |
| Degraded | 10,621 | 27.7 | 30 Mar | 1 Mar-27 Apr | 13 | 5.4% | 3.5% | 31% | 4.3 | 10.3% |
| North-dry (thorn/scrub/grass) | 9,886 | 13.5 | 4 Apr | 26 Feb-4 May | 14 | 7.0% | 6.3% | 32% | 4.6 | 7.5% |
| Farmland inside beats | 18,025 | 13.0 | 4 Apr | 8 Mar-3 May | 14 | 4.5% | 5.3% | 33% | 4.3 | 5.8% |

Single small classes (`out/type_density.csv`):
- *Hardwickia* (228 km²): 90 pts/100 km²/yr, median DOY 81 (22 Mar). It is the earliest and densest class.
- Teak-mixed dry deciduous: 48. Sal-mixed dry deciduous: 49.
- *Anogeissus pendula*: 9.8. *Acacia catechu*: 13.7. Thorn forest: 4.7, with 35% of its points after 15 May.

### A3. Leaf-fall curves (`out/leaf_curve_type.csv`, `out/leaf_curve_type_weekly.csv`)

| Group | NDVI Oct-Dec | NDVI Mar-May (dry) | 50% of loss reached | 80% reached | loss done by 15 Feb | by 15 Mar |
|---|---|---|---|---|---|---|
| North-dry | 0.67 | 0.27 | 28 Dec | 7 Mar | 70% | 84% |
| Degraded | 0.72 | 0.27 | 28 Dec | 21 Feb | 76% | 90% |
| Dry mixed | 0.74 | 0.28 | 3 Jan | 28 Feb | 73% | 87% |
| Teak | 0.77 | 0.30 | 17 Jan | 7 Mar | 70% | 88% |
| Moist mixed | 0.77 | 0.32 | 24 Jan | 14 Mar | 64% | 85% |
| Bamboo | 0.82 | 0.36 | 31 Jan | 14 Mar | 62% | 84% |
| **Sal** | **0.82** | **0.39** | **7 Feb** | **14 Mar** | **58%** | 82% |

- **Green-up:** after about 25 Apr, sal and bamboo lose about 18-20% of their maximum loss again (re-flush): the fraction falls from 0.98 to 0.80 by end May. Teak recovers by about 10%; north-dry and degraded stay dry. This matches the "sal sheds Mar-Apr and flushes quickly" pattern.
- **By year:** in 2023 every type hit the 50% point 14-21 days earlier than in 2022 (sal 21 Feb in 2022 against 31 Jan in 2023; teak 24 Jan against 10 Jan).
- **By division** (`out/leaf_curve_division.csv`): the 50% date runs from **2 Dec (Barwani, Jhabua; Nimar and Jhabua in the south-west)** to **7-21 Feb (Kanha, Satpura TR, Sanjay-Dubri, BTR, North and South Balaghat)**. Ratapani (Obedullahganj) is 24 Jan, in the middle.

### A4. Region medians (`t7_final_table.py`; Singrauli excluded)

| Region (rule used) | Divisions | Forest km² | pts/100 km²/yr | peak wk | median DOY | before 15 Feb | after 15 May | night | FRP | repeat-burn | mean interval | yearly-count corr. with Ratapani | leaf 50% | dry NDVI | scar found |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Ratapani (Obedullahganj) | 1 | 1,717 | 74.7 | 13 | 86 | 7.8% | 0.8% | 30% | 4.3 | 22% | 4.9 yr | 1 | 24 Jan | 0.28 | 88% |
| Teak belt (teak ≥ 30%) | 15 | 17,794 | 41.3 | 13 | 87 | 4.9% | 2.3% | 35% | 4.1 | 14% | 6.8 yr | 0.83 | 10 Jan | 0.28 | 89% |
| Sal belt (sal ≥ 30%) | 11 | 12,840 | 39.6 | 14 | 95 | 0.3% | 4.2% | 31% | 3.8 | 15% | 6.7 yr | 0.75 | 31 Jan | 0.40 | 80% |
| North/west thorn (north-dry ≥ 25%) | 14 | 12,300 | 6.2 | 15.5 | 104 | 2.5% | 10.0% | 16% | 6.3 | 5% | 10.1 yr | 0.39 | 3 Jan | 0.28 | 75% |
| All other mixed | 46 | 46,190 | 24.7 | 14 | 92.5 | 2.3% | 3.5% | 31% | 4.2 | 11% | 7.8 yr | 0.70 | 10 Jan | 0.29 | 90% |

- **Teak belt:** Obedullahganj, Raisen, Sehore, Bhopal, Indore, Khandwa, FDC Khandwa, South Betul, Hoshangabad, Burhanpur, South/West Chhindwara, Chhindwara Project, Chhatarpur, Harda.
- **Sal belt:** North/South Balaghat, both Lamta Projects, Kundam Proj Katni, Umaria, Dindori, East Mandla, Sanjay-Dubri, Kanha TR, Sidhi.
- **North/west thorn:** Morena, Bhind, Gwalior, Datiya, Shivpuri, Madhav NP, Kuno-Palpur, Ashok Nagar, Shajapur, Rajgarh, Tikamgarh, Rewa, North Panna, Panna TR.
- Satpura TR (VTM: 27% teak, 13% sal) falls in "mixed" by these thresholds, but its fire regime looks like the sal belt's.

### A5. Divisions where a Ratapani-calibrated rule is likely to fail (`flags` in `division_types_final.csv`)

Rules behind the flags:

| Flag | Fires when |
|---|---|
| STATIC | FIRMS type-2 share > 5%, or > 5% of points in cells burning ≥ 9 of 13 years |
| EARLY | > 10% of S-NPP points before 15 Feb, or > 12% for NOAA-20 2019-26 |
| EARLY-BURN REGIME CHANGE | share before 15 Feb in 2023-26 at least 10 points higher than in 2014-22 |
| LATE | > 8% of points after 15 May |
| LATER median | median date ≥ 14 days after Ratapani |
| Leaf fall | ≥ 14 days later, or ≥ 28 days earlier, than Ratapani |
| Green canopy | dry-season NDVI ≥ 0.38 |
| Scar found | scar found < 75% |
| FARM | > 35% of points on VTM farmland |
| SPARSE | < 5 pts/100 km²/yr |

Counts: 29 divisions have no flag, 24 have one and 34 have two or more.

| Division | What fails, and why |
|---|---|
| **Kanha TR** (7 flags) | Season window: 11% of fires before 15 Feb (managed early burning; FRP of those points 6.5 MW, 95% daytime) and 10% after 15 May. Median 12 Apr, 16 days after Ratapani. Leaf fall is 14 days later (sal 56%). Dry NDVI 0.50, the highest in MP. Scar found 72%, the lowest tiger reserve in the sample. Density is only 12/100 km²/yr despite sal. |
| **Singrauli** | Static industrial heat: 22% type-2, 63% at night (65% for NOAA-20); its January points have FRP 1.1 MW and are 90% night. Mask type-2 points and persistent cells before every step: model labels, scars, density. |
| **Kuno-Palpur** | Early-burn regime change after 2022: 69%, 27% and 59% of points before 15 Feb in 2023, 2025 and 2026; daytime; in *Anogeissus*/dry deciduous. The 2019-21 training years do not contain this behaviour. NOAA-20 shows 22% before 15 Feb. Scar found 68%. |
| **Satpura TR** | Early-burn jump: 40%, 42% and 41% of points before 15 Feb in 2023, 2024 and 2026; daytime. 9% after 15 May. Leaf fall 14 days later than Ratapani; dry NDVI 0.38. |
| **Sanjay-Dubri, BTR, Sidhi, Anuppur** | Late: median 12-15 Apr; 10-12% of points after 15 May (BTR 30-43% in 2014, 2015, 2019, 2020 and 2023). Sal canopy stays green (dry NDVI 0.39-0.40). Leaf-fall half-date 7-14 Feb. |
| **North and South Balaghat** | Latest leaf fall in MP (50% loss by 17-21 Feb; only 49-50% done by 15 Feb). Fire timing itself is near Ratapani (peak week 14, median 2-5 Apr). A leaf-fall "dryness" feature on Ratapani's calendar would call these forests not ready while they burn. |
| **Gwalior, Shivpuri, Datiya, Bhind, Tikamgarh, Madhav NP, Guna, Rajgarh, Shajapur** | Season sits 2.5-5 weeks later (median 14 Apr-1 May); 6-38% of points after 15 May. FRP is high (6.3 MW median), night share low (7-16%), density 2-17. The yearly counts barely follow Ratapani's (ρ ≤ 0.3). Leaf fall here comes early (December) but fires come late. The 15 Jun cut-off is fine; a peak-season staff calendar copied from Ratapani is not. |
| **Morena, Shajapur, Rewa, Satna** | Scars hard to find (50%, 33%, 68%, 68%) in thorn/scrub/farm mosaic, and few points. |
| **Indore, Sehore, Dewas, Sehore Project** | The Ratapani neighbourhood is even earlier: 9-11% of points before 15 Feb, 14% for NOAA-20 in Indore. A 15 Feb start loses about 1 fire in 10 here, and Indore shows a +14-point early jump after 2022. |
| **Barwani, Jhabua, Alirajpur, Dhar, Sendhwa, Ratlam (south-west)** | Earliest leaf fall in MP (December), sparse fires, 19-51% of points on farmland inside beats. A leaf-fall feature on Ratapani's timing would say "dry" a month early. |

---

## Part B. Sources

### B1. Roy, Behera, Murthy et al. 2015, "New vegetation type map of India prepared using satellite remote sensing", *IJAEOG* 39:142-159; data at Zenodo 11615011 (CC-BY 4.0). **FULL** (paper read in round 3, see `open_datasets.md` A11; **data now used MP-wide**)
- 100 classes from on-screen interpretation of LISS-III (about 2005-10), at 60 m; stated accuracy 90%.
- Within MP beats the per-class areas are listed in A2 and `out/beat_vtm.csv`.
- **Concrete action, threads 1 and 3:**
  - Add per-beat or per-cell VTM shares (sal, teak, dry mixed, moist mixed, degraded, bamboo, north-dry, farm) as static features, using `out/beat_vtm.csv` or the 500 m-cell version (same script, grid instead of beats).
  - Use the type groups as **fuel-model strata** for the all-MP fuel map: sal and bamboo get later-curing, higher-NDVI floors.
  - Expected effect **[inference]**: little inside a single division, but useful across divisions. The groups separate density by up to 4× (13 vs 55 pts/100 km²/yr).

### B2. Debnath, Kiran Chand, Rajashekar & Murthy 2011, "Analysis of multi-temporal satellite data for forest fire characterisation over Central Indian region", ISPRS Archives XXXVIII-8/W20:71-75. https://isprs-archives.copernicus.org/articles/XXXVIII-8-W20/71/2011/ **FULL** (5 pp)
- Covers MP, Chhattisgarh, Jharkhand and Odisha (205,319 km² of forest). MODIS fires with confidence > 50%, masked to natural vegetation, 2001-10, on a 5 km grid.
- Sal versus non-sal: in non-sal (dry deciduous mixed) forest, fire density **rises steeply after Julian day 49 (18 Feb)**. In sal it grows steadily. Sal has the **higher fire density** even with fewer fires.
- EVI of both types falls until about **day 81 (22 Mar)**, then rises. Sal's EVI drop is smaller ("moisture retaining capacity").
- Fire density against air temperature: exponential, R = 0.78. LST against dryness index: R² = 0.86.
- Dryness index Di = (EVI_wet − EVI_dry)/(EVI_wet + EVI_dry), with November as the wet date.
- March is the peak month for both types, then April. 2009 was the anomalous year.
- **Concrete action, thread 1 (all-MP):** use a **type-specific "ready day"**: about 18 Feb for teak and dry mixed, gradual for sal. In our data sal has 0.7% of fires before 15 Feb against 5% for teak, which agrees. Encode it as days since the pixel's own 50% NDVI-loss date (A3), not a fixed calendar date.

### B3. Singh, R.P. et al. 2011, "Biophysical characterization of tropical deciduous forest of Kanha National Park using field and satellite data", ISPRS Archives XXXVIII-8/W20:145-149. https://isprs-archives.copernicus.org/articles/XXXVIII-8-W20/145/2011/ **FULL**
- Ten 0.1 ha plots in Kanha; sal is the dominant species, followed by lendia, jamun, saja, harra and dhawda.
- **Sal leaf fall and low growth come in March, not May** as in the other species.
- Sal LAI from hemispherical photos: **6.95 in September, 2.63 in March**. Forest LAI at one site: 2.26 in March, 3.42 in July, 6.63 in October.
- LAI model: LAI = 49.35·NDVI² − 42.82·NDVI + 10.4 (LISS-III NDVI), r = 0.79 against MODIS LAI.
- Classes (sal, sal-jamun, mixed with bamboo, grassland) were mapped at 85.6% overall accuracy using March, May and October LISS-III.
- March 2010 soil moisture: 4-15%.
- **Concrete action, thread 2 (scars under sal):** an LAI of about 2.6 in March is still a partial canopy. Expect the floor to be part-hidden in sal until leaves drop in March-April. For sal divisions, compare a **post-fire image after 25 Apr** (re-flush) with care: new leaves raise NIR and can mask a dNBR drop. Prefer SWIR-based indices (MIRBI, NBR2) over NDVI-like ones there **[inference]**.
- Our measurement fits: Kanha is 72-78% scar-found against 87-89% in Ratapani and the median division (A5, B11).

### B4. Ray, Malasiya, Verma, Purswani, Qureshi, Khan & Verma 2023, "Characterization of spatial-temporal distribution of forest fire in Chhattisgarh, India, using MODIS-based active fire data", *Sustainability* 15:7046. https://doi.org/10.3390/su15097046 **FULL** (16 pp)
- MODIS 2005-21. Yearly fires went from 1,487 (2005) to 3,074 (2021), with peaks in 2009 and 2017.
- **88.9% of fires fall in March-May: March 47.1%, April 32.0%, May 9.8%.**
- Monthly counts: March 18,000, April 12,239, May 3,730. Monthly mean in March is about 1,059 ± 2,702.
- By MODIS land cover, deciduous broadleaf forest has the most fires, followed by savannas, mixed forest, grassland, woody savanna and shrubland. The hotspot is the Bastar plateau (deciduous).
- Mahua collection (mid-March to end of April) is named as a main cause.
- **Concrete action, thread 1:** an outside check on the east of MP: Chhattisgarh's sal and mixed forest peaks in March, not April. Our sal-belt median is 5 Apr, so MP's eastern sal (Balaghat, Mandla) is about a week later than Chhattisgarh's sample **[inference: different years and sensor; a weak contrast]**. No change needed beyond per-division season terms.

### B5. Srivastava & Garg 2013, "Forest fires in India: regional and temporal analyses", *J. Trop. For. Sci.* 25:228-239. https://jtfs.frim.gov.my/jtfs/article/view/386 **ABSTRACT ONLY** (the PDF link returned an HTML page)
- MODIS 2001-11. Tropical dry deciduous forest had the most fire incidents, with maxima in 2004, 2009 and 2010.
- From FSI summaries of the same period: moderately dense forest held 43% of incidents (57,063) and open forest 40% (53,779).
- **Concrete action:** none beyond B1. Density classes (FSI canopy map) should be a feature in the all-MP model.

### B6. Nandy, Ghosh & Singh 2021, "Assessment of sal (*Shorea robusta*) forest phenology and its response to climatic variables in India", *Environ. Monit. Assess.* 193:616. doi 10.1007/s10661-021-09356-9 **ABSTRACT ONLY** (the ILRI repository holds only a thumbnail; Unpaywall finds no OA copy)
- MODIS EVI 2002-15. Start of season: **16 May for very moist sal, 29 June for dry sal, 17 July for moist sal**. Temperature explains start-of-season better than rainfall.
- **Concrete action, thread 1:** start-of-season (spring flush) in very moist sal comes from mid-May. That matches the re-greening we measured from late April (A3). A "greenness-since-minimum" feature will flag re-flush. Treat re-flush as **lowering** fire probability in sal after about 1 May, while north-dry stays dry until the rains. Expected effect: better late-season (May) ranking in sal divisions **[inference]**.

### B7. Pande 2002-era sal litterfall papers. Pokhriyal et al. 1987 (natural sal, Jhajra, Dehradun) and the Doon Valley sal plantation study (*Indian Forester*). **ABSTRACT ONLY**
- Sal leaf litter peaks in **March-April (40-45% of the year's leaf fall)**. Leaf is 83.9% of total litter (8,287 of 11,271 kg/ha/yr) in the plantation.
- Natural sal: maximum in April, then March, then May.
- Other sal annual litterfall values in the abstracts: 3.7 t/ha/yr (Uttarakhand, with understorey) and 13.4 ± 2.6 t/ha/yr (Das & Mondal 2016, West Bengal).
- **Concrete action, thread 3:** for sal strata, the peak of fresh litter on the floor comes **4-8 weeks later** than in teak (teak sheds Jan-Mar). Use an April peak and a seasonal ramp of litter in sal. With Ratapani's teak ramp, March fuel in sal is overstated and late-April fuel understated **[inference]**.

### B8. Sahu, Khan & Madguni 2024, "Assessing forest fire dynamics and risk zones in central Indian forests: a comparative study of the Khandwa and North Betul forest divisions", *Environ. Monit. Assess.* (Aug 2024). **PARTIAL** (Down To Earth article read in full; paper paywalled)
- MODIS over 22 years. Trend: non-significant increase, about +3 fires/yr in Khandwa and +1/yr in North Betul (Mann-Kendall and Sen's slope).
- AHP risk zones: about 45% (Khandwa) and 50% (North Betul) of forest is high or very high risk.
- Fires cluster. Khandwa's teak forest is at higher risk than Betul's mixed forest.
- High-risk ranges: Khalwa, East and West Kalibhit, Chandgarh, Aonliya (Khandwa); Shahpur, Betul, Sarni, Bhaura (North Betul).
- Causes: mahua and tendu collection.
- **Concrete action, thread 5 (patrol pilot outside Ratapani):** a named range list for a second pilot division. Our data agrees: Khandwa 48 and North Betul 44 pts/100 km²/yr, with 2.6 and 2.9 points per event (larger events than Ratapani's 2.1).

### B9. Mohanty & Mithal (CEEW) 2022, "Managing forest fires in a changing climate". https://www.ceew.in/sites/default/files/ceew-research-on-states-prone-to-forest-wildfires-india-and-mitigation-methods.pdf **FULL** (24 pp)
- Forest-fire hotspot districts 2000-19 include **Harda, Jabalpur and Hoshangabad** in MP; Narsinghpur is a high-intensity-event district.
- **Sheopur** is named among districts "swapping" from flood-prone to drought-prone. Over 79% of hotspot districts lie in Köppen Cwa/Aw zones.
- The report fits the fire season per district each year from AOD. Fire-season AOD is about 30% above the pre-season level, **except in Harda**.
- **Concrete action, thread 1:** independent support for treating Sheopur-Kuno as a shifting regime (see A5). Use per-district season start and end fitted per year (the way CEEW does with AOD) instead of a fixed 15 Feb-15 Jun window. Our VIIRS 10th percentile per division and year gives this directly.

### B10. Forest Survey of India 2022, "Forest fire studies in FSI" (slide deck). https://fsi.nic.in/uploads/documents/doc_8912_forest-fire-activities-1142022.pdf **FULL** (56 slides)
- FAST v3.0 has an "**Industrial and volcanic fire filter mask**" and a "Trees outside forests layer".
- Large forest fire (LFF): at least 3 proximate VIIRS pixels in a pass, tracked while the fire is alive.
- Special LFF monitoring of Similipal and Bandhavgarh in 2020-21. Fire-prone forest area was published in 2019. Beat-level alerts started in 2017.
- **Concrete action, threads 1 and 5:** before the all-MP model, apply a static-source mask like FSI's. FIRMS `type = 2` plus cells burning ≥ 9 of 13 seasons removes Singrauli's 22%. Verify on FSI's own Singrauli alerts that they are already filtered, so field alerts are not duplicated.

### B11. Our own all-MP scar run (15 Oct; `fire-alert-scars/mp/README.md`) joined to forest type (`t5_scars_by_type.py`). **DATA**
- Scar found, sample of 2,905 fires vs 1,472 controls:

  | Forest type | Scar found | Controls showing a scar | Median scar |
  |---|---|---|---|
  | Teak | 87.6% | 4.3% | 47 ha |
  | Degraded | 88.3% | 5.2% | 28 ha |
  | Bamboo | 83.6% | 3.4% | 41 ha |
  | Dry mixed | 82.8% | 3.8% | 43 ha |
  | Moist mixed | 82.7% | 3.9% | 40 ha |
  | North-dry | 82.2% | 1.7% | 30 ha |
  | Sal | 81.9% | 5.5% | 39 ha |
  | Farmland | 85.8% | 4.5% | 20 ha |

- Tiger-reserve events (12,586): sal 82.7% (n = 3,970, median 33 ha); teak 80.0% (63 ha); dry mixed 84.2% (77 ha); north-dry 81.7% (64 ha).
- By month (all sets), the weak months are Feb and Jun:

  | Type | Feb | Mar | Apr | Jun |
  |---|---|---|---|---|
  | Sal | 64% | 83% | 85% | 67% |
  | Moist mixed | 55% | 88% | 88% | 70% |
  | Teak | 66% | 85% | 82% | 57% |

- Spearman across divisions, scar found against sal share: −0.27. Against dry-season NDVI: −0.13.
- **Concrete action, thread 2:**
  - Keep one scar method for all of MP. Add **type-specific thresholds only for February** (pre-leaf-fall) and June (pre-monsoon green-up): for example, require two post-images, or lower the dNBR threshold by type.
  - Expected gain: a few points of recall where it matters, in Kanha and Balaghat in February.
  - The scar-size difference (sal 33-39 ha vs teak and dry mixed 47-77 ha) is real input for thread 4 fire-size priors by type.

### B12. Early ("cool") burning in MP tiger reserves. *Asian Age* 2013 via India Environment Portal, "Management of parks needs relook". https://indiaenvironmentportal.org.in/news-clippings/management-of-parks-needs-relook **PARTIAL** (news summary)
- Meadows in **Kanha, Bandhavgarh and other Project Tiger areas** are burned in winter "as per plan", as "early burning / cool burning", to prevent summer fires. Critics say it favours unpalatable, fire-resistant grasses.
- A visitor blog (2018) describes Kanha staff burning leaf litter along roads as fire lines in March.
- **Concrete action, threads 1 and 5:** label Jan-mid-Feb daytime fires in tiger-reserve divisions as a **management class**. Use FRP, day, location on fire lines or meadows, and whether the same cells burn every year. Then either drop them from the "fire to predict" set or model them separately. Our data: Kanha early points have FRP 6.5 MW and are 95% daytime; Satpura and Kuno show the same pattern from 2023. Ask the field team whether Kuno and Satpura began early burning in 2023 **[the one question to put to the forest department]**.

### B13. Pati, Kaushik, Malasiya, Ray & Khan 2024, "Impacts of forest fire frequency on structure and composition of tropical moist deciduous forest communities of Bandhavgarh", *Trees, Forests and People* 15:100489. doi 10.1016/j.tfp.2023.100489 **ABSTRACT ONLY** (OA on ScienceDirect, but the site returned 403 here)
- Landsat fire-frequency map 2005-21: 71.85% of the area unburned in 17 years; 25.12% low frequency, 2.92% moderate, 0.099% high.
- Fire frequency lowers sapling and seedling density and diversity; moderate frequency raises tree density.
- **Concrete action, thread 1:** in BTR, the "burned 1-2 years ago" signal works on a small share of ground. Our BTR repeat-burn share is 12%, against Ratapani's 22%. Expect the history features to carry less of the model there.

### B14. Kodandapani-style long-term regime by forest type: Karna & Jayakumar 2025, "Long-term assessment of fire regime across different forest types", *Int. J. Ecol. Env. Sci.* 51:425-436 (Sathyamangalam TR, Tamil Nadu). https://doi.org/10.55863/ijees.2025.0733 **FULL**
- Landsat 5/7/8/9 scars digitised for 25 years (2000-24), with FSI Forest Type Map 2020 strata.
- 20.4% of the reserve burned at least once; area falls linearly with fire frequency (classes FF1-FF11).
- Southern dry mixed deciduous forest (58% of the reserve) holds the most fire-frequency classes. Fires run January-May.
- MODIS active-fire burned area underestimates by 90-150% (citing Ramo).
- **Concrete action, thread 3:** a template for a 10-year per-type fire-frequency table on our scar outlines once the all-MP scars finish. It also confirms that an "FSI Forest Type Map 2020" exists as a stratum. The Van Agni WCS serves FTM 2021 as RGB only, and the portal did not answer from here today.

### B15. Uttarakhand sal, pine and mixed (Frontiers in Forests and Global Change 2024, 10.3389/ffgc.2024.1352265; and 2023, 10.3389/ffgc.2023.1198143). **FULL** for 2024 (25 pp), skimmed
- Landsat fire-frequency classes, then field carbon plots. Sal forests are "resilient" to low-intensity fire: tree biomass 270 → 265 (low fire), 243 (moderate), 235 (high) Mg/ha. Sal-soil moisture is 18% against 29% under oak mix.
- **Concrete action:** none for prediction. Low intensity under sal fits our low sal FRP (3.4-3.65 MW).

### B16. Sal seed, mahua, tendu and chironji calendars (news and NGO). Down To Earth (Odisha and Dindori sal seed), IIED "NTFP enterprise: sal seed", DTE on chironji, Mongabay on mahua. **PARTIAL** (news text)
- Sal seed is collected in **May-June**; Baiga families collect in Dindori (MP). 20-30 million forest dwellers in MP, Chhattisgarh and Odisha depend on sal seed, leaves and resin.
- Mahua flowers: March-April, with the dry leaves under the trees cleared by burning.
- Chironji fruit: April-May end.
- Tendu: in summer, starting when mahua blooms (round-12 notes give the exact phad dates).
- **Concrete action, thread 1 (all-MP):** a **sal-seed window feature (15 May-30 Jun)** for divisions with sal share ≥ 30%. These are exactly the divisions with more fires after 15 May (sal 5.9% vs teak 3.0%; Sanjay-Dubri 12%, BTR 11%, Kanha 10%). Expected effect: small, but it targets the late tail the 15 Jun window keeps **[inference]**.

### B17. Bamboo. Gregarious-flowering and fire records: Karnataka 1985 study (IISc ePrints 20086); "fire in May better than March for *D. strictus* culm growth"; Shahdol (MP) 1990 gregarious flowering note in *Indian Forester*; IIT Delhi thesis on bamboo ignition (critical heat flux 15 kW/m² vs 12 for wood). **ABSTRACT ONLY**
- No fuel or fire-behaviour measurement for bamboo litter in central India was found.
- **Concrete action, threads 1 and 4:** our data are the evidence. Bamboo has the **highest density (55/100 km²/yr), the highest night share (49-51%) and the lowest FRP (2.8-3.0 MW)**.
  - Thread 4: treat bamboo patches as **long-smouldering fuels**. For the fire-stopping model, raise the "still burning when unseen" prior in bamboo.
  - Thread 1: add bamboo share (VTM 30/40) as a feature.
  - After a flowering event (none mapped yet), expect a 2-4 year fuel spike **[inference]**.

### B18. Kanha 2009 and Bandhavgarh 2021 press reports; Sariska 2022 NRSC brief report (search snippet only; the PDF now returns 404). **ABSTRACT ONLY**
- 2009: 125 fires in Kanha TR, the most in MP that season.
- Bandhavgarh, late March 2021: burned for days across zones; causes given as mahua leaf burning, elephant deterrence and a cigarette.
- Sariska (Rajasthan; *Anogeissus pendula* dry deciduous, the analogue of Kuno, Shivpuri and Madhav), 27-30 Mar 2022: **11.3 km² burned by Sentinel-2B machine learning against 1 km² from AWiFS**.
- **Concrete action, thread 2:** in *Anogeissus* and thorn forest, coarse sensors miss most of the area. Our 10-20 m method is needed there, and Madhav's median scar (118 ha) shows these fires are big when they happen.

### B19. FSI / ISFR fire-prone class by district. **NOT OBTAINED**
- The Van Agni portal did not respond (HTTP 000 after 120 s). The FSI "Vulnerability of India's forests to fires" PDF was not found online. The fire-prone layer (5 classes; burn shares 8.5-24.3% per season in Ratapani, see `fuel-map/ratapani/README.md`) exists only for Ratapani in our files.
- ISFR 2021 summaries: MP had 47,795 fire counts in Nov 2020-Jun 2021, second after Odisha. 22.27% of India's forest cover is highly or extremely fire-prone.
- **Concrete action, thread 1:** pull `fire_prone_2021` MP-wide from the Van Agni WCS the same way it was pulled for Ratapani, from a network that can reach it. Until then, use our density table as the per-division prior.

---

## How to set each rule outside Ratapani (summary) [inference, from Parts A and B]

| Rule set in Ratapani | Teak belt | Sal belt (east) | North/west thorn | South-west (Nimar, Jhabua) | Tiger reserves with managed burning |
|---|---|---|---|---|---|
| Season window 15 Feb-15 Jun | Fine; Indore, Sehore and Dewas lose 9-11% before 15 Feb | Fine at the start (0.3% before 15 Feb); keep through 15 Jun (4% after 15 May) | Shift the staff peak 3-5 weeks later; 10% after 15 May | Fine | Split out Jan-mid-Feb management burns; do not count them as misses |
| Leaf-fall curve | Teak curve (50% at about 17 Jan) | Sal curve: 50% at 7 Feb, re-flush from late April | Earlier (late Dec) but fires late, so do not tie fire readiness to leaf fall | December | By type |
| "Burned last year" history feature | Strong (14% repeat) | Strong (15%) | Weak (5%) | Weak | Medium |
| Weather-year terms learned in Ratapani | Transfer (ρ = 0.83) | Mostly (0.75) | Do not transfer (0.39) | Partly | Partly |
| Scar method | As is | As is; Feb and Jun need care; smaller scars (33-39 ha) | Scar found 50-75%; farm mosaic | Farm contamination | As is |
| Static-source mask | Not needed | **Needed in Singrauli** | Not needed | Not needed | Not needed |

---

## Datasets and code

| Item | What | Access | Used here | Path or link |
|---|---|---|---|---|
| Roy et al. 2015 VTM | 100 vegetation classes, 60 m, all India | Zenodo 11615011, CC-BY 4.0, 58.6 MB 7z (5.1 GB tif) | Yes, MP-wide | `code/mp_types/un7z.py` (stdlib LZMA2 decoder), `out/beat_vtm.csv` |
| FIRMS VIIRS SP, all MP Jan-Jun | 3 satellites, 2014-26 | already in `fire-alert-scars/alerts_mp/` | Yes | `out/viirs_vtm.parquet` (in-beat points with division and VTM class, 657,897 rows) |
| MOD13A1/MYD13A1 NDVI | 500 m, 16-day ×2 | Planetary Computer, keyless SAS | Yes, 5,220 pixels, 2022-23 | `out/ndvi_samples.parquet`, `out/leaf_curve_*.csv` |
| All-MP scar sample + tiger-reserve scars | 15 Oct run, v1 method | `fire-alert-scars/mp/out/` | Joined to type | `out/scar_by_type*.csv` |
| Patra et al. 2025 sal 10 m map | species map | Zenodo 15086956 (COG) | Not re-used (see `mahua_tendu_mapping.md` A2) | for sal-belt cells, more detailed than VTM |
| FSI FTM 2021 and fire-prone 2021 (Van Agni WCS) | forest type and fire-prone classes | portal down from here | No | to pull MP-wide later |
| Master division table | 87 rows × 46 columns + flags | this round | Yes | `code/mp_types/out/division_types_final.csv` |
| Weekly fire curve per division | 26 weeks × 87 divisions | this round | Yes | `code/mp_types/out/division_weekly.csv` |

Scripts in run order: `t1_join.py` → `t2_vtm.py` → `t3_division.py` → `t4_ndvi.py` → `t4b_leaf_curve.py` → `t5_scars_by_type.py` → `t6_checks.py` → `t7_final_table.py`.
- `t4_ndvi.py` also writes `leaf_fall_*.csv`, whose day-of-year medians are wrong across the year boundary. These files were not copied; use `t4b` instead.
- No credentials are stored. The Planetary Computer SAS token is fetched at run time.

## Reading status
- **FULL, read this round (8):** Debnath 2011; Singh 2011 (Kanha); Ray 2023 (Chhattisgarh); CEEW 2022; FSI 2022 deck; Karna & Jayakumar 2025; Frontiers 2024 Uttarakhand sal/pine; ISPRS 2018 Satpura teak/sal NDVI. The Satpura paper held nothing usable: NDVI is highest in Oct-Nov and lowest in Mar-May, sal compartments declined from sal borer, and there were no fire numbers.
- **Data used in full:** Roy 2015 VTM (the paper was read in round 3).
- **PARTIAL (4):** Sahu 2024 (via DTE); the Asian Age early-burning clip; sal-seed and NTFP calendars (news); ISFR 2021 summaries.
- **ABSTRACT ONLY (7):** Nandy 2021; sal litterfall abstracts (Pokhriyal 1987, Doon plantation, Das & Mondal 2016); Srivastava & Garg 2013; Pati 2024; Reddy 2017 and 2020; bamboo fire records; NRSC Sariska 2022 (snippet).
- **Not reachable:** MP forest-fire management book (fsi.moef.gov.in, expired certificate and then 503); Van Agni portal; ScienceDirect for Pati 2024 and Kumar 2022.
- Consensus search quota was used up (resets 1 Nov).

## Ranked action list (gain and effort; gains are my estimates [inference] unless measured)

1. **Mask static and industrial heat before any all-MP step** (FIRMS `type = 2`, plus 500 m cells burning ≥ 9 of 13 seasons). Threads 1, 2, 5. *Gain:* removes 22% of Singrauli's points and its false "January season". Prevents a wrong per-division model and false field alerts. *Effort:* 1 hour.
2. **Split out managed early burns in tiger reserves** (Kanha, Satpura, Kuno, BTR; Jan-15 Feb, daytime, FRP ≥ 5 MW, same cells most years, on fire lines or meadows). Threads 1, 5. *Gain:* stops 10-40% of a season's points in those divisions being scored as missed fires. Fixes the 2023+ regime break the 2019-21 training years cannot see. *Effort:* half a day, plus one question to the forest department.
3. **Add VTM type shares as per-cell features and as fuel strata** (`out/beat_vtm.csv`; redo on 500 m cells). Threads 1, 3, 4. *Gain:* across-division density differs up to 4× by type. Bamboo and sal get their own smoulder and size priors. Expect +1-3 points of all-MP top-10% capture **[inference]**. *Effort:* half a day.
4. **Replace the fixed leaf-fall curve with each pixel's own NDVI-loss date** (days since 50% loss; loss fraction; re-flush after the minimum). Threads 1, 3. *Gain:* fixes sal (+2-4 weeks) and the south-west (−4-8 weeks), and catches the 2-3 week year-to-year shift (2023 vs 2022). Measured link: earlier leaf fall goes with more fires before 15 Feb (ρ = −0.47). *Effort:* 1 day (MODIS 8-day for all cells, or HLS for 30 m).
5. **Season windows and staff calendars per division from VIIRS percentiles** (10th-90th percentile date per division and year; `division_types_final.csv`). Thread 5. *Gain:* north/west patrol peaks move 3-5 weeks later than Ratapani's. Indore, Sehore and Dewas need cover before 15 Feb. *Effort:* 2 hours.
6. **Pool north/west divisions into one regional model with its own weather terms.** Thread 1. *Gain:* 14 divisions have under 10 pts/100 km²/yr, and yearly counts barely follow Ratapani's (ρ = 0.39). A per-division model there is too noisy. *Effort:* 1 day (fits the GPBoost/hierarchical plan in `multi_region_models.md`).
7. **Type- and month-specific scar thresholds for February and June** (sal and moist mixed in Feb 55-64%, teak in Jun 57%). Thread 2. *Gain:* +10-20 points of recall in those month-type cells, about 3-5% of all events. *Effort:* 1 day, using the sample-and-control design already in `mp/out`.
8. **Fire-size priors by type for the spread and burn-probability maps** (median scar: sal 33-39 ha, teak 47-63, dry mixed 43-77, Madhav/north 64-118). Thread 4. *Gain:* better-calibrated 24-48 h maps outside Ratapani. *Effort:* 2 hours.
9. **Sal-seed window feature (15 May-30 Jun) in sal divisions; mahua window in mahua-dense divisions.** Thread 1. *Gain:* small; targets the late tail (sal 5.9% after 15 May). *Effort:* 2 hours.
10. **Pull FSI fire-prone 2021 and FTM 2021 for all MP** from the Van Agni WCS (as for Ratapani) when the portal is reachable. Threads 1, 3. *Gain:* an official per-district prior and an independent forest-type check on VTM. *Effort:* 2 hours once the portal answers.
