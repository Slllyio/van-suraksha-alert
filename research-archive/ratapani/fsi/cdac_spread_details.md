# C-DAC fire-spread forecasting: everything in the deck

Source: Dr Manish P. Kale (Scientist-F, C-DAC Pune), "Forest Fire Spread Forecasting using High Performance Computing System", presentation to IFS officers, 15 Sep 2026. The PDF is on Akkshay's PC at E:\FIRE\fsi_data. Its text is in `slide_text/Presentation-to-IFS-Officers-FSI-1 (C-DAC HPC spread forecasting).pdf.txt`; I also viewed every page as an image. The deck is an overview. It gives no grid spacings, run namelists, fuel calibration values or accuracy scores beyond the two Sikkim maps.

## Model

- **WRF-SFIRE:** the WRF weather model coupled to a fire module (Mandel, Beezley & Kochanski 2011, GMD 4:591). The atmosphere and the fire feed back on each other.
- **Spread rate:** Rothermel's quasi-empirical surface model (Andrews 2018, USDA RMRS-GTR-371):
  R = I_R ξ (1 + φ_w + φ_s) / (ρ_b ε Q_ig).
  - **Fuel particle constants:**
    - heat content 8,000 Btu/lb
    - total mineral 0.0555
    - effective mineral 0.010
    - particle density 32 lb/ft³
  - **Fuel bed inputs:**
    - surface-area-to-volume ratio σ
    - oven-dry load w₀
    - bed depth δ
    - dead fuel moisture of extinction M_x
  - **Environment inputs:** fuel moisture M_f, midflame wind U, slope tan φ.
- **Fire front:** a level set, ∂ψ/∂t + S‖∇ψ‖ = 0 (Osher & Fedkiw).
- **Fuel models:** a slide shows the LANDFIRE "FBFM13" table, i.e. the 13 Anderson fire behaviour fuel models plus 91 urban, 92 snow/ice, 93 agriculture, 98 water and 99 barren. That is WRF-SFIRE's default fuel category set. C-DAC says it is adapting it with "localised fuel parameterisation" and plans a national fuel model with FSI.
- **Crown fire:** canopy fuels are listed for field collection, but live fuel samples are "not considered". So the runs are surface fire only.

## Inputs (deck "Datasets" table)

| Data | Source | Resolution |
|---|---|---|
| Atmosphere | GFS (NOAA NOMADS), IMD, C-DAC | 25 km down to ~4 km (WRF nests) |
| Fuel: load, depth, SAVR, moisture, particle density, calorific value, total and effective mineral content | Field surveys, FSI, research institutes | Split into fine and coarse fuel |
| Land use / land cover | FSI, Dept of Space | 1:10,000 |
| Terrain | ALOS PALSAR DEM | 12.5 m |
| Administrative boundaries | FSI, forest departments | n/a |
| Fire alerts (ignition points) | FSI, NASA FIRMS, field staff | MODIS 1 km, VIIRS 375 m |

Ignition points arrive automatically from FSI's alert feed into the C-DAC server, or are typed in by hand.

## Sikkim fuel field protocol

- **Plot layout:**
  - 0.1 ha plots (32 m × 32 m, or 20 m × 20 m in complex terrain).
  - Five 1 m × 1 m quadrats: one at each corner diagonal plus the centre.
  - One 5 m × 5 m centre plot.
- **In the 0.1 ha plot:** every tree over 20 cm, with girth, height, canopy base height and canopy length; fuel bed depth.
- **In the 5 m × 5 m plot:** shrub type, count, average girth and height.
- **In the 1 m × 1 m quadrats:** 1 h, 10 h, 100 h and 1000 h dead fuel; litter; grass; dead shrubs.
- **Plot placement:** spread by elevation, slope, vegetation type, past fire records and access.
- **Sampling intensity:** 0.001% of forest area (0.002% in fire-prone South Sikkim), giving 42 plots for the state, plus a few crop-residue samples per district.
- **Rejected as too costly or untested:** 3D voxel sampling and the Western Australia visual fuel load guide.

## Compute and speed

- Runs on PARAM Seva (Sikkim runs) and PARAM Rudra (20 PF, nodes awarded under the National Supercomputing Mission).
- A 24 h forecast takes 17 minutes on 16 nodes.
- Multi-ignition runs: 200 points ingested in one simulation so far, experimental.
- Outputs are GeoTIFF and KML, with alerts to registered users within a buffer they choose.

## Validation shown (West Sikkim, March 2024: Geyzing, Omchung RF, Pemayangtse, Tashiding)

These two cases are NOT the case in the published paper (27 Jan 2023, Maltim, North Sikkim). Figure readings are in `cdac_slides/README.md`.

- **12 Mar 2024, 17:03:** 24 h simulation. The forest department intervened on the forecast line, and the deck says 0.54 km² that was forecast to burn did not.
- **13 Mar 2024, 12:33:** 48 h simulation from a NASA FIRMS alert. The deck says about 3.00 km² was saved after intervention. It was checked by overlaying the forecast on a Sentinel-2A image of 19 Mar 2024.
- No accuracy metric is reported (no area overlap, Sørensen or Jaccard score, or arrival-time error). Both "saved" areas are counterfactual claims.

## Plans

- FSI-C-DAC MoU in progress for a national system with zones for the Himalaya, Deccan, Western Ghats, North East and rest of India.
- High-frequency fire danger rating.
- AI/ML for dynamic land-cover updates.
- NSM 2.0.
- A demo video and press release are linked in the deck.

## What this means for a Ratapani version

- **Ignition point:** the model starts from a known fire, so it forecasts spread, not where new fires start.
- **Fuel models:** Ratapani's litter fires in dry teak forest would map to Anderson low-load models: FBFM 8 or 9 for leaf litter, FBFM 1–3 for grass. The 1 h load should be tied to FSI's < 20 g/ft² class (< 2.2 t/ha).
- **Our earlier finding:** wind direction added nothing to 500 m, 5-day spread prediction in Ratapani. Front distance and freshness dominated (research thread). A physics model should be tested against that baseline on our dated scars: VIIRS day plus the scar perimeter.

## Published setup (Kale et al. 2024, Remote Sensing 16:2480; found 14 Oct)
- **Grid:** WRF domains of 7.2 km, 2.4 km and 800 m, with a 40 m fire mesh.
- **Fuel:** the "Forest" class is set to Anderson model 8, with load 0.27 kg/m², depth 0.061 m and moisture of extinction 0.30.
- **Compute:** a 24 h forecast took 2 h 11 min on 240 cores.
- **Check (27 Jan 2023 fire, Maltim, North Sikkim, mostly scrub):** the forecast burnt 1.72 km² against 1.07 km² mapped from Sentinel-2, about 60% over. No overlap score was given.

More detail is in `scouting/fire_spread_models.md`.
