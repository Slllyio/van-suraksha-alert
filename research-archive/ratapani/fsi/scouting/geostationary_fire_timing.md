# Geostationary fire timing over Ratapani: what can be downloaded, what it shows, and a first local diurnal curve (scouting round 8, topic "geo timing", 14 Oct 2026)

Scope: (1) which geostationary active-fire / FRP products actually cover Ratapani, and which can be downloaded without a login; (2) a real sample over peak-season weeks, compared with our VIIRS, to estimate the local diurnal curve and what the polar passes miss; (3) full reads of the papers that fit diurnal cycles or validate geostationary fire data over South Asia.

Builds on `diurnal_and_controlled_burns.md` (round 7: 16:30 India prior from Giglio, 30-60% of fires active at neither S-NPP pass in a toy model), `fire_detection_sources.md` §1-5, 11 (product list and pixel geometry) and `burn_dating_validation.md` §17 (Jethva, PARTIAL then; FULL now, below).

Sources are marked FULL / PARTIAL / ABSTRACT ONLY. My own reasoning is marked [inference]. No accounts were registered and no credentials were used.

Files (scratch, copy them if you want to keep them):
- Scripts: `/tmp/claude-0/-home-user/be9b8f54-cc26-52cb-bdbb-9c8008a24baf/scratchpad/r8code_geo/` (`gk2a_pull.py` download and cut, `h5c.py` HDF5 reader via the system libhdf5 through ctypes with no new packages, `geos.py` geostationary projection, `gk2a_v2.py` detection, `gk2a_events.py`, `composite_rad.py` / `composite_rad30.py` stacked curve, `fit.py`, `sweep.py` EUMETView FIR sweep, `fir_match.py`, `pairs.py`).
- Data: `/tmp/claude-0/-home-user/be9b8f54-cc26-52cb-bdbb-9c8008a24baf/scratchpad/geo_r8/`. This holds the GK2A brightness-temperature cubes for central India (`gk2a_2023/`, 21 days at 30-minute steps; `gk2a_2024/`, 14 days), detections (`gk2a_det_k3p*.csv`), events (`gk2a_events_*.csv`), composites (`composite_rad*_2023/2024.csv`), the EUMETView FIR sweeps (`sweep_2022.json`, `sweep_2024.json`), and FIRMS India country CSVs for 2022-2024 (`firms/`).

---

## Headline findings

1. **No geostationary *fire product* can be downloaded over Ratapani without a login, except EUMETSAT's FIR, which is close to useless here.**
   - EUMETView WMS layer `msg_iodc:fire` is open, covers Aug 2020 to now at 15-minute steps, and needs no key.
   - In 9 peak days of 2022 (Meteosat-8) and 14 peak days of 2024 (Meteosat-9) it flagged the Ratapani AOI **once** (27 Mar 2022, 13:15 IST, "potential fire"). Over the same days we have 1,000+ VIIRS points.
   - The products that matter are behind free registration: LSA SAF FRP-PIXEL (directory listing open, files return 401), EUMETSAT Data Store SEVIRI IODC L1.5, MOSDAC INSAT-3D/3DR/3DS FIR, JAXA P-Tree Himawari WLF, NSMC FY-4, and KMA NMSC GK2A L2.
2. **The one keyless route that works is raw GK2A AMI L1B on NOAA's AWS bucket** (`noaa-gk2a-pds`, Feb 2023 to now, every 10 minutes).
   - Ratapani is at a view zenith of 61.8°, and a GK2A pixel there is about 2.4 × 4.0 km, roughly 10 km². That is smaller than SEVIRI IODC (about 14 km²) or INSAT (about 19 km²).
   - I wrote a fire detector for it and ran it over central India (21-25 N, 75-81 E) for 3-23 Apr 2023 and 18-31 Mar 2024. The download costs about 1 s per file and nothing is kept except a 211 × 233 pixel box.
3. **Measured detection probability of single-pixel geostationary detection against VIIRS (GK2A, 2023 and 2024 pooled):**
   - **By day, 0.1% for VIIRS clusters under 10 MW, 0.5-1.6% for 10-30 MW, 1.6-6.5% for 30-100 MW, and 7-24% above 100 MW.**
   - **By night, about 1% under 5 MW, 5-6% for 5-10 MW, 12-14% for 10-30 MW, and 45-62% for 30-100 MW.**
   - Precision is 96-100% outside 16:00-18:59 IST (chance level 14-23%). Sunset hours are artefact-ridden.
   - At Ratapani, 69% of day pixel-passes are under 10 MW and none reached 100 MW in the 2024 sample. Single-pixel geostationary detection therefore **cannot date Ratapani fires one by one**: there were 3 AOI events in 21 days of 2023 and 0 in 14 days of 2024.
4. **A stacked ("composite") GK2A signal does give a local diurnal curve.** I took the excess 3.8 µm radiance (proportional to FRP) at every pixel-day with a VIIRS fire and subtracted no-fire controls. The fire signal:
   - **starts at about 08:00-08:30 IST and reaches half its maximum at about 09:00-10:00;**
   - **peaks at 12:10-12:20 IST (2023, 19,946 fire pixel-days) and 13:10-13:30 IST (2024, 8,100);**
   - **falls to half by about 15:00-16:00 and to 13-31% by 17:00**, with a full width at half maximum of 5.8-7.7 h;
   - keeps a **night floor (21:30-05:30) of 12-37% of the peak**.
   - **Ratapani AOI alone (2023, 597 pixel-days): peak at about 11:35-12:15 IST, half-max 08:45-14:15.** The 2024 AOI curve is too noisy to use.
   - [inference] This contradicts the borrowed India prior (peak 16:30 local, IQR 3 h, Giglio 2006), which is dominated by crop burning. **For Ratapani forest fires the 13:30 VIIRS pass sits at or just after the daily peak, not on the rising limb.**
