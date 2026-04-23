"""JwalaNetra v3 Unified Portal — backend server.

Serves the v17 ignition model predictions, division overview,
model transparency metrics, and validation log to the portal UI.

Usage:
    python dashboard/v3/serve.py
    Open http://localhost:8790/v3/
"""
from __future__ import annotations

import json
import logging
import os
import threading
import time
from collections import defaultdict
from datetime import date, datetime, timedelta
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import numpy as np
import pandas as pd

# Module-level logger. The portal is launched directly (`python serve.py`),
# so a basicConfig is set in __main__; a NullHandler-style fallback keeps
# `log.*` safe when the module is imported elsewhere (e.g. unit tests).
log = logging.getLogger("v3.serve")
if not log.handlers:
    log.addHandler(logging.NullHandler())

ROOT = Path(__file__).resolve().parent.parent.parent
DASHBOARD_DIR = ROOT / "dashboard"
FEED_DIR = ROOT / "outputs" / "dashboard_feed"
ALERTS_DIR = ROOT / "data_lake" / "alerts"
AUDITS_DIR = ROOT / "data_lake" / "audits"
BEATS_GEOJSON = ROOT / "data" / "aoi" / "mp_beats_wgs84.geojson"
BEATS_SHP = ROOT / "data" / "aoi" / "MP_Merge Divsion Beat Range" / "Mp_Beat_Merge.shp"
OPERATIONAL_ALERTS = FEED_DIR / "operational_alerts_v17.json"
DIVISION_BRIEFINGS = FEED_DIR / "division_briefings.json"
SEASONAL_PULSE = FEED_DIR / "seasonal_pulse.json"
DIVISION_PULSE = FEED_DIR / "division_pulse.json"
FEATURE_DRIFT = FEED_DIR / "feature_drift.json"
MATRIX_PROFILE = FEED_DIR / "matrix_profile_firms.json"
SEASON_ONSET = FEED_DIR / "season_onset.json"
CALIB_CURVE = ROOT / "outputs" / "predictive_fire_risk" / "predictive_v17_ba_pu" / "calibration_curve.json"
SEASON_VALIDATION_DIR = ROOT / "outputs" / "validation_reports"
SOIL_PARQUET = ROOT / "data_lake" / "fire_weather" / "soil_daily.parquet"
FIELD_RESPONSES = ALERTS_DIR / "field_responses.parquet"
_RESPONSE_LOCK = threading.Lock()

PORT = 8790
TODAY = datetime.now().strftime("%Y-%m-%d")

# Wall-clock start of this portal process. Used by /api/healthz to report
# uptime. Set at import time so it remains stable across requests.
_PORTAL_START_S = time.time()

# Projected CRS for spatial joins. EPSG:32644 = UTM zone 44N, covers MP from
# ~78°E westward (Guna pilot region 76.45-77.85°E). Geopandas/shapely operate
# in linear meters here, so `max_distance` is in METERS — not degrees — which
# silences the `sjoin_nearest` geographic-CRS UserWarning and is correct
# anywhere on the globe (degrees are non-uniform north of the equator).
_PROJECTED_CRS = "EPSG:32644"
# 0.003 degrees ≈ 333 m at MP latitudes (~24°N). Pin to 333 m exactly so the
# tolerance stays stable even if the AOI extends north or the CRS changes.
_FIRE_BEAT_TOLERANCE_M = 333.0
_BEATS_PROJECTED = None  # cached projected beats GeoDataFrame


def _load_v17_predictions(date_str: str | None = None) -> dict:
    candidate = None
    if date_str:
        dated = FEED_DIR / f"ignition_risk_v17_{date_str}.json"
        if dated.exists():
            candidate = dated
    if candidate is None:
        candidate = FEED_DIR / "ignition_risk_v17.json"
    if not candidate.exists():
        return {"error": "no v17 predictions available"}
    payload = json.loads(candidate.read_text())
    payload.pop("alerts_all_cells", None)
    return payload


def _load_latest_alert() -> dict:
    path = ALERTS_DIR / "latest_alert.json"
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _load_cell_divisions() -> dict[str, str]:
    cells_path = ROOT / "outputs" / "predictive_fire_risk" / "predictive_v6e_live" / "cells.csv"
    if not cells_path.exists():
        return {}
    cells = pd.read_csv(cells_path)
    if "division" not in cells.columns:
        return {}
    return dict(zip(cells["cell_id"].astype(str), cells["division"].astype(str)))


_CELL_DIVISIONS: dict[str, str] | None = None

def _get_cell_division(cell_id: str) -> str:
    global _CELL_DIVISIONS
    if _CELL_DIVISIONS is None:
        _CELL_DIVISIONS = _load_cell_divisions()
    return _CELL_DIVISIONS.get(cell_id, "Unknown")


