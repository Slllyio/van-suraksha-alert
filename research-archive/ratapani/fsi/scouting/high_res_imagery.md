# Free or cheap very-high-resolution imagery for small understory burn scars (vhr thread, October 2026)

Scope: sources finer than Sentinel-2 that could help us (a) check our scar labels, (b) date scars more tightly, and (c) find small scars (<2 ha) that Sentinel-2 misses in Ratapani (about 23°N, 77.8°E). This note does not repeat `alert_burn_scars*.md` (S2/Landsat algorithms, Prithvi, FireCCI), `fire_detection_sources.md` (thermal and active-fire sources) or `fire-prediction-landscape.md` §8. That section already decided, on 13 Oct, that we have no Planet access, and that validation uses about 400 points checked by eye plus "dated Google Earth high-res imagery where it exists". Section 0 below measures how much of that imagery exists.

Reading status: 7 papers read in full (Pham-Duc et al. 2026; Balakavi et al. 2025; Walker et al. 2022; Melchiorre & Boschetti 2018; Kim, Lee & Park 2024; Razzak et al. 2021; Simes et al. 2024), 1 paper read in part (Wolters et al. 2023), and 10 official documents or pages read in full (NICFI User Guide, NICFI Jan 2025 notice, Planet TFO-in-GEE doc, Planet forum thread, Bhoonidhi 2025 brochure, Resourcesat-2 handbook, Vadrevu CSDAP pilot sheet, SEN2SR and opensr-test READMEs, Mongabay India drones article). Read as abstract only: Vetrita et al. 2025, Martins et al. 2022, Dalagnol et al. 2023, Cho et al. 2023. Publisher blocks (ScienceDirect, T&F Cloudflare, MDPI main site) stopped the full reads. My own reasoning is marked [inference].

---

## 0. Our own numbers first (computed, not published)

**A. How small are our scars, and how coarse is our dating?** These come from `scratchpad/scar_viirs.csv`: 15,754 burned cell-seasons, 2017–2024, the S2/Landsat scar table used for VIIRS dating.
- Burned area inside a 25 ha cell: median 3.24 ha. 2,036 cell-seasons (13%) have 0.5–1 ha, 2,950 (19%) have 1–2 ha, so **32% of all burned cell-seasons are ≤2 ha**. The minimum is 0.52 ha, which is the 0.5 ha rule.
- The share with a VIIRS match falls with size: 30% for ≤2 ha, 35% for 2–5 ha, 47% for 5–10 ha, 60% for 10–25 ha. Small scars are the ones that lack an independent date.
- The optical dating window (last clear "unburned" to first "burned" look) has a median of 5 days, a mean of 7.0 and a maximum of 20. VHR imagery can only tighten dates where it adds a look inside that window.

**B. What Esri World Imagery / Wayback actually holds over Ratapani (FULL: queried the Wayback metadata services directly).** I queried all 197 Wayback releases (2014 to 24 Sep 2026) at the 30 cm, 60 cm and 1.2 m metadata layers for the sanctuary bounding box (77.337–78.068°E, 22.814–23.109°N). The archive holds **131 distinct VHR acquisitions** (Ikonos 1 m, WorldView-1/2/3/4, GeoEye-1, Vantor Legion; 0.31–0.5 m). Jan–Jun (fire-season) dates by year:

| Season | n | Dates (MMDD) |
|---|---|---|
| 2016 | 2 | 0109, 0112 |
| 2017 | 5 | 0128, 0202, 0203, 0205, 0215 |
| 2018 | 4 | 0119, 0130, 0525, 0614 |
| 2019 | 8 | 0115, 0116, 0118, 0318, 0320, 0401, 0509, 0611 |
| 2020 | 8 | 0109, 0131, 0303, 0309, 0314, 0325, 0402, 0505 |
| 2021 | 4 | 0122, 0203, 0417, 0602 |
| 2022 | 0 | none |
| 2023 | 5 | 0308, 0412, 0425, 0509, 0514 |
| 2024 | 4 | 0116, 0229, 0307, 0604 |
| 2025 | 15 | 0110, 0201, 0203, 0213, 0228, 0301, 0407, 0411, 0412, 0414, 0420, 0514, 0523, 0528, 0616 |
| 2026 | 5 | 0102, 0119, 0206, 0225, 0312 |

Post-monsoon "clean baseline" dates (Oct–Dec) exist for most years too: 2015, 2016, 2018, 2020, 2021, 2022, 2023, 2024 and 2025.

The current World Imagery basemap (release 2026_r09), sampled at 60 random grid-cell centres (57 returned data): **25 of 57 cells (44%) show imagery from 13 Feb–14 Apr 2025** (Legion LG01–LG04, about 0.34 m). That is the peak of the 2025 fire season. The rest show Oct 2024, Nov 2025–Jan 2026 (post-season) or an older WV02 image from Oct 2022.

