# OpenWolf

@.wolf/OPENWOLF.md

This project uses OpenWolf for context management. Read and follow .wolf/OPENWOLF.md every session. Check .wolf/cerebrum.md before generating code. Check .wolf/anatomy.md before reading files.


# FIRE Project (JwalaNetra / VanAagni)

## Project Overview

AI-driven forest fire Early Warning System for **Madhya Pradesh state-wide** (87 forest divisions, 8,973 beats, ~94,000 sq km of forested area). Originally piloted in Guna Division, now scaled to all of MP. Combines satellite remote sensing (HLS, FIRMS VIIRS+MODIS), gradient boosting (LightGBM with Hawkes self-excitation), burnt-area fusion (MCD64A1 + FireCCI51 + S2 dNBR via Andela 2019 flood-fill), and physics-based fire weather indices.

**AOI**: Madhya Pradesh state (lat 21.0-27.0N, lon 74.0-83.0E)
**Pilot focus**: Guna Division (lat 23.80-24.95N, lon 76.45-77.85E) — now expanded statewide
**Forest Type**: Dry deciduous (teak, tendu, mahua, bamboo)
**Fire Season**: February-May (peak March-April)
**Production model**: v17_ba_pu (LightGBM, 111 features) at R@top-5%=47.41% (BA-tiered) / 22.7% (DBSCAN-strict)

## Production Status (2026-04-19, Pivot A v2 sprint COMPLETE — v17.5 hurdle blend SHIPPED)

**Sprint complete + production switched.** `docs/audits/pivot_a_v2_finding.md`.

| Track | Result | Status |
|---|---|---|
| **T1 Hurdle Two-Stage** | +1.77pp low-Hawkes (5.88→7.65%), +0.89pp overall, +1.90pp cold-start, Pareto-better on every metric | **SHIPPED 2026-04-19**. `daily_fire_alert.py` Step 4.5 calls `predict_ignition_v17.py --use-hurdle-blend` by default. |
| **T2 Dynamic World LULC** | FAIL: model ignored DW features (1 of 30 in top-30 by gain), BA-tiered regressed -8.5pp | PARK. DW didn't help. |
| **T3 Combined v18+Hurdle** | FAIL strict: blend_v18_a low-Hawkes 7.06% < 10% target. ALSO worse than T1's blend_v17_a (7.65%). | PARK. |

**Final ship decision:** **v17.5 = v17 + Hurdle Stage A blend (geo_w0.7) is now production default.**
Daily pipeline outputs ~140 CRITICAL / ~720 ALERT / ~1770 WATCH alerts (vs 213/638/1277 raw v17).
Per-alert JSON has new `stage_a_risk` field; payload metadata has `hurdle_blend` block.

**Empirical takeaway:** Pivot A v2 adds Dynamic World 10m monthly LULC
(both bare/crops/trees and 4-week deltas) to the list of satellite
modalities that fail at 2km cell aggregation. The signal-of-interest
(50-200 m² farmer clearings) is sub-cell at our resolution. Same scale
problem that killed S2 dNBR, S1 SAR amplitude, Prithvi-EO-2.0, CLIP,
LLaVA, and temporal NDVI/BSI deltas. **v17 + diagnostic stack is the
satellite-data ceiling.**

---

## Production Status (2026-04-17)

**v17 is at the information-theoretic ceiling** for new-outbreak prediction with current satellite + weather data. 8 improvement experiments in 2026-04-16/17 sessions all failed:

| Experiment | Result | Commit |
|------------|--------|--------|
| VLM precursor (LLaVA-7b) on S2 chips | MW p=0.74 (no signal) | `b8f7f78` |
| CLIP-ViT-L/14 embeddings + classifier | ROC=0.562, perm p=0.095 | `bdd98bb` |
| Temporal NDVI/BSI delta features | 5-fold ROC=0.539 | `18f26e8` |
| Hybrid Bayesian ranking (adaptive λ) | All variants WORSE than statewide | `d134e18` |
| Origination Model B + soft-ensemble | Tradeoff only (more low-Hawkes ≠ more total catches) | `d134e18` |
| Calendar features (v18) | DBSCAN +1.8pp, BA-tiered −11.9pp | `47aef8a` |
| GDELT article geocoding | 0% yield (68% dead links, 88% non-fire articles) | `47aef8a` |
| Deep origination features (VPD anomaly etc.) | 7/8 features scored zero gain | `d134e18` |