5. **Same-day S-NPP / NOAA-20 pairs agree.** On days when both satellites passed with 3 or more fires each, the later pass (on average 50 minutes later, around 13:05 vs 13:55 IST) saw the same number of fire pixels as the earlier one:
   - AOI: mean log ratio −0.003 ± 0.068 (2022) and −0.020 ± 0.090 (2024);
   - central MP: +0.095 ± 0.044 (2022) and −0.022 ± 0.047 (2024).

   Activity is on a plateau around 13:00-14:00, not rising steeply.
6. **What the polar passes miss.** For the fires big enough for GK2A to see, the share of fire-days with **no** VIIRS/MODIS detection that day is small:
   - 2024: 22 events; 91% had a VIIRS day detection, 5% were night-only and 5% had none;
   - 2023: 77 events; 81%, 10% and 9%.

   For the small fires that dominate Ratapani, geostationary data cannot measure the miss rate directly. [inference] The composite curve suggests most burning happens between 09:00 and 16:00, which brackets the 12:40-13:30 passes. So the round-7 toy model (30-60% of fires active at neither S-NPP pass) is probably too pessimistic, unless most Ratapani fires last under about 2 h. I would revise the planning figure to roughly 20-45% [inference].
7. **INSAT-3DS L1B (MIR at 4 km, every 30 minutes) is open on MOSDAC Live**, through ncWMS GetFeatureInfo/GetMap with no login. It is a rolling archive only: 1 Sep 2026 was present and 1 Jul 2026 was gone. It is the best geometry (view zenith 27°), and it can be captured live in Feb-May 2027 with a cron job. It cannot be backfilled.

---

## 1. Products table: what covers Ratapani and what works

Pixel areas use my projection code (`geos.py`): spherical-Earth view zenith angle (VZA), with the GK2A footprint from the real fixed-grid Jacobian.

