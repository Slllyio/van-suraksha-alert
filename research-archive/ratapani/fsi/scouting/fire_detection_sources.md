# Fire detection and dating sources beyond S-NPP VIIRS and MODIS (detect thread, October 2026)

Scope: which other satellites and products can (a) date our Sentinel-2/Landsat scars more tightly, (b) give live alerts within minutes, (c) catch the small litter fires VIIRS misses, over Ratapani (about 23.0 N, 77.4-77.9 E). Each source is marked FULL, PARTIAL or ABSTRACT ONLY. My own reasoning is marked [inference].

## 0. What our own data says first (computed from `ratapani/viirs_snpp_2013_2024.parquet`, 8,117 S-NPP points)

These numbers set the bar every other sensor has to clear.

- **Ratapani VIIRS fires are weak.** Per 375 m pixel, FRP has a median of 4.1 MW, a 90th percentile of 11.2 MW and a 99th percentile of 29.9 MW. Only 1.0% of pixels are 30 MW or more, and 0.3% are 40 MW or more.
- **Grouped into 4 km cells per overpass** (roughly one geostationary pixel), summed FRP has a median of 5.3 MW and a 90th percentile of 22 MW. Only 6.3% of cell-overpasses reach 30 MW, 3.9% reach 40 MW and 2.6% reach 50 MW.
- **Timing.** Day detections fall at 07:00-09:00 UTC, which is 12:30-14:30 IST. Night detections fall at 19:30-21:30 UTC, which is 01:00-03:00 IST. So we only ever see two moments a day. The fire-day of a scar is known only when one of those snapshots catches the fire.
- **The file holds S-NPP only.** It has no NOAA-20 (2018 onward) and no NOAA-21 (2023 onward).
- **Context from `fsi/README.md`.**
  - 38% of first-burn scars (6,044 of 15,754) have a VIIRS date.
  - That falls to about 30% for scars under 2 ha.
  - Sentinel-1 was ruled out because there is one track with a 12-day revisit.

[inference] Any sensor with a minimum detectable FRP around 30-40 MW (all geostationary sensors) will see only the top few percent of Ratapani fires at the VIIRS snapshot time. It may see somewhat more at the daily peak, because it looks 96 times a day. The main gains for the smallest fires have to come from 20-30 m SWIR (Sentinel-2/Landsat), from more VIIRS platforms, and from afternoon-orbit commercial thermal data.

---

## 1. FIRMS now serves geostationary fires over India, including Meteosat IODC (FULL: FIRMS FAQ page and FIRMS geostationary blog, read in full)

Links: https://www.earthdata.nasa.gov/data/tools/firms/faq ; https://www.earthdata.nasa.gov/news/blog/geostationary-active-fire-detection-data-firms (published 27 Jun 2024, updated 15 Jul 2025)

**What it shows**
- FIRMS lists "Provisional Geostationary Active Fire Detections, SEVIRI (Meteosat 9 & 11), EUMETSAT/LSA SAF, … ~30 mins (Europe-Africa-India)". It also lists Himawari-9 (CAMS/IPMA), GOES and MTG-0.
- In the FAQ's satellite codes, "Met11 = Meteosat-11 (MSG IODC)" and "Met9 = Meteosat-9 (MSG 0)". The 2024 blog says the opposite: "Meteosat 9 (IODC): 0°, 45.5°". [inference] One of these labels is out of date. The source to check is whichever Meteosat is at 45.5 E (Section 2).
- Cadence and latency:
  - MSG (SEVIRI) observes every 15 min and reaches FIRMS in about 30 min.
  - MTG and Himawari observe every 10 min and reach FIRMS in about 20-30 min.
- Theoretical minimum fire size at nadir:
  - SEVIRI: about 0.0001 of a 3 km pixel, which is about 900 m² of actively burning fire.
  - GOES: about 4,000 m² at 800 K.
- FIRMS treats all geostationary data as "provisional or beta". It shows only the higher-confidence classes. The layers sit under "GEOSTATIONARY" in Advanced Mode. One merged layer, "Filtered Geostationary (provisional)", combines them.
- FIRMS fields include FRP (MW), Pixel_X/Pixel_Y (pixel size), Acquire_Time (scan start), Confidence (0-1 for FRP-PIXEL) and Day/Night.
- **The FIRMS Area API does not list geostationary sources.**
  - Its sources are LANDSAT_NRT (US/Canada only), MODIS_NRT/SP, VIIRS_SNPP_NRT/SP, VIIRS_NOAA20_NRT/SP and VIIRS_NOAA21_NRT. I checked this on the API page.
  - So geostationary points come through the map/KML/WMS layers, not the CSV API. Archives come from LSA SAF directly.
- Polar latency in FIRMS:
  - NRT arrives within 3 h of the observation.
  - RT (30 min) and URT (under 5 min, often under 60 s) exist only for US/Canada, because they are built from direct broadcast.
  - NOAA-20/21 cross the equator at about 12:40 and 00:40 local time, about 50 min ahead of S-NPP at 13:30/01:30.

