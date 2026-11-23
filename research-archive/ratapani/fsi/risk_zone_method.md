# FSI forest fire risk zone mapping: how FSI does it

**Source:** FSI, "Forest Fire Risk Zone Mapping" (2023-24 report). Saved as `fsi_reports/Forest Fire Risk Zone Mapping.pdf`. Akkshay's copy at E:\FIRE\fsi_data is byte-identical (SHA-256 checked, 14 Oct). I read chapter 1 in full, plus the Madhya Pradesh tables.

**For:** the prediction threads ("WeatherNext and TimesFM pipeline plan", "Fire prediction research").

## Method

- **Model:** log-linear regression (LLRM), fitted separately for each of 8 physiographic zones (merged groups of FSI zones).
  - Target: fire frequency from FSI's historical fire points.
  - Plot data from the National Forest Inventory (NFI) is also used.
- **Input layers:** each is reclassed into 4 classes.

  | Layer | Source |
  |---|---|
  | Forest type (FI) | FSI forest type map 2023 |
  | Forest density | FSI forest cover (VDF / MDF / OF / scrub) |
  | Elevation (EI), aspect (AI), slope (SLI) | ASTER GDEM 30 m |
  | Biotic influence (BII) | buffers around roads and settlements |
  | Grazing (GI) | IDW from NFI grazing observations |
  | Soil (SI) | NBSS&LUP soil map |

- **Equation:** RZ = Ø·FI + α·EI + β·AI + Ω·SLI + §·BII + #·(GI + SI)
  - The coefficients are fitted per zone but **not published**.
  - The weights for each class are not given either.
- **Output:** 5 classes (Very High, High, Moderate, Low, Very Low) for each pixel inside the forest mask.
- **The map is static.** It has no weather and no time dimension.
- **Validation:** none reported. There is no AUC, no hit rate on held-out fires and no confusion matrix.

## Madhya Pradesh (km²)

| | Very High | High | Moderate | Low |
|---|---|---|---|---|
| MP | 2,563.99 | 28,873.28 | 28,961.00 | 9,163.90 |
| Raisen | 38.65 | 949.01 | 1,401.75 | 170.60 |
| Sehore | 15.62 | 511.47 | 601.37 | 77.16 |
| Bhopal | 0.50 | 66.76 | 148.43 | 48.09 |

- Around Ratapani, most forest is High or Moderate, and very little is Very High.
- That leaves almost nothing to separate one 500 m cell from another.

## What it means for our models

- The layers are the static terrain, forest and access factors our models already see: slope, aspect, elevation, canopy from NDVI, and distance to villages and roads. The fuel-strata proxy test already covered forest type × density × slope:
  - on its own it caught 22.6% of first burns, against 16.6% for random;
  - it added nothing to the lean model (28.1% vs 29.1%).
- Each cell's own burn history beats any static map. Our lean model on real beats catches 29.5% (LOSO), against 16.6% for random.
- Our research finding agrees with FSI's biotic-influence layer, but in the opposite direction: interior cells ignite about 2× more often than near-village cells. FSI scores closeness to settlements as higher risk.
- **No experiment needed.** Without the coefficients, the only way to use the map is to rasterise FSI's class map. It isn't published as data, so it would have to be requested from FSI. A rebuilt LLRM from these layers would be a weaker version of what we already have.
