# FSI burnt area mapping: how FSI does it

**Source:** FSI, "Assessment of Forest Fire Burnt Area Report 2023-24". Saved as `fsi_reports/Forest Fire Burnt Area Mapping.pdf`. Akkshay's copy at E:\FIRE\fsi_data is byte-identical (SHA-256 checked, 14 Oct). I read chapter 1 in full, plus the Madhya Pradesh section.

**For:** the "Burn scar for every fire alert" thread.

## Method

- **Imagery:** Sentinel-2 MSI, using SWIR (20 m) and NIR.
  - Season covered: November 2023 to June 2024.
  - Other sensors are used only where Sentinel-2 is cloudy. The report does not name them.
- **Index:**
  - NBR = (NIR − SWIR) / (NIR + SWIR).
  - dNBR = pre-fire NBR − post-fire NBR, from a pre-fire image and a post-fire image.
- **Severity thresholds:** USGS dNBR × 10³ classes, adjusted using a Manipur study and field observations.

  | Class | dNBR × 10³ |
  |---|---|
  | Unburnt | < 100 |
  | Low | 100–269 |
  | Moderate | 270–659 |
  | Severe | ≥ 660 |

- **Delineation:** scars are drawn by visual or semi-automatic interpretation, using band combinations, geometry and texture. There is no fully automatic rule.
- **Mask:** results are clipped to Recorded Forest Area / Green Wash.
- **Minimum mapping unit:** the report lists "MMU" in its glossary but never gives a value.
- **Most important period:** early March to late April.

## How alerts are used

- VIIRS NRT fire points are used to **find** where to look for scars.
- Large-fire polygons (at least 3 adjacent VIIRS pixels) are used to **bound** a scar's extent.
- **There is no per-alert scar product.** No alert ID is linked to a scar polygon, and scars carry no burn dates. The output is one season-wide burnt-area map with severity classes.

## Accuracy

- **Field check:** 674 burnt patches visited; 668 were confirmed burnt.
- **Image check:** 13,365 points interpreted on Landsat-8 OLI.
  - Overall accuracy 98.90%, kappa 0.98.
  - The figures are inflated by the large number of unburnt points.

  | Class | User's accuracy % | Producer's accuracy % |
  |---|---|---|
  | Severe | 73.33 | 73.33 |
  | Moderate | 94.29 | 86.39 |
  | Low | 97.78 | 99.41 |
  | Unburnt | 99.85 | 99.23 |

- **Known sources of false burns:**
  - leaf shedding
  - cloud and terrain shadow, hillshade
  - marshes and wet areas
  - dark soil

## Madhya Pradesh and Ratapani districts (2023-24)

- **MP total:** 3,172.13 km² burnt, which is 3.42% of RFA.
  - Severe 1.13 km², moderate 38.14 km², low 3,132.86 km².
  - Detections: VIIRS 15,878 and MODIS 1,592.
  - The fuel deck quotes the same 3,172.13 km² as "2025-26". The figure is really from 2023-24.

| District | Burnt km² (severe / moderate / low / total) | VIIRS detections, 2022-23 → 2023-24 |
|---|---|---|
| Raisen | 0.00 / 1.27 / 259.85 / 261.12 | 1,352 → 1,696 |
| Sehore | 0.02 / 2.41 / 120.27 / 122.70 | 632 → 1,136 |
| Bhopal | 0.00 / 1.71 / 21.92 / 23.63 | 98 → 123 |

- Raisen has MP's largest **low-severity** burnt area.
- More than 99% of what burns around Ratapani is low severity. That fits light litter fires.

## How this compares with our labels

| | FSI | Our scar labels |
|---|---|---|
| Sensors | Sentinel-2, others when cloudy | Sentinel-2 + Landsat, 2017–2026 |
| Index | dNBR, one pre and one post image, absolute thresholds | NBR drop relative to a 1.5 km surround, over short 2–5 day gaps |
| Dating | none (season map) | window (ws, we], dated to the VIIRS day where one exists |
| Smallest scar | not stated | < 2 ha dropped |
| Accuracy | OA 98.9% (inflated by unburnt points); low class UA 97.8% | ~83% precision / ~71% recall on 400 checked points |
| Alert link | alerts only guide where to look | VIIRS within 750 m dates 88% of fire points |

**What to borrow for per-alert scars:**
- Take each FSI/FIRMS alert as a seed.
- Search Sentinel-2 and Landsat scenes from just before to just after the alert. Use FSI's dNBR thresholds (low ≥ 0.10) for severity.
- Use the large-fire polygon as the extent where one exists.
- Attach the alert ID, scar area, severity and the image pair used.
- Flag low-confidence scars during leaf fall (Jan–Feb, our weakest months) and on shadowed slopes.

**Data still missing:** FSI's scar polygons are not published, so they can't serve as a comparison set without a request to FSI.