| Product | Satellite (lon) | VZA at Ratapani | Pixel here | Years | Cadence | Access route | Login? | Licence | Tested result (14 Oct 2026) |
|---|---|---|---|---|---|---|---|---|---|
| **LSA SAF FRP-PIXEL, MSG-IODC** (HDF5 ListProduct + Quality) | Met-8 41.5 E to Jun 2022, then Met-9 45.5 E | 48.5° / 44.9° | ~3.1 × 4.4 km (~14 km²) | 2017-2026 (directories 2017/…/2026 listed) | 15 min | `https://datalsasaf.lsasvcs.ipma.pt/PRODUCTS/MSG-IODC/FRP-PIXEL/HDF5/YYYY/MM/DD/HDF5_LSASAF_MSG-IODC_FRP-PIXEL-ListProduct_IODC-Disk_YYYYMMDDhhmm` | **Yes**, free (mokey.lsasvcs.ipma.pt signup) | EUMETSAT/LSA SAF data policy, free with attribution | **Directory listing is open** (file names, sizes 92-94 KB per slot for the whole disk). **Files return HTTP 401** (Basic auth). Best product to get once registered |
| **EUMETSAT FIR "Active Fire Monitoring", MSG-IODC** (rendered) | as above | same | marker about 0.16° (~17 km) | 1 Aug 2020 to now | 15 min | EUMETView WMS `https://view.eumetsat.int/geoserver/ows?service=WMS&request=GetMap&layers=msg_iodc:fire&time=…` | **No** | EUMETSAT open imagery | **Works.** Red = fire, yellow = potential fire. No WCS for IODC layers. Only a coarse location. See §2a |
| EUMETView `msg_iodc:ir039` / `ir108` imagery | as above | same | rendered grid about 0.04° | Aug 2020 to now | 15 min | same WMS | No | EUMETSAT | **Works but not radiometric.** 8-bit display stretch; ir108 is clipped at the warm end by day. Not usable for our own detection |
| EUMETSAT Data Store, SEVIRI IODC L1.5 (`EO:EUM:DAT:MSG:HRSEVIRI-IODC`) | as above | same | 3 km nadir | 2017- | 15 min | `api.eumetsat.int/data/search-products` (search is open); download needs a token | **Yes**, free EUMETSAT account | EUMETSAT data policy | Search works (e.g. product `MSG2-SEVI-MSG15-0100-NA-20240325082740`, about 187 MB per slot). Download without a token returns 404 |
| FIRMS "Filtered Geostationary" (SEVIRI, Himawari, GOES) | — | — | — | NRT only | 10-15 min | FIRMS map / WMS | MAP_KEY for WMS | NASA open | **The FIRMS API sources list has no geostationary entry** (checked `/api/data_availability/`: LANDSAT, MODIS, VIIRS only). No archive download |
| **GK2A AMI L1B full disk** (SW038 + IR112 NetCDF4) | GK2A 128.2 E | **61.8°** | **~2.4 × 4.0 km (~10 km²)** | **Feb 2023 to now** on AWS | 10 min | `https://noaa-gk2a-pds.s3.amazonaws.com/AMI/L1B/FD/YYYYMM/DD/HH/gk2a_ami_le1b_sw038_fd020ge_YYYYMMDDhhmm.nc` (~29 MB) | **No** | NOAA Open Data Dissemination; KMA data (attribution) [inference] | **Works.** 1,644 slots × 2 bands pulled and processed. Needs our own detector (§2b) |
| GK2A L2 fire product (FF) / NMSC API | GK2A | same | 2 km nadir | 2019- | 10 min | nmsc.kma.go.kr (API key) | Yes | KMA | Not tested (login). Jethva 2026 used the NMSC API for L1B 2019-2025 |
| Himawari-9 AHI L1b (HSD) | 140.7 E | 73.6° | ~2.2 × 7.9 km | 2022- (H8 2015-2022 in `noaa-himawari8`) | 10 min | `noaa-himawari9` S3 bucket, open | No | NOAA ODD / JMA | Bucket lists open (L1b and L2 cloud/winds; no fire L2). Not processed: extreme limb |
| JAXA P-Tree Himawari Wild Fire (WLF) L2 | 140.7 E | 73.6° | 2 km nadir | 2015- | 10 min | `ftp.ptree.jaxa.jp` (CSV) | **Yes**, P-Tree registration | JAXA terms (credit P-Tree) | FTP connection reset from this container. The userguide (WebFetch) gives full disk, 10-minute L2, CSV, Kurihara 2020 algorithm |
| INSAT-3DS Imager L1B (MIR, TIR1, TIR2, WV counts) | 82 E | 27.3° | ~4.1 × 4.6 km (~19 km²) | **rolling about 6 weeks** (1 Sep-14 Oct 2026 present; 1 Jul absent) | 30 min | MOSDAC Live ncWMS: `https://mosdac.gov.in/live5/wms/live3SL1BSTD4km/products/Insat3s/3S_IMG/YYYY/DDMMM/3SIMG_DDMMMYYYY_hhmm_L1B_STD_V01R00.h5?service=WMS&request=GetFeatureInfo&layers=IMG_MIR…`; slot list via `…/live/backend/satellite_data.php?category_prefix=3SIMG&category_filename=L1B_STD_V01R00&date_val=25MAR2026&timezone=gmt&timezone_formal=0` | **No** (send a Referer header) | ISRO/MOSDAC terms | **Works for recent data.** GetFeatureInfo at Ratapani returned MIR count 754 (13 Oct 08:00 UTC). CoverageJSON is blocked (403). The slot listing for Mar 2025/2026 works, but those files are gone from the live store (500, FileNotFound). The Live "fire" JSON (`getfirejson.php`) returned empty |
| INSAT-3D/3DR/3DS FIR L2 (KML/HDF) | 74 / 82 E | 27° | ~19 km² | 3D 2013-, 3DR 2016-, 3DS 2024- | 15-30 min | MOSDAC catalogue / order | Yes | ISRO | Not tested (login). POD 45% against high-confidence MODIS (Singh 2025, ABSTRACT ONLY) |
| FY-4A/4B FHS (fire/hotspot list) | 105 E (4B); 4A position not verified | 40.7° (105 E) | ~4.1 × 5.5 km | 2018- | 15 min | satellite.nsmc.org.cn | Yes | NSMC | Connection reset from this container. Used for South Asia emissions by Wang 2025 (§3c) |
| MTG FCI FRP (Meteosat-12, 0°) | 0° | 87.5° | — | 2025- | 10 min | LSA SAF | — | — | Beyond the limb. Not usable |

[inference] Ranking for Ratapani:
- **For history, register for LSA SAF FRP-PIXEL** (2017-2026, the only archive with per-pixel FRP). It detects about 4.7 times more pixels than FIR (Roberts 2015, §3b), so expect roughly 5 times the FIR hit rate, which is still only a few percent of fire cells.
- **For the 2027 season, keyless GK2A plus a live INSAT-3DS capture** are enough, and need no accounts.

---

## 2. Sample results (DATA, computed 14 Oct 2026)

### 2a. EUMETSAT FIR via EUMETView, swept every 15 minutes over 21-25 N, 75-81 E

| Window | Satellite | Slots | Slots with any hit in box | Slots touching the Ratapani AOI | FIRMS points in box |
|---|---|---|---|---|---|
| 21-29 Mar 2022 (peak week, 191 VIIRS points on 27 Mar alone) | Met-8 (41.5 E) | 864 | 26 | **1** (27 Mar 13:15 IST, potential fire, at the 46-point VIIRS cluster near 22.98 N 77.77 E) | 27,852 VIIRS + 1,764 MODIS |
| 18-31 Mar 2024 | Met-9 (45.5 E) | 1,344 | 61 | **0** | 17,736 VIIRS + 1,222 MODIS |

Detection rate of FIR for VIIRS clusters, summed FRP per 0.1° cell per pass, with a hit counted within 15 km and ±3 h:

| Year | <10 MW | 10-30 MW | 30-100 MW | 100-300 MW | >300 MW |
|---|---|---|---|---|---|
| 2022 | 0.4% (n = 5,132) | 0.9% | 3.1% | 11.5% (n = 208) | 30% (n = 23) |
| 2024 | 0.8% (n = 4,973) | 2.4% | 3.9% | 21% (n = 71) | 80% (n = 15) |

- Every FIR hit had FIRMS fires within 10 km that day, with summed FRP of 89-2,821 MW.
- Many hits were in the evening (20:15-23:45 IST) over the Narmada-valley forests at 22.3-22.7 N, 77.2-77.6 E, just south of the AOI. [inference] The night background is cooler, so FIR's thresholds trip more easily.
- Concrete action for us: none for labels. Use FIR only as a free live "big fire" flag (thread 5).