**Concrete action for us**
- Thread 5 (live alerts): add the FIRMS "Filtered Geostationary" layer over a Ratapani bounding box (77.2-78.1 E, 22.7-23.3 N) as a second alert stream, polled every 15 min.
  - Settings: keep only FRP-PIXEL confidence of 0.5 or more.
  - Tag each alert "geo, ±2-4 km". A SEVIRI pixel here is about 3 × 4.4 km (Section 2), so it can only point a patrol to a beat cluster, not to a cell.
  - Expected effect: alerts 30-45 min after the scan for the few large fires (top ~5%). That is hours earlier than the 13:30 VIIRS pass for fires that start in the late morning [inference].
- Thread 2 (scar dating): the 15-min record dates a scar to the hour whenever SEVIRI catches it. Use it as a tiebreaker when a scar window has two or more candidate VIIRS days.

---

## 2. LSA SAF Meteosat FRP-PIXEL, including the IODC product (FULL: Wooster et al. 2015, ACP 15:13217; plus the LSA SAF product page, read in full)

Links: https://acp.copernicus.org/articles/15/13217/2015/ ; https://lsa-saf.eumetsat.int/data/products/fire-products/

**Product facts (LSA SAF page)**
- MSG-IODC FRP-Pixel:
  - SEVIRI, 3 km, every 15 min.
  - Available from 2017 to now (NRT).
  - Status "Demonstration". The page lists its region as "Europe, Africa, Middle East".
- MSG 0° FRP-Pixel is "Operational", 2016 to now, with a data record for 2004-2015.
- MTG FRP-Pixel (FCI, 1 km, 10 min, 2025 to now) is "Demonstration".
- MSG FRP-Grid is now "Suspended". FD&M was discontinued in 2024.
- Access is through the LSA SAF Data Server, which needs free registration. Files are HDF5. For NRT data inside the data-record period, contact the Help Desk.

**Satellite history**
- Meteosat-8 was at 41.5 E until 2022.
- Meteosat-9 reached 45.5 E on 20 Apr 2022 and became the prime IODC satellite on 1 Jun 2022.
- Meteosat-8 ended its parallel IODC feed at 09:00 UTC on 1 Jul 2022 and was decommissioned on 13 Oct 2022. Source: NOAA OSPO notices and Wikipedia, ABSTRACT-level.
- I found no announced IODC successor. A 2025 EUMETSAT TWG talk says MSG "remain in use for the IODC service". [inference] Plan for the IODC feed to end within a few years. Pull its archive now.

**Detection limits (Wooster 2015, full text)**
- The FTA algorithm "detects active fire pixels with an FRP down to around 20 MW". Pixels below about 30-40 MW are "typically undercounted".
- The FRP distribution departs from its power law below about 30-40 MW.
- SEVIRI IR3.9 saturates at about 335 K. Near the sub-satellite point, saturation can occur at FRPs as low as 45 MW and typically happens at about 250 MW.
- Compared with MODIS:
  - MODIS measures about 2 times the FRP that SEVIRI measures over Africa (Freeborn 2009).
  - SEVIRI's omission relative to MODIS was 25-74% across the Central African Republic, depending on fire regime.
  - 70%, 79% and 84% of collocated MODIS fire pixels were detected by SEVIRI within 12, 24 and 36 h of the matched MODIS view. SEVIRI more often detected after MODIS, but "quite often" before.
- The paper recommends using MTG's dedicated low-gain MWIR channel in future.

**Geometry for Ratapani (my calculation: spherical Earth, satellite at 42,164 km)**

| Satellite (longitude) | View zenith at Ratapani | Approx. IR pixel here |
|---|---|---|
| Meteosat-9 IODC (45.5 E), SEVIRI 3 km | 45° | ~3.1 × 4.4 km (14 km²) |
| INSAT-3DR (74 E) / INSAT-3DS (82 E), 4 km MIR | 27° | ~4.1 × 4.6 km (19 km²) |
| FY-4B (105 E), AGRI 4 km MIR | 41° | ~4.1 × 5.5 km (23 km²) |
| Himawari-9 (140.7 E), 2 km | 74° | ~2.2 × 7.9 km, at the extreme limb |
| Meteosat-12 / MTG (0°), FCI 1 km | 87.5° | unusable (beyond the limb) |

[inference] The minimum detectable FRP scales roughly with pixel area (Xu 2021, Section 7). That puts SEVIRI at about 30 MW or more at Ratapani, and nearer 40-50 MW for reliable detection. From Section 0, only about 4-6% of Ratapani 4 km fire-cells reach that at the VIIRS snapshot. MTG does not cover India. Himawari is too oblique to be useful.

**Concrete action for us**
- Thread 2 (scar dating), test first:
  - Download IODC FRP-PIXEL for Jan-Jun 2018-2026 clipped to Ratapani. That is about 17,000 15-min slots per season, but the "list" files are small.
  - Match to VIIRS-dated scars within 5 km and ±1 day.
  - Report (i) the share of VIIRS-dated scars that also get a SEVIRI hit, (ii) SEVIRI first-detection hour minus VIIRS time, and (iii) the share of undated scars that SEVIRI dates.
  - Expected: a SEVIRI hit on 5-15% of dated scars, mostly the largest; a few percent of undated big scars gain a date [inference].
- Thread 1 (prediction): if the record holds up, the hour of first SEVIRI detection gives the ignition-hour distribution by beat. That could separate morning-ignition beats from afternoon-ignition beats, which gives a better patrol timing rule.

---

## 3. INSAT-3D / 3DR / 3DS fire products, MOSDAC (PARTIAL)