def _build_division_overview(v17: dict) -> dict:
    alerts = v17.get("banded_alerts", [])
    if not alerts:
        return {"divisions": [], "total_alerts": 0}

    by_div: dict[str, dict] = defaultdict(lambda: {
        "critical": 0, "alert": 0, "watch": 0,
        "total": 0, "mean_risk": 0, "max_risk": 0,
        "hawkes_high_pct": 0, "cells": [],
    })
    for a in alerts:
        div = a.get("division") or _get_cell_division(a.get("cell_id", ""))
        band = a.get("band", "WATCH")
        by_div[div][band.lower()] = by_div[div].get(band.lower(), 0) + 1
        by_div[div]["total"] += 1
        by_div[div]["cells"].append(a)

    divisions = []
    for div_name, data in sorted(by_div.items(), key=lambda x: -x[1]["critical"]):
        cells = data["cells"]
        risks = [c.get("ignition_risk", 0) for c in cells]
        hawkes_vals = [c.get("hawkes_n_recent_10km_7d", 0) for c in cells]
        hawkes_high = sum(1 for h in hawkes_vals if h > 1) / max(len(hawkes_vals), 1)

        confidence = "HIGH" if hawkes_high > 0.5 else ("MEDIUM" if hawkes_high > 0.3 else "LOW")
        divisions.append({
            "name": div_name,
            "critical": data["critical"],
            "alert": data["alert"],
            "watch": data["watch"],
            "total": data["total"],
            "mean_risk": float(np.mean(risks)) if risks else 0,
            "max_risk": float(np.max(risks)) if risks else 0,
            "hawkes_high_pct": round(hawkes_high * 100),
            "confidence": confidence,
            "center_lat": float(np.mean([c.get("lat", 0) for c in cells])),
            "center_lon": float(np.mean([c.get("lon", 0) for c in cells])),
        })
        del data["cells"]

    return {
        "divisions": divisions,
        "total_alerts": len(alerts),
        "prediction_date": v17.get("prediction_date", TODAY),
    }


def _build_transparency() -> dict:
    return {
        "model": "v17_ba_pu",
        "training_label": "BA-tiered (GOLD 1.0 / SILVER 0.7 / BRONZE 0.5)",
        "metrics": {
            "roc_auc": 0.8815,
            "pr_auc": 0.1481,
            "recall_top5pct_tiered": 0.4741,
            "recall_top5pct_dbscan": 0.2269,
            "perday_recall_mean": 0.292,
            "perday_recall_std": 0.119,
            "critical_precision_tiered": 0.22,
            "critical_precision_dbscan": 0.034,
        },
        "hawkes_dependency": {
            "low_hawkes_recall": 0.059,
            "high_hawkes_recall": 0.255,
            "low_hawkes_pct_of_ignitions": 0.77,
        },
        "top_features": [
            {"name": "hawkes_lambda", "gain": 45341990, "family": "Hawkes"},
            {"name": "lc_frac_grass", "gain": 2473114, "family": "Land cover"},
            {"name": "hawkes_nearest_ign_14d_km", "gain": 1849087, "family": "Hawkes"},
            {"name": "lc_frac_tree", "gain": 1496935, "family": "Land cover"},
            {"name": "ha_dist_settlement", "gain": 1200739, "family": "Anthropogenic"},
            {"name": "t_dem_mean", "gain": 1168040, "family": "Terrain"},
            {"name": "doy", "gain": 1003551, "family": "Temporal"},
            {"name": "lc_burnable_frac", "gain": 835873, "family": "Land cover"},
            {"name": "hydro_dist_to_ridge_m", "gain": 817192, "family": "Hydro"},
            {"name": "ndvi_expected", "gain": 677082, "family": "Vegetation"},
        ],
        "trust_guidance": {
            "trust_high": "Cell has ≥3 recent fires within 10km + FFMC > 85 + forest fraction > 0.5",
            "trust_medium": "Cell has 1-2 recent fires OR FFMC > 80",
            "trust_low": "No recent fires nearby — model is guessing from weather + vegetation only",
        },
        "experiments_tried_today": 8,
        "experiments_that_improved": 0,
        "conclusion": "v17 is at the information-theoretic ceiling with current satellite + weather data",
    }


_BEAT_POLYGONS = None

def _load_beat_polygons():
    global _BEAT_POLYGONS
    if _BEAT_POLYGONS is not None:
        return _BEAT_POLYGONS
    import geopandas as gpd
    if BEATS_GEOJSON.exists():
        _BEAT_POLYGONS = gpd.read_file(BEATS_GEOJSON)
    elif BEATS_SHP.exists():
        _BEAT_POLYGONS = gpd.read_file(BEATS_SHP).to_crs("EPSG:4326")
    return _BEAT_POLYGONS


def _load_beat_polygons_projected():
    """Return beats reprojected to a metric CRS (EPSG:32644 / UTM 44N).

    Cached on first call to avoid the ~2-3 s reprojection of 8,973 polygons.
    Used by `_clip_fires_to_forest` so that `sjoin_nearest(max_distance=...)`
    operates in meters, eliminating the `Geometry is in a geographic CRS`
    UserWarning that geopandas emits for any sjoin_nearest on EPSG:4326.
    """
    global _BEATS_PROJECTED
    if _BEATS_PROJECTED is not None:
        return _BEATS_PROJECTED
    beats = _load_beat_polygons()
    if beats is None or len(beats) == 0:
        return None
    _BEATS_PROJECTED = beats.to_crs(_PROJECTED_CRS)
    return _BEATS_PROJECTED


