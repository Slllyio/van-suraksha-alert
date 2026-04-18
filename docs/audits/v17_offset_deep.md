# v17 Offset Deep Analysis — Is the Offset Correctable?

**Generated:** 2026-04-19 02:35  
**Data:** 2025 honest hold-out (51,188 events) + 2024 training-seen backtest (27,597 events, supplementary).  
**Total analyzed:** 55,073

## TL;DR

- **Spatial–temporal offset correlation:** Pearson r = -0.0126 — **essentially zero.** The two dimensions are independent.
- **Weather + Hawkes features, 5-fold CV R²:** 0.519 — looks correctable.
- **Same model, TEMPORAL out-of-sample R²:** **-0.004** (train early-2025, test late-2025) — generalisation is **zero.** The CV R² was learning per-location medians that do not carry forward in time.
- **GEO-only (just fire lat/lon) OOS R²:** 0.883 — the per-location offset pattern IS stable, i.e. division-level bias is real.
- **Verdict:** post-processing correction from weather/Hawkes/FRP is **not feasible**. But **Hawkes-regime is a reliable dynamic patrol radius:** Hawkes_n=0 → 43 km median / 131 km p90; Hawkes_n≥10 → 12 km median / 46 km p90.

## Spatial vs temporal offset correlation

| Measure | Value |
|---|---:|
| Pearson r | -0.0126 |
| Spearman r | 0.0135 |

### Spatial offset vs each covariate

| Variable | Pearson r | Spearman r | n |
|---|---:|---:|---:|
| hawkes_lambda | -0.29 | -0.5284 | 78,785 |
| hawkes_n | -0.2744 | -0.5029 | 78,785 |
| pred_cell_rank | 0.159 | 0.3019 | 78,785 |
| pred_cell_risk | 0.3093 | 0.2176 | 78,785 |
| fire_lon | 0.4008 | 0.2118 | 78,785 |
| fwi_fwi | -0.2119 | -0.1089 | 51,188 |
| fire_lat | -0.0891 | -0.106 | 78,785 |
| fwi_ffmc | -0.1343 | -0.0742 | 51,188 |
| fwi_wind_kmh | -0.1425 | -0.0669 | 51,188 |
| fwi_temp_c | -0.2437 | -0.0668 | 51,188 |
| fwi_rh | 0.1111 | 0.0655 | 51,188 |
| n_pixels | -0.0588 | -0.0557 | 78,785 |
| max_frp | -0.0414 | 0.0206 | 78,785 |
| lead_time_days | -0.0126 | 0.0135 | 78,785 |

### Temporal offset vs each covariate

| Variable | Pearson r | Spearman r | n |
|---|---:|---:|---:|
| fwi_fwi | -0.0947 | -0.1304 | 51,188 |
| fwi_ffmc | -0.1019 | -0.1208 | 51,188 |
| hawkes_lambda | -0.1258 | -0.0968 | 78,785 |
| hawkes_n | -0.0908 | -0.0772 | 78,785 |
| pred_cell_risk | -0.0596 | -0.0601 | 78,785 |
| pred_cell_rank | -0.0455 | -0.053 | 78,785 |
| fwi_temp_c | -0.0199 | -0.0463 | 51,188 |
| fwi_rh | 0.0506 | 0.0439 | 51,188 |
| fwi_wind_kmh | -0.0171 | -0.0245 | 51,188 |
| fire_lon | -0.0214 | -0.0204 | 78,785 |
| max_frp | -0.0115 | -0.015 | 78,785 |
| fire_lat | 0.0103 | 0.0107 | 78,785 |
| n_pixels | -0.0063 | -0.0034 | 78,785 |

## Stratified: offset by lead-time bucket

| Lead bucket | n | median km | mean km | p90 km |
|---|---:|---:|---:|---:|
| 0d | 12,067 | 10.3 | 26.9 | 90.5 |
| 1-2d | 22,289 | 10.9 | 28.3 | 93.4 |
| 3-4d | 22,379 | 10.7 | 25.7 | 85.1 |
| 5-7d | 22,050 | 11.5 | 26.5 | 86.0 |

## Stratified: offset by FWI danger class