Sources:
- INSAT-3DS Operational Data Products document, SAC-ISRO, V1, 26 Feb 2025 (FULL): https://mosdac.gov.in/docs/INSAT-3DS_Operational_Products_V1.pdf
- MOSDAC INSAT-3D/3DR pages (search snippets).
- C.P. Singh (SAC), "Hyper-temporal active forest fire detection using INSAT-3D/3DR over India", ACRS 2017. ABSTRACT ONLY: a-a-r-s.org is "Site Disabled" and the Wayback Machine is blocked here.
- Thapliyal, ITSC-25 slides, May 2025 (FULL): https://itwg.ssec.wisc.edu/wordpress/wp-content/uploads/2025/06/oral.12.03.Thapliyal_itsc25.pdf

**What it shows**
- INSAT-3DS has a Level-2P point product **`3SIMG_L2P_FIR`** (Fire) and `3SIMG_L2P_SMK` (Smoke). For these, "in place of HDF, KML file is generated", with a "chip" file alongside.
- INSAT-3D products list "Fire - using MIR & TIR-1 channels" under code FIR (L2P).
- MIR is 3.80-4.00 µm at 4 km nadir. INSAT-3DR is identical in sensors and products to INSAT-3D.
- Singh 2017 (abstract):
  - A multi-channel contextual algorithm with 15-min data.
  - Validated against MODIS on the Uttarakhand fires of Apr-May 2016, Mount Abu (Apr 2017) and Katra (May 2017).
  - The agreement figure was cut off in every copy I could reach.
- MOSDAC also lists funded projects, for example "INSAT-3D Data for Sub-surface Fire Detection" (IIT Roorkee) and a Punjab RSC fire algorithm.
- ITSC-25 slides:
  - A future INSAT 4th generation "Advanced Imager" with 2 km IR, full disk every 15 min and "Indian landmass every 5 minutes", explicitly for "better fire detection and intensity estimation".
  - EOS-08 (Microsat-2C, launched 16 Aug 2024) carries an EOIR MIR+TIR payload listed for "Forest/agriculture fire monitoring". The slide says "8m". [inference] That is implausible for TIR, so treat it as unverified.

[inference] Geometry (Section 2) is the best of any geostationary satellite: VZA about 27° and a pixel of about 19 km². But the 4 km MIR means a detection limit no better than SEVIRI's. The one South-Asian geostationary validation found (FY-4A, Section 4) suggests small forest fires are mostly missed.

**Concrete action for us**
- Thread 5: register on MOSDAC and pull one peak week (for example 1-7 Apr 2025) of `3SIMG_L2P_FIR` KML for Ratapani. Compare with VIIRS before investing more effort.
- It is worth asking SAC/MOSDAC for the archive of 3D/3DR FIR points 2017-2024. These are Indian data with an Indian user mandate, and they give 15-min timing.
- Archive years: INSAT-3D (2013), 3DR (2016) and 3DS (2024). The start of the FIR archive is not confirmed.

---

## 4. FY-4A/FY-4B fire products (FULL for FY-4A South Asia test)

Source: Accuracy assessment of FY-4A Fire/Hotspot (FHS) product, ISPRS Archives XLVI-4/W6-2021, p. 91. Link: https://isprs-archives.copernicus.org/articles/XLVI-4-W6-2021/91/2021/

**What it shows**
- FY-4A FHS: 2 km, 15 min, from NSMC (satellite.nsmc.org.cn / FY Satellite Download Toolkit, files are .nc).
- Tested against VIIRS on Chitwan (Nepal) and **Valmiki Tiger Reserve (India)**, 12-16 Apr 2021, plus Benguet (Philippines).
- Results:
  - VIIRS saw 18 fire pixels at Valmiki on 12 Apr and 24 on 13 Apr. FY-4A detected only 2 pixels, on the morning of 13 Apr.
  - Chitwan forest fires of about 0.56-4.23 km² were not detected by FY-4A.
  - FY-4A missed fires "smaller than 20 pixels of VIIRS data (~2.82 km²), at less than 4 MW … and brightness temperature lower than 330 K".
- FY-4B (WMO OSCAR) was relocated to 105 E in Feb 2024. Other sources conflict on which FY-4 sits where.
- A FY-4B fire algorithm paper (IEEE TGRS 2023) was validated only over China and Mongolia (search snippet only).

**Concrete action for us:** none for detection. This is the clearest evidence from forested South Asia (a tiger reserve terai forest) that a 2-4 km geostationary product misses nearly all of our class of fire. Use it to set expectations for Sections 2-3.

---

## 5. Himawari-8/9 (search-level only, plus my geometry)

- FIRMS carries Himawari-9 FRP-PIXEL (CAMS/IPMA): 10 min, about 30 min latency.
- Ratapani sits at a view zenith of about 74° (Section 2). A 2015 comparison found "H8 Error of Commission ~8%, Error of Omission ~66%" relative to MODIS, even at good geometry (search snippet, RMIT conference).
- [inference] Not useful for Ratapani.

---

## 6. NOAA-20 and NOAA-21 VIIRS, and the VIIRS archive (FULL: VIIRS C2 375 m User Guide v1.2, June 2025; Schroeder et al. 2014, RSE 143:85, read in full)

