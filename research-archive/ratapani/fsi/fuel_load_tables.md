# FSI surface fuel load: every table and number we have

Sources:
1. Dr Sunil Chandra (FSI) deck "Surface Fuel Load Mapping.pptx" (E:\FIRE\fsi_data), text in `slide_text/`.
2. **The full public report**: FSI Technical Information Series Vol 3 No 2 (2026), "Surface Fuel Load Mapping 2023-24", 108 pages. Downloaded 14 Oct from fsiforestfire.gov.in/Home/Publication into `fsi_reports/Surface Fuel Load Mapping.pdf`. Two sister reports are in the same folder: Forest Fire Risk Zone Mapping, Forest Fire Burnt Area Mapping.

**Important:** neither source publishes the 272 per-stratum mean fuel loads, the sample points or the raster. They give only the method, the class thresholds and area tables. Anyone rebuilding the map has to measure the stratum values again, or ask FSI for them (forestfiremonitoring@gmail.com).

## Method (report section 1.4)

- **Field samples:** 15,114 points pan-India, "collected by ground truth teams in areas adjacent to fire affected area and in different forest stratums further supported with NFI data" (National Forest Inventory).
- **Plot:** 1 ft × 1 ft (deck slide 29). All surface material is collected: litter, duff, grass, twigs, downed wood.
- **Weighing:** fresh weight is recorded in the field. The sample is oven-dried for 3 hours at about 50 °C and weighed again to give the dry weight. Moisture is fresh minus dry.
- **Units:** g/ft² of oven-dry fuel. 1 g/ft² = 10.76 g/m² = 0.1076 t/ha.
- **Strata:** forest type group (17) × canopy density (4) × slope class (4) = 272. Each stratum gets the **mean** of the field samples that fall in it. Strata with no samples are merged into "similar strata"; the merge rule is not given.
- **Layers:**
  - Forest cover map (FSI, from Sentinel-2A per the deck). It is also the forest mask.
  - Forest type map (FSI, 2021 baseline, 1:50,000, Champion & Seth).
  - Slope from 30 m SRTM DEM.
- **Output:** the map is clipped to Recorded Forest Area / Green Wash and shown in 4 classes.
- **Fuel moisture map:** IDW interpolation of moisture from 516 sample locations (section 1.4.4).
- **Stated limits:** weather was left out "due to scale and interoperability limitations". A single date can't capture changes through the season. FSI says periodic resampling is needed.
- **The deck also cites, from Indian literature:**
  - Fuel size classes: 1 h (leaves/needles), 10 h (twigs < 0.7 cm) and 100 h (0.7–2.5 cm).
  - Conversion: fuel load (t/ha) = W_dry(g) × 10,000 / (A(m²) × 10⁶).
  - Chir pine burn efficiency is about 70.8% in May–June.

## Canopy density classes (Table 1.1)

| Class | Tree canopy density |
|---|---|
| Very Dense Forest | ≥ 70% |
| Moderately Dense Forest | 40–70% |
| Open Forest | 10–40% |
| Scrub | < 10% (forest land) |

## Slope classes (Table 1.3, SRTM 30 m)

| Class | Degrees |
|---|---|
| 1 | 0–10 |
| 2 | 11–20 |
| 3 | 21–30 |
| 4 | > 30 |

## Forest type groups (Table 1.2)

| Group | Type | Group | Type |
|---|---|---|---|
| 1 | Tropical Wet Evergreen | 10 | Subtropical Dry Evergreen |
| 2 | Tropical Semi-Evergreen | 11 | Montane Wet Temperate |
| 3 | Tropical Moist Deciduous | 12 | Himalayan Moist Temperate |
| 4 | Littoral and Swamp | 13 | Himalayan Dry Temperate |
| **5** | **Tropical Dry Deciduous (Ratapani: teak and mixed dry deciduous)** | 14 | Sub Alpine |
| 6 | Tropical Thorn | 15 | Moist Alpine Scrub |
| 7 | Tropical Dry Evergreen | 16 | Dry Alpine Scrub |
| 8 | Subtropical Broadleaved Hill | 17 | Plantation / Trees outside forest |
| 9 | Subtropical Pine | | |

## Fuel load classes (Table 1.4)

| Class | g/ft² | t/ha (converted) |
|---|---|---|
| Very High | > 60 | > 6.5 |
| High | 40–60 | 4.3–6.5 |
| Moderate | 20–40 | 2.2–4.3 |
| Low | 0–20 | 0–2.2 |

## National area by class (Table 1.5, RFA/Green Wash)

| Class | km² | % of digitised RFA/GW |
|---|---|---|
| Very High | 15,382.54 | 2.08 |
| High | 61,159.29 | 8.25 |
| Moderate | 234,033.20 | 31.57 |
| Low | 232,302.43 | 31.34 |
| Total | 542,877.46 | 73.24 |

## Madhya Pradesh (Table 2.14.1, km² inside RFA)

| | Very High | High | Moderate | Low | Total |
|---|---|---|---|---|---|
| **Raisen** (most of Ratapani) | 0 | 0 | 64.18 | 2,480.84 | 2,545.02 |
| **Sehore** | 0 | 0 | 42.66 | 1,153.45 | 1,196.11 |
| **Bhopal** | 0 | 0 | 1.54 | 253.57 | 255.11 |
| MP total | 0 | 433.40 | 11,636.70 | 57,492.07 | 69,562.17 |