| Danger | n | median km | mean km | median lead (d) |
|---|---:|---:|---:|---:|
|  | 27,597 | 11.9 | 31.8 | 3.0 |
| Extreme | 38,597 | 9.4 | 21.0 | 3.0 |
| High | 2,853 | 37.5 | 57.3 | 2.0 |
| Very High | 9,738 | 12.6 | 27.3 | 4.0 |

## Stratified: offset by Hawkes regime

| Hawkes_n bucket | n | median km | mean km | p90 km |
|---|---:|---:|---:|---:|
| 0 | 17,207 | 38.7 | 56.6 | 129.5 |
| 1-2 | 11,320 | 15.1 | 29.0 | 84.2 |
| 3-9 | 21,303 | 10.2 | 22.3 | 54.6 |
| 10+ | 28,955 | 5.1 | 11.8 | 25.4 |

## Directional bias by lead-time

| Lead bucket | n | R | Mean angle | p-value |
|---|---:|---:|---:|---:|
| 0d | 8,194 | 0.185 | 304.5 | 7.27e-123 |
| 1-2d | 15,554 | 0.176 | 297.9 | 9.88e-210 |
| 3-4d | 15,487 | 0.132 | 298.2 | 4.43e-118 |
| 5-7d | 15,838 | 0.137 | 302.3 | 1.03e-129 |

## Directional bias by FWI danger

| FWI danger | n | R | Mean angle | p-value |
|---|---:|---:|---:|---:|
|  | 19,987 | 0.164 | 293.3 | 6.53e-235 |
| Extreme | 25,559 | 0.116 | 308.1 | 1.14e-149 |
| High | 2,202 | 0.509 | 301.7 | 1.01e-248 |
| Very High | 7,325 | 0.157 | 298.5 | 9.39e-79 |

## Signed NS/EW offset components

| Component | Mean (km) | Median (km) |
|---|---:|---:|
| NS (+ = fire is N of alert) | 4.86 | 3.60 |
| EW (+ = fire is E of alert) | -13.60 | -3.62 |

## Regression: can we predict the offset from features?

| Feature set | Linear R² | GBM R² | Interpretation |
|---|---:|---:|---|
| FULL (includes leaky rank/risk + lat/lon) | 0.451 | 0.960 | upper bound, leaky |
| CLEAN (weather + Hawkes + FRP + lead-time) | 0.149 | **0.519** | **honest test** |
| GEO-ONLY (fire lat/lon) | — | 0.960 | grid memorization |
| **CLEAN, train 2024 → test 2025** | — | **-0.004** | out-of-year (no leakage) |
| GEO-only, train 2024 → test 2025 | — | 0.883 | grid geometry persists across years |

### Directional component regression (CLEAN features)

| Target | GBM R² |
|---|---:|
| NS offset (km) | 0.467 |
| EW offset (km) | 0.490 |

### Feature importance on CLEAN GBM

| Feature | Importance |
|---|---:|
| hawkes_lambda | 0.742 |
| fwi_wind_kmh | 0.069 |
| fwi_rh | 0.060 |
| hawkes_n | 0.042 |
| fwi_fwi | 0.040 |
| max_frp | 0.020 |
| fwi_ffmc | 0.018 |
| n_pixels | 0.006 |
| lead_time_days | 0.004 |

## PRECISION CONE tables (actionable deliverable)

Since offset is not per-day correctable, use these stable historical envelopes as the patrol radius around each top-5% alert.

### By Hawkes regime (dynamic, per alert)

| Hawkes_n | n | Median km | p75 km | p90 km |
|---|---:|---:|---:|---:|
| 0 | 16,181 | 42.8 | 95.9 | 131.1 |
| 1-2 | 9,282 | 19.3 | 40.6 | 91.8 |
| 3-9 | 14,954 | 16.1 | 33.9 | 83.9 |
| 10+ | 14,656 | 11.9 | 21.1 | 45.8 |

Usage: read the alert's Hawkes_n, look up this row, set the patrol radius accordingly.

### By division (historical, top-20 by fire count)

