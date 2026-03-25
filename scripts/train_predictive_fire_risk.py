"""
scripts/train_predictive_fire_risk.py
======================================
PREDICTIVE Fire Risk Model — Forecast fires BEFORE they happen.

Unlike the detection ensemble (reacts to FIRMS hot spots), this model
predicts: "Which 25-hectare patches will have fire TOMORROW?" using only
information available TODAY.

Unit of prediction: 25-HECTARE PATCH × DAY
  - Regular grid of ~500m × 500m cells covering Guna Division forest area
  - ~6,000 cells inside beat boundaries
  - Fire season: Feb-May each year (2014-2025)
  - Label: 1 if FIRMS detected fire in that cell on that day

Features (all available BEFORE fire):
  - Weather: temp, RH, wind, precip + derived FWI indices
  - Weather anomalies: deviation from monthly climatology
  - Drought accumulation: consecutive dry days, rain deficit
  - NDVI phenology: expected vegetation dryness for that DOY
  - Terrain per cell: slope, elevation, TPI, road distance (direct from 30m raster)
  - Historical fire frequency: how often this cell has burned
  - ABM ignition probability: human fire-starting likelihood
  - Temporal: DOY, month, day of week, is_weekend
  - Lag features: was there fire nearby recently?
  - Spatial context: neighborhood fire density

Usage:
    python scripts/train_predictive_fire_risk.py
    python scripts/train_predictive_fire_risk.py --tag v1 --cell-size 500
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
from collections import defaultdict
from datetime import datetime, timedelta, date
from pathlib import Path

import numpy as np
import pandas as pd
import rasterio
from rasterio.transform import from_bounds
from shapely.geometry import shape, Point, box
from shapely.ops import unary_union
from shapely.strtree import STRtree
import lightgbm as lgb
from sklearn.metrics import (
    roc_auc_score, average_precision_score, f1_score,
    precision_score, recall_score,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent.parent
RASTER_DIR = ROOT / "data" / "rasters"
FIRMS_DIR = ROOT / "data_lake" / "fire_detections" / "firms_viirs_snpp_sp"
POWER_PATH = ROOT / "data_lake" / "fire_weather" / "nasa_power_2013_2025.parquet"
GRIDDED_WX_PATH = ROOT / "data_lake" / "fire_weather" / "nasa_power_gridded.parquet"
FWI_PATH = ROOT / "data_lake" / "fire_weather" / "fwi_daily.parquet"
PHENOLOGY_PATH = ROOT / "data" / "phenology" / "division_ndvi_model.json"
ABM_PATH = ROOT / "data_lake" / "fire_detections" / "abm_ignition_probability.npy"
AOI_PATH = ROOT / "data" / "aoi" / "gunafinal.geojson"
OUT_DIR = ROOT / "outputs" / "predictive_fire_risk"

FIRE_MONTHS = {2, 3, 4, 5}  # Feb-May

# At ~24°N latitude: 1° lon ≈ 101.4 km, 1° lat ≈ 110.6 km
# 500m = 0.00493° lon, 0.00452° lat
DEG_PER_M_LON_24N = 1.0 / 101400.0
DEG_PER_M_LAT_24N = 1.0 / 110600.0


# ═══════════════════════════════════════════════════════════════════════════
# Grid Construction
# ═══════════════════════════════════════════════════════════════════════════

def build_grid(cell_size_m=500):
    """
    Build a regular grid of ~25ha cells covering the Guna Division AOI.

    Returns list of dicts with cell_id, geometry, centroid, row, col, beat, range.
    Only cells that intersect at least one beat polygon are kept.
    """
    log.info(f"Building {cell_size_m}m × {cell_size_m}m grid...")

    # Load beat polygons
    with open(AOI_PATH) as f:
        geojson = json.load(f)

    beat_polys = []
    beat_names = []
    range_names = []
    for feat in geojson["features"]:
        props = feat["properties"]
        geom = shape(feat["geometry"])
        if not geom.is_valid:
            geom = geom.buffer(0)
        beat_polys.append(geom)
        beat_names.append(props.get("BEAT", "Unknown"))
        range_names.append(props.get("RANGE", ""))

    aoi_union = unary_union(beat_polys)
    bounds = aoi_union.bounds  # (minx, miny, maxx, maxy)
    log.info(f"  AOI bounds: {bounds}")
    log.info(f"  AOI area: {aoi_union.area * 101.4 * 110.6:.0f} km²")

    # Grid step in degrees
    dx = cell_size_m * DEG_PER_M_LON_24N
    dy = cell_size_m * DEG_PER_M_LAT_24N

    # Generate grid
    x_start = bounds[0]
    y_start = bounds[1]
    x_end = bounds[2]
    y_end = bounds[3]

    n_cols = int(np.ceil((x_end - x_start) / dx))
    n_rows = int(np.ceil((y_end - y_start) / dy))
    log.info(f"  Grid dimensions: {n_rows} rows × {n_cols} cols = {n_rows * n_cols} total cells")

    # Build spatial index for beats
    tree = STRtree(beat_polys)

    cells = []
    for r in range(n_rows):
        y0 = y_start + r * dy
        y1 = y0 + dy
        for c in range(n_cols):
            x0 = x_start + c * dx
            x1 = x0 + dx
            cell_geom = box(x0, y0, x1, y1)

            # Check intersection with any beat
            candidates = tree.query(cell_geom)
            hit_beat = None
            hit_range = None
            for idx in candidates:
                if beat_polys[idx].intersects(cell_geom):
                    hit_beat = beat_names[idx]
                    hit_range = range_names[idx]
                    break

            if hit_beat is None:
                continue

            cells.append({
                "cell_id": f"r{r:04d}_c{c:04d}",
                "row": r,
                "col": c,
                "geometry": cell_geom,
                "centroid_lon": (x0 + x1) / 2,
                "centroid_lat": (y0 + y1) / 2,
                "beat": hit_beat,
                "range": hit_range,
            })

    log.info(f"  Cells inside AOI: {len(cells)}")
    log.info(f"  Effective area: {len(cells) * cell_size_m * cell_size_m / 1e6:.0f} km²")

    # Store grid metadata for later use
    grid_meta = {
        "x_start": x_start, "y_start": y_start,
        "dx": dx, "dy": dy,
        "n_rows": n_rows, "n_cols": n_cols,
        "cell_size_m": cell_size_m,
    }

    return cells, grid_meta


# ═══════════════════════════════════════════════════════════════════════════
# Cell-Level Static Features
# ═══════════════════════════════════════════════════════════════════════════

def compute_cell_terrain(cells, grid_meta):
    """
    Compute terrain features per cell directly from 30m rasters.

    Each 500m cell covers ~17×17 pixels at 30m resolution.
    We compute mean, max, and std for each terrain variable.
    """
    log.info("Computing terrain stats per cell...")

    terrain_files = {
        "slope": RASTER_DIR / "slope_30m.tif",
        "dem": RASTER_DIR / "dem_30m.tif",
        "tpi": RASTER_DIR / "tpi_30m.tif",
        "road_dist": RASTER_DIR / "road_dist_30m.tif",
    }

    # Load each raster with its own transform (DEM has different grid than slope/tpi)
    ref_path = terrain_files.get("slope")
    if ref_path is None or not ref_path.exists():
        log.warning("No slope raster — skipping terrain")
        return cells

    raster_data = {}  # name -> (data, transform, shape)
    for name, path in terrain_files.items():
        if not path.exists():
            continue
        with rasterio.open(path) as src:
            data = src.read(1).astype(np.float32)
            if name == "dem":
                data[data < -1000] = np.nan
            raster_data[name] = (data, src.transform, (src.height, src.width))

    log.info(f"  Loaded rasters: {list(raster_data.keys())}")
    for name, (data, transform, (H, W)) in raster_data.items():
        valid_pct = 100 * np.sum(~np.isnan(data)) / data.size
        log.info(f"    {name}: shape={data.shape}, bounds=({transform.c:.2f},{transform.f:.2f}), "
                 f"res=({transform.a:.5f},{transform.e:.5f}), valid={valid_pct:.1f}%")

    for cell in cells:
        lon, lat = cell["centroid_lon"], cell["centroid_lat"]
        half_dx = grid_meta["dx"] / 2
        half_dy = grid_meta["dy"] / 2

        for name, (data, transform, (H, W)) in raster_data.items():
            # Convert cell bounds to pixel coords using this raster's own transform
            col_min = max(0, int((lon - half_dx - transform.c) / transform.a))
            col_max = min(W, int((lon + half_dx - transform.c) / transform.a) + 1)
            row_min = max(0, int((lat + half_dy - transform.f) / transform.e))
            row_max = min(H, int((lat - half_dy - transform.f) / transform.e) + 1)

            patch = data[row_min:row_max, col_min:col_max]
            valid = patch[~np.isnan(patch)]
            if len(valid) > 0:
                cell[f"t_{name}_mean"] = float(np.mean(valid))
                cell[f"t_{name}_max"] = float(np.max(valid))
                cell[f"t_{name}_std"] = float(np.std(valid))
            else:
                cell[f"t_{name}_mean"] = 0.0
                cell[f"t_{name}_max"] = 0.0
                cell[f"t_{name}_std"] = 0.0

    log.info(f"  Terrain computed for {len(cells)} cells")
    return cells


def add_cell_abm_ignition(cells):
    """Add ABM ignition probability per cell."""
    if not ABM_PATH.exists():
        for c in cells:
            c["abm_ignition"] = 0.5
        return cells

    abm = np.load(str(ABM_PATH))
    grid_h, grid_w = abm.shape
    lat_min, lat_max = 23.88, 25.11
    lon_min, lon_max = 76.80, 77.49
    abm_max = max(float(abm.max()), 1e-6)

    for cell in cells:
        lat, lon = cell["centroid_lat"], cell["centroid_lon"]
        gy = int((lat_max - lat) / (lat_max - lat_min) * grid_h)
        gx = int((lon - lon_min) / (lon_max - lon_min) * grid_w)
        gy = np.clip(gy, 0, grid_h - 1)
        gx = np.clip(gx, 0, grid_w - 1)
        prob = float(abm[gy, gx])
        cell["abm_ignition"] = prob / abm_max if abm_max > 1.0 else prob

    return cells


# ═══════════════════════════════════════════════════════════════════════════
# FIRMS Labels — Assign detections to grid cells
# ═══════════════════════════════════════════════════════════════════════════

def load_firms_and_assign_cells(cells, grid_meta, expand_radius=3, expand_days=1):
    """
    Load all FIRMS detections, assign each to the grid cell it falls in.

    Spatial expansion: mark cells within `expand_radius` cells (~1.5km at 500m)
    of each detection as positive — accounts for VIIRS 375m position error and
    fire spread.

    Temporal expansion: also mark ±expand_days around each detection.

    Returns cell_id -> set of fire dates.
    """
    log.info("Loading FIRMS detections...")

    # Load from multiple possible directories
    firms_dirs = [
        FIRMS_DIR,
        ROOT / "data_lake" / "fire_detections" / "firms_mp_viirs",  # MP-wide if available
    ]
    frames = []
    for fdir in firms_dirs:
        if not fdir.exists():
            continue
        for f in sorted(fdir.glob("**/*.parquet")):
            df = pd.read_parquet(f)
            if len(df) > 0:
                frames.append(df)

    if not frames:
        raise RuntimeError(f"No FIRMS data found in {firms_dirs}")
    firms = pd.concat(frames, ignore_index=True)
    firms["acq_date"] = pd.to_datetime(firms["acq_date"])

    # Deduplicate (same lat/lon/date)
    firms = firms.drop_duplicates(subset=["latitude", "longitude", "acq_date"])
    log.info(f"  {len(firms)} total detections (deduped)")

    # Build a fast lookup: lon/lat -> cell using grid indices
    x_start = grid_meta["x_start"]
    y_start = grid_meta["y_start"]
    dx = grid_meta["dx"]
    dy = grid_meta["dy"]
    n_rows = grid_meta["n_rows"]
    n_cols = grid_meta["n_cols"]

    # Build cell lookup by (row, col)
    cell_lookup = {}
    for cell in cells:
        cell_lookup[(cell["row"], cell["col"])] = cell["cell_id"]

    fires_by_cell = defaultdict(set)
    direct_matched = 0

    for _, row in firms.iterrows():
        lon, lat = row["longitude"], row["latitude"]
        c = int((lon - x_start) / dx)
        r = int((lat - y_start) / dy)
        fire_date = row["acq_date"].date()

        # Expand temporally: mark day T-1, T, T+1
        fire_dates = [fire_date + timedelta(days=delta)
                      for delta in range(-expand_days, expand_days + 1)]

        # Check if detection lands inside any AOI cell
        if 0 <= r < n_rows and 0 <= c < n_cols:
            hit = cell_lookup.get((r, c))
            if hit is not None:
                direct_matched += 1

            # Spatial expansion: mark all cells within radius
            for dr in range(-expand_radius, expand_radius + 1):
                for dc in range(-expand_radius, expand_radius + 1):
                    # Circular mask (not square)
                    if dr * dr + dc * dc > expand_radius * expand_radius:
                        continue
                    nr, nc = r + dr, c + dc
                    neighbor_id = cell_lookup.get((nr, nc))
                    if neighbor_id is not None:
                        for fd in fire_dates:
                            fires_by_cell[neighbor_id].add(fd)

    total_fire_cell_days = sum(len(v) for v in fires_by_cell.values())
    log.info(f"  Direct matches: {direct_matched}/{len(firms)}")
    log.info(f"  Cells with fires (after expansion): {len(fires_by_cell)}")
    log.info(f"  Total cell-fire-days (expanded): {total_fire_cell_days}")
    log.info(f"  Expansion: radius={expand_radius} cells (~{expand_radius * 500}m), "
             f"days=±{expand_days}")

    return fires_by_cell


def compute_historical_fire_features(fires_by_cell, year_cutoff):
    """
    Compute historical fire frequency per cell using ONLY fires before year_cutoff.
    This prevents temporal leakage — 2025 test samples shouldn't know about 2025 fires.

    Returns dict: cell_id -> {hist_fire_days, hist_fire_freq, hist_fire_years, hist_fire_year_frac}
    """
    n_years = max(year_cutoff - 2014, 1)
    result = {}
    for cid, fire_dates in fires_by_cell.items():
        past_fires = [d for d in fire_dates if d.year < year_cutoff]
        fire_years = len(set(d.year for d in past_fires)) if past_fires else 0
        result[cid] = {
            "hist_fire_days": len(past_fires),
            "hist_fire_freq": len(past_fires) / n_years,
            "hist_fire_years": fire_years,
            "hist_fire_year_frac": fire_years / n_years,
        }
    return result


# ═══════════════════════════════════════════════════════════════════════════
# Weather Features (shared across all cells — single weather station)
# ═══════════════════════════════════════════════════════════════════════════

WEATHER_COLS = ["temp_c", "rh_pct", "wind_kmh", "precip_mm"]


def _enrich_weather_df(weather):
    """Add derived rolling/computed features to a weather DataFrame (indexed by date)."""
    weather["consecutive_dry_days"] = _compute_consecutive_dry(weather["precip_mm"])
    weather["precip_7d"] = weather["precip_mm"].rolling(7, min_periods=1).sum()
    weather["precip_14d"] = weather["precip_mm"].rolling(14, min_periods=1).sum()
    weather["temp_7d_mean"] = weather["temp_c"].rolling(7, min_periods=1).mean()
    weather["rh_7d_min"] = weather["rh_pct"].rolling(7, min_periods=1).min()
    weather["wind_7d_max"] = weather["wind_kmh"].rolling(7, min_periods=1).max()

    # Fuel dryness proxy (Keetch-Byram style)
    weather["fuel_dryness"] = (
        weather["consecutive_dry_days"] * weather["temp_c"].clip(lower=0) / 40.0
    ).clip(upper=10.0)

    # Heat wave indicator
    weather["month"] = weather.index.month
    temp_monthly_hi = weather.groupby("month")["temp_c"].transform(
        lambda x: x.mean() + x.std()
    )
    hot_day = (weather["temp_c"] > temp_monthly_hi).astype(int)
    weather["heat_streak"] = hot_day.groupby(
        (hot_day != hot_day.shift()).cumsum()
    ).cumsum() * hot_day
    return weather


def _compute_fwi_for_series(df):
    """Compute FWI components for a weather DataFrame. Returns merged df."""
    cache_key = f"fwi_{df['temp_c'].iloc[0]:.1f}_{len(df)}"
    try:
        sys.path.insert(0, str(ROOT / "scripts"))
        from compute_fwi import compute_fwi_series
        fwi = compute_fwi_series(df[["date", "temp_c", "rh_pct", "wind_kmh", "precip_mm"]].copy())
        fwi["date"] = pd.to_datetime(fwi["date"])
        fwi_cols = [c for c in fwi.columns if c not in df.columns and c != "date"]
        return df.merge(fwi[["date"] + fwi_cols], on="date", how="left")
    except Exception as e:
        log.warning(f"  FWI computation failed: {e}")
        return df


def load_weather():
    """Load gridded or single-station weather, compute FWI, and anomalies.

    If gridded data exists (15 points across Guna), returns a dict of
    grid_id -> (weather_df, clim_dict) plus a grid_points array for
    nearest-neighbor lookup. Otherwise falls back to single station.
    """
    log.info("Loading weather data...")

    # Try gridded weather first
    if GRIDDED_WX_PATH.exists():
        return _load_gridded_weather()
    else:
        log.info("  No gridded weather — using single station")
        return _load_single_weather()


def _load_gridded_weather():
    """Load multi-point gridded weather."""
    raw = pd.read_parquet(GRIDDED_WX_PATH)
    raw["date"] = pd.to_datetime(raw["date"])
    grid_ids = sorted(raw["grid_id"].unique())
    log.info(f"  Gridded weather: {len(grid_ids)} stations, "
             f"{raw['date'].min().date()} to {raw['date'].max().date()}")

    # Build grid point coordinates for nearest-neighbor lookup
    grid_coords = {}
    for gid in grid_ids:
        row = raw[raw["grid_id"] == gid].iloc[0]
        grid_coords[gid] = (row["grid_lat"], row["grid_lon"])

    # FWI cache for gridded data
    fwi_cache = GRIDDED_WX_PATH.parent / "fwi_gridded_cache.parquet"
    if fwi_cache.exists():
        fwi_all = pd.read_parquet(fwi_cache)
        fwi_all["date"] = pd.to_datetime(fwi_all["date"])
        log.info(f"  Gridded FWI (cached): {len(fwi_all)} rows")
    else:
        log.info("  Computing FWI for all grid points (one-time)...")
        fwi_frames = []
        sys.path.insert(0, str(ROOT / "scripts"))
        from compute_fwi import compute_fwi_series
        for gid in grid_ids:
            gdf = raw[raw["grid_id"] == gid].copy()
            fwi = compute_fwi_series(gdf[["date", "temp_c", "rh_pct", "wind_kmh", "precip_mm"]])
            fwi["grid_id"] = gid
            fwi["date"] = pd.to_datetime(fwi["date"])
            fwi_frames.append(fwi)
        fwi_all = pd.concat(fwi_frames, ignore_index=True)
        fwi_all.to_parquet(fwi_cache, index=False)
        log.info(f"  Gridded FWI computed and cached: {len(fwi_all)} rows")

    # Merge FWI into raw
    fwi_cols = [c for c in fwi_all.columns
                if c not in raw.columns and c not in ("date", "grid_id")]
    merged = raw.merge(fwi_all[["date", "grid_id"] + fwi_cols], on=["date", "grid_id"], how="left")

    # Build per-station weather + climatology
    weather_by_grid = {}
    for gid in grid_ids:
        gdf = merged[merged["grid_id"] == gid].copy()
        gdf = gdf.set_index("date").sort_index()
        gdf = _enrich_weather_df(gdf)

        # Climatology
        clim = {}
        for month in range(1, 13):
            subset = gdf[gdf["month"] == month]
            clim[month] = {
                "mean": subset[WEATHER_COLS].mean().to_dict(),
                "std": subset[WEATHER_COLS].std().to_dict(),
            }
        weather_by_grid[gid] = (gdf, clim)

    return weather_by_grid, grid_coords


def _load_single_weather():
    """Fallback: single station weather."""
    power = pd.read_parquet(POWER_PATH)
    power["date"] = pd.to_datetime(power["date"])
    log.info(f"  NASA POWER: {len(power)} days")

    # Compute FWI
    fwi_cache = POWER_PATH.parent / "fwi_full_history.parquet"
    if fwi_cache.exists():
        fwi_full = pd.read_parquet(fwi_cache)
        fwi_full["date"] = pd.to_datetime(fwi_full["date"])
    else:
        log.info("  Computing FWI for full POWER history (one-time)...")
        power = _compute_fwi_for_series(power)
        fwi_full = None

    weather = power.copy()
    if fwi_full is not None:
        fwi_cols = [c for c in fwi_full.columns if c not in weather.columns and c != "date"]
        weather = weather.merge(fwi_full[["date"] + fwi_cols], on="date", how="left")

    weather = weather.set_index("date").sort_index()
    weather = _enrich_weather_df(weather)

    clim = {}
    for month in range(1, 13):
        subset = weather[weather["month"] == month]
        clim[month] = {
            "mean": subset[WEATHER_COLS].mean().to_dict(),
            "std": subset[WEATHER_COLS].std().to_dict(),
        }

    # Wrap in same format as gridded: single station "default"
    return {"default": (weather, clim)}, None


def _compute_consecutive_dry(precip_series, threshold=1.0):
    is_dry = (precip_series < threshold).astype(int)
    groups = is_dry.ne(is_dry.shift()).cumsum()
    return is_dry.groupby(groups).cumsum()


def get_weather_features(weather, d, clim):
    """Extract weather features for a specific date."""
    features = {}
    ts = pd.Timestamp(d)

    if ts in weather.index:
        row = weather.loc[ts]
    else:
        idx = weather.index.get_indexer([ts], method="nearest")[0]
        if 0 <= idx < len(weather):
            row = weather.iloc[idx]
        else:
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
    features["wx_fuel_dryness"] = float(row.get("fuel_dryness", 0))
    features["wx_heat_streak"] = float(row.get("heat_streak", 0))

    month = d.month if hasattr(d, "month") else pd.Timestamp(d).month
    if month in clim:
        for c in WEATHER_COLS:
            mean = clim[month]["mean"][c]
            std = max(clim[month]["std"][c], 0.01)
            features[f"wx_anom_{c}"] = (features[f"wx_{c}"] - mean) / std

    # ── NTFP season features (domain knowledge: #1 fire cause in dry deciduous) ──
    # Tendu leaf collection: March-June (fires set to clear undergrowth for picking)
    # Mahua flower collection: March-April (fires in mahua groves for easier harvest)
    # Grazing burn: October-December (post-monsoon burns for grass regrowth)
    features["ntfp_tendu_season"] = 1.0 if month in {3, 4, 5, 6} else 0.0
    features["ntfp_mahua_peak"] = 1.0 if month in {3, 4} else 0.0
    features["ntfp_grazing_burn"] = 1.0 if month in {10, 11, 12} else 0.0
    # Fire risk intensity ramps within the season
    doy = d.timetuple().tm_yday if hasattr(d, "timetuple") else pd.Timestamp(d).timetuple().tm_yday
    # Peak fire risk ramp: low Jan→Feb, peaks mid-March to mid-April, tapers May
    if 60 <= doy <= 150:  # ~Mar 1 to May 30
        features["fire_season_intensity"] = float(np.sin(np.pi * (doy - 60) / 90))
    else:
        features["fire_season_intensity"] = 0.0

    return features


# ═══════════════════════════════════════════════════════════════════════════
# NDVI Phenology
# ═══════════════════════════════════════════════════════════════════════════

def load_ndvi_model():
    with open(PHENOLOGY_PATH) as f:
        return json.load(f)


def ndvi_features(doy, ndvi_model):
    coeffs = ndvi_model["coeffs"]
    t = 2 * np.pi * doy / 365.0
    val = coeffs[0]
    n_h = (len(coeffs) - 1) // 2
    for h in range(1, n_h + 1):
        val += coeffs[2*h - 1] * np.cos(h * t)
        val += coeffs[2*h] * np.sin(h * t)

    all_vals = [_ndvi_raw(d, coeffs) for d in range(1, 366)]
    peak = max(all_vals)
    trough = min(all_vals)
    position = (val - trough) / max(peak - trough, 0.01)

    return {"ndvi_expected": val, "ndvi_seasonal_position": position}


def _ndvi_raw(doy, coeffs):
    t = 2 * np.pi * doy / 365.0
    val = coeffs[0]
    n_h = (len(coeffs) - 1) // 2
    for h in range(1, n_h + 1):
        val += coeffs[2*h - 1] * np.cos(h * t)
        val += coeffs[2*h] * np.sin(h * t)
    return val


# ═══════════════════════════════════════════════════════════════════════════
# Neighborhood / Spatial Context Features
# ═══════════════════════════════════════════════════════════════════════════

def build_neighbor_map(cells):
    """
    Build a mapping from cell_id to its 8-connected neighbor cell_ids.
    This enables spatial lag features (fire in adjacent cells).
    """
    lookup = {}
    for cell in cells:
        lookup[(cell["row"], cell["col"])] = cell["cell_id"]

    neighbors = {}
    for cell in cells:
        r, c = cell["row"], cell["col"]
        nbrs = []
        for dr in [-1, 0, 1]:
            for dc in [-1, 0, 1]:
                if dr == 0 and dc == 0:
                    continue
                nid = lookup.get((r + dr, c + dc))
                if nid is not None:
                    nbrs.append(nid)
        neighbors[cell["cell_id"]] = nbrs

    return neighbors


def _assign_cells_to_weather_grid(cells, grid_coords):
    """Map each cell to its nearest weather grid point.

    Returns dict: cell_id -> grid_id.
    If grid_coords is None (single station), all cells map to "default".
    """
    if grid_coords is None:
        return {c["cell_id"]: "default" for c in cells}

    grid_list = list(grid_coords.items())  # [(grid_id, (lat, lon)), ...]
    mapping = {}
    for cell in cells:
        clat, clon = cell["centroid_lat"], cell["centroid_lon"]
        best_gid, best_dist = None, float("inf")
        for gid, (glat, glon) in grid_list:
            dist = (clat - glat) ** 2 + (clon - glon) ** 2
            if dist < best_dist:
                best_dist = dist
                best_gid = gid
        mapping[cell["cell_id"]] = best_gid
    return mapping


# ═══════════════════════════════════════════════════════════════════════════
# Dataset Construction (vectorized)
# ═══════════════════════════════════════════════════════════════════════════

def build_dataset(cell_size_m=500, fire_season_only=True, subsample_neg=10.0):
    """
    Build cell × day training dataset.

    For each cell × each day in the fire season:
      features = weather + terrain + phenology + ignition + history + spatial
      label = 1 if FIRMS detected fire in that cell on that day

    subsample_neg: keep 1-in-N negative samples to manage dataset size.
        At ~6000 cells × ~480 days = 2.9M rows, subsampling 10:1 gives ~290k neg + ~200 pos.
        NOTE: val/test splits are NOT subsampled for honest evaluation.
    """
    log.info("=" * 65)
    log.info("BUILDING PREDICTIVE FIRE RISK DATASET (25ha PATCH GRID)")
    log.info("=" * 65)

    # 1. Build grid
    cells, grid_meta = build_grid(cell_size_m)

    # 2. Compute terrain per cell
    cells = compute_cell_terrain(cells, grid_meta)

    # 3. Load FIRMS + assign to cells (with spatial+temporal expansion)
    fires_by_cell = load_firms_and_assign_cells(cells, grid_meta)

    # 4. Add static features
    cells = add_cell_abm_ignition(cells)

    # Pre-compute historical fire features per year cutoff (prevents temporal leakage)
    hist_by_year = {}
    for yr in range(2014, 2027):
        hist_by_year[yr] = compute_historical_fire_features(fires_by_cell, yr)
    log.info(f"  Historical fire features computed for year cutoffs 2014-2026")

    # 5. Build neighbor map for spatial features
    neighbor_map = build_neighbor_map(cells)

    # 6. Load weather + NDVI
    weather_by_grid, grid_coords = load_weather()
    ndvi_model = load_ndvi_model()

    # Map each cell to its nearest weather grid point
    cell_to_grid = _assign_cells_to_weather_grid(cells, grid_coords)
    grid_ids_used = set(cell_to_grid.values())
    log.info(f"  Weather grid points used: {len(grid_ids_used)}")

    # 7. Generate sample dates — use first grid point's date range
    first_grid = list(weather_by_grid.keys())[0]
    ref_weather = weather_by_grid[first_grid][0]
    weather_start = ref_weather.index.min().date()
    weather_end = ref_weather.index.max().date()

    if fire_season_only:
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
    else:
        d = weather_start
        sample_dates = []
        while d <= weather_end:
            sample_dates.append(d)
            d += timedelta(days=1)
        log.info(f"  All dates: {len(sample_dates)}")

    # Pre-compute weather per (grid_point, date)
    log.info(f"  Pre-computing weather features ({len(grid_ids_used)} grids × {len(sample_dates)} dates)...")
    wx_cache = {}  # (grid_id, date) -> features
    for gid in grid_ids_used:
        wx, clim = weather_by_grid[gid]
        for d in sample_dates:
            wx_cache[(gid, d)] = get_weather_features(wx, d, clim)

    # Pre-compute NDVI per DOY
    ndvi_cache = {}
    for doy in range(1, 367):
        ndvi_cache[doy] = ndvi_features(doy, ndvi_model)

    # Static feature columns from cells (terrain + ABM + location, NOT hist_fire_*)
    static_cols = [k for k in cells[0].keys()
                   if k.startswith("t_") or k in (
                       "abm_ignition", "centroid_lat", "centroid_lon")]

    # 8. Build samples: cell × day
    log.info(f"\nBuilding samples ({len(cells)} cells × {len(sample_dates)} days)...")
    log.info(f"  Raw combinations: {len(cells) * len(sample_dates):,}")
    log.info(f"  Negative subsampling: 1/{subsample_neg:.0f}")

    rows = []
    n_positive = 0
    n_negative_kept = 0
    n_negative_skip = 0

    rng = np.random.RandomState(42)

    for ci, cell in enumerate(cells):
        cid = cell["cell_id"]
        gid = cell_to_grid[cid]  # nearest weather grid point
        fire_dates = fires_by_cell.get(cid, set())
        cell_static = {k: cell[k] for k in static_cols}

        # Neighbor fire dates (for spatial lag)
        nbr_fire_dates = set()
        for nid in neighbor_map.get(cid, []):
            nbr_fire_dates.update(fires_by_cell.get(nid, set()))

        for d in sample_dates:
            label = 1 if d in fire_dates else 0
            year = d.year

            # Subsample negatives in TRAIN years only; keep all val/test
            if label == 0:
                is_train_year = year <= 2023
                if is_train_year and rng.random() > 1.0 / subsample_neg:
                    n_negative_skip += 1
                    continue
                n_negative_kept += 1
            else:
                n_positive += 1

            row = {"cell_id": cid, "date": str(d), "label": label}
            row.update(cell_static)
            row.update(wx_cache[(gid, d)])  # per-cell gridded weather

            # Year-aware historical fire features (no leakage)
            hist = hist_by_year[year].get(cid, {
                "hist_fire_days": 0, "hist_fire_freq": 0.0,
                "hist_fire_years": 0, "hist_fire_year_frac": 0.0,
            })
            row.update(hist)

            doy = d.timetuple().tm_yday
            row.update(ndvi_cache[doy])

            # Temporal features
            row["doy"] = doy
            row["month"] = d.month
            row["is_weekend"] = 1 if d.weekday() >= 5 else 0

            # Lag: days since last fire in this cell
            past_fires = [fd for fd in fire_dates if fd < d]
            row["days_since_last_fire"] = (d - max(past_fires)).days if past_fires else 999

            # Recent fire activity in this cell
            recent = [fd for fd in fire_dates if 0 < (d - fd).days <= 7]
            row["fire_last_7d"] = len(recent)

            # Spatial lag: fire in adjacent cells recently
            nbr_recent = [fd for fd in nbr_fire_dates if 0 < (d - fd).days <= 7]
            row["neighbor_fire_7d"] = len(nbr_recent)

            # Was there fire in any neighbor yesterday?
            yesterday = d - timedelta(days=1)
            row["neighbor_fire_yesterday"] = 1 if yesterday in nbr_fire_dates else 0

            rows.append(row)

        if (ci + 1) % 1000 == 0:
            log.info(f"  Processed {ci+1}/{len(cells)} cells...")

    df = pd.DataFrame(rows)
    log.info(f"\n  Total samples: {len(df):,}")
    log.info(f"  Positive (fire): {n_positive:,} ({n_positive/max(len(df),1)*100:.3f}%)")
    log.info(f"  Negative kept: {n_negative_kept:,}")
    log.info(f"  Negative skipped: {n_negative_skip:,}")

    return df, cells, grid_meta


# ═══════════════════════════════════════════════════════════════════════════
# Temporal Split (no leakage)
# ═══════════════════════════════════════════════════════════════════════════

def temporal_split(df):
    """Train ≤2023, Val 2024, Test 2025."""
    df["year"] = pd.to_datetime(df["date"]).dt.year

    train = df[df["year"] <= 2023].copy()
    val = df[df["year"] == 2024].copy()
    test = df[df["year"] == 2025].copy()

    for name, split in [("Train", train), ("Val", val), ("Test", test)]:
        n_fire = int(split["label"].sum())
        log.info(f"  {name}: {len(split):,} samples ({n_fire} fire, "
                 f"{n_fire/max(len(split),1)*100:.3f}%)")

    return train, val, test


# ═══════════════════════════════════════════════════════════════════════════
# Training
# ═══════════════════════════════════════════════════════════════════════════

def get_feature_cols(df):
    skip = {"cell_id", "date", "label", "year"}
    return [c for c in df.columns if c not in skip]


def train_model(train_df, val_df, test_df, feature_cols, tag="v1"):
    out_dir = OUT_DIR / f"predictive_{tag}"
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
    raw_weight = n_neg / max(n_pos, 1)
    scale_pos_weight = min(raw_weight, 200.0)  # Cap to prevent numerical instability
    log.info(f"\nscale_pos_weight = {scale_pos_weight:.1f} (raw={raw_weight:.0f}, "
             f"{n_pos} pos / {n_neg} neg)")

    params = {
        "objective": "binary",
        "metric": "auc",
        "n_estimators": 3000,
        "max_depth": 5,
        "num_leaves": 31,
        "learning_rate": 0.01,
        "subsample": 0.8,
        "colsample_bytree": 0.8,
        "scale_pos_weight": scale_pos_weight,
        "min_child_samples": 20,
        "reg_alpha": 0.5,
        "reg_lambda": 2.0,
        "random_state": 42,
        "verbose": -1,
        "n_jobs": -1,
    }

    log.info(f"Training LightGBM ({len(feature_cols)} features)...")

    train_data = lgb.Dataset(X_train, label=y_train, feature_name=feature_cols)
    val_data = lgb.Dataset(X_val, label=y_val, feature_name=feature_cols, reference=train_data)

    callbacks = [
        lgb.early_stopping(stopping_rounds=150, verbose=True),
        lgb.log_evaluation(period=100),
    ]

    model = lgb.train(
        {k: v for k, v in params.items() if k != "n_estimators"},
        train_data,
        num_boost_round=params["n_estimators"],
        valid_sets=[train_data, val_data],
        valid_names=["train", "val"],
        callbacks=callbacks,
    )

    # Evaluate
    results = {}
    for name, X, y in [("val", X_val, y_val), ("test", X_test, y_test)]:
        probs = model.predict(X)
        results[name] = evaluate(y, probs, name)

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

    log.info(f"\nSaved to {out_dir}")
    return model, results, importance


def evaluate(y, probs, name):
    """Evaluate with threshold sweep + operational top-K metric."""
    auc = roc_auc_score(y, probs) if len(np.unique(y)) > 1 else 0.0
    ap = average_precision_score(y, probs) if len(np.unique(y)) > 1 else 0.0

    best_f1, best_thr = 0, 0.5
    sweep = []
    for thr in np.arange(0.005, 0.50, 0.005):
        preds = (probs >= thr).astype(int)
        f1 = f1_score(y, preds, zero_division=0)
        prec = precision_score(y, preds, zero_division=0)
        rec = recall_score(y, preds, zero_division=0)
        sweep.append({"threshold": round(float(thr), 3), "f1": f1, "precision": prec, "recall": rec})
        if f1 > best_f1:
            best_f1, best_thr = f1, thr

    log.info(f"\n{'='*60}")
    log.info(f"{name.upper()} RESULTS")
    log.info(f"{'='*60}")
    log.info(f"  AUC-ROC:     {auc:.4f}")
    log.info(f"  AUC-PR:      {ap:.4f}")
    log.info(f"  Best F1:     {best_f1:.4f} @ threshold={best_thr:.3f}")

    # Operational: "If we alert top-K cells per day, how many actual fires do we catch?"
    n_fire = int(y.sum())
    if n_fire > 0:
        sorted_idx = np.argsort(-probs)
        for k in [10, 25, 50, 100, 200]:
            top_k_labels = y[sorted_idx[:k]]
            captured = int(top_k_labels.sum())
            log.info(f"  Top-{k:3d} cells capture: {captured}/{n_fire} fires = {captured/n_fire*100:.1f}%")

    return {
        "auc_roc": float(auc),
        "auc_pr": float(ap),
        "best_f1": float(best_f1),
        "best_threshold": float(best_thr),
        "n_samples": len(y),
        "n_fire": n_fire,
        "sweep": sweep[:20],
    }


# ═══════════════════════════════════════════════════════════════════════════
# Inference: Predict Tomorrow's Risk Map
# ═══════════════════════════════════════════════════════════════════════════

def predict_tomorrow(model_path=None, target_date=None):
    """
    Generate a risk map for tomorrow (or target_date).
    Returns a DataFrame of cell_id, lat, lon, risk_score, risk_level.
    """
    if model_path is None:
        # Find the latest model directory
        model_dirs = sorted(OUT_DIR.glob("predictive_*/model.lgbm"), key=lambda p: p.stat().st_mtime)
        model_path = model_dirs[-1] if model_dirs else OUT_DIR / "predictive_v1" / "model.lgbm"

    model = lgb.Booster(model_file=str(model_path))

    if target_date is None:
        target_date = date.today() + timedelta(days=1)

    log.info(f"Predicting fire risk for {target_date}...")

    # Rebuild grid + features (could be cached in production)
    cells, grid_meta = build_grid()
    cells = compute_cell_terrain(cells, grid_meta)
    cells = add_cell_abm_ignition(cells)

    # Load recent FIRMS for lag features
    fires_by_cell = load_firms_and_assign_cells(cells, grid_meta)
    # Compute historical fire features using all available data (no leakage concern for inference)
    hist_features = compute_historical_fire_features(fires_by_cell, target_date.year + 1)
    for cell in cells:
        cid = cell["cell_id"]
        feats = hist_features.get(cid, {"hist_fire_days": 0, "hist_fire_freq": 0,
                                         "hist_fire_years": 0, "hist_fire_year_frac": 0})
        cell.update(feats)

    weather_by_grid, grid_coords = load_weather()
    cell_to_grid = _assign_cells_to_weather_grid(cells, grid_coords)
    ndvi_model = load_ndvi_model()
    neighbor_map = build_neighbor_map(cells)

    # Pre-compute weather per grid point for target date
    wx_by_grid = {}
    for gid, (wx_df, clim) in weather_by_grid.items():
        wx_by_grid[gid] = get_weather_features(wx_df, target_date, clim)

    doy = target_date.timetuple().tm_yday
    ndvi = ndvi_features(doy, ndvi_model)

    static_cols = [k for k in cells[0].keys()
                   if k.startswith("t_") or k in (
                       "abm_ignition", "hist_fire_days", "hist_fire_freq",
                       "hist_fire_years", "hist_fire_year_frac",
                       "centroid_lat", "centroid_lon")]

    rows = []
    for cell in cells:
        cid = cell["cell_id"]
        gid = cell_to_grid[cid]
        fire_dates = fires_by_cell.get(cid, set())
        nbr_fire_dates = set()
        for nid in neighbor_map.get(cid, []):
            nbr_fire_dates.update(fires_by_cell.get(nid, set()))

        row = {"cell_id": cid}
        row.update({k: cell[k] for k in static_cols})
        row.update(wx_by_grid[gid])  # per-cell gridded weather
        row.update(ndvi)
        row["doy"] = doy
        row["month"] = target_date.month
        row["is_weekend"] = 1 if target_date.weekday() >= 5 else 0

        past_fires = [fd for fd in fire_dates if fd < target_date]
        row["days_since_last_fire"] = (target_date - max(past_fires)).days if past_fires else 999
        recent = [fd for fd in fire_dates if 0 < (target_date - fd).days <= 7]
        row["fire_last_7d"] = len(recent)
        nbr_recent = [fd for fd in nbr_fire_dates if 0 < (target_date - fd).days <= 7]
        row["neighbor_fire_7d"] = len(nbr_recent)
        yesterday = target_date - timedelta(days=1)
        row["neighbor_fire_yesterday"] = 1 if yesterday in nbr_fire_dates else 0

        rows.append(row)

    pred_df = pd.DataFrame(rows)
    feature_cols = [c for c in pred_df.columns if c != "cell_id"]
    X = pred_df[feature_cols].values.astype(np.float32)
    np.nan_to_num(X, copy=False, nan=0.0, posinf=0.0, neginf=0.0)

    probs = model.predict(X)
    pred_df["risk_score"] = probs

    # Risk levels
    pred_df["risk_level"] = "LOW"
    pred_df.loc[pred_df["risk_score"] >= 0.10, "risk_level"] = "MODERATE"
    pred_df.loc[pred_df["risk_score"] >= 0.25, "risk_level"] = "HIGH"
    pred_df.loc[pred_df["risk_score"] >= 0.45, "risk_level"] = "CRITICAL"

    # Add lat/lon back
    cell_coords = {c["cell_id"]: (c["centroid_lat"], c["centroid_lon"], c["beat"], c["range"])
                   for c in cells}
    pred_df["lat"] = pred_df["cell_id"].map(lambda x: cell_coords[x][0])
    pred_df["lon"] = pred_df["cell_id"].map(lambda x: cell_coords[x][1])
    pred_df["beat"] = pred_df["cell_id"].map(lambda x: cell_coords[x][2])
    pred_df["range"] = pred_df["cell_id"].map(lambda x: cell_coords[x][3])

    # Summary
    for level in ["CRITICAL", "HIGH", "MODERATE", "LOW"]:
        n = (pred_df["risk_level"] == level).sum()
        log.info(f"  {level:10s}: {n:5d} cells")

    # Top 20 riskiest cells
    top20 = pred_df.nlargest(20, "risk_score")
    log.info(f"\nTop 20 riskiest cells for {target_date}:")
    for _, r in top20.iterrows():
        log.info(f"  {r['cell_id']:12s}  beat={r['beat']:20s}  "
                 f"range={r['range']:15s}  score={r['risk_score']:.4f}")

    return pred_df


# ═══════════════════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description="Predictive Fire Risk Model (25ha patches)")
    parser.add_argument("--tag", type=str, default="v1")
    parser.add_argument("--cell-size", type=int, default=500, help="Grid cell size in meters")
    parser.add_argument("--fire-season-only", action="store_true", default=True)
    parser.add_argument("--subsample-neg", type=float, default=10.0,
                        help="Subsample negatives 1:N (default 10)")
    parser.add_argument("--predict", type=str, default=None,
                        help="Run prediction for date (YYYY-MM-DD) instead of training")
    args = parser.parse_args()

    if args.predict:
        target = datetime.strptime(args.predict, "%Y-%m-%d").date()
        pred_df = predict_tomorrow(target_date=target)
        out = OUT_DIR / f"risk_map_{target.isoformat()}.csv"
        out.parent.mkdir(parents=True, exist_ok=True)
        pred_df[["cell_id", "lat", "lon", "beat", "range", "risk_score", "risk_level"]].to_csv(
            out, index=False)
        log.info(f"Risk map saved to {out}")
        return

    t0 = time.time()

    # Build dataset
    df, cells, grid_meta = build_dataset(
        cell_size_m=args.cell_size,
        fire_season_only=args.fire_season_only,
        subsample_neg=args.subsample_neg,
    )

    # Split
    log.info("\nTemporal split (train<=2023, val=2024, test=2025)...")
    train, val, test = temporal_split(df)

    # Train
    feature_cols = get_feature_cols(df)
    log.info(f"\nFeatures ({len(feature_cols)}):")
    for fc in feature_cols:
        log.info(f"  {fc}")

    model, results, importance = train_model(train, val, test, feature_cols, tag=args.tag)

    # Save grid metadata
    out_dir = OUT_DIR / f"predictive_{args.tag}"
    with open(out_dir / "grid_meta.json", "w") as f:
        json.dump(grid_meta, f, indent=2)

    # Save cell info (without geometries)
    cell_info = [{k: v for k, v in c.items() if k != "geometry"} for c in cells]
    pd.DataFrame(cell_info).to_csv(out_dir / "cells.csv", index=False)

    # Save dataset (sampled)
    df.to_parquet(out_dir / "dataset.parquet", index=False)

    elapsed = time.time() - t0
    log.info(f"\n{'='*65}")
    log.info(f"PREDICTIVE MODEL COMPLETE -- {elapsed:.0f}s")
    log.info(f"{'='*65}")
    log.info(f"Grid: {len(cells)} cells × {args.cell_size}m")
    log.info(f"Val  AUC: {results['val']['auc_roc']:.4f}")
    log.info(f"Test AUC: {results['test']['auc_roc']:.4f}")


if __name__ == "__main__":
    main()