**Key structural finding**: v17 excels at fire CONTAGION (Hawkes-driven, 25.5% R@5% in high-Hawkes regime) but is near-random on NEW OUTBREAKS (5.9% R@5% in low-Hawkes cells, where 77% of fires actually start). The visual-precursor hypothesis (anthropogenic ground-clearing visible in S2 imagery before ignition) was comprehensively falsified across three independent feature extraction methods.

**Conclusion**: Further improvement requires data outside the current feature set — village-level human activity logs, NTFP collection schedules, patrol reports, or real-time mobile phone density near forest fringes.

## Unified Project Structure

```
FIRE/
├── config.yaml                  # Master configuration (all params)
├── CLAUDE.md                    # This file
├── README.md                    # Project overview
├── Makefile                     # make train, make dashboard, make pipeline
├── Dockerfile + docker-compose  # Container deployment
├── requirements.txt             # Python dependencies
├── .env.example                 # Environment variables template
│
├── src/                         # Core source code (93 files, 13 modules)
│   ├── analysis/                # Fire dynamics, AI services, smoke modeling (25 files)
│   ├── api/                     # REST API endpoints (2 files)
│   ├── dashboard/               # Dashboard app logic (1 file)
│   ├── data/                    # Data ingestion: EarthAccess, FIRMS, GEE, weather (8 files)
│   ├── inference/               # Model inference, detection, alerts, quantization (6 files)
│   ├── model/                   # DL architectures: Prithvi, VanAagni, ROS-UNet (14 files)
│   ├── monitoring/              # Tracking, notifications (3 files)
│   ├── pipeline/                # Daily operational pipeline (2 files)
│   ├── postprocess/             # SAM-based mask refinement (2 files)
│   ├── train/                   # Training: VanAagni, ROS-UNet, LightGBM (12 files)
│   ├── utils/                   # Utilities (2 files)
│   └── viz/                     # Visualization components (3 files)
│
├── scripts/                     # 168 operational/utility scripts
│   ├── download_*.py            # Data download (HLS, FIRMS, DEM, phenology)
│   ├── compute_*.py             # Feature engineering (dNBR, RBR, FWI)
│   ├── build_*.py               # Dataset construction
│   ├── train_*.py               # Model training scripts
│   ├── run_pipeline.py          # Main pipeline orchestrator
│   ├── nrt_alert_pipeline.py    # Near-real-time alerting
│   ├── ews_scheduler.py         # Daily cron scheduler
│   └── exhaustive_*_validation  # Validation suites
│
├── dashboard/                   # Web dashboards
│   ├── app.py                   # Streamlit main dashboard (6 tabs)
│   ├── v2/                      # Dashboard v2 redesign
│   ├── command_horizon.html     # Command horizon view
│   └── portal/                  # Jvala ignition portal (standalone)
│       ├── jvala_dashboard.html # HTML dashboard
│       ├── dashboard_server.py  # Python backend (883 lines)
│       └── config/              # Portal configuration
│
├── models/                      # All trained models
│   ├── ignition/                # LightGBM ignition models (from portal_design)
│   │   ├── ignition2_lgbm.pkl
│   │   ├── ignition_lgbm_NEW_No_.pkl
│   │   └── intensity_lgbm_NEW_No_.pkl
│   ├── vanaagni/                # VanAagni configs + active checkpoints
│   │   └── configs/             # Training configs (binary, severity, original)
│   ├── vanaagni_v1.0/           # Frozen v1.0 release
│   │   ├── vanaagni_fire_detector_v1.0.pth  # 646M param checkpoint
│   │   ├── MODEL_CARD.md        # Performance: P=80.6%, R=69.6%, F1=0.747
│   │   └── test_results.json
│   ├── muhurta/                 # ROS-UNet v1
│   ├── presto/                  # Presto embeddings
│   ├── prithvi_burnscar/        # Burn scar Prithvi model
│   └── sam_vit_h_4b8939.pth     # SAM for post-processing
│
├── data/                        # Working data
│   ├── aoi/                     # 9 GeoJSON boundaries (division, ranges, beats)
│   ├── ground_truth/            # KML fire confirmations
│   ├── labels/                  # Loss labels 2018-2024 (.tif)
│   ├── phenology/               # NDVI time series + Fourier models
│   ├── rasters/                 # DEM, slope, TPI, road distance (30m)
│   ├── state/                   # Cumulative alert rasters
│   └── training/                # Training cache
│
├── data_lake/                   # Large archived data (18 subdirectories)
│   ├── alerts/                  # Alert history (2017-2026)
│   ├── burn_scars/              # Fire links, HLS, Prithvi outputs
│   ├── fire_detections/         # FIRMS MODIS/VIIRS (NRT + historical)
│   ├── fire_labels/ + v2/       # Sentinel-2 tile labels + RBR labels
│   ├── fire_weather/            # FWI daily (2013-2025)
│   ├── land_cover/              # Forest masks (10m, 30m), WorldCover
│   ├── satellite_imagery/       # HLS tiles
│   ├── terrain/                 # Copernicus DEM, slope, aspect
│   ├── training_patches/        # 5 versioned datasets (v1-v5)
│   ├── weather/                 # GFS forecasts
│   └── backbone_cache/          # Pre-computed backbone features
│
├── outputs/                     # All experiment results
│   ├── checkpoints/             # Model checkpoints (detect, vanaagni stages)
│   ├── vanaagni_cls_*/          # 9 classification experiments (v1-v3)
│   ├── dashboard_feed/          # Latest alert GeoJSONs
│   ├── tensorboard/             # Training logs
│   ├── validation_reports/      # System validation CSVs
│   └── guna_pipeline_state.db   # SQLite pipeline state
│
├── paper/                       # Research publication
│   ├── vanaagni_paper.tex/md/pdf
│   ├── VanAagni_Final_Manuscript.docx
│   └── figures/                 # 12 publication figures
│
├── docs/                        # Documentation
│   ├── ARCHITECTURE.md          # System architecture
│   ├── SCRIPTS_INDEX.md         # Categorized script reference
│   ├── FORENSIC_ANALYSIS_20190414.md
│   └── VANAAGNI_SYSTEM_NOTE.md
│
├── tests/                       # Test suite
│   ├── test_api.py
│   ├── test_fwi.py
│   ├── test_model_backbone.py
│   ├── test_presto.py
│   └── test_vanaagni.py
│
├── screenshots/                 # All screenshots (46 PNGs)
├── presentation_screenshots/    # Demo screenshots (13 with captions)
├── notebooks/                   # Jupyter analysis notebooks
├── refs/                        # 12 reference repositories
├── cache/                       # Runtime cache (CatBoost, etc.)
├── logs/                        # Pipeline logs
└── tmp/                         # Temporary files
```

