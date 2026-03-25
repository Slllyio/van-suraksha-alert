"""
scripts/train_predictive_mp_wide.py
====================================
PREDICTIVE Fire Risk Model — Trained on ALL of Madhya Pradesh.

Uses the MP beat shapefile (8,973 beats) to train a generalizable fire
prediction model, then applies it to Guna Division's 25ha grid.

Strategy:
  1. Train on MP-wide beat × day data (thousands of fire events)
  2. The model learns: weather patterns, seasonal timing, spatial recurrence
  3. For Guna: combine MP-wide beat prediction with 25ha terrain features

Unit of prediction: MP BEAT × DAY  (training)
                    25ha PATCH × DAY (Guna inference)

Usage:
    python scripts/train_predictive_mp_wide.py
    python scripts/train_predictive_mp_wide.py --tag v1
    python scripts/train_predictive_mp_wide.py --predict 2025-04-15
"""

# ── PROJ/GDAL env fix ──
import os as _os, sys as _sys
_sys.path.insert(0, _os.path.join(_os.path.dirname(__file__), ".."))
from src.utils.proj_fix import setup_proj_env; setup_proj_env()
del _os, _sys
# ────────────────────────

import argparse
import json
import logging
import os
import time
from collections import defaultdict
from datetime import datetime, timedelta, date
from pathlib import Path

