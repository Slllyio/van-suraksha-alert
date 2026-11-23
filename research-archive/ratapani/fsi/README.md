# Forest Survey of India material (E:\FIRE\fsi_data), read 14 Oct 2026

## What the folder holds

Five presentations from FSI's one-week in-service training for IFS officers in Dehradun (14 to 18 Sep 2026). They are slides, not data: no shapefiles, tables of fire records or rasters. Text extracts are in `slide_text/`. The original decks stay on Akkshay's PC.

| File | Who / what |
|---|---|
| Surface Fuel Load Mapping.pptx | Dr Sunil Chandra, FSI. National surface fuel load map: 272 strata = FSI forest type (17) x canopy density (4) x slope (4), calibrated by oven-dried 1 ft x 1 ft field samples. Classes 0-20 / 20-40 / 40-60 / >60 g/ft2. State burnt-area table (MP 3,172 km2 total, almost all "low burnt") and 2025-26 detections (MP: 20,692 VIIRS, 2nd in India). Nainital and Sariska field-verified burn-severity case studies. |
| Presentation-to-IFS-Officers-FSI-1 (PDF) | Dr Manish Kale, C-DAC Pune. WRF-SFIRE physics fire-spread forecast for 24-48 h on PARAM supercomputers; used live in Sikkim, March 2024. FSI-C-DAC MoU in progress for a national system. |
| Innovation in Forest Fire Mgmt.pptx | Uttarakhand Forest Dept (CCF Pattnaik). Ops numbers, FSI alert flow, mobile app, Chir pine needle collection, community models. Uttarakhand has 2,393 beats. |
| FSI 17th September 2026.pptx | Rudraprayag division fire app and dashboard (Rs 8 lakh), Binsar 2024 accident. |
| Innovative_Approaches_...LITE.pptx | Officer group synthesis of the week, incl. Melghat (Sipna division) and Tamil Nadu case studies. |

## What matters for Ratapani

- **No beat or compartment boundaries, and no ground fire records for MP**, in any file. The 68 pseudo-beats stay until the MP Forest Department shares the Ratapani beat/compartment layer and its fire register.
- **Melghat (dry teak, like Ratapani) warns that Sentinel-2 dNBR reads leaf fall as burn** when imagery spans the season (44% of the division flagged burnt in two years whose ground registers differed by 92%). Our detector compares each pixel to its 1.5 km surroundings over gaps of 20 days or less, so it should be protected. Checked below.
- **Median ground-mapped fire in Melghat was under 3 ha; a VIIRS pixel is ~14 ha.** Our labels drop scars under 2 ha.
- **A watchtower reported a Melghat fire 2 h before NASA FIRMS; FSI raised no alert at all.** Satellite alerts are a safety net, not a full record.
- **Ground truth exists in the system, but behind logins:** FSI's NRT feedback (field staff confirm or reject each alert; MP sent 14 feedbacks so far this season), the Van Agni geo-portal, and division fire registers. The public FSI archive (`fsiforestfire.gov.in/ArchivalData/Search`, 2004 to Jun 2025) only has date, sensor, lat/lon, time: the same as NASA FIRMS, which we already have.
- FSI publications (free PDFs at fsiforestfire.gov.in/Home/Publication): Forest Fire Risk Zonation 2023-24, Surface Fuel Load Mapping 2023-24, Burnt Area Assessment 2023-24. Maps only, no downloadable rasters seen.
- Fire seasons used by forest departments: 15 Feb to 30 Jun (alerts), with winter fires Nov to Feb in the hills.

## Checks run on our labels (2017-2024, scripts in `scripts/`)

**1. Do low-NDVI scars look like leaf fall?** (`scar_vs_viirs.py`, output `scar_viirs_check.csv`) For every first-burn scar cell-window, is there a VIIRS detection within 750 m inside the window (+/- 1 day)? Chance = same cell, window shifted 40 days.

| Pre-fire NDVI | scars | with VIIRS | chance | lift |
|---|---|---|---|---|
| <= 0.25 | 4,824 | 40.0% | 1.4% | 29x |
| 0.25-0.35 | 7,588 | 41.8% | 3.0% | 14x |
| 0.35-0.45 | 2,688 | 33.8% | 6.1% | 6x |
| 0.45-0.55 | 468 | 24.8% | 6.1% | 4x |
| > 0.55 | 29 | 6.9% | 5.2% | 1.3x |

Dry, low-NDVI scars are confirmed by an independent thermal sensor at least as often as any others, so the "NDVI 0.25-0.35 burns 7x more" finding is not a leaf-fall artefact. The weak labels are January (19% with VIIRS) and February (32%), and the rare green-cell scars. Bigger scars agree more (30% for <2 ha, 60% for 10-25 ha).

**2. Do VIIRS fires leave a scar?** (`viirs_vs_scar.py`) 88% of VIIRS fire points (2018-2024, Jan-Jun, 5,238 points) have a scar window within 750 m. Lower in January (64%), 2024 (69%) and 2021 (80%).

**3. How much of the score is a true 2-day forecast?** (`viirs_dated_scoring.py`) 6,064 first burns 2017-24 have a VIIRS date inside their scar window. Using that day as the fire day, the scoring rule's positive cell-days split into: fire 1-2 days ahead (true forecast) 25%, fire 3+ days ahead 26%, fire already happened 49%. Pipeline lean model (LOSO) recall at 5 per beat per day on each: 30.5% / 29.0% / 32.7%, random 14.9% / 14.6% / 14.8%. So the model's lift is about the same (2x) on true forecast days, but half of the scored positives are days after the fire, and the model has no within-window timing skill (flat across the three).

