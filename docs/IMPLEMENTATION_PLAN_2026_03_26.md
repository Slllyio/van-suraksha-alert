# Van Suraksha — Full Pipeline Integration Plan
**Date**: 2026-03-26
**Status**: Active
**Goal**: Wire up all disconnected components into a cohesive operational system

---

## Current State (What Works)

| Component | Status | Notes |
|-----------|--------|-------|
| FIRMS NRT Detection | OPERATIONAL | Daily 06:00 IST, 2h latency |
| FWI Computation | OPERATIONAL | 13-year daily, NASA POWER + gridded |
| Predictive Model (25ha) | OPERATIONAL | v3_gridded AUC=0.937, ensemble ready |
| Dashboard (8 tabs) | OPERATIONAL | Streamlit + CesiumJS 3D twin |
| ABM Ignition | OPERATIONAL | 830 agents, monthly grid |
| Daily Pipeline | OPERATIONAL | 5-step: FWI→FIRMS→Detect→Predict→Unify |

## What's Built But Disconnected (1,500+ LOC orphaned)

| Component | LOC | Gap |
|-----------|-----|-----|
| Fire Physics (Rothermel, Byram) | 89 | Not invoked from pipeline |
| Fire Spread Simulator (Muhurta2D) | ~300 | Demo-only via WebSocket |
| Burn Scar Prithvi | 80+ | Trained, no real-time linkage |
| Smoke Dispersion (Gaussian plume) | 98 | Never called |
| Prescriptive Tactics | 200+ | Generated but never dispatched |
| AI Dispatcher (Hindi + WhatsApp) | 150+ | Local-only logging |
| GFS Forecast Download | ~100 | Not scheduled |
| Ensemble Orchestrator (6-model) | ~400 | Exists in src/analysis/, not used in daily |

---

## Implementation Plan: 6 Phases

### Phase 1: NRT Fire → Predicted Spread (Priority: CRITICAL)
**Goal**: When a fire is detected, predict where it will spread in 6/12/24 hours using existing weather + terrain.

**Steps**:
1. Create `src/analysis/spread_predictor.py`:
   - Input: fire point (lat, lon), FRP_MW, current weather (temp, RH, wind_speed, wind_dir)
   - Load DEM + slope + aspect at fire location (128×128 window, 30m)
   - Compute Rothermel ROS using `fire_physics.py` + terrain adjustment
   - Run Muhurta2D simulator forward 6h, 12h, 24h
   - Output: spread polygon (GeoJSON) + burned area estimate (ha) + arrival times

2. Wire into `scripts/nrt_alert_pipeline.py`:
   - After each fire detection, call `spread_predictor.predict_spread()`
   - Append spread polygon to alert JSON under `"predicted_spread"` key
   - Include wind-corrected ROS, estimated area at 6/12/24h

3. Add spread visualization to Dashboard:
   - Live Alert tab: show spread polygons on map (6h=yellow, 12h=orange, 24h=red)
   - 3D Digital Twin: animate spread on CesiumJS globe

**Data flow**:
```
FIRMS detection → fire_physics.py (Byram intensity, ROS)
                → spread_predictor.py (Muhurta2D simulation)
                → spread_polygon_6h.geojson, spread_polygon_12h.geojson
                → unified_alert.geojson (appended)
                → Dashboard Live Alert tab (visualized)
```

---

### Phase 2: NRT Fire → Probable Burn Scar Estimation (Priority: HIGH)
**Goal**: For each detected fire, estimate its probable burn scar extent using fire physics + satellite-calibrated burn models.

**Steps**:
1. Create `src/analysis/burn_estimator.py`:
   - Input: fire detection (lat, lon, FRP, time), spread polygon from Phase 1
   - Use Phase 1's spread area as initial burn scar estimate
   - Adjust using historical FIRMS→burn scar ratios (from `fire_links.csv`)
   - Calibrate: mean ratio of actual burn area to FIRMS-predicted area
   - Output: estimated burn polygon + area (ha) + confidence

2. Wire burn estimation into alert pipeline:
   - After spread prediction, call `burn_estimator.estimate()`
   - Add `"probable_burn_scar"` to alert JSON
   - Include estimated area, severity, and confidence