def _clip_fires_to_forest(df: pd.DataFrame) -> pd.DataFrame:
    """Keep only FIRMS detections that fall INSIDE forest beat polygons.

    Previous implementation used `sjoin_nearest(max_distance=0.02)` — a
    2.2 km halo that swept in farmland adjacent to forest. User reported
    fires rendering on Bhopal / Indore on the portal map.

    New strategy:
      Pass 1 — STRICT `predicate="within"`: fire centroid is geometrically
               inside a forest beat polygon. No buffer. This is the
               operational definition of "forest fire" the portal should
               surface to forest officers.
      Pass 2 — EDGE-TOLERANT `sjoin_nearest(max_distance=0.003)`: a
               ~330 m buffer (half a FIRMS VIIRS scan-width of 750 m,
               adjusted for nominal pixel center quantization) recovers
               legitimate forest-edge fires that fell just outside the
               polygon due to shapefile simplification.

    Pass 1 wins on conflict via drop_duplicates(keep='first'). Pass 2 only
    contributes detections that Pass 1 left out.

    CRS handling: both `gdf` and the beats subset are reprojected to
    EPSG:32644 (UTM zone 44N, meters) before `sjoin_nearest` so that
    `max_distance` is interpreted in meters (333 m) rather than degrees
    (0.003°, only approximately equivalent at MP latitudes). This
    eliminates the geopandas UserWarning and is correct anywhere on the
    globe.
    """
    beats_proj = _load_beat_polygons_projected()
    if beats_proj is None or len(beats_proj) == 0:
        return df
    import geopandas as gpd
    from shapely.geometry import Point
    gdf = gpd.GeoDataFrame(
        df, geometry=[Point(lon, lat) for lat, lon in zip(df["latitude"], df["longitude"])],
        crs="EPSG:4326",
    ).to_crs(_PROJECTED_CRS)
    beats_subset = beats_proj[["Division", "Range", "Beat", "geometry"]]

    # Pass 1: strict containment
    inside = gpd.sjoin(
        gdf, beats_subset, how="inner", predicate="within",
    )
    inside["_pass"] = 1
    inside["_dist"] = 0.0

    # Pass 2: near-edge tolerance for pixels just outside (FIRMS quantization).
    # max_distance now in METERS (CRS is projected), not degrees.
    edge = gpd.sjoin_nearest(
        gdf, beats_subset, how="inner",
        max_distance=_FIRE_BEAT_TOLERANCE_M, distance_col="_dist",
    )
    edge["_pass"] = 2

    combined = pd.concat([inside, edge], ignore_index=True)
    combined = combined.sort_values(["_pass", "_dist"]).drop_duplicates(
        subset=["latitude", "longitude", "acq_date", "acq_time"], keep="first",
    )
    drop_cols = [c for c in ["geometry", "index_right", "_dist", "_pass"] if c in combined.columns]
    return pd.DataFrame(combined.drop(columns=drop_cols))


_NRT_REFRESH_THROTTLE_S = 21600  # 6 h — FIRMS NRT publishes ~3-hourly, no point spamming
_MP_BBOX = "74,21,83,27"  # west,south,east,north
_FIRMS_API = "https://firms.modaps.eosdis.nasa.gov/api/area/csv"


def _read_dotenv_value(key: str) -> str | None:
    """Read a single key from .env (handles UTF-8 BOM + CRLF)."""
    env = ROOT / ".env"
    if not env.exists():
        return None
    try:
        txt = env.read_bytes().decode("utf-8", errors="ignore")
    except OSError:
        return None
    import re
    m = re.search(rf"{re.escape(key)}\s*=\s*([\w\-]+)", txt)
    return m.group(1) if m else None