- In MP, 62% of RFA forest is Low, 12.5% Moderate and 0.5% High; none is Very High.
- High and Moderate are concentrated in Balaghat, Mandla, Dindori and Seoni.
- Species listed for MP: Tectona grandis, Diospyros tomentosa, Syzygium cumini, Shorea robusta, Boswellia serrata, Dalbergia paniculata, Anogeissus latifolia, Madhuca indica, Terminalia tomentosa, Lagerstroemia parviflora.
- **Ratapani's districts are 97–99% "Low" (< 20 g/ft²).** On FSI's own map, Ratapani is nearly one class, so it can't separate cells inside the sanctuary.

## Other numbers from the deck

- FSI says 93% of fires start on the surface (low intensity).
- Forest cover is 21.76% of India's land (ISFR 2023). Fire-prone forest is 35.46% (ISFR 2021): extremely 2.81%, very high 7.85%, high 11.61%, moderate 13.19%.
- Burnt area (deck says 2025-26; the burnt-area report shows these are 2023-24 figures): MP 3,172.13 km² (severe 1.13, moderate 38.14, low 3,132.86). India 34,562 km².
- Detections Nov 2025–Jun 2026: MP 2,015 MODIS and 20,692 VIIRS.
- Nainital (May 2024) field-checked severity: severe 0.41, moderate 42.17, low 362.84 km². The worst burns were on slopes over 45°.

## Ratapani check already run (`README.md`, fuel strata section)

A proxy of the 272 strata (AlphaEarth clusters × pre-season NDVI quartile × FSI slope class; 95 strata occur in Ratapani), with burn rate standing in for fuel load. On real beats at 5 picks per beat per day:
- On its own it catches 22.6% of first burns, against 16.6% for random.
- Added to the lean model it gives 28.1%, against 29.1% without it.

Measured g/ft² would only help if it differs from what burn history already shows.

## Full read of the report (Akkshay's copy, E:\FIRE\fsi_data\Surface Fuel Load Mapping.pdf, 14 Oct)

**Same file:** it is byte-identical to the public download in `fsi_reports/` (SHA-256 4400d4e0…d4a3, 18,543,613 bytes). I read all 108 pages: front matter, glossary, chapter 1, all 36 state/UT sections, and every figure legend. It holds **no** per-stratum fuel values, sample counts per stratum or per state, regression or model equations, accuracy assessment, sample locations or downloadable raster. The only model is "stratum mean of field samples" (1.4.2).

What it adds beyond the sections above:
- **Definitions (glossary):**
  - Litter = undecomposed woody material of 2 mm to 5 cm diameter.
  - Surface fuel load = dead vegetation, leaves, twigs and branches on the forest floor.
  - Forest cover = at least 1 ha with at least 10% canopy. Canopy classes are as in Table 1.1 (VDF ≥ 70, MDF 40–70, OF 10–40, Scrub < 10).
- **Forest type map:** FSI FTM is built on the 2021 forest cover baseline at 1:50,000. The deck's national FTM figure is "Atlas 2020", from IRS Resourcesat-2 LISS-III 2017–18 data (Champion & Seth 1968 classes).
- **Fuel moisture map (Fig 1.5):** IDW from 516 sample locations. The legend is in **g/ft²** (moisture mass), from 0 to 178. Central India is almost all at the low (green) end. No numbers are given per region.
- **MP map (Fig 2.14.1):** around Raisen and Sehore, the forest inside RFA is drawn as Low fuel load, with no Moderate patches visible at state scale. Moderate (yellow) is concentrated in Balaghat, Mandla, Dindori and Seoni.
- **State table 1.6 (km², RFA/GW area, then Very High / High / Moderate / Low):** MP 92,769.42 RFA/GW → 0 / 433.40 / 11,636.70 / 57,492.07. Comparators:
  - Chhattisgarh: 0 / 449.00 / 19,942.70 / 22,376.29
  - Maharashtra: 0 / 528.75 / 19,528.75 / 17,544.23
  - Uttarakhand: 1,150.21 / 7,869.42 / 6,995.97 / 958.36
  - National total: 15,382.54 / 61,159.29 / 234,033.20 / 232,302.43
- **Very High and High areas** are mostly in Arunachal Pradesh, J&K, Andaman & Nicobar and Uttarakhand (montane wet temperate, Himalayan moist temperate, subtropical pine and tropical semi-evergreen forests).
- **Conclusion (1.6):** weather was left out because of scale and interoperability. FSI says single-date imagery can't give high precision and periodic sampling is needed, and suggests "wall to wall" mapping as further work.
- **Credits:** project investigator Dr Sunil Chandra (FSI FGD, retired), with Vikas Gusain and Satyendra Kumar. ISBN 978-81-979398-0-8.

**For rebuilding the map:** the 272 stratum values have to come from FSI (forestfiremonitoring@gmail.com, FGD Dehradun) or from new plots. Otherwise use literature values for tropical dry deciduous litter. The deck cites Achanakmar-Amarkantak plots using 1 m × 1 m quadrats with high, medium and low fire-frequency zones.