Caveats: each acquisition's footprint covers only part of the bounding box (strips, roughly 13–17 km wide), and the box includes farmland. Footprint polygons can be pulled with `returnGeometry=true` to get per-cell coverage. That is the first job in action 1. Wayback keeps only the images that made it into a published basemap. Google Earth Pro's history slider usually has more dates, but it has no API.

**Concrete action (thread 2, validation):** this is the cheapest strong lead in this note. In 2025, about 44% of the sanctuary has a 0.34 m image taken mid-season. Late-season scars (Feb–Apr) can be checked against it directly, at 30–50 cm, where blackened litter, ash and scorched lower stems show plainly [inference]. For 2017, 2019, 2020 and 2023 there are 5–8 fire-season dates each. A clean pre-season image (Oct–Jan) next to an in-season image gives a pair with a known before/after date bracket.

---

## 1. Planet NICFI tropical basemaps

**Sources:** NICFI Satellite Data Program User Guide (Planet/KSAT, `assets.planet.com/docs/NICFI_User_Guide_EN.pdf`), FULL. NICFI notice of 28 Jan 2025 (`nicfi.no`), FULL. Planet community thread "NICFI … prolongs public access", FULL. Planet doc "Tropical Forest Observatory in GEE" (`docs.planet.com/platform/integrations/google-earth-engine/tfo-gee/`), FULL. Earth Engine catalog page `projects/planet-nicfi/assets/basemaps/asia`, FULL. Nimbo article of 17 Oct 2025, FULL (vendor source).

**What it shows:**
- **Coverage includes India.** The guide says the mosaics "cover tropical forest regions between 30 degrees North and 30 degrees South". India is listed among the 97 contracted countries (section 7.1). The Asia collection's bounding box is −27.5° to 30.2° latitude. Ratapani at 23°N is inside. I could not see a tile directly to confirm that forest in Madhya Pradesh is not masked out as "low forest" [inference: probably covered, because the whole country is listed and no masking of Indian states is mentioned].
- **Product:** PlanetScope "normalized analytic" surface-reflectance mosaics with 4 bands (B, G, R, NIR) at 4.77 m. Biannual mosaics run Dec 2015–Aug 2020 (for example `planet_medres_normalized_analytic_2015-12_2016-05_mosaic`). Monthly mosaics run Sep 2020–Jan 2025. Earth Engine asset: `projects/planet-nicfi/assets/basemaps/asia`, with a `cadence` property ("monthly" or "biannual"). Values are 0–10,000 with scale 0.0001.
- **Licence:** custom non-commercial licence "in support of the NICFI Purpose" (reducing tropical forest loss, biodiversity, and so on). Derivatives and redistribution are allowed for that purpose. "All data products licensed through this program have a **perpetual license** meaning that data downloaded can continue to be used once the program has ended."
- **Access status in 2026: closed for new free users.** The contract ended on 23 Jan 2025. Level 0/1 access was "temporarily" extended, then switched off around 31 Mar–1 Apr 2025 (the Collect Earth Online notice, and an Explorer message reported on the forum). The Norwegian government cancelled the procurement for a next phase in Sep 2025 (Nimbo, citing a 9 Sep 2025 notice; not confirmed on nicfi.no). The mosaics now sit in Earth Engine only as Planet's **Tropical Forest Observatory (TFO)**: "now available only to previous NICFI users as a paid upgrade", purchase at go.planet.com/purchase-tfo, and the collections no longer appear in the public catalog. Earth Engine catalog pages still list availability "to 2026-09-01" (one mirror says 2026-02-01). This fits a paid feed that continues, not free access.

**What it means for us:** NICFI monthly mosaics are also a poor fit for dating. They are monthly composites (best-pixel or median), so a scar inside a month cannot be dated beyond "between mosaics". The biannual 2015–2020 mosaics span Dec–May and Jun–Nov, which only tells us the season burned. For validation, 4.77 m is better than 10 m S2 for the edges of a 1–2 ha scar, but in-season Wayback imagery at 0.3–0.5 m (section 0) is far better, and free.

**Concrete action (threads 2 and 5):** (1) Ask the project lead and any collaborators whether anyone made a NICFI account before Jan 2025 and downloaded Ratapani mosaics. Those files carry a perpetual licence. (2) Do not pay for TFO. Expected gain is small next to sections 0 and 3.

---

## 2. PlanetScope scenes: Education and Research, ESA Third Party Missions

**Sources:** Planet E&R programme page and support articles, read as search-level summaries (PARTIAL). ESA EO Gateway news item and Planet press release on joining ESA Third Party Missions (TPM), 2022 (PARTIAL). Pham-Duc et al. 2026 (section 3), who say they got their scenes free through E&R.