3. Post-fire verification (T+5 to T+30 days):
   - Create `scripts/verify_burn_scars.py`:
     - For each alert older than 5 days, find matching HLS imagery
     - Run Prithvi burn scar model on post-fire HLS
     - Compare predicted vs actual burn area
     - Update fire_links.csv with linkage
     - Compute accuracy metrics (IoU, area ratio)

**Data flow**:
```
FIRMS detection → spread_predictor (6/12/24h polygons)
               → burn_estimator (calibrated burn area)
               → alert JSON: "probable_burn_scar": {...}
               → [5-30 days later] verify_burn_scars.py
               → Prithvi burn scar detection on post-fire HLS
               → fire_links.csv (actual vs predicted linkage)
               → feedback to improve burn_estimator calibration
```

---

### Phase 3: Historical Fire Heat Maps + Pattern Mining (Priority: HIGH)
**Goal**: Mine 10+ years of FIRMS data (1.3M detections) to create operational intelligence.

**Steps**:
1. Create `scripts/build_fire_analytics.py`:
   - Load all FIRMS data (2013-2026, 1.3M detections)
   - Aggregate by: beat, range, month, year
   - Compute: fire frequency, peak month, fire return interval
   - Generate heat maps: spatial density at 500m resolution
   - Output: `outputs/analytics/fire_heat_map.parquet`

2. Create `scripts/build_fire_climatology.py`:
   - For each beat: average fires per month (climatology)
   - Anomaly: current month vs 10-year average
   - Trend: increasing or decreasing fire frequency per beat
   - Correlation: FWI vs fire count (per beat, per month)
   - Output: `outputs/analytics/fire_climatology.json`

3. Add Analytics tab to Dashboard:
   - Heat map: 10-year fire density (spatial)
   - Seasonality: monthly fire count bar chart per range
   - Trends: year-over-year fire count trend lines
   - Anomaly map: which beats are above/below normal this month
   - Top-10 fire-prone beats table

4. Use analytics for prediction calibration:
   - Feed climatology into predictive model as features
   - Adjust ensemble weights by beat-level model performance

**Data flow**:
```
FIRMS detections (2013-2026, 1.3M rows)
  → build_fire_analytics.py
  → fire_heat_map.parquet (spatial density)
  → fire_climatology.json (per-beat monthly stats)
  → Dashboard Analytics tab (visualized)
  → Predictive model features (improved calibration)
```

---

### Phase 4: GFS Forecast → Forward Fire Danger Outlook (Priority: MEDIUM-HIGH)
**Goal**: Use GFS weather forecasts (24/48/72h) to predict fire danger 3 days ahead.

**Steps**:
1. Add GFS fetch to daily pipeline:
   - In `daily_fire_alert.py`, add Step 1b: fetch GFS 0.25° forecast
   - Download T+24, T+48, T+72h from `weather_ingest.py`
   - Extract: temp, RH, wind, precip for Guna grid points
   - Output: `data_lake/weather_forecasts/gfs/forecast_{date}.parquet`

2. Compute forward FWI:
   - Extend `compute_fwi.py` with `--forecast` mode
   - Take current FFMC/DMC/DC state
   - Run Van Wagner equations forward using GFS forecast weather
   - Output: FWI_today, FWI_tomorrow, FWI_+48h, FWI_+72h
   - Output: `data_lake/fire_weather/fwi_forecast.parquet`

3. Generate 3-day fire danger outlook:
   - For each 25ha cell: compute risk_score using forecast weather
   - Generate risk_map_+24h.csv, risk_map_+48h.csv, risk_map_+72h.csv
   - Add to unified_alert.geojson under `"forecast"` section

4. Add Forecast tab to Dashboard:
   - 3-panel map: today, tomorrow, day-after-tomorrow
   - FWI trend line showing forecast trajectory
   - Alert: "FWI expected to reach EXTREME in 48h" banner

