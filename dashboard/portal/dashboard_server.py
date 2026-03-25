#!/usr/bin/env python3
"""
JvalaNetra AI — Dashboard Status Server
=========================================
Lightweight HTTP server that:
  - Scans outputs/jvala/ for *_sop.json files
  - Aggregates them plus rakshak.json (centroid + polygon data)
  - Serves a /api/status JSON endpoint consumed by jvala_dashboard.html
  - Serves the dashboard HTML itself at /
  - Auto-reloads on each request (no caching) so the map stays live

Usage:
  python scripts/dashboard_server.py --config config_jvala.yaml
  python scripts/dashboard_server.py --config config_jvala.yaml --port 8787 --out-dir outputs/jvala

Then open:  http://localhost:8787

Endpoints:
  GET /                     → serves dashboard/jvala_dashboard.html
  GET /api/status           → JSON: { anchor_date, beats: [...], generated_at }
  GET /api/beat/<beat_id>   → full SOP JSON for one beat
  GET /outputs/jvala/*      → static file passthrough (GPX downloads, etc.)
"""

from __future__ import annotations

import argparse
import glob
import json
import logging
import math
import os
import re
import sys
from datetime import datetime, timezone, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import unquote

log = logging.getLogger("jvala.dashboard_server")

_IST = timedelta(hours=5, minutes=30)


# ── Ignition v2 pixel-level model (lazy-loaded at startup) ───────────────────
# NOTE: pickle is used here intentionally to load the LightGBM model trained
# by our own scripts/train_ignition2_model.py. These .pkl files are local
# project assets, not untrusted external data.

import pickle  # nosec B403 — loading our own trained model files
import joblib
import threading

_IGN2_LOCK = threading.Lock()
_IGN2 = {
    "model": None,
    "pca": None,
    "meta": None,
    "grid": None,          # DataFrame: grid_embeddings.parquet (all 137K cells)
    "weather": None,       # dict: cached weather for today
    "weather_date": "",    # str: YYYY-MM-DD of cached weather
    "loaded": False,
}


def _load_ignition2(base_dir: str = ".") -> bool:
    """Load Ignition v2 model, PCA, metadata, and grid embeddings into memory."""
    if _IGN2["loaded"]:
        return True
    with _IGN2_LOCK:
        if _IGN2["loaded"]:
            return True
        try:
            import numpy as np
            root = Path(base_dir)
            model_dir = root / "models"
            data_dir = root / "data" / "training"

            with open(model_dir / "ignition2_lgbm.pkl", "rb") as f:
                _IGN2["model"] = pickle.load(f)  # nosec B301 — own model
            _IGN2["pca"] = joblib.load(model_dir / "ignition2_pca.joblib")
            with open(model_dir / "ignition2_meta.json") as f:
                _IGN2["meta"] = json.load(f)

            import pandas as pd
            _IGN2["grid"] = pd.read_parquet(data_dir / "grid_embeddings.parquet")
            _IGN2["loaded"] = True
            log.info(f"Ignition v2 loaded: {len(_IGN2['grid']):,} grid cells, "
                     f"{len(_IGN2['meta']['features'])} features")
            return True
        except Exception as exc:
            log.warning(f"Ignition v2 load failed (pixel-risk disabled): {exc}")
            return False


