# C-DAC spread-forecasting deck: every slide, every figure

**Source.** Dr Manish P. Kale (Scientist-F, C-DAC Pune), "Forest Fire Spread Forecasting using High Performance Computing System", presentation to IFS officers, 15 Sep 2026.
- Akkshay's copy: `E:\FIRE\fsi_data\Presentation-to-IFS-Officers-FSI-1_261014_192654.pdf`, 29 pages, 4,358,383 bytes.
- This is the same file that `../slide_text/` and `../cdac_spread_details.md` were built from. This pass adds the figures.

**What is in this folder.**
- `slide-01.png` … `slide-29.png`: every slide at 110 dpi.
- `slides_text.txt`: text for each slide.
- `figures/`: the embedded images from slides 20–21 at full resolution:
  - Sentinel-2 image with the forecast outline
  - the forecast map with its time steps
  - Google Earth overlays
  - the WhatsApp exchange with the forest department

Readings marked **[read off figure]** were measured from the images. Readings marked **[inference]** are my interpretation; the deck gives no legend or number for them.

## Slide by slide

| # | Content | What matters for us |
|---|---|---|
| 1–5 | Title, C-DAC background, NSM supercomputers (PARAM Rudra 20 PF; C-DAC has compute nodes for fire runs), NASA global fire video | Nothing technical |
| 6 | Rationale | India has alerts and a weekly danger rating but no national 24/48 h spread forecast. Sikkim FD used it on a live fire "for the first time in the country" |
| 7 | Benefits | GeoTIFF and KML output, SMS alerts within a buffer the user chooses, role-based logins, FSI alerts pushed straight to the C-DAC server, manual ignition entry |
| 8 | System diagram | WRF weather model + SFIRE fire model. Inputs: ignition, atmosphere, fuel parameters, fuel map, terrain. Users: forest departments and state/national disaster authorities |
| 9 | Datasets table | Atmosphere: GFS/IMD/C-DAC, 25 km down to about 4 km. Fuel: load, depth, SAV, moisture, particle density, calorific value, total and effective mineral content, from field/FSI/research institutes, split into fine and coarse fuel. LULC: FSI/Dept of Space, 1:10,000. Terrain: ALOS PALSAR 12.5 m. Boundaries: FSI/FD. Fire alerts: FSI/FIRMS/field staff, MODIS 1 km and VIIRS 375 m |
| 10 | Atmospheric data | Screenshot of NOMADS `gfs/prod`, listing `gfs.YYYYMMDD`, `gdas.*` and `enkfgdas.*` (June 2024). Weather is the public GFS forecast, not a special product |
| 11 | Sikkim fuel plot design | Plot 0.1 ha (32 × 32 m), or 20 × 20 m in steep terrain. Five 1 × 1 m quadrats on the diagonals (A1–A4 at the corners plus the centre) and one 5 × 5 m centre plot. Trees over 20 cm: species, girth, height, canopy base height, canopy length. Live fuel sampled but "not considered". 1 h/10 h/100 h/1000 h dead fuel, litter, grass and dead shrubs in the quadrats. Plots placed by elevation, slope, vegetation type, past fires and access |
| 12 | Sampling intensity | 0.001% of forest area (0.002% in fire-prone South). East 767.45 km² → 8 plots; West 815.9 → 8; North 1,490.26 → 15; South 575.53 → 11; total 3,649.14 km² → **42 plots planned**, plus some crop-residue samples. Source for the percentage: IIRS BCLL (Roy 2012) |
| 13 | Canopy/live fuel | About 100 g of leaves from the lower crown of the dominant species, wet weight recorded, sealed. Marked "not considered" |
| 14–15 | Rejected methods | 3D voxel sampling (too costly); Western Australia visual fuel load guide, 5 × 5 m (untested for Sikkim) |
| 16 | LANDFIRE | FBFM13 table (1–13, 91 urban, 92 snow, 93 agriculture, 98 water, 99 barren) and the LANDFIRE viewer. This is WRF-SFIRE's fuel coding |
| 17 | Rothermel | Same constants as before: heat content 8,000 Btu/lb, total mineral 0.0555, effective mineral 0.010, particle density 32 lb/ft³. Inputs: SAV, load, depth, moisture of extinction, fuel moisture, midflame wind, slope. Ref Andrews 2018 |
| 18 | Level set | ∂ψ/∂t + S‖∇ψ‖ = 0 (Mandel 2011; Osher & Fedkiw) |
| 19 | Operational portal | "Sikkim Wildfire Spread Forecasting and Monitoring System (SWFMS)", login page at swfms.icecloud.in. Features: satellite and ground ignitions, forecast up to 48 h, buffer alerts, reports, role-based logins |
| 20 | Case 1, 12 Mar 2024 | See below |
| 21 | Case 2, 13 Mar 2024 | See below |
| 22 | Publicity | Digital India video and press release, Jul 2026 |
| 23 | FSI–C-DAC MoU (in process) | Objectives include occurrence, spread, intensity and risk modelling, AI/ML, data sharing |
| 24 | Planned architecture | Each satellite pass on day 1, 2, … gives ignition points n1, n2, … nx. These go to an orchestration framework ("SUTRADHAR") on PARAM Rudra. WRF-SFIRE runs with forecast weather (now plus 3 days), a gridded vegetation type map, a DEM and a fuel model, and outputs **hourly** spread. So they intend to restart from every pass |
| 25 | Current work | A 24 h run takes **17 min on 16 nodes**. Experimental runs ingested 200 ignition points. WRF-SFIRE code is being modified "for Indian needs". MoU with FSI underway |
| 26 | National design | Zones: Himalaya, Deccan Peninsula, Western Ghats, North East, rest of India. Inputs MODIS, VIIRS, "INSAT 1D" via FSI alerts. Outputs: 48 h forecast, fire polygon, area estimate, **localised fuel parameterisation**, proximity SMS, reports |
| 27 | Screenshot | FSI Van Agni Geo-Portal with a "Fire spread Forecasting" link. Layers: NRT detections, large fire detections, fire prone map, FFDR, FCM, FTM 2023 |
| 28 | Plans | Integration with FSI's unified portal, a national fuel model with FSI, high-frequency fire danger rating, AI/ML land-cover updates, NSM 2.0 |