### 2b. GK2A, our own detector (temporal-contextual, 30-minute steps)

**Method** (`gk2a_v2.py`):
1. BT(3.8 µm) and BT(11.2 µm) are computed from DN with the file's gain, offset and Teff→Tbb coefficients.
2. Clear-sky test: T11 > 295 K by day (07:00-18:59 IST) or > 280 K by night, and all 8 neighbours clear.
3. For each pixel and time-of-day slot, the background is the median over all days of ΔT = T3.8 − T11.2 and of T3.8. The noise is the MAD over days.
4. The regional median anomaly is removed for each slot.
5. A pixel is flagged as fire if the ΔT anomaly > max(3·MAD, 2.5 K) and the T3.8 anomaly > max(3·MAD, 2 K), with the same pixel or a neighbour also flagged in the slot before or after (≥30 minutes of persistence).
6. Geolocation uses the GEOS normalised projection with a measured −1 line/column offset, found by maximising the anomaly at VIIRS fires.

**Results:**

| | 2023 (3-23 Apr, 972 slots; 36 slots missing on 12 Apr) | 2024 (18-31 Mar, 672 slots) |
|---|---|---|
| Clear fraction, day / night | 0.54 / 0.70 | 0.58 / 0.81 |
| Detections, then kept after dropping 16:00-18:59 IST | 806 → 739 | 316 → 261 |
| Share confirmed by a FIRMS fire within 2 px on the same fire-day (06:00-06:00 IST) | **96%** (chance 23%) | **100%** (chance 14%) |
| POD by day, VIIRS FRP summed per GK2A pixel per pass: <5 / 5-10 / 10-30 / 30-100 / >100 MW | 0.1 / 0.1 / 0.5 / 1.6 / 6.8% | 0.1 / 0.5 / 1.6 / 6.5 / 24.1% |
| POD by night: <5 / 5-10 / 10-30 / 30-100 MW | 1.2 / 5.7 / 14.3 / 44.7% | 0.9 / 5.3 / 12.0 / 61.5% |
| Background MAD, midday vs night | 2.0-2.3 K vs 0.9-1.0 K | 2.7-3.0 K vs 0.8-1.0 K |
| Fire events (clusters per fire-day) | 77; median max VIIRS FRP 38 MW | 22; median 49 MW |
| Events with a VIIRS day detection / night-only / none | 81% / 10% / 9% | 91% / 5% / 5% |
| Events in the Ratapani AOI | **3** | **0** |

The three AOI events in 2023:
- **6 Apr, 21:30-22:00 IST**, 22.84 N 77.85 E. VIIRS had 20 day and 62 night points.
- **7 Apr, 09:00-10:00 IST**, 22.86 N 77.95 E. VIIRS first saw it at 13:19.
- **18 Apr, 08:00-08:30 IST**, 22.99 N 77.56 E. VIIRS first saw it at 14:02.

Two of the three were burning 3.5-6 h before the first VIIRS view. [inference] The 7 Apr event is probably the 6 Apr fire, which burned overnight (62 night points) and was still active at dawn.

Artefacts to know about:
- 16:00-18:59 IST: the sunset terminator. Confirmation drops to 8-50%.
- About 20:00 IST (14:30 UTC): large negative offsets in all pixels. [inference] This is probably the GK2A eclipse-season calibration around the equinox. Drop it.
- 07:00 IST: few files (GK2A housekeeping).

### 2c. The local diurnal curve: stacked GK2A excess 3.8 µm radiance

**Method** (`composite_rad.py`, `composite_rad30.py`):
1. MIR radiance L3.8 comes from the Planck function at 2,632 cm⁻¹.
2. The per-pixel, per-slot clear-sky median is removed, and then the regional median.
3. The anomaly is summed over the 3 × 3 window, which absorbs geolocation error. The sum is proportional to FRP in that roughly 90 km² window, following the MIR radiance method [inference].
4. The result is averaged over all pixel-days with a VIIRS (S-NPP or NOAA-20) fire. A random no-fire control (no FIRMS fire within 3 px and ±1 day, 3,000 pixel-days) is subtracted.

Values below are percent of each curve's maximum, by IST hour (07, 18 and 20 removed as artefacts).