**Data flow**:
```
GFS 0.25° forecast (T+24/48/72h)
  → weather_ingest.py (download + parse)
  → compute_fwi.py --forecast (forward FWI)
  → train_predictive_fire_risk.py --predict (forward risk map)
  → risk_map_+24h.csv, +48h.csv, +72h.csv
  → Dashboard Forecast tab (3-day outlook)
```

---

### Phase 5: Smoke Plume + Population Impact (Priority: MEDIUM)
**Goal**: For each active fire, model downwind smoke plume and estimate affected population.

**Steps**:
1. Wire `src/analysis/smoke_dispersion.py` into alert pipeline:
   - After fire detection + physics calculation:
     - Input: FRP → emission rate (PM2.5 kg/hr)
     - Input: wind speed + direction from FWI
     - Run Gaussian plume model for 1-50 km downwind
     - Output: PM2.5 concentration grid (ug/m³) at surface level

2. Create `src/analysis/population_impact.py`:
   - Load settlement/village locations (from OSM or Census)
   - For each settlement in plume footprint:
     - Estimate PM2.5 exposure
     - Classify: Good (<50), Moderate (50-100), Unhealthy (100-150), Hazardous (>150)
   - Output: list of affected settlements + population + exposure level

3. Add to alerts:
   - `"smoke_plume"`: polygon of PM2.5 > 50 ug/m³
   - `"affected_settlements"`: [{name, population, pm25_ug_m3, health_advisory}]

4. Add Smoke Impact panel to Dashboard:
   - Plume overlay on map (gradient: green→yellow→red)
   - Affected settlement list with distance + exposure
   - Health advisory message

---

### Phase 6: Tactical Dispatch Activation (Priority: MEDIUM)
**Goal**: Wire prescriptive engine → AI dispatcher → field WhatsApp/SMS.

**Steps**:
1. Enable prescriptive dispatch in daily pipeline:
   - In `nrt_alert_pipeline.py`: after generating each fire alert
   - Call `prescriptive_engine.generate_tactical_prescription()`
   - Call `ai_dispatcher.dispatch()` with webhook URL
   - Set `VANAAGNI_DISPATCH_WEBHOOK` environment variable

2. Create dispatch template:
   - Format: structured WhatsApp message with:
     - Fire location (lat, lon, beat, range)
     - Severity + fire type (surface/crown)
     - Tactical mode (Direct/Parallel/Indirect/Defensive)
     - Equipment needed
     - Safety warnings
     - Predicted spread (from Phase 1)
     - Smoke direction (from Phase 5)

3. Add dispatch tracking to Dashboard:
   - Dispatch History tab: when, what, to whom
   - Acknowledgment status: sent → received → dispatched → resolved
   - Response time metrics

---

## Execution Order

```
Phase 1 (Spread)     ████████░░  ← START HERE — highest operational impact
Phase 2 (Burn Scar)  ░░████████  ← builds on Phase 1 spread polygons
Phase 3 (Analytics)   ████░░░░░░  ← independent, can run in parallel
Phase 4 (Forecast)   ░░░░████░░  ← independent, can run in parallel
Phase 5 (Smoke)      ░░░░░░████  ← needs Phase 1 fire physics
Phase 6 (Dispatch)   ░░░░░░░░██  ← needs Phases 1, 5 for full context
```

**Parallelizable**: Phases 3 and 4 are independent of Phase 1/2 and can run concurrently.

## Files to Create/Modify

### New Files:
- `src/analysis/spread_predictor.py` (Phase 1)
- `src/analysis/burn_estimator.py` (Phase 2)
- `src/analysis/population_impact.py` (Phase 5)
- `scripts/build_fire_analytics.py` (Phase 3)
- `scripts/build_fire_climatology.py` (Phase 3)
- `scripts/verify_burn_scars.py` (Phase 2)

### Modified Files:
- `scripts/nrt_alert_pipeline.py` — Add spread + burn + smoke to alerts
- `scripts/daily_fire_alert.py` — Add GFS fetch, forecast FWI steps
- `scripts/compute_fwi.py` — Add --forecast mode
- `src/data/weather_ingest.py` — Add GFS forecast download
- `dashboard/app.py` — Add Analytics, Forecast, Smoke tabs
- `config.yaml` — Add fire physics, smoke, dispatch params