**What it shows:**
- **E&R Basic:** 3,000 km²/month of PlanetScope (and the RapidEye archive), with a 30-day delay on new PlanetScope imagery. Non-commercial only. Open only to students, researchers and staff of accredited universities ("nonprofit and government employees are not eligible"). Accounts last 1 year and renew on proof of affiliation. Raw imagery may not be shared publicly. **Quota catch:** each intersecting scene is charged at least 100 km² when clipping.
- Ratapani's grid covers about 900 km² (3,614 cells × 0.25 km²). PlanetScope scenes are about 25 × 8–23 km, so each daily look at the whole sanctuary costs roughly 4–8 scenes, or 400–800 km² of quota [inference]. So 3,000 km²/month buys about 4–7 full-sanctuary looks per month, or daily looks over one or two hotspot ranges.
- **ESA TPM:** PlanetScope and SkySat archive data are free for non-commercial research after a project proposal is accepted. Eligibility is described as worldwide in Planet's release, but some texts stress European researchers, so it needs checking. This is the main free route to **SkySat** (50–80 cm, tasked, sparse archive).
- NASA CSDA gives Planet data only to US-government-funded investigators [known programme rule; not re-checked here].

**Concrete action (threads 2 and 5):** If any team member has a university affiliation in India or abroad, apply for E&R Basic, which takes days. Spend the quota on **dating**: pull every PlanetScope scene inside the S2 dating window (median 5 days) for about 50 VIIRS-unmatched ≤2 ha scars per season. Walker et al. (section 4) found a PlanetScope look every 2.2 days on average in Punjab (Oct–Nov, hazy). In Ratapani's clear Feb–May, expect a look every 1–2 days [inference], which cuts the window from 5 days to about 1–2. Use the quota on narrow date windows, not on wall-to-wall coverage.

---

## 3. Pham-Duc, Nguyen & Lacava 2026, *Vietnam J. Earth Sci.* 48(2):259–276, doi 10.15625/2615-9783/24315: PlanetScope vs Sentinel-2 for a small forest fire. **FULL** (pp. 261–270 read as page images; the PDF has no text layer)

**What it shows:** one fire on 21 Mar 2025 at Nghiem Mountain, northern Vietnam (bamboo forest, officially about 20 ha). Pre-fire image 17 Jan 2025 and post-fire image 12 May 2025, both cloud-free. PlanetScope SuperDove (PSB.SD) Level 3B at 3 m came free via Planet E&R. S2 L2A was resampled to 3 m in GEE. The index is **dNDVI from red and NIR only**, with threshold **T = 0.10** "consistent with … other studies", then manual removal of seasonal NDVI drops.
- Burned area: PS 20.622 ha, S2 20.225 ha. Both found 19.41 ha (about 94%). S2 alone found 0.81 ha, PS alone 1.21 ha. Disagreement sits on the edges.
- dNDVI_S2 = 1.09 × dNDVI_PS − 0.05, r = 0.97. **PS NDVI is systematically higher than S2** (inside the burn after the fire: PS 0.28–0.66 vs S2 0.16–0.52). Absolute NDVI or dNDVI thresholds therefore do not carry over between the sensors; the authors suggest histogram matching.
- They argue that SWIR indices (NBR/dNBR) are limited for small scars because S2 SWIR is 20 m, at which "the small, irregular burn scars … becomes indistinguishable".
- No ground validation. The post-fire image was taken 52 days after the fire and the scar was still clear in NIR. This was a stand-replacing bamboo burn, not a litter fire.

**Concrete action (thread 2):** with 4-band VHR (PlanetScope, LISS-IV, NICFI), use **dNDVI (NIR drop)** with a threshold fitted to each sensor, not one copied from S2. For our litter fires, canopy NDVI may hardly drop. Section 4 says to use visible-band char indices plus NIR in the first days [inference].

---

## 4. Walker, Sadovnik, Burke, Gibbs et al. 2022, arXiv 2209.10148, "Detecting crop burning in India using satellite data". **FULL**