def _fetch_weather_today() -> dict:
    """Fetch Open-Meteo weather for the division centroid; cache per day."""
    today = datetime.now().strftime("%Y-%m-%d")
    if _IGN2["weather_date"] == today and _IGN2["weather"] is not None:
        return _IGN2["weather"]

    import requests as _req
    import numpy as _np
    lat_c, lon_c = 24.6, 77.2
    target_dt = datetime.strptime(today, "%Y-%m-%d")
    start_str = (target_dt - timedelta(days=6)).strftime("%Y-%m-%d")
    is_hist = (datetime.now() - target_dt).days > 2
    url = ("https://archive-api.open-meteo.com/v1/archive" if is_hist
           else "https://api.open-meteo.com/v1/forecast")
    params = {
        "latitude": lat_c, "longitude": lon_c,
        "start_date": start_str, "end_date": today,
        "daily": "temperature_2m_max,relative_humidity_2m_min,"
                 "wind_speed_10m_max,wind_gusts_10m_max,precipitation_sum",
        "wind_speed_unit": "ms", "timezone": "Asia/Kolkata",
    }
    try:
        resp = _req.get(url, params=params, timeout=15)
        resp.raise_for_status()
        d = resp.json()["daily"]
        t_max = float(d["temperature_2m_max"][-1] or 35.0)
        rh_min = float(d["relative_humidity_2m_min"][-1] or 25.0)
        w_max = float(d["wind_speed_10m_max"][-1] or 3.0)
        g_max = float(d["wind_gusts_10m_max"][-1] or (w_max * 1.5))
        rain_7d = float(sum(x or 0.0 for x in d["precipitation_sum"]))
        es = 0.6108 * _np.exp(17.27 * t_max / (t_max + 237.3))
        vpd = es * (1.0 - rh_min / 100.0)
        wx = {"max_temp_c": t_max, "min_rh_pct": rh_min,
              "wind_speed_ms": w_max, "wind_gust_ms": g_max,
              "rain_7d_mm": rain_7d, "vpd_kpa": round(vpd, 3)}
    except Exception as exc:
        log.warning(f"Weather fetch failed ({exc}); fire-season defaults")
        wx = {"max_temp_c": 38.0, "min_rh_pct": 18.0, "wind_speed_ms": 4.5,
              "wind_gust_ms": 8.0, "rain_7d_mm": 0.0, "vpd_kpa": 4.8}

    _IGN2["weather"] = wx
    _IGN2["weather_date"] = today
    log.info(f"Weather cached for {today}: {wx}")
    return wx


def compute_pixel_risk(new_no: str) -> Optional[dict]:
    """Run Ignition v2 on all 1-ha cells of a compartment.
    Returns {"cells": [{lat,lon,risk}], "shap": [{feature,value}]}."""
    if not _IGN2["loaded"]:
        return None
    import numpy as np
    import pandas as pd

    grid = _IGN2["grid"]
    meta = _IGN2["meta"]
    model = _IGN2["model"]
    pca = _IGN2["pca"]

    # Filter to this compartment
    mask = grid["NEW_No_"] == new_no
    if mask.sum() == 0:
        return {"cells": [], "shap": []}
    df = grid.loc[mask].copy()

    # 1. PCA on 64D embeddings -> 12 PCs
    emb_cols = [f"A{str(i).zfill(2)}" for i in range(64)]
    X_emb = df[emb_cols].fillna(0).values
    pcs = pca.transform(X_emb)
    n_pc = meta.get("pca_components", 12)
    for i in range(n_pc):
        df[f"emb_pc{i}"] = pcs[:, i]

    # 2. Weather (single fetch, broadcast to all cells)
    wx = _fetch_weather_today()
    for k, v in wx.items():
        df[k] = v

    # 3. Derived features
    doy = datetime.now().timetuple().tm_yday
    df["doy_sin"] = np.sin(2 * np.pi * doy / 365.25)
    df["doy_cos"] = np.cos(2 * np.pi * doy / 365.25)

    # FFMC proxy (Van Wagner 1987)
    temp = df["max_temp_c"]
    rh = df["min_rh_pct"]
    wind_kmh = df["wind_speed_ms"] * 3.6
    rain = df["rain_7d_mm"]
    ffmc = 59.5 * np.exp(0.04 * temp) - 1.5 * rh + 0.5 * wind_kmh - 2.0 * rain
    df["ffmc_proxy"] = np.clip(ffmc, 0, 100)

    # ISI (Initial Spread Index)
    _wk = df["wind_gust_ms"] * 3.6
    _mf = 147.2 * (101.0 - df["ffmc_proxy"]) / (59.5 + df["ffmc_proxy"])
    _fW = np.exp(0.05039 * _wk)
    _fF = 91.9 * np.exp(-0.1386 * _mf) * (1.0 + _mf ** 5.31 / 4.93e7)
    df["isi"] = 0.208 * _fW * _fF

    # GDD fraction (Mahua phenology trigger)
    _gdd_base, _gdd_thresh = 10.0, 120.0
    _days = max(0, doy - 32)
    _gpd = float(np.nanmean(df["max_temp_c"].clip(lower=_gdd_base)) - _gdd_base)
    df["gdd_fraction"] = min(1.0, max(0.0, _days * _gpd / _gdd_thresh))

    # 4. Predict
    features = meta["features"]
    X = df[features].fillna(0)
    probs = model.predict_proba(X)[:, 1]

    # 5. SHAP via LightGBM built-in TreeSHAP (pred_contrib)
    shap_top = []
    try:
        booster = model.booster_
        contribs = booster.predict(X.values, pred_contrib=True)
        # Shape: (n_cells, n_features + 1); last column is bias
        feat_contribs = contribs[:, :-1]
        mean_contribs = np.mean(np.abs(feat_contribs), axis=0)
        shap_pairs = [{"feature": features[i], "value": round(float(mean_contribs[i]), 4)}
                      for i in range(len(features))]
        shap_pairs.sort(key=lambda x: abs(x["value"]), reverse=True)
        shap_top = shap_pairs[:6]
    except Exception as exc:
        log.warning(f"SHAP computation failed for {new_no}: {exc}")

    # 6. Build response
    cells = []
    for idx, (_, row) in enumerate(df.iterrows()):
        cells.append({
            "lat": round(float(row["ha_lat"]), 4),
            "lon": round(float(row["ha_lon"]), 4),
            "risk": round(float(probs[idx]) * 100, 2),
        })

    return {"cells": cells, "shap": shap_top}