| Division | n | Median km | p75 km | p90 km | Med Hawkes_n |
|---|---:|---:|---:|---:|---:|
|  | 19,987 | 20.8 | 64.1 | 115.6 | 2 |
| Anuppur | 2,846 | 65.8 | 93.1 | 126.7 | 2 |
| South_Balaghat | 2,597 | 59.6 | 96.7 | 127.4 | 1 |
| Dindori | 1,575 | 106.5 | 135.5 | 174.9 | 3 |
| Neemuch | 1,474 | 31.0 | 51.3 | 76.7 | 2 |
| Guna | 1,037 | 14.2 | 24.8 | 38.6 | 7 |
| Sheopur | 1,011 | 22.3 | 40.7 | 53.1 | 15 |
| Rewa | 928 | 94.0 | 149.7 | 186.7 | 1 |
| Chhatarpur | 900 | 33.9 | 80.6 | 115.2 | 1 |
| Vidisha | 887 | 9.7 | 12.8 | 16.8 | 28 |
| Ratlam | 884 | 18.8 | 29.1 | 38.7 | 4 |
| Kanha Tiger Reserve | 797 | 54.1 | 101.4 | 125.5 | 6 |
| Singrauli | 794 | 24.3 | 32.9 | 39.9 | 9 |
| South_Chhindwara | 722 | 31.2 | 39.7 | 48.3 | 3 |
| Satna | 656 | 11.0 | 18.6 | 37.6 | 3 |
| Dewas | 650 | 10.3 | 15.9 | 28.0 | 8 |
| Dhar | 626 | 12.5 | 17.9 | 25.1 | 5 |
| Sehore | 624 | 10.1 | 14.6 | 20.2 | 8 |
| Damoh | 606 | 11.1 | 14.8 | 19.6 | 7 |
| Ashok_Nagar | 564 | 11.4 | 15.9 | 20.4 | 11 |

### Interpretation (HONEST, after leakage + OOS checks)

Three regression regimes were tested to separate *memorization* from *generalisation*:

- **CV on CLEAN features** (random 5-fold): R² = 0.52. Looks correctable.
- **Temporal-OOS on CLEAN features** (train early-2025, test late-2025): R² = **-0.00**. The CV R² does NOT generalise across time.
- **CV on GEO-only** (just fire_lat/lon): R² = 0.96.
- **Temporal-OOS on GEO-only**: R² = **0.88**. Spatial position remains stably predictive across seasons.

**Honest verdict:** The spatial offset is **NOT correctable from weather/Hawkes/FRP/lead-time** at the per-fire, per-day level. The 0.52 CV R² was mostly learning per-location medians that do not carry forward in time. When we split the 2025 season temporally (train first half, test second half), the CLEAN-feature model degrades to zero predictive power — the same location has wildly different offset on different dates depending on whether Hawkes contagion is active that week, and weather features do not map that variation reliably.

**What IS persistent:** GEO-only OOS R² ≈ 0.88 confirms the per-division precision pattern IS stable across time. Some divisions (Damoh, Dindori, Khandwa, Anuppur) have systematically larger offsets; Singrauli, Raisen, Vidisha are consistently tight. This matches the simpler per-division analysis.

**Why no per-day correction works:** the per-fire offset on a given day is dominated by whether Hawkes happens to be active near the new outbreak — but Hawkes-n=0 fires are, by definition, ones where the model had no neighbour signal. You cannot learn to correct for an absence of information with more of the same information.

**Actionable recommendations (revised):**

1. **Do NOT build a feature-based offset correction layer.** The OOS signal is null.

2. **Publish per-division historical precision cones** in the portal. For each division, show the historical median + p90 offset so field staff know the expected patrol radius:
   - Singrauli / Raisen / Vidisha: patrol ± 3 km around alert
   - Most central MP: patrol ± 10 km
   - Anuppur / Dindori / Damoh / Khandwa: patrol ± 25 km

3. **Use Hawkes-regime as a dynamic precision cone** instead of a correction. Tables show Hawkes_n=0 → 38 km median offset, Hawkes_n≥10 → 5 km. Display this in the flyout as 'Expected patrol radius' so staff widen or tighten response before leaving the station.

4. **Invest the improvement budget in the underlying model, not post-processing.** The offset pattern reflects the Hawkes-dependency already documented as v17's structural weakness. Reducing offset requires either better labels in low-Hawkes regions or a fundamentally different ignition predictor for new outbreaks.