**What it shows (Punjab rice residue, 2019; 681 plots with ground labels: 441 burned, 240 unburned):**
- Mean days between clear looks per plot: **PlanetScope 2.2, Sentinel-2 6.8**. The mean of the longest gap is 8.4 for PS and 12.2 for S2. The worst plot had 13 days without a PS look and 15 without S2.
- "If observed within two days, burn scars are quite obvious in both PlanetScope and Sentinel-2." With only B, G, R, NIR, "most indices commonly used to detect burn scars do not apply". They used SR, NDVI, a **Char Index** CI = (B+G+R) + 15·max(|B−G|, |B−R|, |R−G|), **BAI** = 1/((0.06 − NIR/10000)² + (0.1 − Red/10000)²) on 0–10,000 scaled reflectance, and a bare-soil index.
- The char index (visible only) separates best in the first days, but "this ability … quickly degrades with time". NIR and SWIR (S2 MIRBI) last longer. S2's extra bands extend detectability "for slightly longer intervals" but cannot make up for missing the event.
- Shadow masks matter: the S2 SCL layer "confuse[s] recent burn scars with shadows". They hand-expanded s2cloudless masks.
- Random forest on PS + S2: 82% plot accuracy (burned 91%, unburned 63%); 78% balanced. The number of S2 looks per pixel ranked among the top features ("pixels observed more often … more likely to be classified as burned").

**Concrete action (threads 2 and 5):** (1) For any 4-band VHR, compute **CI and BAI** as well as NDVI, and use them only within about 3–5 days of the burn [inference for forest litter, by analogy with the crop data]. (2) In our S2 scar classifier, check whether S2 look count per cell-season is driving detections. Walker found exactly this bias, and it would leak cloud and coverage patterns into our labels. (3) Never use the S2 SCL shadow class as a mask in hilly Ratapani without checking it against known scars.

---

## 5. Balakavi, Vadrevu & Lasko 2025, *PLOS ONE* 20(7):e0327125, "Mapping burnt areas using very high-resolution imagery and deep learning … Bandipur, India". **FULL** (Europe PMC XML, CC0)

**What it shows:** the only VHR burned-area paper in an Indian dry/moist deciduous tiger reserve I found. One PlanetScope 4-band SR scene (25 Feb 2019, 3 m). Labels are **thresholded PlanetScope band ranges** from points picked by eye, inside a 10 m S2 forest mask. Models are a custom U-Net and a U-Net-GRU, given 256×256×**3** inputs. 15.7% of the area burned. U-Net-GRU: precision 0.971, recall 0.966, F1 0.967, IoU 0.940, AUC 0.98. U-Net: recall 0.928, IoU 0.893. Per tile, 35 validation tiles; Wilcoxon p = 4.4e-8. In their figures, U-Net "misses most of the small burnt areas" in sparse tiles, and U-Net-GRU finds some but "introduces false positives". It confuses water with burn.

**Limits:** labels and test come from the same image and the same threshold rule, so the scores measure agreement with a band threshold, not true accuracy [inference]. No comparison with S2, no smallest-scar size, no dating.

**Concrete action (thread 2):** use it only as evidence that Feb-season burns in Indian deciduous forest are visible on 3 m PlanetScope. Do not copy the accuracy figures. If we get PS scenes, the useful part is the idea of a quick per-scene band threshold on a few hand points, used to make labels for a Wayback/PS check.

---

## 6. Vetrita et al. 2025, *Int. J. Remote Sensing*, doi 10.1080/01431161.2025.2546154, "Evaluating the capabilities of high-resolution PlanetScope and Sentinel-2 … Indonesia's savannas" (Mount Bromo). **ABSTRACT ONLY** (CC BY-NC-ND, but blocked by Cloudflare)

**What it shows:** S2 vs PS burned area: R² = 0.97, OA 0.96, omission 0.08, commission 0.02, Dice 0.94, relative bias −0.06, "comparable to the official BA map". PS's daily revisit "proved valuable for tracking fire progression and detecting rapid vegetation recovery", while S2 was "better suited to longer-term mapping".

**Concrete action (thread 2):** this backs the split of roles: PS/VHR for timing and progression, S2 for extent. The relative bias of −0.06 suggests the two sensors' extents differ by about 6% in savanna. Treat a ±10% area difference between S2 and VHR on our scars as normal, not as an S2 error [inference].

---

## 7. Kim, Lee & Park 2024, *Remote Sensing* 16:2629, "Burned-area mapping using post-fire PlanetScope images and a CNN". **FULL**

**What it shows:** a U-Net on single post-fire PlanetScope images (Korea, Greece; large fires of 1,944–3,282 ha). Labels come from Copernicus EMS, refined by hand with Google Earth Pro history. Six input schemes. **Raw R, G, B, NIR (S1) was best: burned-area F1 0.962, IoU 0.940.** Adding NDVI, GNDVI or BNDVI did not help, and "transferability [is] low when vegetation indices are used". Transfer to a third site (Uljin) was weaker.

**Concrete action (thread 2):** if we train anything on VHR chips, give it the 4 raw bands and skip extra indices. Use pre/post pairs, because our understory burns sit under canopy and single post-fire images will be weak [inference].

---

## 8. Martins, Roy, Huang, Boschetti, Zhang & Yan 2022, *RSE* 280:113203, "Deep learning high-resolution burned area mapping by transfer learning from Landsat-8 to PlanetScope". **ABSTRACT ONLY** (CC BY, but the ScienceDirect PDF was blocked)