## Model Zoo (current)

| Model | Type | Best Metric | Status |
|-------|------|-------------|--------|
| **v17.5 hurdle blend** (geo_w0.7) | v17 × Stage A geometric blend | DBSCAN R@5% 23.55%, low-Hawkes 7.65%, +1.77pp vs v17 | **PRODUCTION (since 2026-04-19)** |
| v17_ba_pu | LightGBM, 111 feats, BA-tiered PU | R@5%=47.41% (tiered) / 22.7% (DBSCAN) | Stage B (used inside v17.5 blend) |
| v17_hurdle_a | Bernoulli, 107 feats (no Hawkes) | PR=0.024, R@5%=29% solo | Stage A (used inside v17.5 blend) |
| v15 ensemble (v13×v14 geo-mean) | LightGBM ensemble | R@5%=40.45% | Predecessor (archive) |
| v9 Hawkes | LightGBM + Hawkes self-excitation | R@5%=39.4% | First Hawkes breakthrough |
| v8 DBSCAN ignition | LightGBM on DBSCAN-clustered ignitions | R@5%=28.1% | Ignition baseline |
| v6e_live | LightGBM, 92 feats, spread labels | ROC=0.9150 | Spread tracker (not predictor) |
| VanAagni v1.0 | Neural (Prithvi-EO-2.0 600M) | P=80.6%, R=69.6%, F1=0.747 | Frozen release (per-pixel detection) |
| Muhurta ROS-UNet | Rate of Spread | Smooth_l1_loss fixed 2026-03-19 | Active |
| SAM ViT-H | Mask refinement | Post-processing | Active |