Links: https://www.earthdata.nasa.gov/s3fs-public/2025-06/VIIRS_C2_AF-375m_User_Guide_1.2.pdf ; https://directreadout.sci.gsfc.nasa.gov/publications_documents/Schroeder_et_al_2014b_RSE.pdf

**What it shows**
- NOAA-20 launched in 2017 and NOAA-21 in 2022. Product IDs: VNP14IMG (S-NPP), VJ114IMG (NOAA-20), VJ214IMG (NOAA-21).
- The effective S-NPP record starts 20 Jan 2012.
- Monthly fire-location summaries (VNP14IMGML / VJ114IMGML / VJ214IMGML) are on a public SFTP server:
  - server `fuoco.geog.umd.edu`, public anonymous login given in the VIIRS 375 m user guide, directory `data/VIIRS/C2/VNP14IMGML` (and the J1/J2 equivalents).
  - Files are posted 1-2 months after each month.
- 375 m compared with 750 m (2021 global data):
  - By day, about 3 times more fire pixels, and 53% of 375 m day pixels had no 750 m match.
  - By night, about 17 times more fire pixels.
- Schroeder 2014:
  - Commission errors were "< 1.2%" for nominal-confidence pixels.
  - At night, a bonfire of radius 1.25 m (about 5 m²) burning at about 1000 K was detected at a 32.7° scan angle.
  - Daytime detection needs larger fires because of the solar background. Gui 2026 cites about 100 m² at 1000 K as the 375 m limit.
- Xu 2021 (Section 7) says the VIIRS minimum detectable FRP only "approximately doubl[es]" from nadir to swath edge, thanks to on-board pixel aggregation.

**Concrete action for us** (thread 2, cheapest gain in this note)
- Add NOAA-20 (2018-2026) and NOAA-21 (2023-2026) points, plus S-NPP 2025-2026, to the dating pipeline.
  - Inputs: the VJ114IMGML/VJ214IMGML monthly CSVs, or FIRMS `VIIRS_NOAA20_SP` / `VIIRS_NOAA21_NRT` through the Area API with a free MAP_KEY.
  - Settings: the same 750 m / window ±1 day rule, nominal+high confidence.
  - Expected effect [inference]:
    - It doubles to triples the daily looks at about 12:40 and 13:30, and at about 00:40 and 01:30.
    - Fires that ignite and die between the two daytime passes become catchable.
    - It should raise the 38% dated share by several points, mostly for 2018+ seasons.
    - Verify by recomputing the dated share per season with and without J1/J2.

---

## 7. Sentinel-3 SLSTR active fire and FRP (FULL: Xu, Wooster et al. 2021, RSE 112460 accepted manuscript; ABSTRACT ONLY: Xu & Wooster 2023, Science of Remote Sensing 100087)

Links: https://kclpure.kcl.ac.uk/ws/files/150763111/SLSTR_Fire_Simulation.pdf ; https://doi.org/10.1016/j.srs.2023.100087

**What it shows**
- Overpass is about 10:00 and 22:00 local, like Terra. SLSTR is expected to replace Terra MODIS.
- Night NRT product from EUMETSAT since March 2020. NTC product from ESA since August 2020.
- **Daytime product "fully operational since March 2022"**. EUMETSAT METIS lists Collection 3.1, released 23 Jan 2025.
- Minimum detectable FRP from 15,416 scenes (F1 channel processing): **2 MW at nadir rising to 6 MW at scan edge**. With S7 processing it is 4 → 19 MW. For comparison, MODIS goes from about 5-8 MW at nadir to about 44 MW beyond 50° VZA.
- Using F1 adds 33% more active-fire pixels, mostly ≤10 MW.
- Daytime (2023 abstract):
  - SLSTR finds 70% of matched MODIS AF pixels plus 16% unique ones.
  - It does less well on the lowest-FRP fires by day and a little better than MODIS by night.
  - It reaches almost 100% detection once about 150 Landsat AF pixels fall inside an SLSTR pixel.

[inference] A 10:00 and 22:00 look gives two new time slots per day, for two satellites (S3A and S3B). The 22:00 slot is valuable: litter fires lit in the afternoon often smoulder and creep into the night. Night detection limits (2 MW) are close to our VIIRS median (4 MW).

**Concrete action for us**
- Thread 2: add S3A/S3B SLSTR FRP (product `SL_2_FRP___`, NTC) for 2020-2026 to the dating pool. Source is the Copernicus Data Space Ecosystem (open and free; the older scihub link is now CDSE).
  - Expected: extra night detections in Mar-Apr. Extra dated scars, mainly 2020+.
  - Check the fraction of SLSTR-only scar dates.
- Thread 5: the 22:00 pass is too late for same-day patrols, but it can flag still-burning sites for a next-morning visit.

---

## 8. Landsat 8/9 active fire (FULL: Schroeder et al. 2016, RSE 185:210; plus the FIRMS FAQ on LFTA)

Links: https://repository.library.noaa.gov/view/noaa/59460/noaa_59460_DS1.pdf ; FIRMS FAQ (Section 1)