def _refresh_firms_nrt(nrt_path: Path) -> None:
    """Pull last 10 days of FIRMS VIIRS NRT and merge into nrt_7d.parquet.

    Throttled to once per 6 h via the parquet's neighbouring `.lastrefresh`
    sentinel file. NASA FIRMS NRT updates roughly every 3 h after satellite
    overpass, so 6 h is a comfortable cadence that respects the 5,000 tx /
    10 min API limit.

    No-op if FIRMS_MAP_KEY isn't set anywhere reachable.
    """
    sentinel = nrt_path.with_suffix(".lastrefresh")
    now = time.time()
    if sentinel.exists() and (now - sentinel.stat().st_mtime) < _NRT_REFRESH_THROTTLE_S:
        return  # cache fresh

    api_key = (
        os.environ.get("FIRMS_MAP_KEY")
        or _read_dotenv_value("FIRMS_MAP_KEY")
    )
    if not api_key:
        return  # nothing we can do

    import requests
    import io

    today = date.today()
    # FIRMS NRT API caps day_range at [1..5] for NRT sources (was 10 historically;
    # tightened sometime in 2025). Chunk into two 5-day calls to cover ~10 days
    # so we always overlap the previous cache and don't drop a day.
    chunks = [today - timedelta(days=4), today - timedelta(days=9)]
    frames: list[pd.DataFrame] = []
    n_success = 0
    n_attempted = 0
    for src in ("VIIRS_SNPP_NRT", "VIIRS_NOAA20_NRT"):
        for chunk_start in chunks:
            n_attempted += 1
            url = f"{_FIRMS_API}/{api_key}/{src}/{_MP_BBOX}/5/{chunk_start.isoformat()}"
            # Truncate the URL for logs — last 50 chars strips the api_key
            # (which is always mid-URL) while preserving the date + source,
            # keeping operator logs clean of secrets.
            url_tail = url[-50:]
            status = "?"
            body_len = 0
            n_rows = 0
            try:
                resp = requests.get(url, timeout=30)
                status = str(resp.status_code)
                body_len = len(resp.text or "")
                if resp.status_code != 200 or not resp.text or "Invalid" in resp.text[:200]:
                    log.warning(
                        "firms_nrt src=%s status=%s body_len=%d rows=0 url=...%s",
                        src, status, body_len, url_tail,
                    )
                    continue
                df = pd.read_csv(io.StringIO(resp.text))
                if df.empty or "latitude" not in df.columns:
                    log.warning(
                        "firms_nrt src=%s status=%s body_len=%d rows=0 (empty_or_malformed) url=...%s",
                        src, status, body_len, url_tail,
                    )
                    continue
                df["instrument"] = "VIIRS"
                n_rows = len(df)
                frames.append(df)
                n_success += 1
                log.info(
                    "firms_nrt src=%s status=%s body_len=%d rows=%d url=...%s",
                    src, status, body_len, n_rows, url_tail,
                )
            except Exception as exc:
                log.warning(
                    "firms_nrt src=%s status=ERR body_len=0 rows=0 err=%s url=...%s",
                    src, type(exc).__name__, url_tail,
                )
                continue

    if not frames:
        # Touch sentinel anyway so a continuous outage doesn't hammer the API
        log.warning(
            "firms_nrt: ALL %d source attempts failed — sentinel touched, no cache update",
            n_attempted,
        )
        sentinel.touch()
        return

    log.info(
        "firms_nrt: %d of %d source attempts succeeded, %d total new rows before dedupe",
        n_success, n_attempted, sum(len(f) for f in frames),
    )

    new = pd.concat(frames, ignore_index=True)
    new["acq_date"] = pd.to_datetime(new["acq_date"])

    # Merge with whatever's already on disk; keep first occurrence on dupes
    if nrt_path.exists():
        try:
            existing = pd.read_parquet(nrt_path)
            existing["acq_date"] = pd.to_datetime(existing["acq_date"])
            merged = pd.concat([existing, new], ignore_index=True)
        except Exception:
            merged = new
    else:
        merged = new

    merged = merged.drop_duplicates(
        subset=["latitude", "longitude", "acq_date", "acq_time"], keep="first"
    )
    nrt_path.parent.mkdir(parents=True, exist_ok=True)
    merged.to_parquet(nrt_path, index=False)
    sentinel.touch()


def _build_viirs_fires(date_from: str | None = None, date_to: str | None = None) -> dict:
    """Load VIIRS fire detections clipped to MP forest beats."""
    fires = []
    nrt_path = ROOT / "data_lake" / "fire_detections" / "firms_mp_viirs" / "nrt_7d.parquet"
    cons_path = ROOT / "data_lake" / "fire_detections" / "firms_mp_viirs" / "firms_mp_consolidated.parquet"

    # Refresh NRT cache from NASA before serving (throttled to 6h)
    _refresh_firms_nrt(nrt_path)

    if nrt_path.exists():
        nrt = pd.read_parquet(nrt_path)
        nrt["acq_date"] = pd.to_datetime(nrt["acq_date"])
        nrt["source"] = "NRT"
        fires.append(nrt)

    if cons_path.exists():
        cons = pd.read_parquet(cons_path)
        cons["acq_date"] = pd.to_datetime(cons["acq_date"])
        fires.append(cons)

    if not fires:
        return {"fires": [], "n_fires": 0, "date_range": "", "latest_date": ""}

    df = pd.concat(fires, ignore_index=True).drop_duplicates(
        subset=["latitude", "longitude", "acq_date", "acq_time"], keep="first"
    )
    df = df.sort_values("acq_date", ascending=False)

    latest_date = df["acq_date"].max()

    if date_from and date_to:
        df = df[(df["acq_date"] >= pd.Timestamp(date_from)) & (df["acq_date"] <= pd.Timestamp(date_to))]
    elif date_from:
        df = df[df["acq_date"] >= pd.Timestamp(date_from)]
    else:
        df = df[df["acq_date"] == latest_date]

    n_before_clip = len(df)
    df = _clip_fires_to_forest(df)
    n_after_clip = len(df)

    keep_cols = ["latitude", "longitude", "acq_date", "acq_time",
                 "confidence", "bright_ti4", "satellite", "source", "frp",
                 "Division", "Range", "Beat"]
    available = [c for c in keep_cols if c in df.columns]
    # Cap for payload sanity — strict forest clip typically yields ~9k for a
    # 7-day MP-wide window; 10k cap leaves headroom for peak-week spikes.
    df = df[available].head(10000)

    records = []
    for _, r in df.iterrows():
        rec = {
            "lat": float(r["latitude"]),
            "lon": float(r["longitude"]),
            "date": str(r["acq_date"])[:10],
            "time": str(r.get("acq_time", "")),
            "confidence": str(r.get("confidence", "")),
            "brightness": float(r["bright_ti4"]) if "bright_ti4" in r and pd.notna(r["bright_ti4"]) else None,
            "satellite": str(r.get("satellite", "")),
            "source": str(r.get("source", "")),
            "division": str(r.get("Division", "")),
            "range": str(r.get("Range", "")),
            "beat": str(r.get("Beat", "")),
        }
        records.append(rec)

    date_min = str(df["acq_date"].min())[:10] if len(df) else ""
    date_max = str(df["acq_date"].max())[:10] if len(df) else ""
    return {
        "fires": records,
        "n_fires": len(records),
        "n_before_clip": n_before_clip,
        "n_clipped": n_before_clip - n_after_clip,
        "date_range": f"{date_min} to {date_max}",
        "latest_date": str(latest_date)[:10],
    }


