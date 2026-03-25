# FIRE Project Scripts Index

## 166 Scripts Organization

### Data Download (12 scripts)
Scripts for fetching raw data from GEE, FIRMS, and other sources:

| Script | Purpose |
|--------|---------|
| `download_hls_imagery.py` | Fetch Sentinel-2 HLS data from GEE for date range |
| `download_firms_hotspots.py` | Download MODIS/VIIRS active fire detections |
| `download_srtm_dem.py` | Fetch elevation data for study region |
| `download_ancillary_layers.py` | Download forest cover, population, roads |
| `download_era5_weather.py` | Download ERA5 climate reanalysis (temp, precip, wind) |
| `download_landcover.py` | Fetch Copernicus LULC product |
| `download_burned_area.py` | Download ESA CCI Burned Area for validation |
| `download_gaul_boundaries.py` | Administrative boundaries |
| `download_viirs_nightlight.py` | NOAA VIIRS nighttime lights |
| `download_gedi_biomass.py` | GEDI spaceborne lidar estimates |
| `download_monthly_composites.py` | Create monthly mosaics for analysis |
| `download_thermal_ir.py` | Sentinel-3 SLSTR thermal bands |

### Feature Engineering (28 scripts)
Compute derived features from raw raster data:

| Script | Purpose |
|--------|---------|
| `compute_spectral_indices.py` | NDVI, NBR, NDMI, EVI, BSI calculations |
| `compute_vegetation_stress.py` | dNBR anomalies, phenology breaks |
| `compute_texture_haralick.py` | Haralick features (contrast, dissimilarity, homogeneity) |
| `compute_texture_gabor.py` | Gabor filter responses for edge patterns |
| `compute_local_variance.py` | Entropy and local variance patches |
| `compute_topographic_features.py` | Slope, aspect, terrain ruggedness index |
| `compute_wind_exposure.py` | Topographic wind routing indices |
| `compute_fuel_load.py` | Biomass and forest structure estimates |
| `compute_drought_index.py` | Standardized Precipitation Index (SPI) |
| `compute_proximity_roads.py` | Distance to nearest road, settlements |
| `compute_proximity_water.py` | Distance to water bodies, reservoirs |
| `compute_temporal_baseline.py` | 10-year NDVI climatology |
| `compute_anomaly_zscore.py` | Z-score normalized anomalies |
| `compute_seasonal_phenology.py` | Peak greenness, growing season length |
| `build_training_patches.py` | Combine features into patch-level datasets |
| `build_validation_patches.py` | Create independent test sets |
| `build_temporal_sequences.py` | Multi-temporal feature stacks for RNNs |
| `extract_patch_statistics.py` | Mean, std, min, max per patch |
| `extract_gee_timeseries.py` | Export 366-day time series per location |
| `extract_hotspot_context.py` | Extract 1km neighborhood features for FIRMS points |
| `extract_weather_context.py` | Interpolate ERA5 to fire locations |
| `extract_dem_hillshade.py` | Hillshade and other terrain visualizations |
| `normalize_feature_scaling.py` | Standardize to mean=0, std=1 |
| `impute_missing_values.py` | Handle clouds, gaps via interpolation |
| `balance_training_classes.py` | SMOTE oversampling and undersampling |
| `augment_training_data.py` | Rotation, flip, noise injection |
| `create_feature_catalog.md` | Metadata for all 128+ features |
| `validate_feature_schema.py` | Check data types, ranges, completeness |

### Training (16 scripts)
Model training and hyperparameter tuning:

| Script | Purpose |
|--------|---------|
| `launch_training.py` | Main entry point for training pipeline |
| `train_lightgbm_v1.py` | Train LightGBM baseline model |
| `train_lightgbm_v2.py` | LightGBM with texture + temporal |
| `train_lightgbm_v3.py` | LightGBM production with balancing |
| `train_neural_vanaagni.py` | Train Prithvi-EO-2.0 based CNN |
| `train_unet_ros.py` | Train U-Net for burn scar detection |
| `train_alert_filter.py` | Secondary classifier for false positive filtering |
| `train_ignition_abm.py` | Calibrate ABM transition probabilities |
| `hyperparameter_search_lgb.py` | Bayesian optimization for LightGBM |
| `hyperparameter_search_neural.py` | Grid search for CNN architecture |
| `cross_validation_5fold.py` | 5-fold CV on training set |
| `retrain_on_new_fires.py` | Incremental learning from field-verified events |
| `retrain_alert_filter_monthly.py` | Monthly retraining on false positives |
| `evaluate_model_performance.py` | ROC, PR curves, F1, precision, recall |
| `ensemble_weights_tuning.py` | Optimize weighted averaging of 3 models |
| `export_model_artifacts.py` | Save model weights, scalers, feature lists |

### Inference (18 scripts)
Run trained models on new data:

| Script | Purpose |
|--------|---------|
| `run_pipeline.py` | Full end-to-end inference workflow |
| `nrt_alert_pipeline.py` | 6-hourly NRT alert scoring |
| `inference_lightgbm.py` | Apply LightGBM ensemble |
| `inference_neural.py` | Apply neural network predictions |
| `inference_unet.py` | Apply U-Net segmentation |
| `ensemble_predict.py` | Combine 3 models with learned weights |
| `post_process_predictions.py` | Morphological operations, thresholding |
| `confidence_calibration.py` | Apply Platt scaling to raw scores |
| `uncertainty_quantification.py` | Monte Carlo dropout for confidence intervals |
| `alert_tier_classification.py` | Assign Tier 1/2/3 based on thresholds |
| `filter_false_positives.py` | Apply alert filter model |
| `spatial_clustering.py` | Group nearby alerts into fire events |
| `temporal_persistence.py` | Track alerts across multiple runs |
| `infer_on_new_hls.py` | Score newly downloaded HLS imagery |
| `infer_on_historical.py` | Batch inference on archive data |
| `export_inference_results.py` | Save GeoJSON, GeoTIFF, CSV outputs |
| `generate_inference_report.py` | Summary statistics per run |
| `notify_via_telegram.py` | Send alerts to Telegram channels |

### Dashboard (6 scripts)
Web interface and visualization:

| Script | Purpose |
|--------|---------|
| `dashboard_server.py` | Streamlit app main entry |
| `ews_dashboard.py` | Real-time map and status tab |
| `dashboard_model_comparison.py` | Model ensemble tab |
| `dashboard_feature_analysis.py` | SHAP interpretability |
| `dashboard_temporal_trends.py` | Historical trend plotting |
| `dashboard_historical_events.py` | Calendar and event archive |

### Validation (9 scripts)
Model validation and verification:

| Script | Purpose |
|--------|---------|
| `exhaustive_validation_v1.py` | Full validation report for LightGBM v1 |
| `exhaustive_validation_v2.py` | Full validation report for LightGBM v2 |
| `exhaustive_validation_v3.py` | Full validation report for LightGBM v3 |
| `exhaustive_validation_neural.py` | Full validation for neural model |
| `exhaustive_validation_unet.py` | Full validation for U-Net model |
| `system_validation_report.py` | End-to-end system accuracy |
| `causal_validation_v4.py` | Assess model robustness to feature perturbations |
| `field_verification_protocol.py` | Validation against field teams |
| `benchmark_against_baselines.py` | Compare vs simple thresholding |

### Utilities (20 scripts)
Support and diagnostic tools:

| Script | Purpose |
|--------|---------|
| `check_data_availability.py` | Verify all required input files |
| `check_gee_credentials.py` | Test GEE authentication |
| `check_disk_space.py` | Monitor storage usage |
| `check_model_versions.py` | List installed model weights |
| `diag_missing_values.py` | Report null counts per feature |
| `diag_feature_distributions.py` | Histograms and statistics |
| `diag_data_quality.py` | Outlier detection, anomaly reports |
| `diag_model_inference.py` | Profile model latency per component |
| `analyze_false_positives.py` | Characterize failure modes |
| `analyze_missed_detections.py` | Analyze fires not detected |
| `analyze_feature_importance.py` | SHAP and permutation importance |
| `analyze_alert_distribution.py` | Spatial clustering of alerts |
| `log_parser.py` | Parse pipeline logs for errors |
| `config_validator.py` | Validate config.yaml structure |
| `generate_summary_stats.py` | Monthly/yearly KPI reports |
| `backup_model_weights.py` | Archive models with timestamps |
| `cleanup_cache_files.py` | Remove intermediate files |
| `monitor_system_health.py` | CPU, memory, network diagnostics |
| `visualize_feature_space.py` | t-SNE/UMAP projections |
| `export_for_sharing.py` | Create data packages for collaborators |

### Scheduling (5 scripts)
Automated pipeline orchestration:

| Script | Purpose |
|--------|---------|
| `ews_scheduler.py` | Main scheduler daemon |
| `scheduled_run.py` | Entry point for scheduled execution |
| `register_ews_task.py` | Register scheduler tasks (Windows Task Scheduler / cron) |
| `schedule_training_retrain.py` | Monthly retraining schedule |
| `schedule_data_cleanup.py` | Weekly cache/temp file cleanup |

---

## Execution Flow

```
ews_scheduler.py (daemon)
├── Every 6 hours: nrt_alert_pipeline.py
│   ├── download_firms_hotspots.py
│   ├── ensemble_predict.py
│   ├── alert_tier_classification.py
│   ├── filter_false_positives.py
│   └── notify_via_telegram.py
├── Daily: download_hls_imagery.py → compute_spectral_indices.py
├── Weekly: exhaustive_validation_v3.py → generate_inference_report.py
└── Monthly: retrain_alert_filter_monthly.py → export_model_artifacts.py
```