**What it shows:** a U-Net trained on existing Landsat-8 burned-area reference data and refined with a smaller PlanetScope set. Applied across Africa to 659 PlanetScope image pairs from 2019. Search snippets give about 13% omission and commission on 30 m Landsat patches. The PlanetScope numbers were not retrieved.

**Concrete action (thread 2):** this is the closest template for us: pretrain on our 10 m S2 scar labels, fine-tune on a few hundred VHR-checked chips. Worth reading in full once someone can reach ScienceDirect, via a library or the author copy at Univ. Idaho VERSO (`verso.uidaho.edu`, record 996630560101851).

---

## 9. Dalagnol et al. 2023, *RSE* 298:113798, "Mapping tropical forest degradation with deep learning and Planet NICFI data". **ABSTRACT / search snippets only** (CC BY; author PDF on researchprofiles.ku.dk blocked by a bot check)

**What it shows (Amazon, NICFI 4.77 m, Aug 2021 mosaic):** a U-Net found burned forest with **10% omission and 34% commission** (logging: 14% and 43%). The model learned from "canopy gaps, burn rings, burn-related colour and texture". Small burn scars were a common error source because they **"disappear in 6–12 months"** from NICFI imagery.

**Concrete action (thread 2):** for annual or seasonal checks with 4–5 m mosaics, expect high commission. Use VHR as a filter that confirms candidate scars, not as an independent detector. A persistence of 6–12 months is for evergreen forest with canopy damage. For our litter fires, the persistence in section 10 is the relevant one.

---

## 10. Melchiorre & Boschetti 2018, *Remote Sensing* 10:750, "Global analysis of burned area persistence time with MODIS data". **FULL** (MDPI CDN mirror)

**What it shows:** persistence is the number of days that NBR keeps burned and unburned MODIS pixels apart (MCD64A1 burns, MCD43 NBR; distributions overlapping by less than 20%). **Global median 29 days.** 86.6% of burned area is separable for at most 48 days. Medians by biome and realm:
- **Tropical forest: Indo-Malay 24 days**, Afrotropic 8, Neotropic 26.
- Tropical grassland and savanna: Afrotropic 28, Australasia 42, Neotropic 27.
- Temperate forest: Australasia >96, Nearctic 67. Boreal: Palearctic 44, Nearctic >96.
- Surface fires with fast regrowth (south-east US) have the shortest persistence. Omission and commission in MCD64A1 bias the estimates downward. Field reflectance in West African savanna came back within 20% of pre-fire levels within 14 days. Central African woodland savanna had a 20% burned/unburned error after 35 days.

**Concrete action (threads 2 and 5):** Ratapani is Indo-Malay tropical dry forest, so plan around a **median of about 3–4 weeks** before a scar fades at 500 m [inference: litter fires under a closed canopy are probably shorter; the first pre-monsoon showers and new leaf flush in May–June shorten it further]. Rules that follow:
1. A VHR image more than about 3 weeks after a fire cannot confirm "unburned". Only use an image as a negative if it falls within about 14 days after the S2 window end.
2. Field verification (thread 5) must be scheduled within about 1–2 weeks of an alert.
3. For S2 label recall, a scar between two clear S2 looks 5 days apart is visible. In 20-day cloud or haze gaps (our maximum), the char signal may already be gone.

---

## 11. Sentinel-2 super-resolution: does it help burn mapping?

**Sources:** SEN2SR GitHub README (ESAOpenSR), FULL. opensr-test README, FULL. Wolters, Bastani & Kembhavi 2023, arXiv 2311.18082, "Zooming Out on Zooming In" (Satlas super-res), PARTIAL (sections 3, 7, 8). Razzak et al. 2021, arXiv 2111.03231, FULL. S2DR3 (Gamma Earth): search-level only.