# ── GeoJSON shapefile index ──────────────────────────────────────────────────

_GEOJSON_PATH = Path("data/gunafinal.geojson")
_GEO_INDEX: Dict[str, dict] = {}      # NEW_No_ (normalised) -> feature

def _polygon_centroid(coords_list) -> Tuple[float, float]:
    """Compute approximate centroid of a MultiPolygon or Polygon coordinate list."""
    lons, lats = [], []
    # coords_list is either [rings] (Polygon) or [[rings]] (MultiPolygon)
    def flatten(obj):
        if isinstance(obj, list) and obj and isinstance(obj[0], (int, float)):
            lons.append(obj[0]); lats.append(obj[1])
        elif isinstance(obj, list):
            for item in obj: flatten(item)
    flatten(coords_list)
    if not lons:
        return (0.0, 0.0)
    return (sum(lons)/len(lons), sum(lats)/len(lats))


def _load_geo_index(base_dir: str = ".") -> None:
    """Load gunafinal.geojson and index features by normalised NEW_No_."""
    global _GEO_INDEX
    path = Path(base_dir) / _GEOJSON_PATH
    if not path.exists():
        log.warning(f"gunafinal.geojson not found at {path} — map overlay disabled")
        return
    try:
        with open(path, encoding="utf-8") as f:
            gj = json.load(f)
        for feat in gj.get("features", []):
            raw_no = str(feat["properties"].get("NEW_No_", "")).strip()
            if raw_no:
                _GEO_INDEX[raw_no] = feat
        log.info(f"GeoJSON index loaded: {len(_GEO_INDEX)} features from {path.name}")
    except Exception as exc:
        log.warning(f"Failed to load GeoJSON index: {exc}")


def _extract_beat_no(beat_id: str) -> str:
    """Extract the P NNN part from beat_id like 'GOUMUKH / P 156' -> 'P 156'."""
    m = re.search(r"(P\s*\d+)$", beat_id.strip(), re.IGNORECASE)
    return m.group(1).upper() if m else ""


def _get_geo_for_beat(beat_id: str) -> Optional[dict]:
    """Look up the GeoJSON feature for a given beat_id."""
    if not _GEO_INDEX:
        return None
    beat_no = _extract_beat_no(beat_id)
    if beat_no and beat_no in _GEO_INDEX:
        return _GEO_INDEX[beat_no]
    # Fallback: try matching by BEAT name prefix
    beat_name = beat_id.split("/")[0].strip().upper()
    for no, feat in _GEO_INDEX.items():
        if str(feat["properties"].get("BEAT", "")).upper() == beat_name:
            return feat
    return None


