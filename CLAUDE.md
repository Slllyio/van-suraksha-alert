# FIRE Project (JwalaNetra / VanAagni)

## Project Overview

AI-driven forest fire Early Warning System for **Guna Division, Madhya Pradesh** (~2,144 sq km, 8 Forest Ranges, 139 Beats). Combines satellite remote sensing (HLS, FIRMS, Dynamic World), deep learning (Prithvi-EO-2.0 600M), gradient boosting (LightGBM), and physics-based fire weather indices to detect, classify, and predict forest fires.

**AOI**: Guna Division, MP (lat 23.80-24.95N, lon 76.45-77.85E)
**Forest Type**: Dry deciduous (teak, tendu, mahua, bamboo)
**Fire Season**: February-May (peak March-April)

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

## Model Zoo

| Model | Type | Best Metric | Status |
|-------|------|-------------|--------|
| LightGBM v3_expanded | Classification | AUC 0.824, F1 0.805 | CURRENT BEST |
| VanAagni v1.0 | Neural (Prithvi-EO-2.0) | P=80.6%, R=69.6%, F1=0.747 | Frozen release |
| LightGBM Ignition | Ignition probability | AUC 0.9997 (2023 holdout) | Production |
| LightGBM Intensity | Fire intensity | In portal models | Production |
| Muhurta ROS-UNet | Rate of Spread | Loss function needs fix | BROKEN |
| SAM ViT-H | Mask refinement | Post-processing | Active |

## Known Issues (from 10-agent audit, 2026-03-14) — UPDATED 2026-03-19

### FIXED (2026-03-19):
1. ~~CRITICAL: ROS U-Net loss incoherent~~ **FIXED** — `src/train/train_ros_unet.py`
   Changed from `F.mse_loss(ros_field * 60.0, target_growth * 100.0)` (dimensionally incoherent)
   to `F.smooth_l1_loss(ros_field, ros_target)` with physics-reasonable 5 m/min target.
   Also replaced `nn.BCELoss()` with `nn.SmoothL1Loss()` (ROS is continuous, not binary).
2. ~~HIGH: GFS precipitation unit bug~~ **FIXED** — `src/data/weather_ingest.py`
   Old code: `prec.attrs.get("units","").startswith("m")` matched "mm" incorrectly.
   New code: explicit unit checking for "m" vs "mm" vs "kg m**-2".

### FALSE ALARMS (confirmed NOT bugs):
3. ~~CRITICAL: Paper figures contain fabricated confusion matrix~~ **FALSE ALARM**
   Code in `paper/generate_vanaagni_figures.py` correctly requires real `test_results.json`
   with `confusion_matrix` key from actual model inference. Skips if unavailable.
4. ~~HIGH: Van Wagner FMC=100% should be 60-85%~~ **FALSE ALARM**
   Values in `scripts/compute_fwi.py` (FFMC0=85.0, DMC0=6.0, DC0=15.0) are standard
   Van Wagner 1987 startup codes, NOT fuel moisture content percentages.

### REMAINING (need attention):
5. **HIGH**: Wind direction 270deg in `src/data/weather_ingest.py` — actually correct
   meteorological formula `(270 - arctan2(v,u)) % 360` but should be parameterizable in config.
6. **HIGH**: LightGBM alert filter in `scripts/train_alert_filter.py` — code is complete
   (965 lines) but has never been executed. Needs: ground truth data + run the script.
7. **MEDIUM**: 183 training samples may overlap train/val — needs dedup audit of
   `data_lake/training_patches_v5/` manifest against spatial block split.

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
make setup          # Create venv + install deps
make train-lgbm     # Train LightGBM classifier
make train-vanaagni # Train VanAagni neural model
make dashboard      # Launch Streamlit dashboard (port 8501)
make pipeline       # Run NRT alert pipeline (single pass)
make scheduler      # Start daily EWS scheduler daemon
make test           # Run pytest suite
make lint           # Run ruff + pyright
make clean          # Remove tmp/ cache/ __pycache__/
```

## Tech Stack

- **Python 3.10+**, PyTorch, LightGBM, scikit-learn
- **Prithvi-EO-2.0-600M-TL** (IBM/NASA foundation model via terratorch)
- **Google Earth Engine** (satellite data pipeline)
- **Streamlit** (dashboard)
- **AMD RX 9060 XT** (DirectML training - custom Conv3d shim for Prithvi)
- **Google Gemini 2.0 Flash** (VLM features)
- **FIRMS** (NASA fire detections - VIIRS + MODIS)