## Coordination note from the Fire prediction research thread (14 Oct, 14:20Z)

Same dating problem, different sensor. The research thread is pulling **Sentinel-1 GRD** (radar, sees through cloud, 6-12 day revisit per orbit) as mean VV/VH backscatter per 500 m cell per acquisition, Dec-Jun 2017-2026, to `/mnt/project-files/ratapani/ee/s1/` (pull running on Akkshay's PC, `E:\FIRE\ratapani\ee\s1\`). Burns drop VH by ~1-3 dB in dry deciduous forest, so a radar change date can narrow the optical window independently of VIIRS, which misses the small cool fires (check 1 above: only 30% of <2 ha scars have VIIRS).

Split so nothing is done twice:
- **FSI thread**: combined labels (scar = where, VIIRS = which day) under `ratapani/fsi/`, and the three-way scoring split (ahead / late / after).
- **Research thread**: radar change dates per scar window (`ratapani/ee/s1/s1_change_dates.csv`, columns season, cell_id, window_start, window_end, s1_date_before, s1_date_after, vh_drop_db), then a check of radar dates against VIIRS dates where both exist (agreement rate, median offset). If radar dates agree with VIIRS, they extend day-level dating to the 60-70% of scars VIIRS never sees, and the FSI thread's combined labels can take `s1_date_after` as a second day source. Results will be posted here and in the research README.

**Update 14:25Z (research thread): Sentinel-1 is out.** Ratapani has one S1 track (descending, relative orbit 63) at 12-day revisit, no ascending pass, so radar gaps are wider than the optical windows and cannot date scars. The split above is void: day-level dating stays with the FSI thread's scar-plus-VIIRS labels. The research thread will not build `s1_change_dates.csv`.

## True-lead labels (built 14 Oct to the SCORING.md "True-lead variant" spec)

`true_lead_labels.parquet`, seasons 2017-2024 (the VIIRS file ends in 2024), built by `scripts/build_true_lead_labels.py`. One row per valid cell-day of the main rule. Columns: `season, date, cell_id, pos_main` (main rule), `pos` (true-lead positive: t = d-2 or d-1), `valid_strict`, `valid_lenient`, `dated` (cell's first burn has a VIIRS day), `fire_day` (d). Score on rows where `valid_strict` (or `valid_lenient`) is true, with `pos` as the label. VIIRS points are nominal/high confidence, matched within 750 m of the cell centre on [ws, we+1], then d is clipped into (ws, we].

- 15,754 first burns, 6,044 VIIRS-dated (38%).
- Strict: 2,287,679 valid cell-days, 11,292 positives (base rate 0.49%). Lenient: 2,353,841, 77,454 positives (3.29%). Main rule: 111,022 positives.
- Pipeline lean model (existing LOSO predictions, not retrained), recall at 5 per beat per day: strict 38.0% vs random 17.4%; lenient 30.4% vs 15.7%. At 10: strict 60.7% vs 34.8%; lenient 51.3% vs 30.9%.

The research thread (owns the scar labels) is working on Sentinel-1 radar dating for the same timing problem; these labels only use VIIRS days, so they can be swapped for radar-dated ones later.

## FSI-style fuel strata test (14 Oct, `scripts/fuel_strata.py`, `results/fuel_strata.json`)

Proxy for FSI's 272 strata: forest type = 17 AlphaEarth clusters, canopy = pre-season NDVI quartile, slope = FSI classes (95 strata occur in Ratapani). Strata burn rate from training seasons only; LOSO 2017-24; real 94 beats, 5 picks per beat per day.

| Ranking | Main rule | True 2-day leads (strict) |
|---|---|---|
| Random | 16.6% | 18.8% |
| Strata burn rate alone (static map) | 22.6% | 28.9% |
| Lean model | 29.5% | 38.9% |
| Lean, restacked (control) | 29.1% | 38.5% |
| Lean + strata | 28.1% | 37.4% |

A static FSI-style fuel map beats random but adds nothing on top of the lean model (slightly worse). The model's per-cell burn history and dryness already carry what the strata know. A fuel map built from measured g/ft2 values would only help if its values differ from what burn history already says.

## FSI method notes (14 Oct)
- `burnt_area_method.md`: FSI's Sentinel-2 dNBR burnt-area method, thresholds, accuracy, Raisen/Sehore/Bhopal figures. There is no per-alert scar product.
- `risk_zone_method.md`: FSI's static LLRM risk zones. Coefficients unpublished, no validation reported.
- `fast3_alert_system.md`: FAST 3.0 alert flow, large-fire rule, SMS feedback form, pre-warning and KBDI.

## true_lead_labels_v2.parquet (14 Oct 2026)
Same as true_lead_labels.parquet, except a burn may be dated to the window's start day itself (the fire came after that morning's clear image). v1 clipped these one day late. 1,123 of 5,826 dated cells move one day earlier. Script: scripts/build_true_lead_labels_v2.py. Strict positives 11,285 (v1 11,292). Re-scored by the pipeline thread on v2 (SCORING.md now points to v2): strict lean classifier 39.5% (v1 38.9%), lean ensemble 40.7%, random 20.0%; lenient 31.9 / 32.6 / 18.0%.