**What it shows**
- Uses OLI SWIR (band 7, 2.2 µm) plus bands 1-6, day and night, plus multi-temporal tests over the previous 176 days.
- **Daytime 50% detection is about 4 m² of effective fire area at 950 K** (firewood-type combustion). At night it is about 1 m².
- Global daytime commission error was **0.2%**. The worst cases were factory roofs in China (34.6% within one scene) and an industrial park in Indonesia.
- **North India** was one of six high-activity regions, with negligible commission. Cloud left fewer than 5 of 11 usable scenes over 176 days there.
- Pixel saturation and "folding" are common in large fires but do not stop detection.
- The USGS **LFTA** product is produced only for CONUS, southern Canada and northern Mexico (FIRMS: "Currently curated for FIRMS US/Canada"). It is not produced for India.
- Revisit is 16 days per satellite, 8 days combined. Overpass is about 10:30 local.

**Concrete action for us**
- Thread 2 and thread 3: run the Schroeder day algorithm ourselves on every Landsat 8/9 scene over Ratapani (path 145/146, row 44), 2013-2026, in Earth Engine. The tests are a handful of band ratios on TOA reflectance (bands 7, 6, 5), as given in the paper's Section 3.1.
  - Any AF pixel inside a scar polygon dates that scar exactly (fire burning at about 10:30 that day). It also marks the fire front at the time.
  - Expected: a few percent of scars dated exactly [inference]. Detection is near-certain if the fire is burning at overpass, and fire-free scenes cost nothing.
- A free bonus: the "fire front at time t" pixels are the spread thread's (thread 4) best validation data at 30 m.

---

## 9. Sentinel-2 active fire detection (FULL: Gui et al. 2026, IEEE TGRS 64:4100314; ABSTRACT ONLY: Hu, Ban & Nascetti 2021, JAG 101:102347)

Links: https://arroma.uiowa.edu/docs/publication/paper_pdf/2025/gui_et_al_2025.pdf ; Earth Engine code: https://code.earthengine.google.com/15eace03767b83992d26231e240175a0 ; Hu 2021: https://doi.org/10.1016/j.jag.2021.102347 (gold OA, but the publisher PDF was blocked here, and the lirias copy is only page 1)

**What Gui 2026 shows (full text)**
- Daytime S2 MSI at 20 m, TOA reflectance.
- Step 1, potential fire pixel: **(ρ12 − ρ8A)/(ρ12 + ρ8A) > 0.5** and **−0.05 < (ρ8A − ρ4) < 0.15**.
- Step 2, cloud, snow and water masks: one combined test using (ρ3−ρ12)/(ρ3+ρ12), ρ8A < ρ11 and ρ12 > 0.5 (see eq. 3 in the paper). Images are restricted to under 30% cloud.
- Step 3, roof rules:
  - red: 0 ≤ |ρ3−ρ2| ≤ 0.05 and (ρ4−ρ3)/ρ3 > 0.5
  - blue: ρ2 > ρ3, ρ2 > ρ4, (ρ2−ρ3)/ρ3 > 0.2
  - white: (ρ2+ρ3+ρ4) > 0.6 with ρ12 < 1, or > 0.9 with ρ12 < 1.4
  - plus PV-plant and impervious masks.
- Step 4: a pixel detected **more than 4 times at the same location** is treated as an industrial fixed source.
- Commission was **0.1-3%** after filtering, down from about 8-30% before. Omission was about 3-4% on average, with a maximum of about 7-8% in African grassland.
- Landsat 8/9 with the same method: commission about 1-4%, omission about 5-8%.
- **Relative to S2 detections, VIIRS omitted 94.86% and MODIS 94.47% of S2 AF pixels** on S2 orbits in eastern/central China, 2023. VIIRS AF counts were under 10% of S2-confirmed AFs in matched grids.
  - [inference] This is pixel counting: one 375 m pixel stands for up to about 350 S2 pixels, so per-fire omission is far lower. Still, many small, short-lived fires are seen only by S2.
- S2 passes about 2-3 h before VIIRS, and "most Sentinel-2 AFs can be burned out when VIIRS passes".
- S2B/S2C plus L8/9 together give about 2-3 day global fine-scale AF.

**Hu 2021 (as cited by Gui 2026):** adaptive multi-criteria on B4/B11/B12 at 20 m over fire-prone biomes. Average omission 4%, but mean commission 14% and above 40% on complex surfaces.

**Concrete action for us** (thread 2, the highest-value new idea in this note)
- We already pull every S2 scene to build the scars. Add the Gui test as one extra band in the same Earth Engine export.
  - Inputs: L1C TOA B2, B3, B4, B8A, B11, B12.
  - Settings: Gui steps 1-4. Use the >4-repeats rule over 2017-2026 to kill fixed sources such as brick kilns or factories near Obaidullaganj/Mandideep. Ignore roof rules inside the forest mask.
- Any AF pixel inside or on the edge of a scar gives the exact fire day (about 10:45 IST), even for <2 ha scars VIIRS never sees.
- It also catches fires VIIRS misses outright (thread 5 ground truth).
- Expected [inference]: S2 revisits every 5 days, or about 2-3 days with S2C. The fire must be burning at 10:45, and Ratapani fires likely peak after noon. So perhaps 3-8% of scars get an exact date, with a bias toward long-burning fires. Effort is about half a day.

---

## 10. GOES-16 as the closest analogue to our small understory fires (FULL: Li, Zhang, Kondragunta, Schmidt & Holmes 2020, RSE, accepted manuscript)

Link: https://repository.library.noaa.gov/view/noaa/41607/noaa_41607_DS1.pdf