| Hour (IST) | 06 | 08 | 09 | 10 | 11 | 12 | 13 | 14 | 15 | 16 | 17 | 19 | 21 | 22 | 23 | 00 | 01 | 02 | 03 | 04 | 05 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 2023 all fire pixel-days (n = 19,946) | 10 | 31 | 61 | 78 | 88 | **100** | 87 | 65 | 40 | 19 | 13 | 24 | 19 | 20 | 17 | 15 | 17 | 17 | 17 | 13 | 13 |
| 2023 VIIRS night-only pixel-days (n = 6,727) | 15 | 39 | 77 | 97 | **100** | **100** | 83 | 66 | 43 | 20 | 14 | 32 | 30 | 31 | 30 | 28 | 30 | 27 | 26 | 22 | 22 |
| 2023 VIIRS sum ≥50 MW (n = 1,007) | 5 | 21 | 52 | 69 | 83 | **100** | 82 | 64 | 46 | 20 | 14 | 20 | 16 | 14 | 14 | 19 | 14 | 12 | 10 | 8 | 7 |
| **2023 Ratapani AOI (n = 597)** | 7 | 29 | 76 | 92 | **100** | 93 | 71 | 41 | 38 | 13 | 5 | 18 | 10 | 16 | 22 | 19 | 19 | 21 | 14 | 15 | 13 |
| 2024 all fire pixel-days (n = 8,100) | 27 | 17 | 39 | 68 | 82 | 92 | **100** | 96 | 72 | 40 | 31 | 63 | 46 | 39 | 32 | 33 | 33 | 40 | 43 | 44 | 41 |
| 2024 VIIRS sum ≥50 MW (n = 287) | 7 | 8 | 21 | 42 | 63 | 68 | **100** | 85 | 53 | 29 | 22 | 38 | 29 | 34 | 30 | 21 | 19 | 18 | 22 | 19 | 18 |
| 2024 Ratapani AOI (n = 451): too noisy, max at 02 h | 59 | 39 | 26 | 41 | 31 | 65 | 93 | 97 | 38 | 36 | 40 | 44 | 27 | 19 | 45 | 51 | 71 | 100 | 71 | 60 | 55 |

Gaussian fit to 08:00-18:00 at 30-minute resolution (Andela 2015 form, `fit.py`):

| Curve | Peak (IST) | σ (h) | FWHM (h) | Half-max window (empirical) | Night mean / peak |
|---|---|---|---|---|---|
| 2023 all fire-days | **12.20** | 2.60 | 6.1 | ~09:00 → ~15:15 | 0.16 |
| 2023 Ratapani AOI | **11.60** | 2.25 | 5.3 | ~09:00 → ~14:15 | 0.16 |
| 2023 FRP ≥50 MW | 12.40 | 2.45 | 5.8 | ~09:30 → ~15:15 | 0.12 |
| 2024 all fire-days | **13.20** | 3.25 | 7.7 | ~10:00 → ~16:15 | 0.37 |
| 2024 FRP ≥50 MW | 13.45 | 1.95 | 4.6 | ~11:00 → ~15:45 | 0.22 |

Comparison: Andela 2015 (Africa SEVIRI) gives woody savanna 13.2 h with σ 0.94 h. Giglio 2006 gives India 16.5 h with IQR 3 h.

Reading [inference]:
- **The fire signal in central-MP and Ratapani forests is a late-morning to early-afternoon cycle.** It starts by 08:00-09:00 IST and peaks between 11:30 and 13:30. It is broader than African savanna (σ about 2.5 h against 1 h) and much earlier than the 16:30 India prior.
- **Selection bias:** pixel-days were picked by VIIRS detections near 13:30 and 01:30, which pulls the curve toward 13:30. Three checks argue that the shape is real:
  - the 2023 peak falls before the pass, at 12:15;
  - the VIIRS-night-only subset, which was not selected by any day pass, peaks at the same time (11:30-12:30);
  - the S-NPP/NOAA-20 pairs are flat across 13:05-13:55 (§2d).
- **Other caveats:**
  - the 3 × 3 window mixes neighbouring fires;
  - the daytime 3.8 µm channel carries reflected sunlight. It is removed on average by the per-slot background, but it adds noise;
  - the clear-sky mask (T11 > 295 K) may thin late-afternoon samples;
  - only two windows (one per year) were processed.
- **The night floor (12-37% of the peak) is real overnight burning.** It is highest for VIIRS-night-only pixel-days (22-31%) and decays slowly from 21:00 to 05:00. That fits the 26-30% night share already seen in VIIRS and the FSI data.

### 2d. Same-day S-NPP versus NOAA-20 daytime passes (`pairs.py`; FIRMS country CSVs 2022 and 2024; Feb-May; days with ≥3 fire pixels in each pass)

| Region, year | Days | Median gap | log(later / earlier) fire-pixel count | log ratio of FRP |
|---|---|---|---|---|
| AOI 2022 | 69 | 0.83 h | −0.003 ± 0.068 | +0.009 ± 0.076 |
| AOI 2024 | 52 | 0.68 h | −0.020 ± 0.090 | +0.039 ± 0.106 |
| Central MP 2022 | 120 | 0.83 h | +0.095 ± 0.044 | +0.134 ± 0.043 |
| Central MP 2024 | 114 | 0.83 h | −0.022 ± 0.047 | +0.018 ± 0.054 |

The result is the same whichever satellite passes later, which rules out a sensor bias. [inference] Between about 13:05 and 13:55 IST, fire activity changes by at most about +10% per 50 minutes. That is a plateau near the peak, consistent with §2c.

### 2e. Aqua's drift as a time probe (MODIS, AOI, Feb-May)

- The Aqua day pass moved from 13:40 (2013-2022) to 14:08 (2024) and 14:42 (2025).
- The Aqua / NOAA-20 day-count ratio was 0.17 (2019), 0.155 (2021), 0.135 (2022), 0.09 (2023), 0.086 (2024) and 0.139 (2025).
- There is no clear rise as Aqua moved later. That is consistent with a plateau or slow decline after 13:30, but the series is too noisy to use [inference].

### 2f. What share of fire-days do the polar passes miss?