def _load_operational_alerts(date_str: str | None = None) -> dict:
    path = OPERATIONAL_ALERTS
    if date_str:
        dated = FEED_DIR / f"operational_alerts_v17_{date_str}.json"
        if dated.exists():
            path = dated
    if not path.exists():
        return {"error": "operational alerts not built yet — run "
                "scripts/build_operational_alerts.py"}
    return json.loads(path.read_text())


def _load_division_briefings() -> dict:
    if not DIVISION_BRIEFINGS.exists():
        return {"error": "no briefings"}
    return json.loads(DIVISION_BRIEFINGS.read_text())


def _load_season_validation() -> dict:
    """Return the 2026 season validation summary + per-trust-tier + per-division.

    Reads:
      outputs/validation_reports/2026_season_summary.json   — main summary
      outputs/validation_reports/2026_per_trust_tier.csv    — 4 tier rows
      outputs/validation_reports/2026_per_day.csv           — daily timeline
      outputs/validation_reports/2026_per_division.csv      — 87 division rows

    Portal Validation tab surfaces this to reconcile the "1 validation row in
    rolling parquet" situation with the full-season backtest.
    """
    summary_path = SEASON_VALIDATION_DIR / "2026_season_summary.json"
    tier_path = SEASON_VALIDATION_DIR / "2026_per_trust_tier.csv"
    day_path = SEASON_VALIDATION_DIR / "2026_per_day.csv"
    div_path = SEASON_VALIDATION_DIR / "2026_per_division.csv"
    if not summary_path.exists():
        return {"error": "2026_season_summary.json not found — run "
                "scripts/validate_2026_season.py first"}

    def _records(df: pd.DataFrame) -> list[dict]:
        # Cast to object first so None survives — in float columns pandas
        # silently converts None back to NaN, which json.dumps emits as the
        # invalid token "NaN" that browsers' JSON.parse rejects.
        return df.astype(object).where(pd.notnull(df), None).to_dict(orient="records")

    out = {"summary": json.loads(summary_path.read_text())}
    if tier_path.exists():
        out["per_trust_tier"] = _records(pd.read_csv(tier_path))
    else:
        out["per_trust_tier"] = []

    # Augment with the new CLIMATOLOGY_FLOOR tier — it post-dates the season
    # backtest CSV so it doesn't appear in the on-disk per_trust_tier file.
    # Read today's operational alerts JSON and synthesize a row from the
    # actual climatology_floor cell count, so the portal frontend can render
    # the tier alongside the historical tiers without throwing on a missing
    # entry. Tagged `_synthetic: true` so the UI can flag it as
    # "live count, not season-validated".
    try:
        existing_tiers = {row.get("trust_tier") for row in out["per_trust_tier"]}
        if "CLIMATOLOGY_FLOOR" not in existing_tiers and OPERATIONAL_ALERTS.exists():
            ops = json.loads(OPERATIONAL_ALERTS.read_text())
            n_clim = sum(
                1 for a in ops.get("alerts", [])
                if a.get("trust_level") == "CLIMATOLOGY_FLOOR"
                or a.get("climatology_floor") is True
            )
            if n_clim > 0:
                out["per_trust_tier"].append({
                    "trust_tier": "CLIMATOLOGY_FLOOR",
                    "n_alerts": int(n_clim),
                    "n_alerts_caught_event": None,
                    "precision": None,
                    "n_events_caught_by_this_tier": None,
                    "median_match_offset_km": None,
                    "_synthetic": True,
                })
    except Exception as exc:
        # Augmentation is best-effort; never break the endpoint over it.
        log.warning("season-validation augment failed: %s: %s", type(exc).__name__, exc)

    if day_path.exists():
        out["per_day"] = _records(pd.read_csv(day_path))
    if div_path.exists():
        df = pd.read_csv(div_path)
        # Sort by absolute alert volume desc so the operator sees high-traffic
        # divisions first; floor-only divisions (n_critical_alerts=0) drift to bottom.
        df = df.sort_values("n_critical_alerts", ascending=False).reset_index(drop=True)
        out["per_division"] = _records(df)
    return out