**What they show:**
- **SEN2SR** gives 2.5 m from 10 m RGBN (x4) and 10 m from the 20 m red-edge/SWIR (x2). The flagship model is a latent diffusion or Mamba model, which needs a GPU and CUDA ≥12. Lite version: `pip install sen2sr mlstac`. The licence is unclear (the repo lists both CC0-1.0 and MIT). The paper is on SSRN, abstract 5247739.
- **opensr-test** scores models for hallucination (detail in SR but not in the true high-res image), omission and improvement. For example, Satlas: hallucination 0.80, omission 0.11, improvement 0.09. superimage: 0.20 / 0.63 / 0.17. So models either invent detail or leave it out. None adds much true detail (improvement ≤0.20).
- **Wolters et al., Finding 7: "Super-resolution outputs are ineffective for machine consumption."** On six downstream tasks, average score was **low-res input 0.673 vs SRCNN 0.502, HighResNet 0.604, ESRGAN 0.615**. Finding 5: diffusion models "generate realistic but inaccurate" output. Only SR-pretrained *weights* helped (Finding 8).
- **Razzak et al. 2021** (S2 → PlanetScope multi-image SR, building delineation): IoU **bicubic 0.60, single-image SR 0.56, multi-image SR 0.60, bicubic of 4 revisits stacked 0.62, real PlanetScope 0.69**. Instance F1: bicubic 0.33, SISR 0.30, MISR 0.36, PlanetScope 0.51. Single-image SR did *worse* than bicubic. Stacking several revisits gave the gain, not SR.
- **S2DR3** (Gamma Earth, Oct 2023): 12 bands to 1 m. The developers claim it reconstructs features "down to 3 m". It is commercial, and I found no licence or validation for burn mapping.
- No paper tests SEN2SR, S2DR3 or Satlas SR on burned-area mapping (several searches). The one fire-mapping paper that addresses the point (BAM-MRCD, arXiv 2601.09262) deliberately left out SR modules because they "may impute noise".

**Concrete action (thread 2): do not use super-resolved S2 as labels or as model input.** Expected gain is zero to negative. A cheaper version of the same idea is to feed 2–4 S2 looks inside the window as stacked inputs (Razzak: +0.02 IoU, +0.04 F1 over a single look). Never show SR images to the people checking labels by eye, because made-up char patches would bias the check.

---

## 12. ISRO Resourcesat-2/2A LISS-IV (5.8 m) and Cartosat via Bhoonidhi

**Sources:** NRSC Bhoonidhi brochure 2025, FULL. Resourcesat-2 handbook, FULL (specs). Bhoonidhi user manual v2.0 and the space-policy slides could not be downloaded (connection reset).

**What it shows:**
- Under the Indian Space Policy 2023, **IRS data of 5 m and coarser is open data for all users** on Bhoonidhi (`bhoonidhi.nrsc.gov.in`). The list includes **ResourceSat-1, 2, 2A**, so LISS-IV at 5.8 m is open. Download flow: register, then Select > Search > Add to Cart > Download. There is a STAC API (`bhoonidhi.nrsc.gov.in/bhoonidhi-api`); email bhoonidhi@nrsc.gov.in to enable it.
- **Data finer than 5 m (Cartosat-1, -2, -2S, -3; KompSat-3/3A) is free for Indian Government entities** that submit a declaration, and priced through NSIL for others. **The MP Forest Department is a Government entity**, so Cartosat-2S/3 (0.65 m / 0.25–0.3 m pan) could be free if the DFO or the department's IT cell requests it [inference from the policy wording].
- LISS-IV: bands B2 green 0.52–0.59, B3 red 0.62–0.68, B4 NIR 0.77–0.86 µm. **No blue, no SWIR.** 5.8 m at nadir, 10-bit. MX swath 70 km on RS-2 (23 km on RS-1). **5-day revisit** by ±26° steering. Acquisitions are programmed, so the archive over a given site is patchy [inference]. Two satellites (RS-2, RS-2A) give about 2–3 day revisit if both are tasked [inference; not confirmed].
- No published LISS-IV burned-area accuracy study for Indian forest fires was found. National burned-area mapping used AWiFS 56 m (Reddy et al. 2017, *Current Science*).

**Concrete action (threads 2 and 5):**
1. Register on Bhoonidhi. Search LISS-IV MX over Ratapani, Jan–Jun 2017–2026, and list the dates. Each date that falls inside one of our S2 dating windows adds a look (dating). Each date within about 2 weeks after a fire gives a 5.8 m check (validation).
2. Use dNDVI or BAI (green, red, NIR only; no char index without blue). Fit thresholds to the sensor (section 3).
3. Ask the Forest Department to request Cartosat-3 tasking or archive for one season under the Government-entity declaration. That gives 0.3 m imagery we could share legally within the project.

---

## 13. Drones (UAV) in Indian forest-fire work, and drone burn mapping

**Sources:** Mongabay India, Aug 2024, "Conservation drones need to overcome some takeoff troubles", FULL. Simes, Pádua & Moutinho 2024, *Remote Sensing* 16:30, FULL. MP Forest Department IT cell site lists a presentation on drone monitoring (not opened).