**Key model files:**
- `outputs/predictive_fire_risk/predictive_v17_ba_pu/model.txt` — production LightGBM
- `scripts/predict_ignition_v17.py` — daily prediction helper (called by `daily_fire_alert.py`)
- `outputs/dashboard_feed/ignition_risk_v17.json` — latest predictions (2,128 banded alerts)

## v3 Portal — Forest Officer Dashboard (port 8790)

Single-page portal at `dashboard/v3/` for forest officers, built with industry-best UI/UX patterns (UXmatters crisis UX, UXPin dashboard principles, CARTO geo-viz). Launch:

```bash
python dashboard/v3/serve.py
# Open http://localhost:8790/v3/
```

**5 tabs:**
1. **Live Map** — MapLibre dark map with v17 cells (CRITICAL/ALERT/WATCH), confidence ring gauge, layer toggles, click-to-detail flyout with action recommendations (Dispatch/Patrol/Awareness)
2. **Divisions** — 74 division cards with alert counts + Hawkes coverage + confidence badges
3. **Model Card** — honest performance metrics, weakness disclosure (5.9% low-Hawkes recall), trust guidance, feature importance bars
4. **Validation** — rolling field validation log from `data_lake/alerts/v17_validation_rolling.parquet`
5. **VIIRS Fires** — date-range picker for historical FIRMS detections (1.35M rows, 2014-2026), spatially clipped to forest beats (1,199 raw → 297 forest fires on 2026-04-07)

**Forest beat clipping**: Uses `data/aoi/mp_beats_wgs84.geojson` (8,973 beats from `Mp_Beat_Merge.shp` reprojected to WGS84). Spatial join via `gpd.sjoin_nearest` with 0.02° tolerance (~2km) to handle polygon boundary precision. ~75% of raw VIIRS detections clipped out as non-forest.

**Backend endpoints** (`dashboard/v3/serve.py`):
- `/api/ignition-v17[?date=YYYY-MM-DD]` — v17 banded alerts
- `/api/division-overview` — alerts aggregated by division (joins cells.csv for mapping)
- `/api/model-transparency` — static metrics + trust guidance
- `/api/validation-log` — rolling field validation
- `/api/viirs-fires?from=YYYY-MM-DD&to=YYYY-MM-DD` — forest-clipped VIIRS detections
- `/api/beats-boundary` — beat polygon GeoJSON for map overlay

## Known Issues + Resolved Items

### FIXED 2026-03-19
- ROS U-Net loss incoherence (dimensional) — `src/train/train_ros_unet.py` now uses `F.smooth_l1_loss`
- GFS precipitation unit bug — `src/data/weather_ingest.py` now explicitly checks "m" vs "mm" vs "kg m**-2"

### CONFIRMED DEAD ENDS (do not re-attempt — see commit history for evidence)
- **Dynamic World monthly LULC at 2km cells** (Pivot A v2 T2, 2026-04-19) — added bare/crops/trees mean+max+4wk deltas. v18 model ignored them (1 of 30 in top-30 by gain), BA-tiered regressed -8.5pp. Same scale problem: 50-200 m² farmer clearings invisible when averaged over 4 km² cell. See `feedback_pivot_a_v2_dw_no_signal.md`.
- **VLM zero-shot on S2 chips** — LLaVA-7b emits templated responses, image-agnostic at 30m resolution. See `docs/audits/vlm_pilot_finding.md` and `feedback_vlm_llava_7b_indiscriminate.md`
- **CLIP embeddings + classifier** — 5-fold ROC=0.562, perm p=0.095. See `docs/audits/clip_pilot_finding.md`
- **Temporal NDVI/BSI deltas** — 5-fold ROC=0.539. See `docs/audits/temporal_delta_finding.md`
- **Sentinel-1 SAR amplitude (PS-1)** — both VV+ASC (21% cov) and VH+both-orbits (100% cov) gave ρ≈0.01, p>0.3. Anthropogenic <100m² clearings invisible at 2km cell. See `feedback_ps1_sar_amplitude_dead.md`
- **GDELT article geocoding** — district-centroid only, 0% village-level yield from news article NER
- **Hybrid Bayesian ranking** — All λ-blend variants DECREASE aggregate R@5% vs statewide
- **Pre-2017 NISAR** — sensor launched Feb 2026, no usable historical data until ~2027