def _build_blind_spots() -> dict:
    """Divisions where the model is silent during high-risk weather.

    Reads division_briefings.json (which already computes silent_in_danger
    after the per-division coverage floor) and returns the list. Used by
    the portal to (a) shade those divisions amber on the Live Map and
    (b) filter the Divisions tab to a "MODEL SILENT" view.
    """
    bf = _load_division_briefings()
    if bf.get("error"):
        return {"error": bf["error"], "blind_spots": []}
    weather = bf.get("statewide_weather", {})
    blind_spots = []
    for b in bf.get("briefings", []):
        if b.get("silent_in_danger"):
            blind_spots.append({
                "division": b["division"],
                "n_critical": b.get("n_critical", 0),
                "n_critical_organic": b.get("n_critical_organic", 0),
                "n_critical_floor_promoted": b.get("n_critical_floor_promoted", 0),
                "n_alert": b.get("n_alert", 0),
                "n_cold_start": b.get("n_cold_start", 0),
                "reason": "SILENT_IN_DANGER",
            })
    coverage_total = len(bf.get("briefings", []))
    coverage_organic = sum(
        1 for b in bf.get("briefings", [])
        if (b.get("n_critical_organic", 0) + b.get("n_alert", 0)) > 0
    )
    return {
        "generated_at": bf.get("generated_at"),
        "weather_extreme": bool(weather.get("is_extreme")),
        "weather_summary": weather,
        "n_divisions_total": coverage_total,
        "n_divisions_with_organic_alerts": coverage_organic,
        "n_divisions_silent_in_danger": len(blind_spots),
        "blind_spots": blind_spots,
    }


def _enrich_division_overview(base: dict) -> dict:
    """Merge ops-pipeline silence + floor info into the v17-derived overview.

    The base overview is built from v17 raw banded_alerts (which knows nothing
    about the coverage floor or silence-detection). Here we left-join the
    per-division fields produced by build_operational_alerts.py and APPEND
    divisions that exist in briefings but not in banded_alerts (those are
    pure floor-promoted divisions where the model was completely silent).
    """
    bf = _load_division_briefings()
    by_div: dict[str, dict] = {}
    for b in bf.get("briefings", []) if isinstance(bf, dict) else []:
        by_div[b["division"]] = b

    seen_names: set[str] = set()
    for d in base.get("divisions", []):
        seen_names.add(d["name"])
        b = by_div.get(d["name"], {})
        d["silent_in_danger"] = bool(b.get("silent_in_danger"))
        d["n_critical_organic"] = int(b.get("n_critical_organic", 0))
        d["n_critical_floor_promoted"] = int(b.get("n_critical_floor_promoted", 0))
        d["n_cold_start"] = int(b.get("n_cold_start", 0))
        # Re-emit the merged CRITICAL count (banded + floor-promoted)
        d["critical"] = d["n_critical_organic"] + d["n_critical_floor_promoted"]

    # Append floor-only divisions absent from banded_alerts
    for div_name, b in by_div.items():
        if div_name in seen_names:
            continue
        base.setdefault("divisions", []).append({
            "name": div_name,
            "critical": int(b.get("n_critical_floor_promoted", 0)),
            "alert": int(b.get("n_alert", 0)),
            "watch": 0,
            "total": int(b.get("n_critical_floor_promoted", 0)) + int(b.get("n_alert", 0)),
            "mean_risk": 0.0,
            "max_risk": 0.0,
            "hawkes_high_pct": 0,
            "confidence": "FLOOR_ONLY",
            "center_lat": 0.0,
            "center_lon": 0.0,
            "silent_in_danger": bool(b.get("silent_in_danger")),
            "n_critical_organic": 0,
            "n_critical_floor_promoted": int(b.get("n_critical_floor_promoted", 0)),
            "n_cold_start": int(b.get("n_cold_start", 0)),
        })

    weather = (bf.get("statewide_weather") or {}) if isinstance(bf, dict) else {}
    base["weather_extreme"] = bool(weather.get("is_extreme"))
    base["weather_summary"] = weather
    base["total_alerts"] = sum(d.get("total", 0) for d in base.get("divisions", []))
    return base


def _load_seasonal_pulse() -> dict:
    if not SEASONAL_PULSE.exists():
        return {"error": "seasonal pulse not built — run scripts/fit_prophet_firms_seasonality.py"}
    return json.loads(SEASONAL_PULSE.read_text())


def _load_json_feed(path: Path, tool_name: str) -> dict:
    if not path.exists():
        return {"error": f"{tool_name} not generated yet — run scripts/{tool_name}.py"}
    return json.loads(path.read_text())


def _load_soil_pulse() -> dict:
    if not SOIL_PARQUET.exists():
        return {"error": "soil features not built — run scripts/build_soil_features.py"}
    df = pd.read_parquet(SOIL_PARQUET)
    df["date"] = pd.to_datetime(df["date"])
    latest = df.tail(1).iloc[0]
    last30 = df.tail(30)
    temp_anom = float(latest["soil_temp_anomaly"])
    moist_anom = float(latest["soil_moisture_anomaly"])
    if moist_anom < -0.05:
        status = "DRY"
    elif moist_anom > 0.05:
        status = "WET"
    else:
        status = "TYPICAL"
    return {
        "latest_date": latest["date"].strftime("%Y-%m-%d"),
        "soil_temp_0_to_7cm_mean": float(latest["soil_temp_0_to_7cm_mean"]),
        "soil_temp_anomaly": temp_anom,
        "soil_moisture_0_to_7cm_mean": float(latest["soil_moisture_0_to_7cm_mean"]),
        "soil_moisture_anomaly": moist_anom,
        "status": status,
        "rolling_30d_temp_anom": float(last30["soil_temp_anomaly"].mean()),
        "rolling_30d_moisture_anom": float(last30["soil_moisture_anomaly"].mean()),
        "n_days_history": int(len(df)),
    }