**What it shows:**
- **Panna TR (MP):** drones were deployed from 2017 under a WII/NTCA tiger-monitoring pilot. The WII project engineer says human-caused fire incidents "came down" by about half after drone patrols began (deterrence), and that drones "accurately calculate burned areas". Forest departments use few long-range drones: six across Corbett, Panna and Rajaji. A VTOL costs about ₹20 lakh. The Trinity F90+ VTOL flies about 90 min and covers 5–7 km² per flight. Quadcopters fly about 35–40 min. The UAS Rules 2021 apply. Experts call for forest-specific SOPs and marked flight zones for privacy.
- **Simes et al. 2024 (Portugal, 40 ha fire, flown 5–6 months after):** a DJI Phantom 4 Pro (RGB, 2.4 cm) plus Parrot Sequoia (G, R, red-edge, NIR, 9.4 cm) at 80 m height, 80/70% overlap, 8 ha. Burnt/unburnt accuracy: RF on RGB 95.5%; SVM on multispectral 97.2%; RF on RGB + multispectral 96.59%. RGB alone confused mild and severe burns. **S2 dNBR matched the UAV area only when the UAV's "low severity" class was counted as unburnt.** In other words, S2 misses low-severity patches [inference from their Fig. 3 text].

**Concrete action (threads 2 and 5):** a ₹1–2 lakh quadcopter with RGB is enough to map 1–2 ha litter burns within days (about 8 ha per 15–20 min flight at 80 m). Use it in field verification (thread 5) on a sample of about 20–30 fresh alerts per season to measure (a) the smallest scar that S2 catches, and (b) how much low-severity margin S2 leaves out. That gives the "how small can S2 see" number that no paper gives us. Fly within 1–2 weeks of the fire (section 10). Cost and SOP: borrow the Panna/WII setup.

---

## 14. Other sources checked

- **Planet Fusion** (daily 3 m gap-filled, PlanetScope fused with S2/Landsat/MODIS): commercial. Only a restricted copy exists (terrabyte/LRZ, for German users). No burned-area paper found. A gap-filled daily product would smear the 1–3 day char signal [inference]. Not useful for us.
- **Maxar/Vantor Open Data:** released only for disaster activations, CC BY-NC 4.0. India entries are floods only (Oct 2023); no forest-fire events. Not useful for Ratapani.
- **SkySat:** only through ESA TPM proposals (section 2) or paid tasking.
- **Vadrevu, NASA CSDA pilot sheet "Burnt Area Mapping in South/Southeast Asia using … Planet data"** (FULL, 1 page): Barnala, Punjab, single date, 90% cloud-free. PlanetScope detected **5% more burnt area than Landsat and 9% more than Sentinel-2**. That is the order of size for VHR's extra recall on crop burns.
- **Cho et al. 2023, IEEE JSTARS 16:242** (ABSTRACT ONLY; IEEE PDF blocked): a U-Net on single PlanetScope images, 17 scenes from 12 Korean forest fires. The "optimal and most stable band combination is red, green, blue, and NIR", which agrees with Kim et al.
- **Google Earth Pro historical imagery:** free and manual, with no API. Usually has more dates than Wayback. Its terms allow screenshots with attribution in research, but not bulk extraction for model training [check terms before any automated use].

---

## Which source for which thread

| Need | Best source | Why | Expected gain [inference unless cited] |
|---|---|---|---|
| **Validate S2 scar labels (thread 2)** | Esri Wayback / World Imagery at 0.3–0.5 m, in-season dates (section 0); Google Earth Pro for extra dates | Free. 60 Jan–Jun dates 2016–2026. 44% of cells have 0.34 m imagery from Feb–Apr 2025 | Measured precision of the S2 labels on ≥400 cells, with sizes down to 0.5 ha. Probably shows S2 misses low-severity margins (Simes et al.) |
| **Date scars (thread 2, VIIRS-unmatched small scars)** | PlanetScope scenes via E&R Basic (daily), then LISS-IV via Bhoonidhi (5-day steerable) | The only near-daily sources. NICFI is monthly and SR adds nothing | Window cut from 5 days median to about 1–2 days for scars with a PS look (Walker: PS look every 2.2 days, S2 every 6.8) |
| **Small-scar recall (<2 ha)** | Drone RGB in the field (fresh alerts) plus Wayback/Cartosat pairs | Directly measures S2 omission by size | First local estimate of S2 omission for 0.5–2 ha scars. Vadrevu's crop case: +5–9% area from VHR |
| **Live alert check (thread 5)** | Drone; Bhoonidhi LISS-IV once the STAC API is enabled | Fast; free | Field check inside the 3–4 week persistence window (Melchiorre: Indo-Malay forest median 24 days) |
| **Label generation at scale** | S2/Landsat (keep). Not SR, not NICFI | SR hurts machine use (Wolters, Razzak); NICFI closed and monthly | Avoids a negative gain |

---

## Datasets table