**What it shows**
- Setting: south-eastern US prescribed burns, small understory fires, a good analogue for teak litter fires. Reference data were Landsat-8, VIIRS 375 m and state permit records for Georgia and Florida.
- **ABI detection probability exceeded 95% only when an ABI pixel held more than 114 Landsat-8 fire pixels or more than 11 VIIRS pixels.** Below 50 Landsat pixels or 5 VIIRS pixels, it fell under 14% and 37%.
- Within ±8 h, ABI detected 19% more of the Landsat-observed fires and 29% more of the VIIRS-observed fires than it did at the same time. Omission dropped by up to 33%.
- **ABI detected 6-22% (Georgia) and 31-42% (Florida) more ground-recorded prescribed fires than VIIRS did.** Even so, it "missed many very small fires" because it hardly detects fires below about 34.5 MW.

[inference] This is the best published evidence that a 2-km, 10-15 min geostationary sensor, used over a whole day, can beat twice-daily VIIRS on ground-recorded small understory fires. Florida's 31-42% gain shows how much depends on timing (fires that start and stop between passes). For us, SEVIRI is coarser (14 km² here, compared with ABI's 4 km²), so expect a much smaller gain.

**Concrete action for us:** use Li 2020's metric (detection probability against the number of VIIRS pixels per geo pixel) when we test SEVIRI and INSAT in Sections 2-3. It turns "does it work" into one curve.

---

## 11. Dating ignitions to the hour by combining geostationary and polar data

**Benali et al. 2016, "Determining Fire Dates and Locating Ignition Points With Satellite Data", Remote Sens. 8:326 (ABSTRACT ONLY; MDPI blocked)**
- Link: https://doi.org/10.3390/rs8040326
- Used MODIS active fires interpolated over burn scars. Study regions were Alaska, Portugal, Greece, California and SE Australia.
- Dated about 76% of burnt area. Start dates had MEF 0.91 and end dates MEF 0.73.
- Ignition time and place agreed with records within 12 h and 2 km. The ability to date rose with fire size.
- A 2022 arXiv paper describes this as first-detection-equals-ignition, with errors "up to a day".

**Korea, March 2025 wildfires (KJRS 2025; PARTIAL, about 60% of the page read through WebFetch)**
- Link: https://www.kjrs.org/journal/view.html?pn=mostdownload&uid=1117&vmd=Full
- 79 Korea Forest Service ignitions, with 9 cases detected by every product.
- **Mean lag from ignition to first detection:** GK-2A LightGBM 12.9 min, Himawari AHI 16.3 min, GK-2A FF product 18.2 min, MODIS 210 min, VIIRS 318 min.
- The ML model had recall 0.329 and precision 0.987. A small daytime fire was missed by all products. At night, VIIRS found two extra fires.
- Matching used a 2-pixel buffer and ±3 h.

**GOFER (Liu et al. 2024, ESSD 16:1395; ABSTRACT ONLY)**
- Hourly perimeters from GOES-East and West for 28 California fires. Mean IoU against final perimeters was 0.77 (VIIRS-based FEDS: 0.83).
- Large fires only.

**Hall et al. 2019 (IJAEOG 83:101928; ABSTRACT ONLY):** validates GOES-16 and SEVIRI against Landsat-8. Numbers not obtained.

[inference] There is no published method that dates *small* fires to the hour from geostationary data. For Ratapani, a practical scheme is a "time bracket" per scar:
- earliest possible = last clear S2/Landsat image without the scar, or the last pass with no detection;
- latest possible = the first detection from any of S2-AF (10:45), Landsat-AF (10:30), SLSTR (10:00/22:00), NOAA-20/21 (12:40/00:40), S-NPP (13:30/01:30), SEVIRI/INSAT (15 min);
- then pick the most likely day inside the bracket with the fire-weather prior already in our model.
Our current rule uses only the S-NPP passes.

---

## 12. Commercial and new thermal constellations

**OroraTech OT-NRT (FULL: Level-2 ActiveFire Product User Guide v1.0.2, NASA CSDA, Sept 2026)**
- Link: https://science.nasa.gov/wp-content/uploads/2026/09/ororatech-level-2-activefire-product-user-guide-v1-0-2-public.pdf
- Sensor and coverage:
  - 200 m GSD, MWIR + LWIR, 410 km combined swath, roll up to ±30°.
  - **Two scans a day, at about 04:00 and about 16:00 local, "to provide data during the peak afternoon burn period"**.
- Processing and delivery:
  - Detection runs onboard. Latency is "within minutes", limited mainly by ground-station contact.
  - Fields include cluster area (m²), age and lifetime (minutes) and confidence (low to very high).
  - Delivered through the Wildfire Solution web app and REST API.
- Validation by ESA's Copernicus Contributing Missions team (June 2026): joint detection rate 77.8% against VIIRS and 96.1% against MTG. The dataset was small, and the product has no cloud mask in the algorithm.
- Licence: commercial. NASA CSDA access is for US-government-funded researchers. India coverage is not stated.
- [inference] The 16:00 pass is exactly our gap. Ratapani's daytime VIIRS fires sit at 12:30-14:30 IST, and many litter fires are lit after midday.
- **Concrete action (thread 5):** ask OroraTech for a trial or quote for the Ratapani bounding box, Mar-Apr 2027. Evaluate on the share of verified fires seen only at 16:00.