- **Measured, for geostationary-detectable fires (median VIIRS max FRP 38-49 MW):** 5-9% of fire-days had no VIIRS or MODIS detection that day, and a further 5-10% were seen only at night.
- **Not measurable from geostationary data for small fires:** GK2A detects 0.1% of the under-10 MW pixel-passes that make up 69% of Ratapani day detections.
- [inference] Plugging the measured curve into the round-7 toy model instead of the assumed one (peak 13-14 h, σ 1.5-2.5 h): with a burning window peaking at about 12:30 and spanning roughly 09:00-16:00, a fire lit at 09:00-11:00 is mostly still burning at 12:40-13:30 if it lasts 3 h or more. The miss rate is driven by fires lit after about 14:00 that die before 00:40, and by fires shorter than about 2 h lit before 10:30.
  - Of the 08:00-17:59 area under the composite curve, 23% (2023) and 38% (2024) falls after 14:00.
  - My planning estimate is that **about 20-45% of fire-days are active at neither NOAA-20 nor S-NPP pass**. That is down from 30-60%, before detection-probability losses.

---

## 3. Per-source sections

### 3a. Jethva, H. 2026, "Timing the flames: geostationary satellite detection of diurnally shifting stubble burning in northwestern India", Remote Sens. 18:1506 (CC BY). https://doi.org/10.3390/rs18101506 ; PDF from mdpi-res.com. **FULL** (27 pp, all text read)

**What it shows**
- GK2A AMI, 2019-2025, hourly 12:00-18:00 IST, Punjab and Haryana, Oct-Nov.
  - BT is computed from the sw038 and ir112 counts with the KMA sample-code coefficients.
  - The test is ΔTb = T3.8 − T11.2, normalised by the mean of the 09:00-11:00 IST hours.
  - Thresholds depend on the hour (Table 1). Low / nominal / high confidence at 12:00-14:00 is ΔTb_norm > 3 / 4 / 5 K, with T3.8 ≥ 303 K and T11.2 ≥ 293 K. At 15:00-16:00 it is >2.5 / 3.5 / 4.5 K, and at 17:00 >2 / 3 / 4 K.
  - The AMI cloud mask calls fire and smoke "probably cloudy", so those pixels are taken back with strict BT tests.
- Pixel about 3.8-4 km over NW India.
- AMI false positives against VIIRS (within 0.04°, 14:00 slot vs the 13:40 VIIRS pass): **1.6% (2020), 4% (2021), 4% (2022)**. A ±2 K change in threshold changes them to 1-10%.
- **50% of AMI-detected fires had collocated VIIRS FRP ≤100 MW, and 80% ≤150 MW.** In other words, AMI sees only fires of tens of MW and above.
- The burning peak shifted from 13:00-14:00 IST (2019-2021) to about 1 h later (2022-23) and to 16:00-17:00 IST (2024-25).
- Cloud fractions in Punjab were 32, 24, 7, 11, 15, 2 and 5% for 2019-2025.
- Aqua passes over NW India: 13:44 (2021), 13:53, 14:05, 14:32, 15:12 (2025), expected about 15:50 by Aug 2026.
- Estimated share of fires missed: VIIRS missed about 64% in 2025 and about 56% in 2024; MODIS missed about 40% and about 32%.

**Concrete action for us**
- Thread 2 (dating) and "Cleaner fire labels": our GK2A pipeline (§2b) is the Jethva approach generalised:
  - every 30 minutes, 24 h a day;
  - a per-pixel temporal background instead of the 09:00-11:00 normalisation, because forest fires are already burning by 09:00 (§2c), so Jethva's normalisation would erase them;
  - a MAD-scaled threshold.

  Keep the per-pixel temporal background.
- Thread 1 (prediction): the NW India shift shows that burning hours change with policy. Refit our curve every season (action 3) rather than freezing it.
- Thread 5 (alerts): Aqua now passes Ratapani at about 15:20 IST (FSI data, round 7) and should approach about 16:00 by 2027. [inference] FSI's Aqua alerts are becoming a free mid-afternoon view.

### 3b. Roberts, Wooster, Xu, Freeborn et al. 2015, "LSA SAF Meteosat FRP products – Part 2: Evaluation and demonstration for use in the Copernicus Atmosphere Monitoring Service (CAMS)", ACP 15:13241-13267. https://acp.copernicus.org/articles/15/13241/2015/ **PARTIAL** (abstract, §3.1-3.2 in full, Tables 1-2 and Fig. 4-5 captions; CAMS assimilation sections skimmed)

**What it shows**
- FRP-PIXEL against MODIS, per fire pixel, MODIS restricted to ±30° scan.

| Region | Omission | Commission | Per-fire FRP slope | Area-based FRP slope |
|---|---|---|---|---|
| N Africa | 65% | 9% | 0.96 | 0.65 |
| S Africa | 77% | 13% | 0.97 | 0.53 |
| S America (mean VZA 59°) | 91% | 39% | 0.97 | 0.22 |
| Europe (mean VZA 54°) | 97% | 30% | 0.88 | 0.11 |

- **Four SEVIRI products, S Africa, Aug 2014 (Table 2):**

| Product | Omission | Commission | Pixels detected (FRP-PIXEL = 33,414) |
|---|---|---|---|
| FRP-PIXEL | 77% | 13% | 33,414 |
| WFABBA | 82-88% | 4-7% | — |
| FDeM | 92% | 5% | — |
| **FIR** | **95%** | **6%** | **7,151** |

  FIR matched only 5% of MODIS fire pixels, against 23% for FRP-PIXEL.
- FRP-PIXEL can detect down to about 20 MW at the sub-satellite point. Counts are under-estimated below about 50 MW. Applying the MODIS algorithm to SEVIRI would give a minimum of 70-80 MW.

