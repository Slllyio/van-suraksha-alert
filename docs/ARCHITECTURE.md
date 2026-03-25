# FIRE Project Architecture

## System Overview

The FIRE (Fire Information and Response Engine) system is an end-to-end wildfire detection and early warning pipeline built on Google Earth Engine data. The architecture follows a sequential flow:

**HLS Imagery → Feature Engineering → ML Models → Dashboard → Alerts**

### Key Data Flow

1. **HLS Data Ingestion**: Sentinel-2 HLS imagery is downloaded from GEE and organized into spatial patches
2. **Feature Extraction**: 13 specialized modules compute spectral, textural, and temporal features
3. **Model Ensemble**: Multiple model architectures (LightGBM, neural networks, U-Net) generate predictions
4. **NRT Processing**: FIRMS hotspot data combined with model scores drives real-time alert classification
5. **Dashboard Visualization**: Streamlit interface displays results across 6 integrated tabs
6. **Telegram Dispatch**: Alert notifications are pushed to subscribers via Telegram API

---

## 13 Source Modules and Responsibilities

| Module | Purpose |
|--------|---------|
| **gee_integration** | GEE authentication, image download, preprocessing |
| **patch_generation** | Tile HLS scenes into fixed-size spatial patches |
| **spectral_indices** | NDVI, NBR, dNBR, NDMI, EVI, NDII calculations |
| **texture_features** | Haralick texture, edge detection, local variance |
| **temporal_features** | Phenology, seasonal baseline, z-score anomalies |
| **alert_filter** | ML classifier for true vs false fire alerts |
| **model_ensemble** | Aggregates predictions from LightGBM, neural, U-Net |
| **nrt_pipeline** | Real-time alert scoring and dispatch |
| **firms_integration** | FIRMS hotspot download and geocoding |
| **dem_processing** | Elevation, slope, aspect from SRTM DEM |
| **validation** | Cross-validation, field verification, accuracy metrics |
| **dashboard_core** | Data aggregation for web visualization |
| **utils** | File I/O, logging, configuration management |

---

## Model Zoo

### 1. LightGBM Classification (v1, v2, v3)
- **v1**: Initial baseline (32 features, ~80% accuracy)
- **v2**: Expanded with texture and temporal features (~85% accuracy)
- **v3**: Production model with class balancing and threshold tuning (~87% accuracy)
- Input: 128+ tabular features per patch
- Output: Fire probability [0, 1]

### 2. VanAagni Neural Network
- Architecture: 3-layer CNN encoder + temporal attention
- Backbone: Prithvi-EO-2.0 pre-trained on 100M remote sensing images
- Input: Multi-temporal HLS bands (RGB, NIR, SWIR)
- Output: Fire mask + confidence
- Inference time: ~200ms per patch

### 3. ROS U-Net
- Architecture: U-Net with residual blocks
- Task: Burn scar and fire boundary detection
- Training data: 2000 labeled Sentinel-2 scenes
- Output: Pixel-level fire probability maps
- Post-processing: Connected component analysis for fire extent

### 4. Ignition ABM (Agent-Based Model)
- Simulates fire ignition probability from weather + fuel + topography
- Agent states: Dormant → Active → Burned
- Transition rules: FWI index × vegetation stress × slope
- Provides contextual prior for alert confidence scoring

---

## Dashboard Interface

**Streamlit-based web application with 6 tabs:**

1. **Real-Time Map**: Interactive Folium/Leaflet map with current hotspots and alerts
2. **Model Comparison**: LightGBM vs Neural vs U-Net side-by-side confidence distributions
3. **Feature Analysis**: SHAP values showing top 10 predictive features per alert
4. **Temporal Trends**: Time series of alert count, confidence, false positive rate
5. **NRT Pipeline Status**: Latest FIRMS download timestamp, model inference latency
6. **Historical Events**: Calendar view of past fires with damage severity estimates

---

## NRT (Near Real-Time) Alert Pipeline

**Frequency**: Runs every 6 hours

1. **FIRMS Data Fetch**: Download past 24h MODIS/VIIRS detections
2. **Spatial Matching**: Link hotspots to pre-computed patch features
3. **Ensemble Scoring**: 
   - P_fire = 0.4×LightGBM + 0.3×Neural + 0.3×U-Net
4. **Alert Classification**:
   - Tier 1 (P > 0.85): High confidence, immediate dispatch
   - Tier 2 (0.70 < P ≤ 0.85): Medium confidence, log for review
   - Tier 3 (0.50 < P ≤ 0.70): Low confidence, monitoring mode
5. **False Positive Filter**: Secondary classification on FIRMS metadata (edge pixels, sun glint)
6. **Telegram Notification**: Sends alert map, coordinates, confidence, and recommended action