import numpy as np
import pandas as pd
import geopandas as gpd
from shapely.geometry import Point
from shapely.strtree import STRtree
import lightgbm as lgb
from sklearn.metrics import (
    roc_auc_score, average_precision_score, f1_score,
    precision_score, recall_score,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent.parent

# ── Data paths ──
MP_BEAT_SHP = Path(r"C:\Users\S.C.C\Downloads\MP_Merge Divsion Beat Range\MP_Merge\Mp_Beat_Merge.shp")
GUNA_AOI = ROOT / "data" / "aoi" / "gunafinal.geojson"
FIRMS_DIRS = [
    ROOT / "data_lake" / "fire_detections" / "firms_mp_viirs",
    ROOT / "data_lake" / "fire_detections" / "firms_viirs_snpp_sp",
]
POWER_PATH = ROOT / "data_lake" / "fire_weather" / "nasa_power_2013_2025.parquet"
FWI_PATH = ROOT / "data_lake" / "fire_weather" / "fwi_daily.parquet"
PHENOLOGY_PATH = ROOT / "data" / "phenology" / "division_ndvi_model.json"
RASTER_DIR = ROOT / "data" / "rasters"
OUT_DIR = ROOT / "outputs" / "predictive_fire_risk"

FIRE_MONTHS = {2, 3, 4, 5}
WEATHER_COLS = ["temp_c", "rh_pct", "wind_kmh", "precip_mm"]


# ═══════════════════════════════════════════════════════════════════════════
# Load MP Beats
# ═══════════════════════════════════════════════════════════════════════════

def load_mp_beats():
    """Load all MP beat polygons, reproject to WGS84."""
    log.info("Loading MP beat shapefile...")
    gdf = gpd.read_file(MP_BEAT_SHP)
    gdf = gdf.to_crs(epsg=4326)

    log.info(f"  {len(gdf)} beats, {gdf['Division'].nunique()} divisions")
    log.info(f"  Bounds: {gdf.total_bounds}")

    # Compute centroids and area
    gdf["centroid_lon"] = gdf.geometry.centroid.x
    gdf["centroid_lat"] = gdf.geometry.centroid.y
    gdf["area_km2"] = gdf.geometry.area * 111 * 111  # rough deg² -> km²

    # Create a unique beat ID (Division_Range_Beat)
    gdf["beat_id"] = (gdf["Division"].astype(str) + "_" +
                      gdf["Range"].astype(str) + "_" +
                      gdf["Beat"].astype(str))

    # Flag Guna division beats
    gdf["is_guna"] = gdf["Division"].str.contains("Guna", case=False, na=False)
    n_guna = gdf["is_guna"].sum()
    log.info(f"  Guna Division: {n_guna} beats")

    return gdf


# ═══════════════════════════════════════════════════════════════════════════
# Load FIRMS & Assign to Beats
# ═══════════════════════════════════════════════════════════════════════════

def load_all_firms():
    """Load all available FIRMS data (Guna + MP-wide)."""
    log.info("Loading FIRMS detections...")
    frames = []
    for fdir in FIRMS_DIRS:
        if not fdir.exists():
            continue
        for f in sorted(fdir.glob("**/*.parquet")):
            if "consolidated" in f.name:
                continue
            df = pd.read_parquet(f)
            if len(df) > 0:
                frames.append(df)

    if not frames:
        raise RuntimeError(f"No FIRMS data found in {FIRMS_DIRS}")

    firms = pd.concat(frames, ignore_index=True)
    firms["acq_date"] = pd.to_datetime(firms["acq_date"])
    firms = firms.drop_duplicates(subset=["latitude", "longitude", "acq_date"])
    log.info(f"  {len(firms)} total detections (deduped)")
    log.info(f"  Date range: {firms['acq_date'].min().date()} to {firms['acq_date'].max().date()}")

    return firms


def assign_firms_to_beats(firms, gdf):
    """Assign FIRMS detections to MP beats using vectorized spatial join."""
    log.info("Assigning FIRMS to beats...")

    # Create GeoDataFrame from FIRMS points
    firms_gdf = gpd.GeoDataFrame(
        firms[["latitude", "longitude", "acq_date"]].copy(),
        geometry=gpd.points_from_xy(firms["longitude"], firms["latitude"]),
        crs="EPSG:4326",
    )

    # Spatial join — much faster than iterrows
    joined = gpd.sjoin(firms_gdf, gdf[["beat_id", "geometry"]], how="inner", predicate="within")
    log.info(f"  Matched: {len(joined)}/{len(firms)}")

    # Group by beat_id → set of fire dates
    fires_by_beat = defaultdict(set)
    for beat_id, grp in joined.groupby("beat_id"):
        fires_by_beat[beat_id] = set(grp["acq_date"].dt.date)

    total_fire_beat_days = sum(len(v) for v in fires_by_beat.values())
    log.info(f"  Beats with fires: {len(fires_by_beat)}")
    log.info(f"  Total beat-fire-days: {total_fire_beat_days}")

    return fires_by_beat


# ═══════════════════════════════════════════════════════════════════════════
# Weather (single station — shared across all MP)
# ═══════════════════════════════════════════════════════════════════════════

def load_weather():
    """Load NASA POWER weather + FWI indices."""
    log.info("Loading weather data...")

    power = pd.read_parquet(POWER_PATH)
    power["date"] = pd.to_datetime(power["date"])

    fwi = None
    if FWI_PATH.exists():
        fwi = pd.read_parquet(FWI_PATH)
        fwi["date"] = pd.to_datetime(fwi["date"])

    weather = power.copy()
    if fwi is not None:
        fwi_cols = [c for c in fwi.columns if c not in weather.columns and c != "date"]
        weather = weather.merge(fwi[["date"] + fwi_cols], on="date", how="left")

    weather = weather.set_index("date").sort_index()
    weather["month"] = weather.index.month

    # Climatology
    clim = {}
    for month in range(1, 13):
        subset = weather[weather["month"] == month]
        clim[month] = {
            "mean": subset[WEATHER_COLS].mean().to_dict(),
            "std": subset[WEATHER_COLS].std().to_dict(),
        }

    # Derived
    weather["consecutive_dry_days"] = _compute_consecutive_dry(weather["precip_mm"])
    weather["precip_7d"] = weather["precip_mm"].rolling(7, min_periods=1).sum()
    weather["precip_14d"] = weather["precip_mm"].rolling(14, min_periods=1).sum()
    weather["temp_7d_mean"] = weather["temp_c"].rolling(7, min_periods=1).mean()
    weather["rh_7d_min"] = weather["rh_pct"].rolling(7, min_periods=1).min()
    weather["wind_7d_max"] = weather["wind_kmh"].rolling(7, min_periods=1).max()

    log.info(f"  Weather: {len(weather)} days")
    return weather, clim


def _compute_consecutive_dry(precip_series, threshold=1.0):
    is_dry = (precip_series < threshold).astype(int)
    groups = is_dry.ne(is_dry.shift()).cumsum()
    return is_dry.groupby(groups).cumsum()


def get_weather_features(weather, d, clim):
    features = {}
    ts = pd.Timestamp(d)
    if ts in weather.index:
        row = weather.loc[ts]
    else:
        idx = weather.index.get_indexer([ts], method="nearest")[0]
        row = weather.iloc[idx] if 0 <= idx < len(weather) else None

    if row is None:
        return {f"wx_{c}": 0.0 for c in WEATHER_COLS}

    for c in WEATHER_COLS:
        features[f"wx_{c}"] = float(row.get(c, 0.0))
    for fwi_col in ["ffmc", "dmc", "dc", "isi", "bui", "fwi"]:
        val = row.get(fwi_col, np.nan)
        features[f"wx_{fwi_col}"] = float(val) if not pd.isna(val) else 0.0
    features["wx_consecutive_dry"] = float(row.get("consecutive_dry_days", 0))
    features["wx_precip_7d"] = float(row.get("precip_7d", 0))
    features["wx_precip_14d"] = float(row.get("precip_14d", 0))
    features["wx_temp_7d_mean"] = float(row.get("temp_7d_mean", 0))
    features["wx_rh_7d_min"] = float(row.get("rh_7d_min", 0))
    features["wx_wind_7d_max"] = float(row.get("wind_7d_max", 0))

    month = d.month if hasattr(d, "month") else pd.Timestamp(d).month
    if month in clim:
        for c in WEATHER_COLS:
            mean = clim[month]["mean"][c]
            std = max(clim[month]["std"][c], 0.01)
            features[f"wx_anom_{c}"] = (features[f"wx_{c}"] - mean) / std

    return features


# ═══════════════════════════════════════════════════════════════════════════
# NDVI Phenology
# ═══════════════════════════════════════════════════════════════════════════

def load_ndvi_model():
    if PHENOLOGY_PATH.exists():
        with open(PHENOLOGY_PATH) as f:
            return json.load(f)
    return None


def ndvi_features(doy, ndvi_model):
    if ndvi_model is None:
        return {"ndvi_expected": 0.0, "ndvi_seasonal_position": 0.0}
    coeffs = ndvi_model["coeffs"]
    t = 2 * np.pi * doy / 365.0
    val = coeffs[0]
    n_h = (len(coeffs) - 1) // 2
    for h in range(1, n_h + 1):
        val += coeffs[2*h - 1] * np.cos(h * t)
        val += coeffs[2*h] * np.sin(h * t)
    all_vals = [_ndvi_raw(d, coeffs) for d in range(1, 366)]
    position = (val - min(all_vals)) / max(max(all_vals) - min(all_vals), 0.01)
    return {"ndvi_expected": val, "ndvi_seasonal_position": position}


def _ndvi_raw(doy, coeffs):
    t = 2 * np.pi * doy / 365.0
    val = coeffs[0]
    for h in range(1, (len(coeffs) - 1) // 2 + 1):
        val += coeffs[2*h - 1] * np.cos(h * t) + coeffs[2*h] * np.sin(h * t)
    return val


# ═══════════════════════════════════════════════════════════════════════════
# Dataset Construction
# ═══════════════════════════════════════════════════════════════════════════

def compute_hist_features(fires_by_beat, year_cutoff):
    """Historical fire features per beat, only counting fires before year_cutoff."""
    n_years = max(year_cutoff - 2014, 1)
    result = {}
    for bid, dates in fires_by_beat.items():
        past = [d for d in dates if d.year < year_cutoff]
        fire_years = len(set(d.year for d in past)) if past else 0
        result[bid] = {
            "hist_fire_days": len(past),
            "hist_fire_freq": len(past) / n_years,
            "hist_fire_years": fire_years,
            "hist_fire_year_frac": fire_years / n_years,
        }
    return result


def build_dataset(gdf, fires_by_beat, subsample_neg=20.0):
    """Build beat × day dataset for all of MP."""
    log.info("=" * 65)
    log.info("BUILDING MP-WIDE PREDICTIVE DATASET")
    log.info("=" * 65)

    weather, clim = load_weather()
    ndvi_model = load_ndvi_model()

    # Historical features per year cutoff
    hist_by_year = {}
    for yr in range(2014, 2027):
        hist_by_year[yr] = compute_hist_features(fires_by_beat, yr)

    # Sample dates (fire season only)
    weather_start = weather.index.min().date()
    weather_end = weather.index.max().date()
    sample_dates = []
    for year in range(2014, 2026):
        for month in FIRE_MONTHS:
            for day in range(1, 32):
                try:
                    d = date(year, month, day)
                    if weather_start <= d <= weather_end:
                        sample_dates.append(d)
                except ValueError:
                    continue
    log.info(f"  Fire season dates: {len(sample_dates)}")

    # Pre-compute weather per date
    wx_cache = {}
    for d in sample_dates:
        wx_cache[d] = get_weather_features(weather, d, clim)
    ndvi_cache = {}
    for doy in range(1, 367):
        ndvi_cache[doy] = ndvi_features(doy, ndvi_model)

    # Build samples
    beat_ids = gdf["beat_id"].values
    n_beats = len(beat_ids)
    log.info(f"  {n_beats} beats × {len(sample_dates)} dates = {n_beats * len(sample_dates):,} combos")

    rng = np.random.RandomState(42)
    rows = []
    n_positive = 0
    n_negative_kept = 0

    for bi, beat_id in enumerate(beat_ids):
        beat_row = gdf.iloc[bi]
        fire_dates = fires_by_beat.get(beat_id, set())

        static = {
            "centroid_lat": beat_row["centroid_lat"],
            "centroid_lon": beat_row["centroid_lon"],
            "area_km2": beat_row["area_km2"],
            "is_guna": 1 if beat_row["is_guna"] else 0,
        }

        for d in sample_dates:
            label = 1 if d in fire_dates else 0
            year = d.year

            # Subsample negatives in train years only
            if label == 0:
                if year <= 2023 and rng.random() > 1.0 / subsample_neg:
                    continue
                n_negative_kept += 1
            else:
                n_positive += 1

            row = {"beat_id": beat_id, "date": str(d), "label": label}
            row.update(static)
            row.update(wx_cache[d])

            hist = hist_by_year[year].get(beat_id, {
                "hist_fire_days": 0, "hist_fire_freq": 0.0,
                "hist_fire_years": 0, "hist_fire_year_frac": 0.0,
            })
            row.update(hist)

            doy = d.timetuple().tm_yday
            row.update(ndvi_cache[doy])

            row["doy"] = doy
            row["month"] = d.month
            row["is_weekend"] = 1 if d.weekday() >= 5 else 0

            # Lag features
            past_fires = [fd for fd in fire_dates if fd < d]
            row["days_since_last_fire"] = (d - max(past_fires)).days if past_fires else 999
            recent = [fd for fd in fire_dates if 0 < (d - fd).days <= 7]
            row["fire_last_7d"] = len(recent)

            rows.append(row)

        if (bi + 1) % 1000 == 0:
            log.info(f"  Processed {bi+1}/{n_beats} beats...")

    df = pd.DataFrame(rows)
    log.info(f"\n  Total samples: {len(df):,}")
    log.info(f"  Positive: {n_positive:,} ({n_positive/max(len(df),1)*100:.3f}%)")
    log.info(f"  Negative: {n_negative_kept:,}")

    return df


# ═══════════════════════════════════════════════════════════════════════════
# Temporal Split + Training
# ═══════════════════════════════════════════════════════════════════════════

def temporal_split(df):
    df["year"] = pd.to_datetime(df["date"]).dt.year
    train = df[df["year"] <= 2023].copy()
    val = df[df["year"] == 2024].copy()
    test = df[df["year"] == 2025].copy()
    for name, split in [("Train", train), ("Val", val), ("Test", test)]:
        n_fire = int(split["label"].sum())
        log.info(f"  {name}: {len(split):,} ({n_fire} fire, {n_fire/max(len(split),1)*100:.3f}%)")
    return train, val, test


def get_feature_cols(df):
    skip = {"beat_id", "date", "label", "year"}
    return [c for c in df.columns if c not in skip]


def train_model(train_df, val_df, test_df, feature_cols, tag="v1"):
    out_dir = OUT_DIR / f"mp_wide_{tag}"
    out_dir.mkdir(parents=True, exist_ok=True)

    X_train = train_df[feature_cols].values.astype(np.float32)
    y_train = train_df["label"].values
    X_val = val_df[feature_cols].values.astype(np.float32)
    y_val = val_df["label"].values
    X_test = test_df[feature_cols].values.astype(np.float32)
    y_test = test_df["label"].values

    for arr in [X_train, X_val, X_test]:
        np.nan_to_num(arr, copy=False, nan=0.0, posinf=0.0, neginf=0.0)

    n_pos = int(y_train.sum())
    n_neg = int((y_train == 0).sum())
    scale_pos_weight = min(n_neg / max(n_pos, 1), 200.0)
    log.info(f"\nscale_pos_weight = {scale_pos_weight:.1f} ({n_pos} pos / {n_neg} neg)")

    params = {
        "objective": "binary",
        "metric": "auc",
        "max_depth": 6,
        "num_leaves": 31,
        "learning_rate": 0.01,
        "subsample": 0.8,
        "colsample_bytree": 0.8,
        "scale_pos_weight": scale_pos_weight,
        "min_child_samples": 50,
        "reg_alpha": 0.5,
        "reg_lambda": 2.0,
        "random_state": 42,
        "verbose": -1,
        "n_jobs": -1,
    }

    log.info(f"Training LightGBM ({len(feature_cols)} features)...")
    train_data = lgb.Dataset(X_train, label=y_train, feature_name=feature_cols)
    val_data = lgb.Dataset(X_val, label=y_val, feature_name=feature_cols, reference=train_data)

    model = lgb.train(
        params,
        train_data,
        num_boost_round=5000,
        valid_sets=[train_data, val_data],
        valid_names=["train", "val"],
        callbacks=[lgb.early_stopping(150, verbose=True), lgb.log_evaluation(200)],
    )

    results = {}
    for name, X, y, split_df in [("val", X_val, y_val, val_df),
                                  ("test", X_test, y_test, test_df)]:
        probs = model.predict(X)
        results[name] = evaluate(y, probs, name, split_df)

    # Feature importance
    importance = pd.DataFrame({
        "feature": feature_cols,
        "importance": model.feature_importance(importance_type="gain"),
    }).sort_values("importance", ascending=False)

    log.info(f"\nTop 20 features:")
    for _, row in importance.head(20).iterrows():
        log.info(f"  {row['feature']:35s} {row['importance']:.0f}")

    # Save
    model.save_model(str(out_dir / "model.lgbm"))
    importance.to_csv(out_dir / "feature_importance.csv", index=False)
    with open(out_dir / "results.json", "w") as f:
        json.dump(results, f, indent=2)

    log.info(f"\nSaved to {out_dir}")
    return model, results, importance


def evaluate(y, probs, name, split_df=None):
    auc = roc_auc_score(y, probs) if len(np.unique(y)) > 1 else 0.0
    ap = average_precision_score(y, probs) if len(np.unique(y)) > 1 else 0.0

    best_f1, best_thr = 0, 0.5
    for thr in np.arange(0.01, 0.50, 0.005):
        preds = (probs >= thr).astype(int)
        f1 = f1_score(y, preds, zero_division=0)
        if f1 > best_f1:
            best_f1, best_thr = f1, thr

    log.info(f"\n{'='*60}")
    log.info(f"{name.upper()} RESULTS")
    log.info(f"{'='*60}")
    log.info(f"  AUC-ROC:     {auc:.4f}")
    log.info(f"  AUC-PR:      {ap:.4f}")
    log.info(f"  Best F1:     {best_f1:.4f} @ threshold={best_thr:.3f}")

    n_fire = int(y.sum())
    if n_fire > 0:
        sorted_idx = np.argsort(-probs)
        for k in [10, 50, 100, 200, 500]:
            captured = int(y[sorted_idx[:k]].sum())
            log.info(f"  Top-{k:3d} capture: {captured}/{n_fire} = {captured/n_fire*100:.1f}%")

    # Guna-specific results if split_df available
    if split_df is not None and "is_guna" in split_df.columns:
        guna_mask = split_df["is_guna"].values == 1
        if guna_mask.sum() > 0:
            guna_y = y[guna_mask]
            guna_probs = probs[guna_mask]
            guna_fire = int(guna_y.sum())
            if guna_fire > 0 and len(np.unique(guna_y)) > 1:
                guna_auc = roc_auc_score(guna_y, guna_probs)
                log.info(f"\n  GUNA DIVISION:")
                log.info(f"    AUC: {guna_auc:.4f} ({guna_fire} fires in {guna_mask.sum()} samples)")

    return {
        "auc_roc": float(auc),
        "auc_pr": float(ap),
        "best_f1": float(best_f1),
        "best_threshold": float(best_thr),
        "n_samples": len(y),
        "n_fire": n_fire,
    }


# ═══════════════════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description="MP-wide Predictive Fire Risk Model")
    parser.add_argument("--tag", type=str, default="v1")
    parser.add_argument("--subsample-neg", type=float, default=20.0)
    args = parser.parse_args()

    t0 = time.time()

    # Load MP beats
    gdf = load_mp_beats()

    # Load FIRMS
    firms = load_all_firms()

    # Assign to beats
    fires_by_beat = assign_firms_to_beats(firms, gdf)

    # Build dataset
    df = build_dataset(gdf, fires_by_beat, subsample_neg=args.subsample_neg)

    # Split
    log.info("\nTemporal split...")
    train, val, test = temporal_split(df)

    # Train
    feature_cols = get_feature_cols(df)
    log.info(f"\nFeatures ({len(feature_cols)}):")
    for fc in feature_cols:
        log.info(f"  {fc}")

    model, results, importance = train_model(train, val, test, feature_cols, tag=args.tag)

    elapsed = time.time() - t0
    log.info(f"\n{'='*65}")
    log.info(f"MP-WIDE PREDICTIVE MODEL COMPLETE -- {elapsed:.0f}s")
    log.info(f"{'='*65}")
    log.info(f"Val  AUC: {results['val']['auc_roc']:.4f}")
    log.info(f"Test AUC: {results['test']['auc_roc']:.4f}")


if __name__ == "__main__":
    main()