**Concrete action for us**
- Thread 2: this explains our FIR result (§2a). FIR is the worst SEVIRI product, and Ratapani is at VZA 45-49°.
- **Register for LSA SAF and pull FRP-PIXEL (not FIR) for Jan-Jun 2017-2026 over 21-25 N, 75-81 E** (action 2). Expect about 4-5 times the FIR detections. That is still only the >30-50 MW fires: Ratapani has 5.8% of 3-4 km cell-passes ≥30 MW, 2.2% ≥50 MW and 0.5% ≥100 MW (S-NPP + NOAA-20, 2013-2024).
- Use the Andela/Roberts Gaussian (peak, σ) fitted to central-India FRP-PIXEL as a second check on §2c.

### 3c. Wang, Tian & Shi 2025, "Estimation of biomass burning emissions in South and Southeast Asia based on FY-4A satellite observations", Atmosphere 16:582. https://doi.org/10.3390/atmos16050582 **PARTIAL** (methods §2, the India results paragraph, §4.3 comparison; via pdftotext)

**What it shows**
- FY-4A AGRI FHS fire list (2 km, every 15 minutes, NSMC portal, 2020-2022). Fires are clustered into 5 km cells, and FRP is integrated with an exponential ramp before the first and after the last detection (β 0.5, γ 0.01).
- South Asia subcontinent C emissions: FY-4A 497.6 Tg over 3 years, against GFED 280.1, GFAS 248.6, FEER 585.5 and FY-3D 591.9.
- Forest and woodland make up over 85% of emissions. In India, fires concentrated in central India in 2020.
- No diurnal-curve numbers and no per-fire validation against VIIRS.

**Concrete action for us:** none directly. [inference] The ramp and decay integration is a template for turning sparse detections into daily FRE if we ever want fuel consumption (thread 3). FY-4 access needs NSMC registration and was unreachable from here.

### 3d. CAMS "GOES and Himawari FRP-PIXEL Product User Manual" (KCL/IPMA). https://wiki.earthdata.nasa.gov/download/attachments/32079892/CAMS_FRP_GOES_and_HIMAWARI_PUM.pdf **PARTIAL** (product contents and algorithm sections)

**What it shows**
- Himawari FRP-PIXEL uses the same FTA algorithm as SEVIRI.
- 2 × 2 km pixels at the sub-satellite point, every 10 minutes, HDF5 List and Quality files.
- Per-pixel confidence 0-1. The quality file says why a pixel has no fire (cloud, sun glint, not processed).
- Himawari full disk is 5,500 × 5,500 pixels.

**Concrete action for us:** none. Himawari's VZA at Ratapani is 73.6°. If someone does register for P-Tree WLF, check first whether Ratapani lies inside the processed disk.

### 3e. JAXA P-Tree user guide, Wild Fire product. https://www.eorc.jaxa.jp/ptree/userguide.html **PARTIAL** (WebFetch summary)

**What it shows:** WLF L2 is full disk at 2 km, every 10 minutes, CSV, using the Kurihara et al. 2020 algorithm. It needs a P-Tree account; FTP access was refused from here.

**Concrete action for us:** low priority (geometry).

### 3f. Singh, C.P. (SAC) 2017, "Hyper-temporal active forest fire detection using INSAT-3D/3DR over India", ACRS 2017. https://a-a-r-s.org/proceeding/ACRS2017/Missing_Proceedings/1517.pdf **ABSTRACT ONLY** (HTTP 403 to curl and WebFetch; content from search snippets)

**What it shows:** a multi-channel contextual algorithm on 15-minute INSAT-3D/3DR MIR, validated against MODIS for Uttarakhand (Apr-May 2016), Mount Abu (Apr 2017) and Katra (May 2017) with an "index of agreement". No diurnal numbers were visible. The follow-up, Singh et al. 2025 on INSAT-3DS (POD 45.31% against high-confidence MODIS), is already in round 7 as ABSTRACT ONLY.

**Concrete action for us:** thread 5. INSAT-3DS L1B is keyless on MOSDAC Live for the latest few weeks only. **Run a cron job from 1 Feb 2027 that pulls IMG_MIR and IMG_TIR1 for the AOI box every 30 minutes** (GetMap PNG with a fixed colour-scale range, or GetFeatureInfo per pixel), and apply the same temporal-background detector. That gives a second geostationary view at the best available geometry (VZA 27°).

### 3g. Xu, Wooster, Kaneko et al. 2017, "Major advances in geostationary FRP retrieval over Asia and Australia stemming from use of Himawari-8 AHI", RSE 193:138-149. **ABSTRACT ONLY** (no open copy; the GOFC 2017 slides returned 503 and a TLS error)

**What it shows:** AHI detects many more fires than MTSAT or FY-2. FRP agrees strongly with MODIS. AHI undercounts fires with FRP above 40 MW because of its pixel area. Omission was about 66-70% and commission 6-8% against MODIS (slide snippets).

**Concrete action for us:** none (Ratapani is at the limb).

### 3h. Other sources checked

- **LSA SAF data-service Readme** (open, read in full). The archive is restricted to registered users. Access is through wget with `--user/--password`, WebDAV, or THREDDS for NetCDF only (FRP-PIXEL is HDF5, so THREDDS does not apply). **FULL**
- **FY-3D active fire slides** (CMA, AOMSUC-12, 2022): a polar product and not relevant to timing. **PARTIAL**
- **Vadrevu & Eaturu 2024** (VIIRS night fires): South Asia's night share is 28.25%. India's trend is positive but not significant. **ABSTRACT ONLY** (search snippet)
- **MOSDAC Live front-end JavaScript** (read to find the endpoints): this is a data-access source, not a paper. Endpoints are listed in §1.
- I found no paper giving an hourly diurnal cycle for **forest** fires anywhere in India. §2c is, as far as I can tell, the first such curve for central India [inference].

