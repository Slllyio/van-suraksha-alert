"""
scripts/train_pixel_lgbm.py
============================
Strategy D: Pixel-Level LightGBM Fire Risk Model

Trains a per-pixel (30m) fire risk classifier using:
  - Static terrain: DEM, slope, TPI, road_distance (30m rasters)
  - Fire weather: FWI daily anomalies + raw indices (AOI-level)
  - NDVI phenology anomaly: deviation from Fourier seasonal model
  - Historical fire density: FIRMS multi-year fire count per grid cell
  - Spatial context: neighborhood terrain stats (3×3, 5×5 windows)

Labels from FIRMS VIIRS/MODIS detections (375m → 30m nearest pixel).
Negative samples: random forest pixels on same date (no fire detected).

Spatial block splitting: divide AOI into ~5km blocks, assign train/val/test
by block to prevent spatial leakage.

Usage:
    python scripts/train_pixel_lgbm.py
    python scripts/train_pixel_lgbm.py --neg-ratio 5 --tag v1
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
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import rasterio
from scipy.ndimage import uniform_filter
import lightgbm as lgb
from sklearn.metrics import (
    roc_auc_score, average_precision_score, f1_score,
    precision_score, recall_score, confusion_matrix,
    precision_recall_curve,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent.parent
RASTER_DIR = ROOT / "data" / "rasters"
FWI_PATH = ROOT / "data_lake" / "fire_weather" / "fwi_daily.parquet"
FIRMS_DIR = ROOT / "data_lake" / "fire_detections" / "firms_viirs_snpp_sp"
PHENOLOGY_PATH = ROOT / "data" / "phenology" / "division_ndvi_model.json"
FIRE_GRID_PATH = ROOT / "data_lake" / "fire_detections" / "firms_fire_season_grid.npy"
AOI_PATH = ROOT / "data" / "aoi" / "gunafinal.geojson"
OUT_DIR = ROOT / "outputs" / "pixel_lgbm"

# ═══════════════════════════════════════════════════════════════════════════
# Terrain Loading
# ═══════════════════════════════════════════════════════════════════════════

TERRAIN_FILES = {
    "slope": "slope_30m.tif",    # Load slope FIRST as reference grid
    "tpi": "tpi_30m.tif",
    "road_dist": "road_dist_30m.tif",
    "dem": "dem_30m.tif",        # DEM has larger extent, will be resampled
}


def load_terrain_rasters():
    """Load all terrain rasters. Returns dict of arrays + shared transform/shape."""
    rasters = {}
    ref_transform = None
    ref_shape = None

    for name, fname in TERRAIN_FILES.items():
        path = RASTER_DIR / fname
        if not path.exists():
            log.warning(f"Missing raster: {path}")
            continue
        with rasterio.open(path) as src:
            data = src.read(1).astype(np.float32)
            transform = src.transform
            nodata = src.nodata
            if ref_transform is None:
                ref_transform = transform
                ref_shape = data.shape
            # Handle rasters with different extent — resample to match reference
            if data.shape != ref_shape:
                log.info(f"  {name}: shape {data.shape} != ref {ref_shape}, resampling to match")
                data = _align_raster(path, ref_transform, ref_shape)
            # Replace nodata sentinel values with NaN
            if nodata is not None:
                data[data == nodata] = np.nan
            # DEM-specific: replace extreme negatives (nodata=-32768)
            if name == "dem":
                data[data < -1000] = np.nan
            rasters[name] = data
            valid_data = data[~np.isnan(data)] if np.any(np.isnan(data)) else data
            log.info(f"  Loaded {name}: shape={data.shape}, "
                     f"range=[{np.nanmin(valid_data):.1f}, {np.nanmax(valid_data):.1f}], "
                     f"nan={np.isnan(data).sum():,}")

    # Add neighborhood context features (3×3 and 5×5 windows)
    for name in list(rasters.keys()):
        arr = rasters[name]
        rasters[f"{name}_mean3"] = uniform_filter(arr, size=3, mode="nearest")
        rasters[f"{name}_mean5"] = uniform_filter(arr, size=5, mode="nearest")
        rasters[f"{name}_std3"] = _local_std(arr, size=3)

    return rasters, ref_transform, ref_shape


def _align_raster(path, target_transform, target_shape):
    """Resample a raster to match target grid using nearest-neighbor."""
    from rasterio.warp import reproject, Resampling
    with rasterio.open(path) as src:
        out = np.zeros(target_shape, dtype=np.float32)
        reproject(
            source=src.read(1),
            destination=out,
            src_transform=src.transform,
            src_crs=src.crs or "EPSG:4326",
            dst_transform=target_transform,
            dst_crs="EPSG:4326",
            resampling=Resampling.nearest,
        )
    return out


def _local_std(arr, size=3):
    """Compute local standard deviation using uniform_filter trick."""
    mean = uniform_filter(arr, size=size, mode="nearest")
    mean_sq = uniform_filter(arr ** 2, size=size, mode="nearest")
    variance = np.clip(mean_sq - mean ** 2, 0, None)
    return np.sqrt(variance)


# ═══════════════════════════════════════════════════════════════════════════
# FWI Weather Features
# ═══════════════════════════════════════════════════════════════════════════

WEATHER_COLS = ["temp_c", "rh_pct", "wind_kmh", "precip_mm",
                "ffmc", "dmc", "dc", "isi", "bui", "fwi"]
WEATHER_SHORT = ["temp", "rh", "wind", "precip",
                 "ffmc", "dmc", "dc", "isi", "bui", "fwi"]


def load_fwi():
    """Load FWI daily data + compute monthly climatology."""
    fwi = pd.read_parquet(FWI_PATH)
    fwi["date"] = pd.to_datetime(fwi["date"])
    fwi = fwi.set_index("date")
    fwi["month"] = fwi.index.month

    clim = {}
    for month in range(1, 13):
        subset = fwi[fwi["month"] == month]
        if len(subset) == 0:
            continue
        clim[month] = {
            "mean": subset[WEATHER_COLS].mean().values.astype(np.float32),
            "std": subset[WEATHER_COLS].std().values.astype(np.float32),
        }
    return fwi, clim


def get_weather_features(fwi_df, date, clim, lookback=7):
    """Compute weather anomaly + raw features for a given date."""
    features = {}
    month = date.month

    if month not in clim:
        return {f"anomaly_{s}": 0.0 for s in WEATHER_SHORT}

    m_mean = clim[month]["mean"]
    m_std = np.where(clim[month]["std"] < 1e-6, 1.0, clim[month]["std"])

    # Current day
    ts = pd.Timestamp(date)
    if ts in fwi_df.index:
        row = fwi_df.loc[ts]
    else:
        idx = fwi_df.index.get_indexer([ts], method="nearest")[0]
        row = fwi_df.iloc[idx]

    raw = row[WEATHER_COLS].values.astype(np.float32)
    anomaly = (raw - m_mean) / m_std

    for i, name in enumerate(WEATHER_SHORT):
        features[f"anomaly_{name}"] = float(anomaly[i])

    # Raw values for key fire indices
    for idx_i, key_name in [(9, "fwi"), (6, "dc"), (5, "dmc"), (4, "ffmc"), (8, "bui")]:
        features[f"raw_{key_name}"] = float(raw[idx_i])

    # 7-day lookback
    anomaly_7d = []
    for d in range(lookback):
        dt = date - timedelta(days=d)
        ts_d = pd.Timestamp(dt)
        dt_month = dt.month
        if dt_month in clim and ts_d in fwi_df.index:
            r = fwi_df.loc[ts_d][WEATHER_COLS].values.astype(np.float32)
            a = (r - clim[dt_month]["mean"]) / np.where(
                clim[dt_month]["std"] < 1e-6, 1.0, clim[dt_month]["std"])
            anomaly_7d.append(a)

    if len(anomaly_7d) > 0:
        stack = np.array(anomaly_7d)
        for i, name in enumerate(WEATHER_SHORT):
            features[f"anomaly7d_{name}_mean"] = float(np.mean(stack[:, i]))
            features[f"anomaly7d_{name}_max"] = float(np.max(stack[:, i]))
            features[f"anomaly7d_{name}_trend"] = float(stack[0, i] - stack[-1, i])
    else:
        for name in WEATHER_SHORT:
            features[f"anomaly7d_{name}_mean"] = 0.0
            features[f"anomaly7d_{name}_max"] = 0.0
            features[f"anomaly7d_{name}_trend"] = 0.0

    return features


# ═══════════════════════════════════════════════════════════════════════════
# NDVI Phenology Anomaly
# ═══════════════════════════════════════════════════════════════════════════

def load_ndvi_model():
    """Load Fourier phenology model for NDVI."""
    with open(PHENOLOGY_PATH) as f:
        model = json.load(f)
    return model


def ndvi_expected(doy, coeffs):
    """Compute expected NDVI from Fourier model at given day-of-year."""
    # Fourier: a0 + a1*cos(2π*doy/365) + b1*sin(2π*doy/365) + a2*cos(4π*doy/365) + ...
    t = 2 * np.pi * doy / 365.0
    val = coeffs[0]
    n_harmonics = (len(coeffs) - 1) // 2
    for h in range(1, n_harmonics + 1):
        val += coeffs[2*h - 1] * np.cos(h * t)
        val += coeffs[2*h] * np.sin(h * t)
    return val


def get_ndvi_features(date, ndvi_model):
    """Compute NDVI phenology features for a date."""
    doy = date.timetuple().tm_yday
    coeffs = ndvi_model["coeffs"]
    expected = ndvi_expected(doy, coeffs)
    residual_std = ndvi_model.get("residual_std", 0.05)

    # Fire season NDVI stress: how far below seasonal peak
    peak_ndvi = max(ndvi_expected(d, coeffs) for d in range(1, 366))
    trough_ndvi = min(ndvi_expected(d, coeffs) for d in range(1, 366))
    seasonal_position = (expected - trough_ndvi) / max(peak_ndvi - trough_ndvi, 0.01)

    return {
        "ndvi_expected": expected,
        "ndvi_residual_std": residual_std,
        "ndvi_seasonal_position": seasonal_position,
        "doy": doy,
        "month": date.month,
        "is_fire_season": 1 if date.month in (2, 3, 4, 5) else 0,
    }


# ═══════════════════════════════════════════════════════════════════════════
# Historical Fire Density
# ═══════════════════════════════════════════════════════════════════════════

def load_fire_density(transform, shape):
    """Load and resample fire density grid to match 30m terrain grid."""
    fire_grid = np.load(str(FIRE_GRID_PATH))  # (139, 114) — coarse grid

    # Compute bounds of the coarse grid from AOI
    # The fire grid covers the AOI with ~1km cells
    aoi_bounds = _get_aoi_bounds()
    lon_min, lat_min, lon_max, lat_max = aoi_bounds

    # Create upsampled version matching 30m grid
    H, W = shape
    density = np.zeros((H, W), dtype=np.float32)

    grid_h, grid_w = fire_grid.shape
    for row in range(H):
        for col in range(W):
            # Get lon/lat of this 30m pixel
            lon = transform.c + col * transform.a
            lat = transform.f + row * transform.e
            # Map to fire grid cell
            gx = int((lon - lon_min) / (lon_max - lon_min) * grid_w)
            gy = int((lat_max - lat) / (lat_max - lat_min) * grid_h)
            gx = np.clip(gx, 0, grid_w - 1)
            gy = np.clip(gy, 0, grid_h - 1)
            density[row, col] = fire_grid[gy, gx]

    # Also compute distance-weighted density (Gaussian smooth)
    from scipy.ndimage import gaussian_filter
    density_smooth = gaussian_filter(density, sigma=10)  # ~300m radius

    return density, density_smooth


def load_fire_density_fast(transform, shape):
    """Vectorized version of fire density resampling — much faster."""
    fire_grid = np.load(str(FIRE_GRID_PATH))
    aoi_bounds = _get_aoi_bounds()
    lon_min, lat_min, lon_max, lat_max = aoi_bounds

    H, W = shape
    grid_h, grid_w = fire_grid.shape

    # Build coordinate arrays
    cols = np.arange(W)
    rows = np.arange(H)
    lons = transform.c + cols * transform.a
    lats = transform.f + rows * transform.e

    # Map to fire grid indices
    gx = ((lons - lon_min) / (lon_max - lon_min) * grid_w).astype(int)
    gy = ((lat_max - lats) / (lat_max - lat_min) * grid_h).astype(int)
    gx = np.clip(gx, 0, grid_w - 1)
    gy = np.clip(gy, 0, grid_h - 1)

    # Fancy indexing
    density = fire_grid[gy[:, None], gx[None, :]]

    from scipy.ndimage import gaussian_filter
    density_smooth = gaussian_filter(density.astype(np.float32), sigma=10)

    return density.astype(np.float32), density_smooth


def _get_aoi_bounds():
    """Get AOI bounding box from GeoJSON."""
    with open(AOI_PATH) as f:
        g = json.load(f)
    coords = []
    for feat in g["features"]:
        geom = feat["geometry"]
        if geom["type"] == "Polygon":
            for ring in geom["coordinates"]:
                coords.extend(ring)
        elif geom["type"] == "MultiPolygon":
            for poly in geom["coordinates"]:
                for ring in poly:
                    coords.extend(ring)
    c = np.array(coords)
    return (c[:, 0].min(), c[:, 1].min(), c[:, 0].max(), c[:, 1].max())


# ═══════════════════════════════════════════════════════════════════════════
# FIRMS Fire Pixel Sampling
# ═══════════════════════════════════════════════════════════════════════════

def load_all_firms():
    """Load all FIRMS VIIRS detections into single DataFrame."""
    frames = []
    for f in sorted(FIRMS_DIR.glob("*.parquet")):
        df = pd.read_parquet(f)
        if len(df) > 0:
            frames.append(df)
    if not frames:
        raise RuntimeError(f"No FIRMS data found in {FIRMS_DIR}")
    all_firms = pd.concat(frames, ignore_index=True)
    all_firms["acq_date"] = pd.to_datetime(all_firms["acq_date"])
    log.info(f"Loaded {len(all_firms)} FIRMS detections ({all_firms['acq_date'].min().date()} to {all_firms['acq_date'].max().date()})")
    return all_firms


def firms_to_pixels(firms_df, transform, shape):
    """Convert FIRMS lat/lon to raster row/col indices."""
    lons = firms_df["longitude"].values
    lats = firms_df["latitude"].values

    # Inverse transform: pixel = (lon - origin_lon) / pixel_size
    cols = ((lons - transform.c) / transform.a).astype(int)
    rows = ((lats - transform.f) / transform.e).astype(int)

    H, W = shape
    valid = (rows >= 0) & (rows < H) & (cols >= 0) & (cols < W)

    firms_df = firms_df.copy()
    firms_df["pixel_row"] = rows
    firms_df["pixel_col"] = cols
    firms_df["in_bounds"] = valid

    return firms_df[valid].copy()


# ═══════════════════════════════════════════════════════════════════════════
# Spatial Block Splitting
# ═══════════════════════════════════════════════════════════════════════════

BLOCK_SIZE_DEG = 0.05  # ~5km blocks (legacy grid-based fallback)
H3_BLOCK_RES = 6       # H3 resolution for spatial CV blocking (~36 km² hexes)


def assign_spatial_blocks(rows, cols, transform, seed=42, use_h3=True):
    """
    Assign each pixel to a spatial block, then split blocks into train/val/test.

    Parameters
    ----------
    use_h3 : bool
        If True (default), use H3 hexagonal blocking which provides better
        spatial separation than rectangular grids — hexes have uniform adjacency
        (6 neighbors vs 4/8 for squares) and no edge/corner artifacts.
        Falls back to grid-based blocking if h3 is not installed.
    """
    lons = transform.c + cols * transform.a
    lats = transform.f + rows * transform.e

    if use_h3:
        try:
            import h3
            # H3 res 6 → ~36 km² hexes — good separation for Guna Division
            block_ids = np.array([
                h3.latlng_to_cell(float(lat), float(lon), H3_BLOCK_RES)
                for lat, lon in zip(lats, lons)
            ])
            unique_blocks = np.unique(block_ids)
            log.info(f"   H3 blocking (res {H3_BLOCK_RES}): {len(unique_blocks)} unique hexes")
        except ImportError:
            log.warning("h3 not installed — falling back to grid-based blocking")
            use_h3 = False

    if not use_h3:
        # Legacy grid-based fallback
        block_x = (lons / BLOCK_SIZE_DEG).astype(int)
        block_y = (lats / BLOCK_SIZE_DEG).astype(int)
        block_ids = block_x * 10000 + block_y
        unique_blocks = np.unique(block_ids)

    # Shuffle and assign splits (70/15/15)
    rng = np.random.RandomState(seed)
    shuffled = unique_blocks.copy()
    rng.shuffle(shuffled)

    n = len(shuffled)
    n_train = int(n * 0.7)
    n_val = int(n * 0.15)

    block_to_split = {}
    for i, b in enumerate(shuffled):
        if i < n_train:
            block_to_split[b] = "train"
        elif i < n_train + n_val:
            block_to_split[b] = "val"
        else:
            block_to_split[b] = "test"

    splits = np.array([block_to_split[b] for b in block_ids])
    return splits, block_ids


# ═══════════════════════════════════════════════════════════════════════════
# Dataset Construction
# ═══════════════════════════════════════════════════════════════════════════

def build_pixel_dataset(neg_ratio=5, max_fire_dates=None):
    """
    Build training dataset with one row per pixel-date.

    For each FIRMS detection date:
      - Fire pixels: all FIRMS detections on that date (mapped to 30m grid)
      - Negative pixels: `neg_ratio` random non-fire forest pixels per fire pixel

    Returns: DataFrame with features + label + split
    """
    log.info("=" * 65)
    log.info("BUILDING PIXEL-LEVEL DATASET")
    log.info("=" * 65)

    # Load all static data
    log.info("\n1. Loading terrain rasters...")
    terrain, transform, shape = load_terrain_rasters()
    H, W = shape
    log.info(f"   Grid: {H}×{W} = {H*W:,} pixels")

    log.info("\n2. Loading fire density...")
    fire_density, fire_density_smooth = load_fire_density_fast(transform, shape)
    terrain["fire_density"] = fire_density
    terrain["fire_density_smooth"] = fire_density_smooth

    log.info("\n3. Loading FWI weather...")
    fwi_df, clim = load_fwi()

    log.info("\n4. Loading NDVI phenology model...")
    ndvi_model = load_ndvi_model()

    log.info("\n5. Loading FIRMS detections...")
    firms = load_all_firms()
    firms_px = firms_to_pixels(firms, transform, shape)
    log.info(f"   {len(firms_px)} detections within AOI raster bounds")

    # Group by date
    firms_px["date"] = firms_px["acq_date"].dt.date
    fire_dates = sorted(firms_px["date"].unique())
    if max_fire_dates:
        fire_dates = fire_dates[:max_fire_dates]
    log.info(f"   {len(fire_dates)} unique fire dates")

    # Build valid pixel mask (where we have terrain data — no NaN in any raster)
    valid_mask = np.ones((H, W), dtype=bool)
    for tname in ["slope", "dem", "tpi", "road_dist"]:
        if tname in terrain:
            valid_mask &= ~np.isnan(terrain[tname])
    n_valid = valid_mask.sum()
    log.info(f"   Valid pixels: {n_valid:,} / {H*W:,}")

    # Pre-compute valid pixel indices for negative sampling
    valid_rows, valid_cols = np.where(valid_mask)

    log.info(f"\n6. Sampling pixels ({neg_ratio}:1 neg:fire ratio)...")
    rng = np.random.RandomState(42)
    all_rows = []
    terrain_names = sorted(terrain.keys())

    for di, fire_date in enumerate(fire_dates):
        # Fire pixels for this date
        day_firms = firms_px[firms_px["date"] == fire_date]
        fire_rows_arr = day_firms["pixel_row"].values
        fire_cols_arr = day_firms["pixel_col"].values

        # Deduplicate fire pixels (VIIRS 375m → multiple detections per 30m pixel)
        fire_pixels = set(zip(fire_rows_arr, fire_cols_arr))

        # Expand fire to ~375m footprint (VIIRS pixel size)
        expanded_fire = set()
        for r, c in fire_pixels:
            for dr in range(-6, 7):  # ±6 pixels ≈ ±180m ≈ VIIRS half-pixel
                for dc in range(-6, 7):
                    nr, nc = r + dr, c + dc
                    if 0 <= nr < H and 0 <= nc < W and valid_mask[nr, nc]:
                        expanded_fire.add((nr, nc))

        n_fire = len(expanded_fire)
        if n_fire == 0:
            continue

        # Sample negatives (random valid pixels not in fire zone)
        n_neg = min(n_fire * neg_ratio, n_valid - n_fire)
        fire_set = expanded_fire
        neg_pixels = set()
        attempts = 0
        while len(neg_pixels) < n_neg and attempts < n_neg * 3:
            idx = rng.randint(0, len(valid_rows))
            px = (valid_rows[idx], valid_cols[idx])
            if px not in fire_set:
                neg_pixels.add(px)
            attempts += 1

        # Weather features (same for all pixels on this date — AOI-level)
        weather_feats = get_weather_features(fwi_df, fire_date, clim)
        ndvi_feats = get_ndvi_features(fire_date, ndvi_model)

        # Extract features for fire + neg pixels
        for label, pixel_set in [(1, expanded_fire), (0, neg_pixels)]:
            for r, c in pixel_set:
                row_data = {"label": label, "pixel_row": r, "pixel_col": c,
                            "date": str(fire_date)}
                # Terrain features
                for tname in terrain_names:
                    row_data[tname] = float(terrain[tname][r, c])
                # Weather (shared per date)
                row_data.update(weather_feats)
                # NDVI
                row_data.update(ndvi_feats)
                all_rows.append(row_data)

        if (di + 1) % 20 == 0 or di == len(fire_dates) - 1:
            log.info(f"   Date {di+1}/{len(fire_dates)}: {fire_date} — "
                     f"{n_fire} fire + {len(neg_pixels)} neg pixels")

    df = pd.DataFrame(all_rows)
    log.info(f"\n   Total samples: {len(df):,} ({df['label'].sum():,} fire, "
             f"{(df['label']==0).sum():,} neg)")

    # Assign spatial block splits
    log.info("\n7. Assigning spatial block splits...")
    splits, block_ids = assign_spatial_blocks(
        df["pixel_row"].values, df["pixel_col"].values, transform
    )
    df["split"] = splits
    df["block_id"] = block_ids

    for s in ["train", "val", "test"]:
        sub = df[df["split"] == s]
        log.info(f"   {s:6s}: {len(sub):,} samples ({sub['label'].sum():,} fire)")

    return df, terrain_names, transform, shape


# ═══════════════════════════════════════════════════════════════════════════
# Training
# ═══════════════════════════════════════════════════════════════════════════

def get_feature_cols(df):
    """Get feature column names (exclude metadata columns)."""
    skip = {"label", "pixel_row", "pixel_col", "date", "split", "block_id"}
    return [c for c in df.columns if c not in skip]


def train_model(df, feature_cols, tag="v1"):
    """Train LightGBM on train split, evaluate on val and test."""
    out_dir = OUT_DIR / f"pixel_lgbm_{tag}"
    out_dir.mkdir(parents=True, exist_ok=True)

    train_df = df[df["split"] == "train"]
    val_df = df[df["split"] == "val"]
    test_df = df[df["split"] == "test"]

    X_train = train_df[feature_cols].values.astype(np.float32)
    y_train = train_df["label"].values
    X_val = val_df[feature_cols].values.astype(np.float32)
    y_val = val_df["label"].values
    X_test = test_df[feature_cols].values.astype(np.float32)
    y_test = test_df["label"].values

    # Handle NaN/inf
    X_train = np.nan_to_num(X_train, nan=0.0, posinf=0.0, neginf=0.0)
    X_val = np.nan_to_num(X_val, nan=0.0, posinf=0.0, neginf=0.0)
    X_test = np.nan_to_num(X_test, nan=0.0, posinf=0.0, neginf=0.0)

    n_pos = y_train.sum()
    n_neg = (y_train == 0).sum()
    scale_pos_weight = n_neg / max(n_pos, 1)
    log.info(f"scale_pos_weight = {scale_pos_weight:.2f}")

    params = {
        "objective": "binary",
        "metric": ["auc", "binary_logloss"],
        "n_estimators": 1000,
        "max_depth": 4,
        "num_leaves": 15,
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

    log.info(f"\nTraining LightGBM ({len(feature_cols)} features)...")
    log.info(f"  Train: {len(X_train):,} | Val: {len(X_val):,} | Test: {len(X_test):,}")

    train_data = lgb.Dataset(X_train, label=y_train, feature_name=feature_cols)
    val_data = lgb.Dataset(X_val, label=y_val, feature_name=feature_cols, reference=train_data)

    callbacks = [
        lgb.early_stopping(stopping_rounds=100, verbose=True),
        lgb.log_evaluation(period=100),
    ]

    model = lgb.train(
        {k: v for k, v in params.items() if k not in ("n_estimators",)},
        train_data,
        num_boost_round=params["n_estimators"],
        valid_sets=[train_data, val_data],
        valid_names=["train", "val"],
        callbacks=callbacks,
    )

    # Evaluate
    results = {}
    for split_name, X, y in [("val", X_val, y_val), ("test", X_test, y_test)]:
        probs = model.predict(X)
        metrics = evaluate_split(y, probs, split_name)
        results[split_name] = metrics

    # Feature importance
    importance = pd.DataFrame({
        "feature": feature_cols,
        "importance": model.feature_importance(importance_type="gain"),
    }).sort_values("importance", ascending=False)

    log.info(f"\nTop 20 features:")
    for _, row in importance.head(20).iterrows():
        log.info(f"  {row['feature']:40s} {row['importance']:.0f}")

    # Save
    model.save_model(str(out_dir / "model.lgbm"))
    importance.to_csv(out_dir / "feature_importance.csv", index=False)

    with open(out_dir / "results.json", "w") as f:
        json.dump(results, f, indent=2)

    with open(out_dir / "params.json", "w") as f:
        json.dump(params, f, indent=2)

    log.info(f"\nModel + results saved to {out_dir}")
    return model, results, importance


def evaluate_split(y, probs, name):
    """Evaluate binary classification with threshold sweep."""
    auc = roc_auc_score(y, probs) if len(np.unique(y)) > 1 else 0.0
    ap = average_precision_score(y, probs) if len(np.unique(y)) > 1 else 0.0

    # Threshold sweep
    best_f1, best_thr = 0, 0.5
    sweep_rows = []
    for thr in np.arange(0.1, 0.95, 0.05):
        preds = (probs >= thr).astype(int)
        f1 = f1_score(y, preds, zero_division=0)
        prec = precision_score(y, preds, zero_division=0)
        rec = recall_score(y, preds, zero_division=0)
        sweep_rows.append({"threshold": round(thr, 2), "f1": f1, "precision": prec, "recall": rec})
        if f1 > best_f1:
            best_f1, best_thr = f1, thr

    # Default threshold
    preds_05 = (probs >= 0.5).astype(int)
    cm = confusion_matrix(y, preds_05, labels=[0, 1])

    metrics = {
        "auc_roc": float(auc),
        "auc_pr": float(ap),
        "best_threshold": float(best_thr),
        "best_f1": float(best_f1),
        "f1_at_05": float(f1_score(y, preds_05, zero_division=0)),
        "precision_at_05": float(precision_score(y, preds_05, zero_division=0)),
        "recall_at_05": float(recall_score(y, preds_05, zero_division=0)),
        "tp": int(cm[1, 1]), "fp": int(cm[0, 1]),
        "fn": int(cm[1, 0]), "tn": int(cm[0, 0]),
        "n_samples": len(y),
        "n_fire": int(y.sum()),
        "threshold_sweep": sweep_rows,
    }

    log.info(f"\n{'='*60}")
    log.info(f"{name.upper()} RESULTS")
    log.info(f"{'='*60}")
    log.info(f"  AUC-ROC:     {auc:.4f}")
    log.info(f"  AUC-PR:      {ap:.4f}")
    log.info(f"  Best F1:     {best_f1:.4f} @ threshold={best_thr:.2f}")
    log.info(f"  F1@0.5:      {metrics['f1_at_05']:.4f}")
    log.info(f"  P@0.5:       {metrics['precision_at_05']:.4f}")
    log.info(f"  R@0.5:       {metrics['recall_at_05']:.4f}")
    log.info(f"  TP={cm[1,1]}  FP={cm[0,1]}  FN={cm[1,0]}  TN={cm[0,0]}")

    return metrics


# ═══════════════════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description="Strategy D: Pixel-Level LightGBM")
    parser.add_argument("--neg-ratio", type=int, default=5,
                        help="Negative:fire pixel sampling ratio (default: 5)")
    parser.add_argument("--max-fire-dates", type=int, default=None,
                        help="Limit fire dates for smoke testing")
    parser.add_argument("--tag", type=str, default="v1",
                        help="Experiment tag for output directory")
    args = parser.parse_args()

    t0 = time.time()

    # Build dataset
    df, terrain_names, transform, shape = build_pixel_dataset(
        neg_ratio=args.neg_ratio,
        max_fire_dates=args.max_fire_dates,
    )

    feature_cols = get_feature_cols(df)
    log.info(f"\nFeatures ({len(feature_cols)}):")
    for fc in feature_cols:
        log.info(f"  {fc}")

    # Train
    model, results, importance = train_model(df, feature_cols, tag=args.tag)

    # Save dataset for reproducibility
    out_dir = OUT_DIR / f"pixel_lgbm_{args.tag}"
    df.to_parquet(out_dir / "training_data.parquet", index=False)

    elapsed = time.time() - t0
    log.info(f"\n{'='*65}")
    log.info(f"STRATEGY D COMPLETE — {elapsed:.0f}s")
    log.info(f"{'='*65}")
    log.info(f"Val  AUC: {results['val']['auc_roc']:.4f}  |  Best F1: {results['val']['best_f1']:.4f}")
    log.info(f"Test AUC: {results['test']['auc_roc']:.4f}  |  Best F1: {results['test']['best_f1']:.4f}")


if __name__ == "__main__":
    main()