## Case 1: 12 March 2024, run at 17:03, 24 h (slide 20)

- **Place [read off figure]:** West Sikkim, between Gyalzing (Geyzing) Block, Yangten, Omchung RF, Legship Block and Tashiding Block, along the river.
- **Forecast map with time steps (`figures/s20_forecast_map_timesteps.png`).**
  - A red star marks an ignition inside a large grey area around Gyalzing Block.
  - To the east, a separate coloured footprint sits around Omchung RF: magenta in the core, green-yellow around it, pink on the outside.
  - **[inference]** The three colours are successive forecast time steps (magenta first, pink last). The grey area is an earlier run or the area already burnt. No legend is shown.
- **Sentinel-2 false-colour image with the forecast outline in black.**
  - A dark (burnt-looking) patch sits top-left inside a yellow dashed line. The slide labels that line "Area saved from burning (0.54 km²) which otherwise was forecasted to burn".
  - A blue line is labelled "Fire could not cross beyond this line". The forest department photos show a hose line and fire tender working along a hill road there.
  - **[inference]** The "saved" area is where the fire hit a road and the crew held it. WRF-SFIRE has no road in its fuel map, so it forecast spread across.
- **WhatsApp with the FD:**
  - 16:22: "15 hrs. simulation" map sent.
  - 16:26: "We had some habitation layer available with us so used it" (habitation added as non-burnable, ad hoc).
  - FD: "Spreading fast", "Fire is still continuing and spreading".
  - C-DAC asks "Is it matching with simulation?" FD: "Yes, it's similar".
  - That is the only field check given for this case.
  - **[inference]** A 15 h map already existed before the 17:03 run, so they re-ran during the day.
- **Pixelation [read off figure]:**
  - Forecast edges are blocky staircases, consistent with a fire grid of a few tens of metres. The 2024 paper used 40 m.
  - The forecast leaves **holes on dense dark-green forest patches**: fire is forecast to run through scrub and grass and skip closed forest.
  - That follows from their forest fuel: FBFM 8 at 0.27 kg/m², 6 cm deep, windrf 0.36, which barely spreads.

## Case 2: 13 March 2024, run at 12:33, 48 h, from a NASA FIRMS alert (slide 21)