**FireSat (Earth Fire Alliance / Muon Space / Google) (news only, ABSTRACT level)**
- Protoflight launched 14 Mar 2025. Three operational satellites launched 7 Jul 2026.
- Six-channel IR. Claimed detection of fires "as small as 5 × 5 m". At least twice-daily coverage now, with an hourly global target by 2029.
- Data access: early adopters first. No public portal or pricing found.
- **Action:** apply to EFA's early-adopter or partner programme on behalf of MP Forest Department and FSI. A 5 × 5 m detection limit is about our litter-fire scale.

**ECOSTRESS (ISS, about 70 m LST) (ABSTRACT ONLY: UC Irvine California fires study, Dryad doi:10.5061/dryad.q83bk3jz0)**
- The ISS orbit at 51.6° inclination covers MP at varying local times, including afternoon. Revisit is about 1-5 days.
- There is no operational fire product. The study used LST ≥ 60 °C as the hotspot test, with median hotspot temperatures of 62-77 °C.
- Data are free from LP DAAC.
- **Action (thread 2, low priority):** list ECOSTRESS afternoon granules over Ratapani for Mar-Apr 2019-2026, threshold LST ≥ 60 °C inside scar windows. These are extra exact dates at odd hours.

**constellr:** an LST service (30 m-class), not an active fire product. Not pursued. TRISHNA (ISRO-CNES, 57 m TIR) is planned but not yet usable.

---

## 13. Bhuvan / NRSC / FSI (search-level, PARTIAL)

- NRSC's Sariska 2022 report says alerts are generated "within 30 minutes of the satellite pass (day & night from MODIS, S-NPP and JPSS)" received at Shadnagar. They are sent to FSI and shown on Bhuvan (https://bhuvan-app1.nrsc.gov.in/disaster/disaster.php?id=fire).
  - [inference] This is the only India route to sub-hour VIIRS latency, because FIRMS RT/URT is US/Canada only.
- FSI FAQ: NRSC processes MODIS and SNPP-VIIRS. Only hotspots inside forest areas become "forest fire" alerts.
- NDRC 2019 minutes: "NRSC does not conduct any validation exercises" for the VIIRS/MODIS fire products.
- The "5.64% of fire incidents identified by MODIS and VIIRS in Uttarakhand" figure (Kalaranjini et al. 2020, cited in Chandel et al. 2022) could not be traced to the original.
- **Action (thread 5):** confirm whether FSI's FAST feed already includes NOAA-20/21 (JPSS). If it does, use FSI/NRSC alerts (latency about 30 min) as the live stream and FIRMS only for archives.

---

## 14. VIIRS 375 m false-alarm and omission for small understory fires: what the numbers say

- **Commission:**
  - Globally under 1.2% (Schroeder 2014).
  - Over the US south-east and Brazil, other studies range widely (see `field_alert_systems.md` §C).
  - FSI ground checks in Uttarakhand found 6-7% real forest fires, but that is mostly an issue of definition (farm fires, non-forest).
- **Omission:**
  - VIIRS 375 m detected far fewer ground-recorded small prescribed fires than GOES-16 over the course of a day (Li 2020, Section 10).
  - VIIRS AF counts were under 10% of S2-detected small-fire pixels (Gui 2026; pixel-based).
  - Our own figure: 30% of <2 ha scars and 38% of all scars have a VIIRS date.
- **Detection floor:** about 100 m² at 1000 K by day (Gui citing [8]); about 5 m² at night (bonfire test, Schroeder 2014).

[inference] Most omission is about timing (fires that burn between passes), not sensitivity. Hence the ranking below favours more looks (NOAA-20/21, SLSTR, S2/Landsat AF, a 16:00 commercial pass) over coarser 15-min geostationary data.

---

## Datasets