### REMAINING (need attention)
- **HIGH**: Wind direction 270° in `src/data/weather_ingest.py` — formula `(270 - arctan2(v,u)) % 360` is correct meteorologically but should be config-parameterizable
- **HIGH**: LightGBM alert filter in `scripts/train_alert_filter.py` (965 lines) has never been executed. Needs ground truth + run
- **MEDIUM**: 183 training samples may overlap train/val in `data_lake/training_patches_v5/` — needs dedup audit
- **LOW**: Beat boundary layer not yet added to v3 portal Tab 1 (Live Map). Pattern from VIIRS tab can be copied

## Development Conventions

- **Config**: ALL parameters in `config.yaml` - zero hardcoded values
- **Scripts**: Named descriptively with verb prefix (download_, compute_, build_, train_, run_)
- **Models**: Saved to `models/` with metadata JSON alongside .pkl/.pth
- **Screenshots**: NEVER at project root - always in `screenshots/` or `presentation_screenshots/`
- **Data**: Raw satellite data in `data_lake/`, processed/working data in `data/`
- **Outputs**: Each experiment gets its own `outputs/vanaagni_cls_*` folder
- **Testing**: pytest with tests in `tests/`
- **Linting**: ruff + pyright (see pyrightconfig.json)

## Key Commands

```bash
# Daily operations
python scripts/daily_fire_alert.py              # Full daily pipeline (FWI + FIRMS + v17 + alerts)
python scripts/predict_ignition_v17.py          # v17 prediction only (production model)
python scripts/validate_v17_daily.py            # Field validation backtest

# Model training (only if re-training needed; v17 is at ceiling)
python scripts/train_v17_ba_pu.py               # Retrain v17 with BA-tiered PU labels
python scripts/audit_v17_per_week.py            # Brutal per-cell-date audit
python scripts/audit_low_hawkes_subset.py       # Low-Hawkes ablation diagnostic

# Portals
python dashboard/v3/serve.py                    # v3 unified portal (RECOMMENDED) → http://localhost:8790/v3/
python dashboard/v2/serve_real_data.py          # v2 Command Horizon (legacy)
python dashboard/portal/dashboard_server.py     # Jvala beat-level portal (port 8787)
streamlit run dashboard/app.py                  # Original Streamlit dashboard

# Make targets (legacy)
make setup | train-lgbm | dashboard | pipeline | test | lint | clean
```

## Tech Stack

- **Python 3.12**, PyTorch 2.4.1 + torch-directml, LightGBM 4.6, scikit-learn 1.8
- **Prithvi-EO-2.0-300M/600M** (IBM/NASA foundation model — frozen, used for embeddings only)
- **Google Earth Engine** (satellite data pipeline; van-suraksha-alert project)
- **MapLibre GL JS 4.7** + **deck.gl** (v3 portal mapping)
- **GeoPandas** + **Shapely** (forest beat spatial joins)
- **AMD RX 9060 XT** (DirectML training — custom Conv3d shim for Prithvi; works on torch 2.4 only, broken on 2.11)
- **Ollama** local VLM (LLaVA-7b confirmed image-agnostic on satellite chips)
- **FIRMS** (NASA NRT fire detections — VIIRS + MODIS, 1.35M historical rows)
- **Sentinel-2 SR Harmonized** via GEE getDownloadURL (NPY format) for chip extraction
- **MCD64A1 + FireCCI51** burnt-area products (Andela 2019 flood-fill clustering for label augmentation)

## graphify

This project has a graphify knowledge graph at graphify-out/.

Rules:
- Before answering architecture or codebase questions, read graphify-out/GRAPH_REPORT.md for god nodes and community structure
- If graphify-out/wiki/index.md exists, navigate it instead of reading raw files
- After modifying code files in this session, run `python3 -c "from graphify.watch import _rebuild_code; from pathlib import Path; _rebuild_code(Path('.'))"` to keep the graph current