- **Ignition [read off figure]:** 27°17′24.05″N, 88°16′08.45″E (pin near Yangtey, east of Geyzing, West Sikkim).
- **Google Earth overlay (`figures/s21_forecast_on_google_earth_48h.png`).**
  - The white forecast outline covers a band about 6 km east–west, from Pelling City and Pemayangtse Monastery in the west to Tashiding Forest Block and the river in the east, and down to Umchung in the south.
  - It has many unburnt holes, again on dense forest.
  - **[inference, rough]** By landmarks (Pelling to Pemayangtse is about 1.2–1.5 km) the image is about 3–3.7 m per pixel. That makes the forecast envelope about 4 × 2.5 km, and the filled area of order 4–5 km².
- **Sentinel-2A, 19 Mar 2024 (6 days later), forecast outline in yellow (`figures/s21_sentinel2_19mar2024_with_forecast.png`).**
  - The eastern part of the outline, around the ignition and towards Tashiding and the river, shows grey-cyan, non-vegetated tones: burnt or dry ground.
  - The western part (Pemayangtse–Pelling side) is still **bright red, healthy vegetation**.
  - A smoke plume is still visible near the top centre on 19 Mar.
  - C-DAC's caption: "Area could not burn (after FD intervention) around 3.00 km² (This was forecasted to be burnt)".
  - **[inference]** The forecast over-reached westward by about 3 km² over 48 h. Whether the FD stopped it is a claim the image cannot test: no control run and no fire line is shown. Read plainly, the forecast burnt area was roughly double to triple the burnt area.

## What this changes in `../cdac_spread_details.md`

1. **The deck's two cases are not the published case.**
   - Kale et al. 2024 (Remote Sensing 16:2480) validates one fire: the VIIRS alert of **27 Jan 2023 near Maltim, North Sikkim**. There the forecast was 1.72 km² against 1.07 km² mapped on Sentinel-2; the burnt land was mostly scrub (76% open scrub).
   - The deck's cases are **12 and 13 Mar 2024 in West Sikkim** (Geyzing, Omchung RF, Pemayangtse, Tashiding). Neither has a published accuracy score.
   - In all three cases the forecast is larger than what burnt: about +60% in 2023, and about 3 km² unburnt in Mar 2024.
2. **42 plots planned vs 23 used.** The deck plans 42 plots of 0.1 ha. The 2024 paper used 23 (11 forest, 6 open scrub, 5 dense scrub, 1 grassland).
3. **Run time.**
   - The paper reports 2 h 11 min on 240 cores for 24 h.
   - The deck now reports **17 min on 16 nodes** for 24 h, after optimisation. Node size isn't given. On PARAM Rudra, 16 nodes is probably 768 or more cores **[inference]**.
4. **Restarts from each pass are the plan (slide 24).** Every satellite pass becomes a new set of ignition points, and the model outputs hourly spread. That matches the best practice found in the literature (VIIRS re-initialisation took Sørensen from 0.54 to 0.79).
5. **Barriers are missing from their fuel map.** The only "saved" areas shown sit behind a road where crews worked. Habitation was added by hand mid-event. Roads, streams and fire lines have to be non-fuel cells, or the model will over-predict.
6. **Closed forest is treated as a near-barrier.** With FBFM 8 at 0.27 kg/m², closed forest is a barrier in their runs. In Ratapani, closed teak with heavy leaf litter is the main fuel, so copying their forest fuel would forecast almost no spread. Use TL6/FBFM 9-type litter, as the full-read note found from Saha 2002.

## Lessons for a Ratapani spread model

1. Burn non-fuel into the fuel raster: roads (Microsoft road detections, 132 km inside the sanctuary), streams, reservoirs, fire lines and villages. C-DAC's "saved" areas are probably mostly this.
2. Restart from every detection (VIIRS S-NPP, NOAA-20 and NOAA-21, plus scars) rather than running 48 h free.
3. Score every forecast against the Sentinel-2 scar, with Sørensen and Jaccard plus over/under area, against a distance-only baseline. C-DAC never publishes an overlap score, so beating their claims means reporting one.
4. Fit fuel-class spread multipliers on dated Ratapani fires rather than taking Sikkim values. The FSI large-fire archive (`../fsi_portal/lff_mp.csv`: first and last detection plus extent) gives MP growth data.