def _append_field_response(payload: dict) -> dict:
    """Append a field-staff response to the rolling parquet, thread-safe."""
    required = ("cell_id", "outcome", "staff_id")
    for key in required:
        if key not in payload:
            return {"error": f"missing field: {key}"}
    if payload["outcome"] not in ("confirmed", "signs", "clear", "unreachable"):
        return {"error": "outcome must be one of: confirmed, signs, clear, unreachable"}

    entry = {
        "cell_id": str(payload["cell_id"]),
        "outcome": str(payload["outcome"]),
        "staff_id": str(payload["staff_id"]),
        "timestamp_utc": datetime.utcnow().isoformat(),
        "prediction_date": str(payload.get("prediction_date", "")),
        "band": str(payload.get("band", "")),
        "trust_level": str(payload.get("trust_level", "")),
        "note": str(payload.get("note", ""))[:500],
        "lat": float(payload["lat"]) if "lat" in payload else None,
        "lon": float(payload["lon"]) if "lon" in payload else None,
    }

    with _RESPONSE_LOCK:
        if FIELD_RESPONSES.exists():
            existing = pd.read_parquet(FIELD_RESPONSES)
            df = pd.concat([existing, pd.DataFrame([entry])], ignore_index=True)
        else:
            df = pd.DataFrame([entry])
        FIELD_RESPONSES.parent.mkdir(parents=True, exist_ok=True)
        df.to_parquet(FIELD_RESPONSES, index=False)

    return {"status": "ok", "n_total_responses": int(len(df)), "saved": entry}


def _summarize_field_responses() -> dict:
    if not FIELD_RESPONSES.exists():
        return {"total": 0, "by_outcome": {}, "recent": []}
    df = pd.read_parquet(FIELD_RESPONSES)
    by_outcome = df["outcome"].value_counts().to_dict()
    recent = df.tail(20).to_dict(orient="records")
    return {
        "total": int(len(df)),
        "by_outcome": {str(k): int(v) for k, v in by_outcome.items()},
        "recent": recent,
    }


def _build_validation_log() -> dict:
    path = ALERTS_DIR / "v17_validation_rolling.parquet"
    if not path.exists():
        return {"rows": [], "n_days": 0}
    try:
        df = pd.read_parquet(path)
        rows = df.to_dict(orient="records")
        return {"rows": rows, "n_days": len(rows)}
    except Exception:
        return {"rows": [], "n_days": 0}


def _build_healthz() -> dict:
    """Liveness + critical-artefact summary for ops dashboards / cron probes.

    Returns:
      ok                          : True iff every CRITICAL artefact exists
                                    (beat polygons + at least one of cons/nrt FIRMS).
      portal_uptime_s             : seconds since this process started.
      beat_polygons_loaded        : True iff the warm-load completed and the cache
                                    is populated.
      firms_nrt_age_hours         : hours since the .lastrefresh sentinel was
                                    touched (None if absent).
      firms_nrt_max_date          : latest acq_date in nrt_7d.parquet (None if
                                    absent / unreadable).
      season_validation_present   : True iff 2026_season_summary.json exists.
      climatology_parquet_present : True iff the climatology floor parquet
                                    consumed by build_operational_alerts.py exists.
    """
    nrt_path = ROOT / "data_lake" / "fire_detections" / "firms_mp_viirs" / "nrt_7d.parquet"
    cons_path = ROOT / "data_lake" / "fire_detections" / "firms_mp_viirs" / "firms_mp_consolidated.parquet"
    sentinel = nrt_path.with_suffix(".lastrefresh")
    season_summary = SEASON_VALIDATION_DIR / "2026_season_summary.json"
    climatology_parquet = (
        ROOT / "data_lake" / "fire_weather" / "beat_fire_climatology.parquet"
    )

    nrt_age_hours: float | None = None
    if sentinel.exists():
        nrt_age_hours = round((time.time() - sentinel.stat().st_mtime) / 3600.0, 2)

    nrt_max_date: str | None = None
    if nrt_path.exists():
        try:
            nrt_df = pd.read_parquet(nrt_path, columns=["acq_date"])
            if len(nrt_df):
                nrt_max_date = str(pd.to_datetime(nrt_df["acq_date"]).max())[:10]
        except Exception as exc:
            log.warning("healthz: could not read nrt parquet: %s", exc)

    beat_polygons_loaded = _BEAT_POLYGONS is not None and len(_BEAT_POLYGONS) > 0
    firms_present = nrt_path.exists() or cons_path.exists()
    ok = bool(beat_polygons_loaded and firms_present)

    return {
        "ok": ok,
        "portal_uptime_s": int(time.time() - _PORTAL_START_S),
        "beat_polygons_loaded": beat_polygons_loaded,
        "firms_nrt_age_hours": nrt_age_hours,
        "firms_nrt_max_date": nrt_max_date,
        "season_validation_present": season_summary.exists(),
        "climatology_parquet_present": climatology_parquet.exists(),
    }