| Name | Link | Resolution | Time of day (IST) / revisit | Years | Licence | Access |
|---|---|---|---|---|---|---|
| VIIRS NOAA-20 375 m (VJ114IMG / ML) | sftp fuoco.geog.umd.edu ; FIRMS API `VIIRS_NOAA20_SP` | 375 m | ~12:40, ~00:40 daily | 2018- | NASA open | SFTP monthly CSV; FIRMS MAP_KEY |
| VIIRS NOAA-21 375 m (VJ214IMG) | FIRMS `VIIRS_NOAA21_NRT` ; UMD SFTP | 375 m | ~12:40, ~00:40, 50 min phase from N20 | 2023- | NASA open | as above |
| VIIRS S-NPP 2025-26 (update) | FIRMS `VIIRS_SNPP_NRT/SP` | 375 m | 13:30, 01:30 | 2012- | NASA open | as above |
| Sentinel-3 SLSTR FRP (`SL_2_FRP___`) | Copernicus Data Space Ecosystem | 1 km | ~10:00, ~22:00; S3A + S3B | night 2020-, day Mar 2022- | Copernicus free | CDSE OData/STAC |
| Meteosat IODC FRP-PIXEL | https://lsa-saf.eumetsat.int (Data Server) ; FIRMS geostationary layer | 3 km nadir, ~3 × 4.4 km here | every 15 min, 24 h | 2017- (Met-8 41.5 E to Jun 2022, then Met-9 45.5 E) | free, registration | HDF5 lists; FIRMS KML/WMS |
| INSAT-3DS fire `3SIMG_L2P_FIR` | https://mosdac.gov.in | 4 km MIR | 15-30 min | 2024- (3D/3DR FIR earlier, unconfirmed) | MOSDAC registration | KML points |
| FY-4A/4B FHS | satellite.nsmc.org.cn | 2-4 km | 15 min | 2018- | NSMC registration | .nc |
| Landsat 8/9 OLI (run Schroeder 2016 ourselves) | Earth Engine `LANDSAT/LC08|LC09/C02/T1_TOA` | 30 m | ~10:30, 8 days combined | 2013- | public domain | GEE |
| Sentinel-2 MSI (run Gui 2026 rule) | GEE `COPERNICUS/S2_HARMONIZED` ; code link in §9 | 20 m | ~10:45, 5 days (2-3 with S2C) | 2017- (2015-) | Copernicus free | GEE |
| ECOSTRESS LST (ECO2LSTE / ECO_L2T_LSTE) | LP DAAC / AppEEARS | 70 m | variable, afternoon possible | 2018- | NASA open | AppEEARS |
| OroraTech OT-NRT | OroraTech WFS API | 200 m | ~04:00, ~16:00 | 2025- | commercial | REST API (quote) |
| FireSat (EFA) | earthfirealliance.org | ~5 m fire detection claimed | ≥2/day now | 2026- | early adopter | apply |
| NRSC/FSI alerts | fsiforestfire.gov.in ; Bhuvan | MODIS/VIIRS | ~30 min after pass | ongoing | Govt | FSI portal/SMS |

---

## Ranked action list

| # | Action | Thread | Gain (my estimate) | Effort |
|---|---|---|---|---|
| 1 | Add NOAA-20 (2018-) and NOAA-21 (2023-) VIIRS, plus S-NPP 2025-26, to scar dating and the label build. Re-measure the dated share per season. | 2, 1 | +several points of dated scars, more true-lead labels | 0.5 day |
| 2 | Run the Gui 2026 S2 active-fire rule (and Schroeder 2016 on Landsat) on every scene we already use. AF inside a scar gives the exact day, including <2 ha scars. Use the >4-repeat filter for kilns. | 2, 4, 5 | exact dates for a few % of scars; 30 m fire fronts for spread validation | 0.5-1 day |
| 3 | Add Sentinel-3 SLSTR FRP day and night (2020-) to the dating pool, especially the 22:00 pass. | 2 | extra night-burning detections, 2 MW floor at night | 0.5 day |
| 4 | Pull the Meteosat IODC FRP-PIXEL archive (2017-2026) for Ratapani before the service ends. Measure hit rate and hour offset against VIIRS-dated scars with the Li 2020 curve. | 2, 1 | hour-of-ignition for the largest ~5-15% of fires; ignition-hour prior per beat | 1 day |
| 5 | Add the FIRMS "Filtered Geostationary" layer as a second live alert stream (15-min poll, confidence ≥0.5, labelled ±3 km). | 5 | earlier alerts for big fires only | 0.5 day |
| 6 | Confirm whether the FSI/NRSC feed includes NOAA-20/21, and its latency. Use it as the primary live feed (FIRMS RT/URT is not offered for India). | 5 | alerts about 30 min after pass | email |
| 7 | Trial OroraTech (16:00 pass) and apply to the FireSat early-adopter programme for Mar-Apr 2027. Score on fires only they see. | 5, 2 | fills the afternoon gap, where most litter fires burn | quote / application |
| 8 | Register on MOSDAC and test one week of INSAT-3DS `FIR` KML against VIIRS. Request the 3D/3DR archive. | 5, 2 | likely small (4 km MIR), but Indian 15-min timing | 0.5 day |
| 9 | Build a per-scar "time bracket" (last clear image, then first detection from any sensor) and replace single-day S-NPP dating with the most-likely day inside it. | 2, 1 | cleaner true-lead labels | 1 day after 1-4 |
| 10 | ECOSTRESS afternoon LST ≥ 60 °C inside scar windows. | 2 | a few extra exact dates | 0.5 day |

Not worth pursuing for Ratapani: MTG/Meteosat-12 (beyond the limb), Himawari (VZA 74°), FY-4 (missed nearly all Valmiki/Chitwan forest fires), the LFTA product itself (North America only; run the algorithm instead).

## Reading status

- **FULL (11):**
  - Wooster 2015 ACP
  - Schroeder 2016 (Landsat)
  - Schroeder 2014 (VIIRS)
  - Gui 2026 TGRS
  - Xu 2021 SLSTR (accepted manuscript)
  - Li 2020 GOES-16 (accepted manuscript)
  - FY-4A ISPRS 2021
  - OroraTech L2 user guide 2026
  - INSAT-3DS products document
  - VIIRS C2 user guide
  - FIRMS FAQ and geostationary blog (counted as one)
- **PARTIAL:** Korea KJRS 2025; LSA SAF product page; Thapliyal ITSC-25 slides.
- **ABSTRACT ONLY:**
  - Hu 2021
  - Xu & Wooster 2023
  - Benali 2016
  - Singh 2017 (INSAT)
  - Hall 2019
  - GOFER 2024
  - FireSat news
  - ECOSTRESS UCI study
  - Kalaranjini 2020 (secondary citation)