# ── Aggregator ────────────────────────────────────────────────────────────────

import time

_DASHBOARD_CACHE = {
    "data": None,
    "last_mtime": 0.0,
    "last_scanned_time": 0.0,
}

def _scan_latest_info(out_dir: str) -> tuple[str, float, list]:
    """Returns (anchor_date, latest_file_mtime, files_for_latest_date) using fast scandir."""
    dates = set()
    latest_mtime = 0.0
    all_files = []
    try:
        with os.scandir(out_dir) as it:
            for entry in it:
                if entry.name.endswith("_sop.json") and entry.is_file():
                    stat = entry.stat()
                    if stat.st_mtime > latest_mtime:
                        latest_mtime = stat.st_mtime
                    m = re.search(r"(\d{4}-\d{2}-\d{2})_sop\.json$", entry.name)
                    if m:
                        dates.add(m.group(1))
                    all_files.append((entry.name, entry.path))
    except Exception:
        pass
        
    anchor = max(dates) if dates else ""
    files_for_latest = sorted([p for n, p in all_files if anchor in n]) if anchor else []
    return anchor, latest_mtime, files_for_latest


def load_all_beats(out_dir: str, anchor_date: Optional[str] = None) -> Dict[str, Any]:
    """
    Aggregate all SOP JSON files for a given anchor_date (or latest if None).
    Returns a dict matching the structure expected by JVALA_DATA in the dashboard.
    """
    global _DASHBOARD_CACHE
    current_time = time.time()
    
    try:
        current_dir_mtime = os.path.getmtime(out_dir)
    except OSError:
        current_dir_mtime = 0.0

    is_latest_query = anchor_date is None
    
    if is_latest_query:
        # Return cache if directory hasn't changed or scanned in last 2 seconds
        if _DASHBOARD_CACHE["data"] is not None and (
            current_time - _DASHBOARD_CACHE["last_scanned_time"] < 2.0 or 
            current_dir_mtime == _DASHBOARD_CACHE["last_mtime"]
        ):
            return _DASHBOARD_CACHE["data"]

        anchor_date, _, files = _scan_latest_info(out_dir)
    else:
        # Search specifically for the requested date using fast scandir
        files = []
        try:
            with os.scandir(out_dir) as it:
                for entry in it:
                    if entry.is_file() and entry.name.endswith(f"_{anchor_date}_sop.json"):
                        files.append(entry.path)
            files.sort()
        except OSError:
            pass

    if not files or not anchor_date:
        return {"anchor_date": "", "beats": [], "generated_at": _now_ist()}

    beats: List[Dict] = []
    for sop_path in files:
        try:
            with open(sop_path, encoding="utf-8") as f:
                sop = json.load(f)
        except Exception as exc:
            log.warning(f"Error reading {sop_path}: {exc}")
            continue

        beat_id   = sop.get("beat_id", "?")
        safe_id   = beat_id.replace(" ", "_").replace("/", "-")

        # Load paired files
        rak_path  = os.path.join(out_dir, f"{safe_id}_{anchor_date}_rakshak.json")
        cfl_path  = os.path.join(out_dir, f"{safe_id}_{anchor_date}_cfl.geojson")
        muh_path  = os.path.join(out_dir, f"muhurta/{safe_id}_{anchor_date}_muhurta.json")

        rakshak = _load_json_safe(rak_path)
        cfl_gj  = _load_json_safe(cfl_path)
        muhurta = _load_json_safe(muh_path) or {}

        # Extract centroid: prefer GeoJSON shapefile (most accurate)
        geo_feat = _get_geo_for_beat(beat_id)
        polygon  = None
        centroid = None
        new_no   = None   # compartment number for Ignition v2 grid lookup
        if geo_feat:
            new_no = str(geo_feat["properties"].get("NEW_No_", "")).strip() or None
            geom = geo_feat["geometry"]
            # Convert MultiPolygon -> first polygon ring for DeckGL PolygonLayer
            if geom["type"] == "MultiPolygon":
                polygon = geom["coordinates"][0][0]  # first ring of first polygon
            elif geom["type"] == "Polygon":
                polygon = geom["coordinates"][0]
            if polygon:
                lon, lat = _polygon_centroid(polygon)
                centroid = [round(lon, 6), round(lat, 6)]
        # Fall back to SOP-embedded centroid if no GeoJSON match
        if not centroid:
            centroid = sop.get("centroid") or [
                sop.get("centroid_lon", None),
                sop.get("centroid_lat", None),
            ]

        # Extract CFL line coords
        cfl_features = (cfl_gj or {}).get("features") or []
        cfl_line = None
        if cfl_features:
            geom = cfl_features[0].get("geometry") or {}
            cfl_line = geom.get("coordinates")  # list of [lon, lat]

        # SHAP reasons — normalise both old and new schemas
        raw_shap = sop.get("shap_reasons") or []
        shap = []
        for item in raw_shap:
            if isinstance(item, dict):
                shap.append({"feature": item.get("feature","?"), "value": item.get("value", 0.0)})
            elif isinstance(item, (list, tuple)) and len(item) >= 2:
                shap.append({"feature": str(item[0]), "value": float(item[1])})

        # Muhurta — prefer dedicated muhurta JSON (richer) over SOP summary
        muh_stage = muhurta.get("confidence_stage") or sop.get("muhurta_stage") or "C"
        muh_safe  = muhurta.get("safe") if muhurta else sop.get("muhurta_safe", False)
        muh_start = muhurta.get("start_utc") or (sop.get("muhurta") or {}).get("start_utc")
        muh_end   = muhurta.get("end_utc")   or (sop.get("muhurta") or {}).get("end_utc")

        beats.append({
            "id":            safe_id,
            "name":          beat_id,
            "new_no":        new_no,
            "tier":          sop.get("tier", "CLEAR"),
            "risk_score":    sop.get("risk_score", 5),
            "p_ignition":    sop.get("p_ignition", 0.0),
            "ema_score":     sop.get("ema_score", 0.0),
            "confidence":    sop.get("confidence", 0.0),
            "spread_area_ha":sop.get("spread_area_ha"),
            "spread_tier":   sop.get("spread_tier"),
            "centroid":      centroid,
            "polygon":       polygon,
            "cfl_line":      cfl_line,
            "cfl_rank":      sop.get("cfl_rank", "no_line"),
            "muhurta": {
                "stage":     muh_stage,
                "safe":      muh_safe,
                "start_utc": muh_start,
                "end_utc":   muh_end,
            },
            "shap":          shap,
            # Extra fire weather (from muhurta JSON if available)
            "flame_length_m":  muhurta.get("flame_length_m", 0.0),
            "byram_kw_m":      muhurta.get("byram_intensity_kw_m", 0.0),
            "haines_index":    muhurta.get("haines_index", 0),
            "fuel_load_t_ha":  rakshak.get("fuel_load_t_ha", 0.0) if rakshak else 0.0,
            "sop_file":        sop.get("sop_file", f"{safe_id}_{anchor_date}_sop.json"),
            "gpx_file":        f"gpx/{safe_id}_{anchor_date}_cfl.gpx",
        })

    # Sort by risk_score ascending (highest risk first)
    beats.sort(key=lambda b: (b["risk_score"], b["name"]))

    # Load scheduler state if available
    scheduler_state: Optional[dict] = None
    sched_path = os.path.join(out_dir, "..", "..", "state", "scheduler_state.json")
    try:
        with open(os.path.normpath(sched_path), encoding="utf-8") as sf:
            scheduler_state = json.load(sf)
    except Exception:
        pass

    result = {
        "anchor_date":  anchor_date,
        "beats":        beats,
        "generated_at": _now_ist(),
        "total_beats":  len(beats),
        "high_risk":    sum(1 for b in beats if b["risk_score"] <= 2),
        "scheduler":    scheduler_state,
    }
    
    # Update cache if this was a request for the latest generic data
    if is_latest_query:
        _DASHBOARD_CACHE["data"] = result
        _DASHBOARD_CACHE["last_mtime"] = current_dir_mtime
        _DASHBOARD_CACHE["last_scanned_time"] = current_time
        
    return result