---

## 4. Ranked action list

Gain and effort are my estimates [inference] unless marked as measured.

| # | Action | Thread | Inputs and settings | Expected gain | Effort |
|---|---|---|---|---|---|
| 1 | **Replace the diurnal prior in the dating and alert code with the measured central-MP curve:** Gaussian peak 12:15-13:15 IST, σ about 2.5 h, plus a night floor of about 15-35% of peak. Use the 2023 Ratapani AOI fit (peak 11:36, σ 2.25 h) as the local variant | 2, 5, "Cleaner fire labels" | §2c tables; `composite_rad30_*.csv` | Correct timing logic: the 13:30 pass is at or after the peak, so "fire started that morning" is the default reading of a day detection | 1 h |
| 2 | **Register for LSA SAF (free) and pull MSG-IODC FRP-PIXEL ListProducts for Jan-Jun 2017-2026, clipped to 21-25 N, 75-81 E** (about 92 KB per slot × 96 per day × 180 days × 10 years ≈ 16 GB in total, about 2 MB per day after clipping). Fit the diurnal curve with FRP weighting; compare with §2c | 2, 1 | FRP-PIXEL HDF5 (needs h5py, or the `h5c.py` ctypes reader); confidence ≥0.5 | A 10-year, FRP-calibrated curve for large fires, and dates for the top ~5% of fires | 1 day plus a registration form |
| 3 | **Extend the keyless GK2A pipeline to all of Feb-May 2023-2026** (about 1,700 slots per month at 30 minutes; about 2 GB of transient download per day; minutes of processing) and **refit the curve per month and per year**. Add a per-beat curve for the 10 busiest beats | 1, 2, 5 | `gk2a_pull.py` + `gk2a_v2.py` + `composite_rad30.py`; drop the 16:00-18:59 and 20:00 IST slots | Seasonal shift in ignition hour (Feb managed burns vs Apr wildfire); tests the round-7 claim that winter fires are lit late morning | 0.5-1 day |
| 4 | **Revise the "missed by both passes" planning figure from 30-60% to about 20-45%**, and attach the curve to the toy model | "Cleaner fire labels" | Round-7 `sim.py` with μ = 12.3 h, σ = 2.5 h | More honest recall ceiling | 1 h |
| 5 | **Live 2027 capture of INSAT-3DS MIR and TIR1 from MOSDAC Live (keyless, rolling ~6 weeks)** for the AOI every 30 minutes from 1 Feb 2027, and also GK2A from AWS | 5, 2 | Endpoints in §1; send the Referer header; store PNG or per-pixel counts | A second geostationary view at VZA 27°, with no account needed | 0.5 day of setup |
| 6 | Use GK2A night detections (POD 45-62% for 30-100 MW clusters at night) as an **early "big fire still burning at 21:00-23:00" flag**, 2-4 h before the 00:40/01:30 passes | 5 | Same detector run in near real time on the AWS feed (latency is minutes) | Earlier night alerts for the few large fires (0-3 per month in the AOI) | 0.5 day |
| 7 | Use EUMETView FIR only as a free live layer for very large fires (>100 MW) | 5 | WMS poll every 15 minutes | Marginal | 1 h |
| 8 | Register on MOSDAC and request the INSAT-3D/3DR FIR archive for Mar-Apr 2017-2023 (only if action 2 fails) | 2 | — | Probably similar to FRP-PIXEL; INSAT has better geometry | Slow |

Not worth pursuing for Ratapani: Himawari (VZA 74°), MTG (beyond the limb), EUMETView ir039/ir108 imagery (not radiometric), FIRMS geostationary download (does not exist).

## Reading status

- **FULL 2:** Jethva 2026 (Remote Sens.); LSA SAF data-service Readme.
- **PARTIAL 5:** Roberts et al. 2015 ACP Part 2; Wang et al. 2025 Atmosphere (FY-4A); CAMS GOES/Himawari PUM; JAXA P-Tree user guide; FY-3D CMA slides.
- **ABSTRACT ONLY 3:** Singh 2017 ACRS (403); Xu et al. 2017 RSE; Vadrevu & Eaturu 2024.
- **Data analyses: 6.**
  - EUMETView FIR sweeps for 2022 and 2024 (2,208 slots);
  - GK2A detection over 2023 and 2024 (1,644 slots, 2 bands);
  - GK2A stacked radiance curves (28,046 fire pixel-days);
  - S-NPP / NOAA-20 same-day pairs (355 day-pairs);
  - Aqua drift ratios;
  - FRP class shares for the AOI.
- **Access tests: 14 endpoints.** Working without login: EUMETView WMS, LSA SAF listing, EUMETSAT Data Store search, GK2A AWS, Himawari AWS listing, MOSDAC Live INSAT-3DS L1B and the FIRMS country archive. Login, blocked or not available: LSA SAF files (401), EUMETSAT download (404 without token), the FIRMS geostationary API (absent), P-Tree FTP (reset), NSMC (reset), MOSDAC archive (older files gone from the live store) and the MOSDAC fire JSON (empty).