| Name | Link | Resolution | Years | Licence | How to access |
|---|---|---|---|---|---|
| Esri World Imagery Wayback | livingatlas.arcgis.com/wayback ; metadata `https://metadata.maptiles.arcgis.com/arcgis/rest/services/World_Imagery_Metadata_<YYYY_rNN>/MapServer/<4\|5\|6>/query` ; config `https://s3-us-west-2.amazonaws.com/config.maptiles.arcgis.com/waybackconfig.json` | 0.31–1 m (WV2/3/4, GE01, Legion, Ikonos) | 2000–2026; 131 dates over Ratapani | Esri terms (viewing, with attribution; check before export or ML) | Wayback app for viewing; REST query for dates and footprints (I used `returnGeometry=false`; set it true for polygons) |
| Google Earth Pro history | earth.google.com (desktop) | about 0.3–2.5 m | varies | Google Earth terms; attribution | Manual history slider |
| Planet NICFI basemaps (Asia) | `projects/planet-nicfi/assets/basemaps/asia` | 4.77 m, B, G, R, NIR | biannual Dec 2015–Aug 2020; monthly Sep 2020–Jan 2025 (paid TFO after) | NICFI non-commercial; perpetual for data already downloaded | Closed to new free users since about 1 Apr 2025; paid TFO for previous NICFI users only |
| PlanetScope scenes, E&R Basic | planet.com/industries/education-and-research | 3 m, 4 or 8 bands | 2016–present (30-day delay) | Non-commercial; no public redistribution | University account; 3,000 km²/month; minimum 100 km² per scene |
| PlanetScope and SkySat, ESA TPM | earth.esa.int/eogateway (Third Party Missions) | 3 m; SkySat 0.5–0.8 m | archive | Non-commercial research | Project proposal to ESA |
| Resourcesat-2/2A LISS-IV MX | bhoonidhi.nrsc.gov.in | 5.8 m, G, R, NIR; 70 km swath; 5-day revisit | 2011–present (RS-2), 2016– (RS-2A) | Open data (≥5 m), Indian Space Policy 2023 | Register, then Search > Cart > Download; STAC API on request |
| Cartosat-2S/3 | bhoonidhi.nrsc.gov.in | 0.25–0.65 m pan, about 1–2.5 m MX | 2016– | Free to Indian Government entities with a declaration; NSIL-priced otherwise | Through the MP Forest Department |
| SEN2SR (not recommended) | github.com/ESAOpenSR/SEN2SR | 2.5 m from S2 | n/a | CC0 or MIT (unclear) | pip `sen2sr`; GPU |
| opensr-test benchmark | github.com/ESAOpenSR/opensr-test | n/a | n/a | open | For checking any SR claim |

---

## Ranked action list

1. **Wayback in-season check of S2 scars (thread 2). Gain high, effort low (2–3 days).** Pull footprint polygons for the 60 Jan–Jun acquisitions (2016–2026). Intersect them with the 500 m grid. For each footprint cell, pair the in-season image with the closest earlier clean image. Check by eye a stratified sample of about 400 cells (S2-burned vs S2-unburned, by size class 0.5–2 / 2–5 / >5 ha), only where the VHR date falls within about 14 days after the S2 burn window. Output: precision and recall of the S2 labels by size, which the project has never measured. Start with 2025, where 44% of cells have Feb–Apr imagery.
2. **Drone field protocol for fresh alerts (thread 5, and calibration for thread 2). Gain high, effort medium.** RGB quadcopter, 80 m height, 80/70% overlap, flown within 1–2 weeks of the fire. About 20–30 burns per season. Map each burn edge and compare with S2. This gives the smallest scar size that S2 detects and the low-severity margin it misses.
3. **Bhoonidhi LISS-IV date inventory (threads 2 and 5). Gain medium, effort low (1 day).** Register, list all LISS-IV MX dates over Ratapani in Jan–Jun 2017–2026, and mark those inside our S2 dating windows. Use dNDVI/BAI with sensor-fitted thresholds. Ask the Forest Department for a Cartosat declaration.
4. **Planet E&R Basic for dating small VIIRS-unmatched scars (thread 2). Gain medium, effort low if someone is university-affiliated.** Spend about 3,000 km²/month on narrow 5–7 day windows around about 50 small scars per season. Use CI, BAI and NDVI within 3–5 days. Expect the median window to fall from 5 to about 1–2 days.
5. **Leakage check from S2 look counts (thread 2 labels, thread 1 features). Gain small to medium, effort very low.** Correlate scar detection with the number of clear S2 looks per cell-season. Walker et al. found look count among the strongest predictors of "burned".
6. **Ask about perpetual-licence NICFI downloads (thread 2). Gain small, effort trivial.** Only worth it if someone already has the files.
7. **Do not pursue:** S2 super-resolution (SEN2SR, S2DR3, Satlas) for labels or inputs (Wolters: low-res 0.673 vs SR 0.502–0.615 downstream); paid NICFI/TFO; Planet Fusion; Maxar/Vantor Open Data.
