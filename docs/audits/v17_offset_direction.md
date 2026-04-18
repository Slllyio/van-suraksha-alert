# v17 Spatial Offset Direction Analysis

**Generated:** 2026-04-19 01:00

When v17 misses a real fire, is its prediction shifted in a consistent direction (systematic bias) or spread uniformly (random error)? For every 2025 fire where the nearest top-5% cell was more than 5.0 km away, we compute the bearing from the actual fire to the model's nearest alerted cell and apply a Rayleigh test for circular non-uniformity.

## Global result

| Metric | Value |
|---|---:|
| Fires analysed | 35,359 |
| Mean resultant vector R | **0.1529** |
| Mean bearing (deg) | 306.8 |
| Mean compass direction | **NW** |
| Rayleigh p-value | 0.00e+00 |

**Systematic bias** toward NW (R=0.15).

## Compass distribution

| Direction | # fires | Pct |
|---|---:|---:|
| N | 2,308 | 6.5% |
| NNE | 1,797 | 5.1% |
| NE | 1,915 | 5.4% |
| ENE | 1,637 | 4.6% |
| E | 2,136 | 6.0% |
| ESE | 1,641 | 4.6% |
| SE | 1,655 | 4.7% |
| SSE | 1,772 | 5.0% |
| S | 2,207 | 6.2% |
| SSW | 1,912 | 5.4% |
| SW | 2,050 | 5.8% |
| WSW | 1,345 | 3.8% |
| W | 2,773 | 7.8% |
| WNW | 3,622 | 10.2% |
| NW | 4,105 | 11.6% |
| NNW | 2,484 | 7.0% |

A uniform distribution would put ~6.25% in each of the 16 bins.

## By Hawkes regime

| Regime | n | R | Mean angle | Compass | p-value |
|---|---:|---:|---:|---|---:|
| Low-Hawkes (new outbreaks, n<=1) | 12,051 | 0.238 | 294.7 | WNW | 9.74e-297 |
| High-Hawkes (contagion, n>=3) | 21,058 | 0.122 | 323.7 | NW | 1.57e-136 |

## Divisions with strongest bias (min 50 missed fires)

| Division | n | R | Mean angle | Compass | p-value |
|---|---:|---:|---:|---|---:|
| Bhind | 455 | 0.900 | 279.4 | W | 7.70e-161 |
| Anuppur | 2904 | 0.792 | 294.0 | WNW | 0.00e+00 |
| Singrauli | 794 | 0.788 | 342.5 | NNW | 8.75e-215 |
| Kanha Tiger Reserve | 808 | 0.787 | 303.8 | NW | 3.24e-218 |
| Dindori | 1602 | 0.771 | 328.3 | NNW | 0.00e+00 |
| Sendhwa | 289 | 0.770 | 30.8 | NNE | 4.28e-75 |
| Hoshangabad | 565 | 0.739 | 164.3 | SSE | 1.24e-134 |
| Rewa | 936 | 0.714 | 196.4 | SSW | 3.84e-208 |
| Indore | 470 | 0.700 | 144.0 | SE | 1.24e-100 |
| South_Chhindwara | 727 | 0.687 | 340.9 | NNW | 1.56e-149 |
| Sheopur | 1016 | 0.678 | 77.1 | ENE | 2.71e-203 |
| South_Balaghat | 2650 | 0.638 | 310.6 | NW | 0.00e+00 |
| North_Balaghat | 318 | 0.628 | 294.8 | WNW | 2.86e-55 |
| Datiya | 414 | 0.599 | 283.3 | WNW | 3.87e-65 |
| FDCM_Vidisha | 126 | 0.570 | 78.4 | ENE | 1.60e-18 |

## How to read this

- **Rayleigh R**: 0 = uniform directions (random), 1 = all point same way (systematic bias)
- **Rayleigh p**: null = "directions are uniform." p < 0.01 = bias is real
- If global R < 0.15, errors are essentially **random** (random walk-style miss pattern)
- If some divisions have R > 0.3 while others are ~0, the model has **localised biases** — potentially from boundary effects (cells near division edges) or from FIRMS detection timing (afternoon wind direction)