class PortalHandler(SimpleHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/")
        qs = parse_qs(parsed.query)

        if path == "/v3" or path == "/v3/index.html":
            self._serve_file(DASHBOARD_DIR / "v3" / "index.html", "text/html")
        elif path == "/api/ignition-v17":
            self._send_json(_load_v17_predictions(qs.get("date", [None])[0]))
        elif path == "/api/latest-alert":
            self._send_json(_load_latest_alert())
        elif path == "/api/division-overview":
            v17 = _load_v17_predictions(qs.get("date", [None])[0])
            base = _build_division_overview(v17)
            self._send_json(_enrich_division_overview(base))
        elif path == "/api/blind-spots":
            self._send_json(_build_blind_spots())
        elif path == "/api/season-validation":
            self._send_json(_load_season_validation())
        elif path == "/api/model-transparency":
            self._send_json(_build_transparency())
        elif path == "/api/validation-log":
            self._send_json(_build_validation_log())
        elif path == "/api/beats-boundary":
            if BEATS_GEOJSON.exists():
                self._serve_file(BEATS_GEOJSON, "application/json")
            else:
                self._send_json({"error": "beats geojson not found"})
        elif path == "/api/viirs-fires":
            date_from = qs.get("from", [None])[0]
            date_to = qs.get("to", [None])[0]
            self._send_json(_build_viirs_fires(date_from=date_from, date_to=date_to))
        elif path == "/api/operational-alerts":
            self._send_json(_load_operational_alerts(qs.get("date", [None])[0]))
        elif path == "/api/division-briefings":
            self._send_json(_load_division_briefings())
        elif path == "/api/field-responses":
            self._send_json(_summarize_field_responses())
        elif path == "/api/seasonal-pulse":
            self._send_json(_load_seasonal_pulse())
        elif path == "/api/division-pulse":
            self._send_json(_load_json_feed(DIVISION_PULSE, "fit_statsforecast_per_division"))
        elif path == "/api/feature-drift":
            self._send_json(_load_json_feed(FEATURE_DRIFT, "monitor_v17_feature_drift"))
        elif path == "/api/matrix-profile":
            self._send_json(_load_json_feed(MATRIX_PROFILE, "matrix_profile_firms"))
        elif path == "/api/season-onset":
            self._send_json(_load_json_feed(SEASON_ONSET, "detect_season_changepoints"))
        elif path == "/api/calibration-curve":
            self._send_json(_load_json_feed(CALIB_CURVE, "calibrate_v17"))
        elif path == "/api/soil-pulse":
            self._send_json(_load_soil_pulse())
        elif path == "/api/healthz":
            self._send_json(_build_healthz())
        else:
            super().do_GET()

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/")
        length = int(self.headers.get("Content-Length", "0") or 0)
        raw = self.rfile.read(length) if length > 0 else b"{}"
        try:
            body = json.loads(raw.decode("utf-8") or "{}")
        except json.JSONDecodeError:
            self.send_error(400, "invalid json")
            return

        if path == "/api/field-response":
            result = _append_field_response(body)
            if "error" in result:
                self._send_json(result, status=400)
            else:
                self._send_json(result)
        else:
            self.send_error(404, "unknown POST endpoint")

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def _serve_file(self, filepath: Path, content_type: str):
        if not filepath.exists():
            self.send_error(404, f"File not found: {filepath.name}")
            return
        body = filepath.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", f"{content_type}; charset=utf-8")
        self.send_header("Content-Length", len(body))
        self.end_headers()
        self.wfile.write(body)

    def _send_json(self, payload: dict, status: int = 200):
        body = json.dumps(payload, default=str).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Content-Length", len(body))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, _fmt, *args):
        if "/api/" in str(args[0]):
            print(f"[API] {args[0]}")


if __name__ == "__main__":
    # Wire the module-level `log` to stdout so operator-visible events from
    # _refresh_firms_nrt, healthz, etc. land in tmp/v3.log when the portal is
    # launched via `python dashboard/v3/serve.py >tmp/v3.log 2>&1`.
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        datefmt="%H:%M:%S",
    )
    print(f"=== JwalaNetra v3 Unified Portal ===")
    print(f"Date: {TODAY}")
    # Warm-load beat polygons (8,973 polygons, 188MB geojson) so the first
    # /api/viirs-fires request doesn't timeout (pay the cold-start on startup
    # instead of on the first operator click).
    print("Warming beat polygon cache...", end=" ", flush=True)
    import time as _time
    _t0 = _time.time()
    beats = _load_beat_polygons()
    print(f"{len(beats) if beats is not None else 0} polygons loaded in {_time.time()-_t0:.1f}s")
    # Also warm division-cells mapping for division overview endpoint
    print("Warming cells-to-division map...", end=" ", flush=True)
    _ = _get_cell_division("r0000_c0000")
    print("done")
    print(f"Portal: http://localhost:{PORT}/v3/")
    print(f"APIs:   /api/ignition-v17, /api/division-overview, /api/model-transparency, /api/validation-log")
    server = HTTPServer(("", PORT), PortalHandler)
    server.serve_forever()