def _load_json_safe(path: str) -> Optional[dict]:
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def _now_ist() -> str:
    return (datetime.now(timezone.utc) + _IST).isoformat(timespec="seconds")


# ── HTTP Handler ──────────────────────────────────────────────────────────────

class JvalaHandler(BaseHTTPRequestHandler):
    # Injected by __init__ of server
    out_dir:   str = "outputs/jvala"
    dash_dir:  str = "dashboard"
    base_dir:  str = "."

    def do_GET(self):
        path = unquote(self.path.split("?")[0])

        if path in ("/", "/index.html", "/dashboard"):
            self._serve_file(
                os.path.join(self.dash_dir, "jvala_dashboard.html"),
                "text/html; charset=utf-8"
            )
        elif path == "/api/status":
            self._serve_api_status()
        elif path == "/api/scheduler":
            self._serve_scheduler()
        elif path == "/api/backtest":
            self._serve_backtest()
        elif path == "/api/stream":
            self._serve_stream()
        elif path == "/api/beats-geojson":
            self._serve_beats_geojson()
        elif path.startswith("/api/pixel-risk/"):
            new_no = path[len("/api/pixel-risk/"):]
            self._serve_pixel_risk(new_no)
        elif path.startswith("/api/beat/"):
            beat_safe_id = path[len("/api/beat/"):]
            self._serve_beat(beat_safe_id)
        elif path.startswith("/api/gpx/"):
            beat_safe_id = path[len("/api/gpx/"):]
            self._serve_gpx(beat_safe_id)
        elif path == "/api/forecast":
            self._serve_forecast()
        elif path == "/api/forecast/dates":
            self._serve_forecast_dates()
        elif path.startswith("/outputs/"):
            rel = path.lstrip("/")
            self._serve_file(rel, self._mime(rel))
        elif path.startswith("/data/"):
            rel = path.lstrip("/")
            self._serve_file(rel, self._mime(rel))
        else:
            self._send_404()

    def _serve_api_status(self):
        data = load_all_beats(self.out_dir)
        body = json.dumps(data, indent=2, ensure_ascii=False).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(body)

    def _serve_beats_geojson(self):
        """Serve the complete gunafinal.geojson shapefile."""
        path = os.path.join(self.base_dir, "data", "gunafinal.geojson")
        self._serve_file(path, "application/geo+json; charset=utf-8")

    def _serve_pixel_risk(self, new_no: str):
        """Run Ignition v2 on 1-ha grid cells for one compartment."""
        import time as _t
        t0 = _t.monotonic()
        result = compute_pixel_risk(new_no)
        elapsed = (_t.monotonic() - t0) * 1000
        if result is None:
            body = json.dumps({"error": "Ignition v2 not loaded"}).encode("utf-8")
            self.send_response(503)
        else:
            cells = result["cells"]
            shap_data = result.get("shap", [])
            log.info(f"pixel-risk/{new_no}: {len(cells)} cells, "
                     f"{len(shap_data)} SHAP features in {elapsed:.0f}ms")
            body = json.dumps({"cells": cells, "shap": shap_data,
                               "count": len(cells),
                               "new_no": new_no}).encode("utf-8")
            self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Cache-Control", "max-age=300")  # cache 5min (weather changes slowly)
        self.end_headers()
        self.wfile.write(body)

    def _serve_stream(self):
        """Server-Sent Events endpoint to notify frontend of new SOP json files."""
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        
        last_mtime = 0
        while True:
            import time
            latest = 0
            # Use os.scandir for highly efficient directory traversal instead of glob
            try:
                with os.scandir(self.out_dir) as it:
                    for entry in it:
                        if entry.name.endswith("_sop.json") and entry.is_file():
                            try:
                                mtime = entry.stat().st_mtime
                                if mtime > latest: latest = mtime
                            except OSError: pass
            except OSError:
                pass
                
            if last_mtime == 0:
                last_mtime = latest
            elif latest > last_mtime:
                last_mtime = latest
                try:
                    self.wfile.write(b'data: {"update": true}\n\n')
                    self.wfile.flush()
                except Exception:
                    break # Client disconnected
            
            try:
                # Keep-alive comment every 2s
                self.wfile.write(b": keep-alive\n\n")
                self.wfile.flush()
            except Exception:
                break
            time.sleep(2)

    def _serve_scheduler(self):
        """Serve scheduler_state.json directly."""
        path = os.path.join(self.base_dir, "state", "scheduler_state.json")
        if not os.path.exists(path):
            body = json.dumps({"status": "not_running", "message": "Scheduler not started"}).encode()
        else:
            with open(path, encoding="utf-8") as f:
                body = f.read().encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _serve_backtest(self):
        """Aggregate model meta + GDD images + run history for the back-test tab."""
        import glob as _glob

        # ── 1. Model meta files ───────────────────────────────────────────────
        models_dir  = os.path.join(self.base_dir, "models")
        ignition_meta: dict = {}
        intensity_meta: dict = {}
        try:
            hits = _glob.glob(os.path.join(models_dir, "*ignition*meta.json"))
            if hits:
                with open(sorted(hits)[-1], encoding="utf-8") as f:
                    ignition_meta = json.load(f)
        except Exception:
            pass
        try:
            hits = _glob.glob(os.path.join(models_dir, "*intensity*meta.json"))
            if hits:
                with open(sorted(hits)[-1], encoding="utf-8") as f:
                    intensity_meta = json.load(f)
        except Exception:
            pass

        # ── 2. GDD validation images already in outputs/jvala/ ───────────────
        gdd_urls = []
        for img in sorted(_glob.glob(os.path.join(self.out_dir, "gdd_validation_*.png"))):
            gdd_urls.append("/outputs/jvala/" + os.path.basename(img))

        # ── 3. Pipeline run history ────────────────────────────────────────────
        runs_dir = os.path.join(self.out_dir, "pipeline_runs")
        run_history = []
        for rfile in sorted(_glob.glob(os.path.join(runs_dir, "run_*.json")), reverse=True)[:30]:
            try:
                with open(rfile, encoding="utf-8") as f:
                    run_history.append(json.load(f))
            except Exception:
                pass

        # ── 4. Validation metrics from validate_models.py ─────────────────────
        val_report_path = os.path.join(self.out_dir, "validation", "validation_report.json")
        val_report: dict = {}
        try:
            if os.path.exists(val_report_path):
                with open(val_report_path, encoding="utf-8") as f:
                    val_report = json.load(f)
        except Exception:
            pass

        val_plots = []
        val_dir_url = "/outputs/jvala/validation"
        for fname in [
            "roc_curve_ignition_2023.png",
            "pr_curve_ignition_2023.png",
            "confusion_ignition_2023.png",
            "confusion_intensity_holdout.png",
        ]:
            full = os.path.join(self.out_dir, "validation", fname)
            if os.path.exists(full):
                val_plots.append(f"{val_dir_url}/{fname}")

        payload = {
            "ignition_model":     ignition_meta,
            "intensity_model":    intensity_meta,
            "gdd_images":         gdd_urls,
            "run_history":        run_history,
            "validation_metrics": val_report,   # live computed holdout metrics
            "validation_plots":   val_plots,    # paths to PNG artefacts
        }
        body = json.dumps(payload, indent=2, ensure_ascii=False).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(body)

    def _serve_beat(self, safe_id: str):
        anchor = _latest_date_dir(self.out_dir)
        path   = os.path.join(self.out_dir, f"{safe_id}_{anchor}_sop.json")
        self._serve_file(path, "application/json; charset=utf-8")

    def _serve_gpx(self, safe_id: str):
        """Find the latest GPX file for this beat and stream as a download."""
        import glob as _glob
        gpx_dir = os.path.join(self.out_dir, "gpx")
        pattern = os.path.join(gpx_dir, f"{safe_id}_*_cfl.gpx")
        matches = sorted(_glob.glob(pattern), reverse=True)
        if not matches:
            self._send_404()
            return
        gpx_path = matches[0]
        with open(gpx_path, "rb") as f:
            body = f.read()
        filename = os.path.basename(gpx_path)
        self.send_response(200)
        self.send_header("Content-Type", "application/gpx+xml")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def _serve_file(self, rel_path: str, content_type: str = "application/octet-stream"):
        full = os.path.join(self.base_dir, rel_path) if not os.path.isabs(rel_path) else rel_path
        if not os.path.isfile(full):
            self._send_404()
            return
        with open(full, "rb") as f:
            body = f.read()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _serve_forecast(self):
        """
        GET /api/forecast[?date=YYYY-MM-DD]
        Returns the forecast JSON for a given date (default: latest).
        """
        from urllib.parse import urlparse, parse_qs
        qs        = parse_qs(urlparse(self.path).query)
        date_param = qs.get("date", [None])[0]
        fc_dir    = os.path.join(self.out_dir, "forecast")
        if date_param:
            fp = os.path.join(fc_dir, f"forecast_{date_param}.json")
        else:
            fp = os.path.join(fc_dir, "forecast_latest.json")

        if os.path.isfile(fp):
            try:
                data = json.loads(open(fp, encoding="utf-8").read())
                body = json.dumps(data, ensure_ascii=False).encode("utf-8")
                self.send_response(200)
            except Exception:
                body = b'{"error": "parse error"}'
                self.send_response(500)
        else:
            body = json.dumps({"error": "forecast not available", "path": fp}).encode("utf-8")
            self.send_response(404)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(body)

    def _serve_forecast_dates(self):
        """
        GET /api/forecast/dates
        Returns list of available forecast dates (most recent first, max 30).
        """
        import glob as _glob
        fc_dir = os.path.join(self.out_dir, "forecast")
        try:
            files = _glob.glob(os.path.join(fc_dir, "forecast_2*.json"))
            dates = sorted(
                [os.path.basename(f)[9:-5] for f in files],
                reverse=True,
            )[:30]
        except Exception:
            dates = []
        body = json.dumps({"dates": dates}, ensure_ascii=False).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def _send_404(self):
        self.send_response(404)
        self.end_headers()
        self.wfile.write(b"Not found")

    def _mime(self, path: str) -> str:
        ext = path.rsplit(".", 1)[-1].lower()
        return {
            "json": "application/json",
            "geojson": "application/geo+json",
            "gpx": "application/gpx+xml",
            "html": "text/html",
            "png": "image/png",
            "jpg": "image/jpeg",
            "js": "text/javascript",
            "css": "text/css",
        }.get(ext, "application/octet-stream")

    def log_message(self, fmt, *args):
        log.info(f"HTTP {args[0]} {args[1]} {args[2]}")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(description="JvalaNetra Dashboard Server")
    ap.add_argument("--config",  default="config_jvala.yaml")
    ap.add_argument("--port",    type=int,  default=8787)
    ap.add_argument("--host",    default="0.0.0.0")
    ap.add_argument("--out-dir", default="outputs/jvala")
    ap.add_argument("--base-dir", default=".")
    args = ap.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
        datefmt="%H:%M:%S",
    )

    # Inject dirs into handler class
    JvalaHandler.out_dir  = args.out_dir
    JvalaHandler.dash_dir = os.path.join(args.base_dir, "dashboard")
    JvalaHandler.base_dir = args.base_dir

    # Load GeoJSON index
    _load_geo_index(args.base_dir)

    # Load Ignition v2 model for pixel-level risk (non-blocking: warns if missing)
    _load_ignition2(args.base_dir)

    # Use ThreadingHTTPServer so SSE streams don't block other requests
    server = ThreadingHTTPServer((args.host, args.port), JvalaHandler)
    log.info(f"JvalaNetra Dashboard → http://localhost:{args.port}")
    log.info(f"API status           → http://localhost:{args.port}/api/status")
    log.info(f"SOP outputs dir      → {args.out_dir}")
    log.info("Press Ctrl+C to stop.")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        log.info("Server stopped.")
        server.server_close()


if __name__ == "__main__":
    main()
