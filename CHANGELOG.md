# Changelog - FIRE (JwalaNetra / VanAagni)

All notable changes to this project are documented here.

## [Unreleased]
- 10-agent forensic audit identified CRITICAL issues (ROS loss, duplicate training data, fabricated figures)
- Dashboard redesign v2 (dark theme, 6 tabs)

## [1.0.0] - 2026-03-05 - VanAagni Fire Detector v1.0
### Added
- Prithvi-EO-2.0-600M-TL backbone + UNet decoder + FiLM weather conditioning
- 646M params (94M trainable), trained on AMD RX 9060 XT (DirectML)
- Fire Precision 80.6%, Fire Recall 69.6%, Fire F1 0.747

## [0.9.0] - 2026-02 - LightGBM v3 Expanded (BEST classification)
### Added
- v3_expanded model: AUC-ROC 0.824, AUC-PR 0.859, F1 0.805
- 180 features including dNBR expanded features
- Prithvi-EO-2.0 backbone upgrade from 100M to 600M

## [0.8.0] - 2026-01 - Scoring Engine + Dashboard
### Added
- Streamlit dashboard with 6 tabs (Live Alert, Fire History, Burn Scars, FWI, Weather, Land Cover)
- NRT alert pipeline from FIRMS VIIRS + MODIS
- Van Wagner FWI implementation
- Carbon audit generation

## [0.7.0] - 2025-12 - LightGBM Classification Series
### Added
- lgbm_v1 through v3_tuned: 8 iterative model experiments
- Feature engineering: 136-387 features tested
- Spatial block cross-validation

## [0.6.0] - 2025-11 - Data Lake + GEE Pipeline
### Added
- 18-directory data lake structure
- GEE pipeline for HLS, FIRMS, DEM, WorldCover, Dynamic World
- 12,444 training samples (2013-2025)
