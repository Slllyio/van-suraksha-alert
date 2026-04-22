"""Extensive 2026-fire-season validation of v17.5 + per-division coverage floor.

Reads:
  outputs/dashboard_feed/ignition_risk_v17_YYYY-MM-DD.json     (raw v17.5)
  outputs/dashboard_feed/operational_alerts_v17_YYYY-MM-DD.json (with floor + trust tiers)
  data_lake/fire_detections/firms_mp_viirs/firms_mp_consolidated.parquet (ground truth)

For each date D in window:
  1. Cluster FIRMS detections in [D, D+CATCH_WINDOW_DAYS] into ignition events
     using DBSCAN(eps=2km, min_samples=2). Matches v17 training-label grain.
  2. For each event, find the nearest predicted cell within MATCH_RADIUS_KM
     (separately per band CRITICAL > ALERT > WATCH).
  3. Tag each event with:
       caught_at_band, caught_by_trust_tier, caught_by_floor,
       spatial_offset_km, temporal_offset_days
  4. For each predicted CRITICAL cell, compute precision = "did ANY event
     land within MATCH_RADIUS_KM and within [D, D+CATCH_WINDOW_DAYS]?".

Aggregates across all dates into:
  outputs/validation_reports/2026_season_summary.json
  outputs/validation_reports/2026_per_day.csv
  outputs/validation_reports/2026_per_division.csv
  outputs/validation_reports/2026_per_fire.csv
  outputs/validation_reports/2026_per_trust_tier.csv

Usage:
  python scripts/validate_2026_season.py
  python scripts/validate_2026_season.py --start 2026-02-16 --end 2026-04-07
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.spatial import cKDTree
from sklearn.cluster import DBSCAN

sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)
logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger()

ROOT = Path(__file__).resolve().parents[1]
FEED_DIR = ROOT / "outputs" / "dashboard_feed"
FIRMS_CONS = ROOT / "data_lake" / "fire_detections" / "firms_mp_viirs" / "firms_mp_consolidated.parquet"
FIRMS_NRT = ROOT / "data_lake" / "fire_detections" / "firms_mp_viirs" / "nrt_7d.parquet"
OUT_DIR = ROOT / "outputs" / "validation_reports"

# Catch window: a prediction on day D is "credited" with any FIRMS event
# detected in the next 7 days (matches v17 training-window definition).
CATCH_WINDOW_DAYS = 7

# Match radius: a predicted cell catches an event if the event centroid
# falls within this distance (km). Cells are ~2km wide so 4km gives
# tolerance for FIRMS pixel quantization (375m) and centroid offset.
MATCH_RADIUS_KM = 4.0

# DBSCAN clustering of FIRMS detections into ignition events.
DBSCAN_EPS_DEG = 2.0 / 111.0   # ~2 km in degrees latitude
DBSCAN_MIN_SAMPLES = 2          # Single-pixel detections excluded as noise

# Confidence filter — only count "high"/"nominal"/"h"/"n" detections as
# ground truth. Low-confidence FIRMS are noisy and inflate denominators.
HIGH_CONF_VALUES = {"h", "n", "high", "nominal"}


# ---------------------------------------------------------------------------
# Load helpers
# ---------------------------------------------------------------------------

def load_firms(forest_clip: bool = True) -> pd.DataFrame:
    """Load + concat all FIRMS detections, optionally forest-beat clipped.

    v17 scores FOREST cells only; agricultural-field fires outside forest
    beats are not the model's target and inflate the denominator. The portal
    `/api/viirs-fires` endpoint does the same clip — we mirror it here so
    validation numbers reconcile with what operators see in the UI.
    """
    frames = []
    if FIRMS_CONS.exists():
        df = pd.read_parquet(FIRMS_CONS)
        df["acq_date"] = pd.to_datetime(df["acq_date"])
        frames.append(df)
    if FIRMS_NRT.exists():
        df = pd.read_parquet(FIRMS_NRT)
        df["acq_date"] = pd.to_datetime(df["acq_date"])
        frames.append(df)
    if not frames:
        raise FileNotFoundError("No FIRMS parquets found")
    out = pd.concat(frames, ignore_index=True)
    out = out.drop_duplicates(
        subset=["latitude", "longitude", "acq_date", "acq_time"], keep="first"
    )
    # Confidence filter
    out["confidence"] = out["confidence"].astype(str).str.lower()
    out = out[out["confidence"].isin(HIGH_CONF_VALUES)].reset_index(drop=True)

    if forest_clip:
        log.info("Forest-beat clipping %d FIRMS detections...", len(out))
        out = _forest_clip(out)
        log.info("  After clip: %d (kept %.1f%%)", len(out),
                 100 * len(out) / max(1, len(out) + 0))
    return out


def _forest_clip(df: pd.DataFrame) -> pd.DataFrame:
    """Spatial-join FIRMS to mp_beats polygons. Same logic as portal."""
    import geopandas as gpd
    from shapely.geometry import Point
    beats_path = ROOT / "data" / "aoi" / "mp_beats_wgs84.geojson"
    if not beats_path.exists():
        log.warning("No beats geojson at %s — skipping forest clip", beats_path)
        return df
    beats = gpd.read_file(beats_path)
    gdf = gpd.GeoDataFrame(
        df, geometry=[Point(lon, lat) for lat, lon in zip(df["latitude"], df["longitude"])],
        crs="EPSG:4326",
    )
    joined = gpd.sjoin_nearest(
        gdf, beats[["Division", "Range", "Beat", "geometry"]],
        how="inner", max_distance=0.02, distance_col="_dist",
    )
    joined = joined.sort_values("_dist").drop_duplicates(
        subset=["latitude", "longitude", "acq_date", "acq_time"], keep="first"
    )
    return pd.DataFrame(joined.drop(columns=["geometry", "index_right", "_dist"]))


def cluster_firms_to_events(firms_window: pd.DataFrame) -> pd.DataFrame:
    """DBSCAN-cluster FIRMS detections into ignition events.

    Returns one row per event with centroid lat/lon, first detection date,
    and member count. Matches v17 training-label clustering.
    """
    if len(firms_window) == 0:
        return pd.DataFrame(columns=["event_id", "lat", "lon", "first_date", "n_dets", "max_frp"])
    coords = firms_window[["latitude", "longitude"]].to_numpy()
    db = DBSCAN(eps=DBSCAN_EPS_DEG, min_samples=DBSCAN_MIN_SAMPLES, metric="euclidean").fit(coords)
    firms_window = firms_window.copy()
    firms_window["event_id"] = db.labels_
    # Drop noise (label = -1)
    valid = firms_window[firms_window["event_id"] >= 0]
    if len(valid) == 0:
        return pd.DataFrame(columns=["event_id", "lat", "lon", "first_date", "n_dets", "max_frp"])
    grouped = valid.groupby("event_id").agg(
        lat=("latitude", "mean"),
        lon=("longitude", "mean"),
        first_date=("acq_date", "min"),
        n_dets=("latitude", "size"),
        max_frp=("frp", "max"),
    ).reset_index()
    return grouped


def haversine_km(lat1: float, lon1: float, lat2: np.ndarray, lon2: np.ndarray) -> np.ndarray:
    """Fast haversine distance from one point to a vector of points."""
    R = 6371.0
    lat1r = np.radians(lat1)
    lat2r = np.radians(lat2)
    dlat = lat2r - lat1r
    dlon = np.radians(lon2 - lon1)
    a = np.sin(dlat / 2) ** 2 + np.cos(lat1r) * np.cos(lat2r) * np.sin(dlon / 2) ** 2
    return 2 * R * np.arcsin(np.sqrt(a))


# ---------------------------------------------------------------------------
# Per-day evaluation
# ---------------------------------------------------------------------------

def evaluate_day(
    target_date: pd.Timestamp,
    firms_in_window: pd.DataFrame,
    ops_json: dict,
) -> tuple[list[dict], list[dict]]:
    """Evaluate one prediction date.

    Returns (per_event_records, per_alert_records):
      per_event_records: one row per FIRMS event in [D, D+7]; how it was caught
      per_alert_records: one row per CRITICAL alert; whether it caught an event
    """
    events = cluster_firms_to_events(firms_in_window)
    alerts = ops_json.get("alerts", [])
    if not alerts:
        return [], []

    alerts_df = pd.DataFrame(alerts)
    alerts_df["band"] = alerts_df["budget_tier"].fillna(alerts_df.get("band", "WATCH"))
    alerts_df["trust_level"] = alerts_df["trust_level"].fillna("MEDIUM")
    alerts_df["floor_promoted"] = alerts_df.get("floor_promoted", False).fillna(False).astype(bool)

    # KDTree on alert lat/lon (degrees) for fast nearest lookup; we'll re-check
    # the matched distance using haversine for accurate km units.
    alert_coords = alerts_df[["lat", "lon"]].to_numpy()
    alert_tree = cKDTree(alert_coords) if len(alert_coords) > 0 else None

    BAND_RANK = {"CRITICAL": 3, "ALERT": 2, "WATCH": 1}
    per_event = []
    for _, ev in events.iterrows():
        # Find K nearest alerts; check each against MATCH_RADIUS_KM
        if alert_tree is None:
            continue
        k = min(10, len(alerts_df))
        _, idxs = alert_tree.query([ev.lat, ev.lon], k=k)
        if k == 1:
            idxs = [int(idxs)]
        else:
            idxs = [int(i) for i in idxs]

        best_band_rank = 0
        best_alert = None
        best_distance = float("inf")
        for ai in idxs:
            cand = alerts_df.iloc[ai]
            d_km = haversine_km(ev.lat, ev.lon, np.array([cand.lat]), np.array([cand.lon]))[0]
            if d_km > MATCH_RADIUS_KM:
                continue
            br = BAND_RANK.get(cand.band, 0)
            if br > best_band_rank or (br == best_band_rank and d_km < best_distance):
                best_band_rank = br
                best_alert = cand
                best_distance = d_km

        if best_alert is None:
            per_event.append({
                "date": target_date.strftime("%Y-%m-%d"),
                "event_lat": float(ev.lat),
                "event_lon": float(ev.lon),
                "first_detection_date": ev.first_date.strftime("%Y-%m-%d"),
                "n_dets": int(ev.n_dets),
                "max_frp": float(ev.max_frp) if pd.notna(ev.max_frp) else None,
                "caught_at_band": "MISSED",
                "caught_by_trust_tier": "",
                "caught_by_floor": False,
                "caught_by_division": "",
                "spatial_offset_km": None,
                "offset_east_km": None,
                "offset_north_km": None,
                "bearing_deg": None,
                "temporal_offset_days": None,
            })
        else:
            tdays = (ev.first_date - target_date).days
            # Signed offset vector from alert -> event (km east/north).
            # east_km > 0 means event is EAST of alert; positive north_km means NORTH.
            lat_mid_rad = np.radians((ev.lat + float(best_alert["lat"])) / 2)
            east_km = float((ev.lon - float(best_alert["lon"])) * 111.320 * np.cos(lat_mid_rad))
            north_km = float((ev.lat - float(best_alert["lat"])) * 110.574)
            # Bearing in compass degrees from alert -> event (0=N, 90=E, 180=S, 270=W)
            bearing = float((np.degrees(np.arctan2(east_km, north_km)) + 360) % 360)
            per_event.append({
                "date": target_date.strftime("%Y-%m-%d"),
                "event_lat": float(ev.lat),
                "event_lon": float(ev.lon),
                "first_detection_date": ev.first_date.strftime("%Y-%m-%d"),
                "n_dets": int(ev.n_dets),
                "max_frp": float(ev.max_frp) if pd.notna(ev.max_frp) else None,
                "caught_at_band": str(best_alert.band),
                "caught_by_trust_tier": str(best_alert.trust_level),
                "caught_by_floor": bool(best_alert.floor_promoted),
                "caught_by_division": str(best_alert.get("division", "")),
                "spatial_offset_km": float(best_distance),
                "offset_east_km": east_km,
                "offset_north_km": north_km,
                "bearing_deg": bearing,
                "temporal_offset_days": int(tdays),
            })

    # Per-alert precision: did each CRITICAL catch any event?
    per_alert = []
    crit_alerts = alerts_df[alerts_df["band"] == "CRITICAL"]
    if len(events) > 0:
        event_coords = events[["lat", "lon"]].to_numpy()
        event_tree = cKDTree(event_coords)
    else:
        event_tree = None

    for _, alert in crit_alerts.iterrows():
        a_lat = float(alert["lat"])
        a_lon = float(alert["lon"])
        if event_tree is None:
            caught = False
            offset = None
        else:
            _, ei = event_tree.query([a_lat, a_lon], k=1)
            ei = int(ei) if np.isscalar(ei) else int(ei.flat[0])
            d_km = haversine_km(
                a_lat, a_lon,
                np.array([events.iloc[ei].lat]),
                np.array([events.iloc[ei].lon]),
            )[0]
            caught = d_km <= MATCH_RADIUS_KM
            offset = float(d_km) if caught else None
        per_alert.append({
            "date": target_date.strftime("%Y-%m-%d"),
            "cell_id": str(alert["cell_id"]),
            "division": str(alert.get("division", "")),
            "trust_level": str(alert["trust_level"]),
            "floor_promoted": bool(alert["floor_promoted"]),
            "is_cold_start": bool(alert.get("is_cold_start", False)),
            "rank": float(alert["rank"]),
            "ignition_risk": float(alert["ignition_risk"]),
            "caught_an_event": bool(caught),
            "match_offset_km": offset,
        })

    return per_event, per_alert


# ---------------------------------------------------------------------------
# Aggregation
# ---------------------------------------------------------------------------

def per_day_summary(per_event: pd.DataFrame, per_alert: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for d, eg in per_event.groupby("date"):
        ag = per_alert[per_alert["date"] == d]
        n_events = len(eg)
        n_caught = (eg["caught_at_band"] != "MISSED").sum()
        n_caught_critical = (eg["caught_at_band"] == "CRITICAL").sum()
        n_caught_floor = (eg["caught_by_floor"] == True).sum()  # noqa: E712
        n_crit = len(ag)
        n_crit_hit = ag["caught_an_event"].sum()
        rows.append({
            "date": d,
            "n_events": int(n_events),
            "n_caught_any_band": int(n_caught),
            "n_caught_critical": int(n_caught_critical),
            "n_caught_by_floor": int(n_caught_floor),
            "recall_any_band": float(n_caught / n_events) if n_events else None,
            "recall_critical": float(n_caught_critical / n_events) if n_events else None,
            "n_critical_alerts": int(n_crit),
            "n_critical_caught_event": int(n_crit_hit),
            "precision_critical": float(n_crit_hit / n_crit) if n_crit else None,
            "median_spatial_offset_km": float(eg["spatial_offset_km"].median())
                if eg["spatial_offset_km"].notna().any() else None,
            "median_temporal_offset_days": float(eg["temporal_offset_days"].median())
                if eg["temporal_offset_days"].notna().any() else None,
        })
    return pd.DataFrame(rows).sort_values("date").reset_index(drop=True)


def per_division_summary(per_event: pd.DataFrame, per_alert: pd.DataFrame) -> pd.DataFrame:
    rows = []
    all_divs = set(per_alert["division"].dropna().unique()) | set(
        per_event[per_event["caught_by_division"] != ""]["caught_by_division"].unique()
    )
    for div in sorted(all_divs):
        eg = per_event[per_event["caught_by_division"] == div]
        ag = per_alert[per_alert["division"] == div]
        n_events_caught = len(eg)
        n_crit = len(ag)
        n_crit_hit = ag["caught_an_event"].sum()
        n_crit_floor = ag["floor_promoted"].sum()
        n_floor_hit = ag[ag["floor_promoted"] & ag["caught_an_event"]].shape[0]
        rows.append({
            "division": div,
            "n_events_caught": int(n_events_caught),
            "n_critical_alerts": int(n_crit),
            "n_critical_floor_promoted": int(n_crit_floor),
            "n_critical_caught_event": int(n_crit_hit),
            "n_floor_caught_event": int(n_floor_hit),
            "precision_critical": float(n_crit_hit / n_crit) if n_crit else None,
            "precision_floor": float(n_floor_hit / n_crit_floor) if n_crit_floor else None,
        })
    return pd.DataFrame(rows).sort_values("n_critical_alerts", ascending=False).reset_index(drop=True)


def per_trust_tier_summary(per_alert: pd.DataFrame, per_event: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for tier in ["HIGH", "MEDIUM", "COLD_START", "DIVISION_FLOOR"]:
        ag = per_alert[per_alert["trust_level"] == tier]
        eg_caught = per_event[per_event["caught_by_trust_tier"] == tier]
        n_alerts = len(ag)
        n_alert_hits = ag["caught_an_event"].sum()
        n_caught_events = len(eg_caught)
        rows.append({
            "trust_tier": tier,
            "n_alerts": int(n_alerts),
            "n_alerts_caught_event": int(n_alert_hits),
            "precision": float(n_alert_hits / n_alerts) if n_alerts else None,
            "n_events_caught_by_this_tier": int(n_caught_events),
            "median_match_offset_km": float(ag["match_offset_km"].median())
                if ag["match_offset_km"].notna().any() else None,
        })
    return pd.DataFrame(rows)


def season_summary(per_event: pd.DataFrame, per_alert: pd.DataFrame, n_days: int) -> dict:
    n_events = len(per_event)
    n_caught = (per_event["caught_at_band"] != "MISSED").sum()
    n_caught_crit = (per_event["caught_at_band"] == "CRITICAL").sum()
    n_caught_floor = per_event["caught_by_floor"].sum()
    n_crit_alerts = len(per_alert)
    n_crit_hit = per_alert["caught_an_event"].sum()
    n_floor_alerts = per_alert["floor_promoted"].sum()
    n_floor_hits = per_alert[per_alert["floor_promoted"] & per_alert["caught_an_event"]].shape[0]

    # Unique-event metrics: each real fire event appears in up to 7 overlapping
    # [D, D+7] catch-windows. The windowed metric above counts each window-entry
    # separately (correct for "average per-day prediction quality"); the unique
    # metric below collapses by (event_lat, event_lon, first_detection_date) to
    # answer "did we catch this fire at least once during the season".
    ev_key = per_event.assign(
        key=per_event.apply(
            lambda r: f"{r.first_detection_date}|"
                      f"{round(r.event_lat, 2)}|{round(r.event_lon, 2)}",
            axis=1,
        )
    )
    unique = ev_key.groupby("key").agg(
        caught_ever=("caught_at_band", lambda s: (s != "MISSED").any()),
        caught_crit_ever=("caught_at_band", lambda s: (s == "CRITICAL").any()),
        best_band=("caught_at_band", lambda s: s[s != "MISSED"].iloc[0]
                   if (s != "MISSED").any() else "MISSED"),
    ).reset_index()
    n_unique = len(unique)
    n_unique_caught = int(unique["caught_ever"].sum())
    n_unique_caught_crit = int(unique["caught_crit_ever"].sum())

    return {
        "window_days": int(n_days),
        "n_ignition_events_observed": int(n_events),
        "n_unique_ignition_events": int(n_unique),
        "unique_recall_any_band": float(n_unique_caught / n_unique) if n_unique else None,
        "unique_recall_critical": float(n_unique_caught_crit / n_unique) if n_unique else None,
        "n_caught_any_band": int(n_caught),
        "n_caught_critical": int(n_caught_crit),
        "n_caught_by_floor_promoted_alerts": int(n_caught_floor),
        "season_recall_any_band": float(n_caught / n_events) if n_events else None,
        "season_recall_critical": float(n_caught_crit / n_events) if n_events else None,
        "season_recall_floor_share": float(n_caught_floor / n_caught) if n_caught else None,
        "n_critical_alerts_total": int(n_crit_alerts),
        "n_critical_alerts_floor_promoted": int(n_floor_alerts),
        "n_critical_caught_event": int(n_crit_hit),
        "n_floor_caught_event": int(n_floor_hits),
        "season_precision_critical": float(n_crit_hit / n_crit_alerts) if n_crit_alerts else None,
        "season_precision_floor": float(n_floor_hits / n_floor_alerts) if n_floor_alerts else None,
        "median_spatial_offset_km": float(per_event["spatial_offset_km"].median())
            if per_event["spatial_offset_km"].notna().any() else None,
        "median_temporal_offset_days": float(per_event["temporal_offset_days"].median())
            if per_event["temporal_offset_days"].notna().any() else None,
        "spatial_offset_histogram_km": {
            "0-2": int(((per_event["spatial_offset_km"] >= 0) & (per_event["spatial_offset_km"] < 2)).sum()),
            "2-4": int(((per_event["spatial_offset_km"] >= 2) & (per_event["spatial_offset_km"] < 4)).sum()),
            "4-8": int(((per_event["spatial_offset_km"] >= 4) & (per_event["spatial_offset_km"] < 8)).sum()),
            "8-16": int(((per_event["spatial_offset_km"] >= 8) & (per_event["spatial_offset_km"] < 16)).sum()),
            "missed": int((per_event["caught_at_band"] == "MISSED").sum()),
        },
        "temporal_offset_histogram_days": {
            "same_day": int((per_event["temporal_offset_days"] == 0).sum()),
            "+1d": int((per_event["temporal_offset_days"] == 1).sum()),
            "+2-3d": int(((per_event["temporal_offset_days"] >= 2) & (per_event["temporal_offset_days"] <= 3)).sum()),
            "+4-7d": int(((per_event["temporal_offset_days"] >= 4) & (per_event["temporal_offset_days"] <= 7)).sum()),
            "missed": int((per_event["caught_at_band"] == "MISSED").sum()),
        },
        "directional_bias": _directional_bias(per_event),
        "generated_at": datetime.now().isoformat(),
    }


def _directional_bias(per_event: pd.DataFrame) -> dict:
    """Signed offset analysis: is there a systematic N/S/E/W bias?

    Returns the MEAN signed east/north offset + a compass-rose histogram.
    - mean_east_km > 0: alerts are systematically WEST of actual fires
      (events lie to the east of where we predicted)
    - mean_north_km > 0: alerts are systematically SOUTH of actual fires

    Reject-H0 rule-of-thumb: if |mean| > SEM × 2 (95% CI doesn't include 0),
    the bias is directionally consistent. Otherwise random noise.
    """
    caught = per_event[per_event["caught_at_band"] != "MISSED"].copy()
    caught = caught.dropna(subset=["offset_east_km", "offset_north_km", "bearing_deg"])
    n = len(caught)
    if n == 0:
        return {"n_caught": 0, "note": "no catches to analyse"}

    east = caught["offset_east_km"].to_numpy()
    north = caught["offset_north_km"].to_numpy()
    bearings = caught["bearing_deg"].to_numpy()

    mean_east = float(east.mean())
    mean_north = float(north.mean())
    sem_east = float(east.std(ddof=1) / np.sqrt(n))
    sem_north = float(north.std(ddof=1) / np.sqrt(n))

    # Compass-rose histogram (8 sectors, 45° each).
    # 0=N, 45=NE, 90=E, 135=SE, 180=S, 225=SW, 270=W, 315=NW
    sectors = {"N": 0, "NE": 0, "E": 0, "SE": 0, "S": 0, "SW": 0, "W": 0, "NW": 0}
    sector_names = list(sectors.keys())
    for b in bearings:
        idx = int(((b + 22.5) % 360) / 45) % 8
        sectors[sector_names[idx]] += 1

    # Mean resultant length — |R|/n where R is the sum of unit vectors.
    # Values near 1 = all events in same direction; near 0 = isotropic.
    theta = np.radians(bearings)
    rx, ry = np.cos(theta).mean(), np.sin(theta).mean()
    mrl = float(np.sqrt(rx * rx + ry * ry))
    mean_bearing = float((np.degrees(np.arctan2(ry, rx)) + 360) % 360)

    # z-score-ish for east/north bias
    z_east = float(abs(mean_east) / sem_east) if sem_east > 0 else 0.0
    z_north = float(abs(mean_north) / sem_north) if sem_north > 0 else 0.0
    bias_significant = z_east > 2 or z_north > 2

    return {
        "n_caught": int(n),
        "mean_east_km": mean_east,
        "mean_north_km": mean_north,
        "sem_east_km": sem_east,
        "sem_north_km": sem_north,
        "z_east": z_east,
        "z_north": z_north,
        "bias_is_significant_95ci": bias_significant,
        "bias_interpretation": (
            f"alerts are systematically {'EAST' if mean_east < 0 else 'WEST'} and "
            f"{'SOUTH' if mean_north > 0 else 'NORTH'} of actual fires "
            f"by ({abs(mean_east):.2f}, {abs(mean_north):.2f}) km"
            if bias_significant else "directional offset is not systematic (random-noise dominated)"
        ),
        "compass_rose_counts": sectors,
        "mean_resultant_length": mrl,
        "mean_bearing_deg": mean_bearing,
    }


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default="2026-02-16")
    ap.add_argument("--end", default="2026-04-22")
    args = ap.parse_args()

    start = datetime.strptime(args.start, "%Y-%m-%d").date()
    end = datetime.strptime(args.end, "%Y-%m-%d").date()
    log.info("Validation window: %s -> %s", start, end)

    log.info("Loading FIRMS consolidated + NRT...")
    firms = load_firms()
    log.info("FIRMS rows (high-conf): %d, range %s -> %s",
             len(firms), firms.acq_date.min(), firms.acq_date.max())
    firms_max_date = firms.acq_date.max().date()

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    all_events: list[dict] = []
    all_alerts: list[dict] = []
    n_days_processed = 0
    n_days_missing_pred = 0

    d = start
    while d <= end:
        d_str = d.strftime("%Y-%m-%d")
        pred_path = FEED_DIR / f"ignition_risk_v17_{d_str}.json"
        ops_path = FEED_DIR / f"operational_alerts_v17_{d_str}.json"
        if not pred_path.exists() or not ops_path.exists():
            n_days_missing_pred += 1
            d += timedelta(days=1)
            continue

        # FIRMS catch window: [D, min(D+7, firms_max)]
        win_end = min(pd.Timestamp(d) + pd.Timedelta(days=CATCH_WINDOW_DAYS),
                      pd.Timestamp(firms_max_date))
        win_firms = firms[
            (firms.acq_date >= pd.Timestamp(d)) & (firms.acq_date <= win_end)
        ]

        try:
            ops_json = json.loads(ops_path.read_text())
        except Exception as e:
            log.error("Skip %s — parse error: %s", d_str, e)
            d += timedelta(days=1)
            continue

        per_event, per_alert = evaluate_day(
            pd.Timestamp(d), win_firms, ops_json,
        )
        all_events.extend(per_event)
        all_alerts.extend(per_alert)
        n_days_processed += 1
        if n_days_processed % 10 == 0:
            log.info("  ...%d days processed", n_days_processed)

        d += timedelta(days=1)

    log.info("Processed %d days, missing %d.", n_days_processed, n_days_missing_pred)
    if n_days_processed == 0:
        log.error("No predictions found in window. Run scripts/run_2026_backfill.py --execute first.")
        return 1

    per_event_df = pd.DataFrame(all_events)
    per_alert_df = pd.DataFrame(all_alerts)
    log.info("Total: %d events, %d CRITICAL alerts.", len(per_event_df), len(per_alert_df))

    # 5 outputs
    summary = season_summary(per_event_df, per_alert_df, n_days_processed)
    (OUT_DIR / "2026_season_summary.json").write_text(json.dumps(summary, indent=2, default=str))
    log.info("Wrote 2026_season_summary.json")

    per_day_summary(per_event_df, per_alert_df).to_csv(OUT_DIR / "2026_per_day.csv", index=False)
    log.info("Wrote 2026_per_day.csv")

    per_division_summary(per_event_df, per_alert_df).to_csv(OUT_DIR / "2026_per_division.csv", index=False)
    log.info("Wrote 2026_per_division.csv")

    per_event_df.to_csv(OUT_DIR / "2026_per_fire.csv", index=False)
    log.info("Wrote 2026_per_fire.csv (%d rows)", len(per_event_df))

    per_trust_tier_summary(per_alert_df, per_event_df).to_csv(
        OUT_DIR / "2026_per_trust_tier.csv", index=False,
    )
    log.info("Wrote 2026_per_trust_tier.csv")

    log.info("=" * 70)
    log.info("SEASON SUMMARY (preview)")
    log.info("  events observed: %d", summary["n_ignition_events_observed"])
    log.info("  recall any band: %s", summary["season_recall_any_band"])
    log.info("  recall CRITICAL: %s", summary["season_recall_critical"])
    log.info("  CRITICAL precision: %s", summary["season_precision_critical"])
    log.info("  FLOOR precision: %s", summary["season_precision_floor"])
    log.info("  events caught by floor-promoted alerts: %d", summary["n_caught_by_floor_promoted_alerts"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
