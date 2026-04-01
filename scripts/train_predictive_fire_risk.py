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
MP_GRIDDED_WX_PATH = ROOT / "data_lake" / "fire_weather" / "nasa_power_mp_gridded.parquet"
MP_EXTENDED_WX_PATH = ROOT / "data_lake" / "fire_weather" / "nasa_power_mp_extended.parquet"
FWI_PATH = ROOT / "data_lake" / "fire_weather" / "fwi_daily.parquet"
PHENOLOGY_PATH = ROOT / "data" / "phenology" / "division_ndvi_model.json"
ABM_PATH = ROOT / "data_lake" / "fire_detections" / "abm_ignition_probability.npy"
ABM_CALIBRATED_PATH = ROOT / "data_lake" / "human_activity" / "abm_ignition_calibrated.npy"
AOI_PATH = ROOT / "data" / "aoi" / "gunafinal.geojson"
ALPHAEARTH_PATH = ROOT / "data" / "training" / "alphaearth_grid_500m.parquet"
SETTLEMENT_DIST_PATH = ROOT / "data_lake" / "human_activity" / "dist_to_settlement_1km.npy"
ROAD_DIST_PATH = ROOT / "data_lake" / "human_activity" / "dist_to_road_1km.npy"
BEAT_FIRE_DENSITY_PATH = ROOT / "data_lake" / "human_activity" / "beat_fire_density.csv"
GRID_EMBEDDINGS_PATH = ROOT / "data" / "portal_embeddings" / "grid_embeddings.parquet"
WORLDCOVER_PATH = ROOT / "data_lake" / "terrain" / "worldcover_guna_raw.tif"
WORLDCOVER_TILES_DIR = ROOT / "data_lake" / "terrain" / "worldcover_tiles"
ASPECT_PATH = ROOT / "data_lake" / "terrain" / "aspect_guna_30m.tif"
MP_BEAT_PATH = ROOT / "data" / "aoi" / "MP_Merge Divsion Beat Range" / "MP_Merge" / "Mp_Beat_Merge.shp"
OUT_DIR = ROOT / "outputs" / "predictive_fire_risk"

FIRE_MONTHS = {2, 3, 4, 5}  # Feb-May

# ── v5: Features excluded from training (harmful/dead/redundant) ──
EXCLUDED_FEATURES = {
    # Spatial memorization — model memorizes locations instead of learning conditions
    "centroid_lat", "centroid_lon",
    # Redundant calendar — fire_season_intensity is just sin(doy), already captured by doy
    "fire_season_intensity",
    # Zero importance in v4 — statistically useless
    "month", "is_weekend", "is_peak_doy",
    "ntfp_tendu_season", "ntfp_mahua_peak", "ntfp_grazing_burn",
}

# At ~24°N latitude: 1° lon ≈ 101.4 km, 1° lat ≈ 110.6 km
# 500m = 0.00493° lon, 0.00452° lat
DEG_PER_M_LON_24N = 1.0 / 101400.0
DEG_PER_M_LAT_24N = 1.0 / 110600.0


# ═══════════════════════════════════════════════════════════════════════════
# Grid Construction
# ═══════════════════════════════════════════════════════════════════════════

def build_grid(cell_size_m=500, aoi_mode="guna"):
    """
    Build a regular grid covering the AOI.

    aoi_mode:
      - "guna" (default): Guna Division beat boundaries
      - "mp": All Madhya Pradesh (FIRMS fire extent, no beat filtering)

    Returns list of dicts with cell_id, geometry, centroid, row, col, beat, range.
    """
    log.info(f"Building {cell_size_m}m × {cell_size_m}m grid (aoi={aoi_mode})...")

    # Grid step in degrees
    dx = cell_size_m * DEG_PER_M_LON_24N
    dy = cell_size_m * DEG_PER_M_LAT_24N

    if aoi_mode == "mp":
        # MP-wide: use actual forest beat boundaries from shapefile
        import geopandas as gpd

        if not MP_BEAT_PATH.exists():
            raise FileNotFoundError(
                f"MP Beat shapefile not found: {MP_BEAT_PATH}\n"
                "Place Mp_Beat_Merge.shp in data/aoi/MP_Merge Divsion Beat Range/MP_Merge/"
            )

        log.info(f"  Loading MP beat boundaries from {MP_BEAT_PATH.name}...")
        gdf = gpd.read_file(MP_BEAT_PATH)
        if gdf.crs and not gdf.crs.is_geographic:
            gdf = gdf.to_crs(epsg=4326)
            log.info(f"  Reprojected to WGS84 (EPSG:4326)")

        beat_polys = []
        beat_names = []
        range_names = []
        division_names = []
        for _, row in gdf.iterrows():
            geom = row.geometry
            if geom is None or geom.is_empty:
                continue
            if not geom.is_valid:
                geom = geom.buffer(0)
            beat_polys.append(geom)
            beat_names.append(str(row.get("Beat", "Unknown")))
            range_names.append(str(row.get("Range", "")))
            division_names.append(str(row.get("Division", "")))

        log.info(f"  MP beats loaded: {len(beat_polys)} (from {gdf['Division'].nunique()} divisions)")

        aoi_union = unary_union(beat_polys)
        bounds = aoi_union.bounds
        log.info(f"  MP forest bounds: {bounds}")

        x_start = bounds[0]
        y_start = bounds[1]
        x_end = bounds[2]
        y_end = bounds[3]

        n_cols = int(np.ceil((x_end - x_start) / dx))
        n_rows = int(np.ceil((y_end - y_start) / dy))
        log.info(f"  Grid dimensions: {n_rows} rows × {n_cols} cols = {n_rows * n_cols} total cells")

        tree = STRtree(beat_polys)

        cells = []
        for r in range(n_rows):
            y0 = y_start + r * dy
            y1 = y0 + dy
            for c in range(n_cols):
                x0 = x_start + c * dx
                x1 = x0 + dx
                cell_geom = box(x0, y0, x1, y1)

                candidates = tree.query(cell_geom)
                hit_beat = None
                hit_range = None
                hit_division = None
                for idx in candidates:
                    if beat_polys[idx].intersects(cell_geom):
                        hit_beat = beat_names[idx]
                        hit_range = range_names[idx]
                        hit_division = division_names[idx]
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
                    "division": hit_division,
                })

        log.info(f"  MP forest cells: {len(cells)}")

    else:
        # Guna mode: use beat boundaries
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

        x_start = bounds[0]
        y_start = bounds[1]
        x_end = bounds[2]
        y_end = bounds[3]

        n_cols = int(np.ceil((x_end - x_start) / dx))
        n_rows = int(np.ceil((y_end - y_start) / dy))
        log.info(f"  Grid dimensions: {n_rows} rows × {n_cols} cols = {n_rows * n_cols} total cells")

        tree = STRtree(beat_polys)

        cells = []
        for r in range(n_rows):
            y0 = y_start + r * dy
            y1 = y0 + dy
            for c in range(n_cols):
                x0 = x_start + c * dx
                x1 = x0 + dx
                cell_geom = box(x0, y0, x1, y1)

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

def compute_cell_terrain(cells, grid_meta, aoi_mode="guna"):
    """
    Compute terrain features per cell directly from 30m rasters.

    Each 500m cell covers ~17×17 pixels at 30m resolution.
    We compute mean, max, and std for each terrain variable.
    """
    log.info("Computing terrain stats per cell...")

    # Use MP-wide rasters if available and aoi=mp
    mp_slope = RASTER_DIR / "slope_mp_30m.tif"
    mp_dem = RASTER_DIR / "dem_mp_30m.tif"
    mp_tpi = RASTER_DIR / "tpi_mp_30m.tif"

    if aoi_mode == "mp" and mp_dem.exists():
        terrain_files = {
            "slope": mp_slope if mp_slope.exists() else RASTER_DIR / "slope_30m.tif",
            "dem": mp_dem,
            "tpi": mp_tpi if mp_tpi.exists() else RASTER_DIR / "tpi_30m.tif",
            "road_dist": RASTER_DIR / "road_dist_30m.tif",
        }
        log.info("  Using MP-wide terrain rasters")
    else:
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
    """Add ABM ignition probability per cell.

    Prefers calibrated ABM grid (calibrated against FIRMS detections) if available,
    falls back to original ABM ignition probability.
    """
    # Try calibrated first, then original
    abm_path = None
    if ABM_CALIBRATED_PATH.exists():
        abm_path = ABM_CALIBRATED_PATH
        log.info("  ABM: using calibrated ignition grid")
    elif ABM_PATH.exists():
        abm_path = ABM_PATH
        log.info("  ABM: using original ignition grid (calibrated not found)")
    else:
        log.warning("  ABM: no ignition grid found — using default 0.5")
        for c in cells:
            c["abm_ignition"] = 0.5
        return cells

    abm = np.load(str(abm_path))
    grid_h, grid_w = abm.shape
    lat_min, lat_max = 23.88, 25.11
    lon_min, lon_max = 76.80, 77.49
    abm_max = max(float(abm.max()), 1e-6)
    log.info(f"  ABM: shape={abm.shape}, max={abm_max:.4f}")

    for cell in cells:
        lat, lon = cell["centroid_lat"], cell["centroid_lon"]
        # Only sample within the ABM grid's spatial extent
        if lat_min <= lat <= lat_max and lon_min <= lon <= lon_max:
            gy = int((lat_max - lat) / (lat_max - lat_min) * grid_h)
            gx = int((lon - lon_min) / (lon_max - lon_min) * grid_w)
            gy = np.clip(gy, 0, grid_h - 1)
            gx = np.clip(gx, 0, grid_w - 1)
            prob = float(abm[gy, gx])
            cell["abm_ignition"] = prob / abm_max if abm_max > 1.0 else prob
        else:
            cell["abm_ignition"] = 0.0  # unknown for out-of-range cells

    return cells


def add_cell_alphaearth(cells, mode="none", n_pca=16):
    """Add AlphaEarth 64-D embeddings per cell.

    Args:
        cells: list of cell dicts with cell_id
        mode: "none" (skip), "raw64" (all 64 dims), "pca16" (PCA to n_pca dims)
        n_pca: number of PCA components (only used if mode contains "pca")

    Returns cells with added aef_* features.
    """
    if mode == "none":
        return cells

    if not ALPHAEARTH_PATH.exists():
        log.warning(f"AlphaEarth file not found: {ALPHAEARTH_PATH}")
        log.warning("  Run: python scripts/resample_alphaearth_to_500m.py")
        return cells

    emb_cols = [f"A{i:02d}" for i in range(64)]
    aef = pd.read_parquet(ALPHAEARTH_PATH)
    log.info(f"AlphaEarth embeddings loaded: {len(aef)} cells, mode={mode}")

    # Build lookup: cell_id -> embedding vector
    aef_lookup = {}
    for _, row in aef.iterrows():
        aef_lookup[row["cell_id"]] = row[emb_cols].values.astype(np.float32)

    if "pca" in mode:
        from sklearn.decomposition import PCA
        # Fit PCA on all available embeddings
        all_vecs = np.stack(list(aef_lookup.values()))
        pca = PCA(n_components=n_pca, random_state=42)
        pca.fit(all_vecs)
        var_explained = pca.explained_variance_ratio_.sum()
        log.info(f"  PCA({64}->{n_pca}): {var_explained:.1%} variance retained")

        # Transform all embeddings
        for cid in aef_lookup:
            aef_lookup[cid] = pca.transform(aef_lookup[cid].reshape(1, -1))[0]

        feature_names = [f"aef_pc{i:02d}" for i in range(n_pca)]
    else:
        feature_names = [f"aef_{i:02d}" for i in range(64)]

    # Zero vector for cells without embeddings
    zero_vec = np.zeros(len(feature_names), dtype=np.float32)

    n_hit, n_miss = 0, 0
    for cell in cells:
        vec = aef_lookup.get(cell["cell_id"], zero_vec)
        if cell["cell_id"] in aef_lookup:
            n_hit += 1
        else:
            n_miss += 1
        for name, val in zip(feature_names, vec):
            cell[name] = float(val)

    # Add change features if available in the parquet
    change_cols = [c for c in aef.columns if c.startswith("aef_change_")]
    if change_cols:
        change_lookup = {}
        for _, row in aef.iterrows():
            change_lookup[row["cell_id"]] = {c: float(row[c]) for c in change_cols}
        for cell in cells:
            changes = change_lookup.get(cell["cell_id"], {c: 0.0 for c in change_cols})
            cell.update(changes)
        log.info(f"  Change features added: {change_cols}")

    log.info(f"  AlphaEarth: {n_hit} matched, {n_miss} missing (filled with zeros)")
    return cells


# ═══════════════════════════════════════════════════════════════════════════
# Human Activity Features (Phase 2)
# ═══════════════════════════════════════════════════════════════════════════

def add_cell_human_activity(cells, grid_meta, aoi_mode="guna"):
    """
    Add human activity features per cell:
      - ha_dist_settlement: distance to nearest settlement (km)
      - ha_dist_road: distance to nearest road (km)
      - ha_beat_fire_density: historical fire density per hectare (beat-level)
      - ha_mahua_zone: binary NTFP mahua collection zone
      - ha_tendu_zone: binary NTFP tendu leaf collection zone
    """
    log.info("Adding human activity features...")
    n_features = 0

    # ── MP-wide distance rasters (TIF, preferred for all-MP training) ──
    mp_settle_path = RASTER_DIR / "settlement_dist_mp.tif"
    mp_road_path = RASTER_DIR / "road_dist_mp.tif"

    # ── 1. Settlement distance ──
    if mp_settle_path.exists() and aoi_mode == "mp":
        _sample_tif_raster(cells, mp_settle_path, "ha_dist_settlement")
        n_features += 1
    elif SETTLEMENT_DIST_PATH.exists():
        _sample_npy_raster(cells, SETTLEMENT_DIST_PATH, "ha_dist_settlement",
                           lat_range=(23.88, 25.11), lon_range=(76.80, 77.49))
        n_features += 1
    else:
        log.warning("  Settlement distance raster not found — skipping")
        for c in cells:
            c["ha_dist_settlement"] = 5.0  # default

    # ── 2. Road distance ──
    if mp_road_path.exists() and aoi_mode == "mp":
        _sample_tif_raster(cells, mp_road_path, "ha_dist_road")
        n_features += 1
    elif ROAD_DIST_PATH.exists():
        _sample_npy_raster(cells, ROAD_DIST_PATH, "ha_dist_road",
                           lat_range=(23.88, 25.11), lon_range=(76.80, 77.49))
        n_features += 1
    else:
        log.warning("  Road distance raster not found — skipping")
        for c in cells:
            c["ha_dist_road"] = 5.0

    # ── 3. Beat fire density (CSV, join by beat name) ──
    if BEAT_FIRE_DENSITY_PATH.exists():
        bfd = pd.read_csv(BEAT_FIRE_DENSITY_PATH)
        # Build case-insensitive lookup (GeoJSON uses UPPERCASE, CSV uses Title Case)
        density_lookup = {}
        for _, row in bfd.iterrows():
            key = row["Beat"].strip().upper().replace("-", " ").replace("_", " ")
            density_lookup[key] = float(row["fire_density"])
        n_hit = 0
        for c in cells:
            beat = c.get("beat", "Unknown").strip().upper().replace("-", " ").replace("_", " ")
            density = density_lookup.get(beat, 0.0)
            c["ha_beat_fire_density"] = density
            if density > 0:
                n_hit += 1
        log.info(f"  Beat fire density: {n_hit}/{len(cells)} cells matched")
        n_features += 1
    else:
        log.warning("  Beat fire density CSV not found — skipping")
        for c in cells:
            c["ha_beat_fire_density"] = 0.0

    # ── 4. Mahua/Tendu NTFP zones (from grid_embeddings.parquet) ──
    if GRID_EMBEDDINGS_PATH.exists():
        emb = pd.read_parquet(GRID_EMBEDDINGS_PATH, columns=["ha_lat", "ha_lon", "mahua_zone", "tendu_zone"])
        # Build KD-tree-like lookup: find nearest embedding point per cell
        emb_lats = emb["ha_lat"].values
        emb_lons = emb["ha_lon"].values
        emb_mahua = emb["mahua_zone"].values
        emb_tendu = emb["tendu_zone"].values

        for c in cells:
            lat, lon = c["centroid_lat"], c["centroid_lon"]
            dists = (emb_lats - lat) ** 2 + (emb_lons - lon) ** 2
            idx = np.argmin(dists)
            c["ha_mahua_zone"] = float(emb_mahua[idx])
            c["ha_tendu_zone"] = float(emb_tendu[idx])
        n_features += 2
        log.info(f"  Mahua/Tendu zones: loaded from {len(emb)} embedding points")
    else:
        log.warning("  Grid embeddings not found — skipping NTFP zones")
        for c in cells:
            c["ha_mahua_zone"] = 0.0
            c["ha_tendu_zone"] = 0.0

    log.info(f"  Human activity features added: {n_features}")
    return cells


def _sample_npy_raster(cells, npy_path, feature_name, lat_range, lon_range):
    """Sample a .npy raster at cell centroids using geographic bounds."""
    data = np.load(str(npy_path))
    grid_h, grid_w = data.shape
    lat_min, lat_max = lat_range
    lon_min, lon_max = lon_range

    for cell in cells:
        lat, lon = cell["centroid_lat"], cell["centroid_lon"]
        gy = int((lat_max - lat) / (lat_max - lat_min) * grid_h)
        gx = int((lon - lon_min) / (lon_max - lon_min) * grid_w)
        gy = np.clip(gy, 0, grid_h - 1)
        gx = np.clip(gx, 0, grid_w - 1)
        cell[feature_name] = float(data[gy, gx])

    valid = [c[feature_name] for c in cells if c[feature_name] > 0]
    log.info(f"  {feature_name}: shape={data.shape}, "
             f"range=[{data.min():.2f}, {data.max():.2f}], "
             f"cells_with_value={len(valid)}")


def _sample_tif_raster(cells, tif_path, feature_name):
    """Sample a GeoTIFF raster at cell centroids using rasterio transform."""
    import rasterio

    with rasterio.open(tif_path) as src:
        data = src.read(1)
        transform = src.transform
        H, W = data.shape

        n_valid = 0
        for cell in cells:
            lat, lon = cell["centroid_lat"], cell["centroid_lon"]
            # Convert geographic coords to pixel coords via affine transform
            col = int((lon - transform.c) / transform.a)
            row = int((lat - transform.f) / transform.e)
            col = max(0, min(W - 1, col))
            row = max(0, min(H - 1, row))
            val = float(data[row, col])
            cell[feature_name] = val
            if val > 0:
                n_valid += 1

    log.info(f"  {feature_name} (TIF): shape={data.shape}, "
             f"range=[{data.min():.2f}, {data.max():.2f}], "
             f"cells_with_value={n_valid}/{len(cells)}")


# ═══════════════════════════════════════════════════════════════════════════
# Aspect Features (Phase 4)
# ═══════════════════════════════════════════════════════════════════════════

def add_cell_aspect(cells, grid_meta):
    """
    Compute aspect-derived features per cell from 30m aspect raster:
      - asp_sin: mean sin(aspect) — east-west component
      - asp_cos: mean cos(aspect) — north-south component
      - asp_south_frac: fraction of pixels with aspect 135°-225° (south-facing)
    """
    if not ASPECT_PATH.exists():
        log.warning("Aspect raster not found — skipping aspect features")
        for c in cells:
            c["asp_sin"] = 0.0
            c["asp_cos"] = 0.0
            c["asp_south_frac"] = 0.0
        return cells

    log.info("Computing aspect features per cell...")

    with rasterio.open(ASPECT_PATH) as src:
        aspect_data = src.read(1).astype(np.float32)
        transform = src.transform
        H, W = src.height, src.width

    half_dx = grid_meta["dx"] / 2
    half_dy = grid_meta["dy"] / 2

    for cell in cells:
        lon, lat = cell["centroid_lon"], cell["centroid_lat"]
        col_min = max(0, int((lon - half_dx - transform.c) / transform.a))
        col_max = min(W, int((lon + half_dx - transform.c) / transform.a) + 1)
        row_min = max(0, int((lat + half_dy - transform.f) / transform.e))
        row_max = min(H, int((lat - half_dy - transform.f) / transform.e) + 1)

        patch = aspect_data[row_min:row_max, col_min:col_max]
        valid = patch[(patch >= 0) & (patch <= 360)]

        if len(valid) > 0:
            rad = np.deg2rad(valid)
            cell["asp_sin"] = float(np.mean(np.sin(rad)))
            cell["asp_cos"] = float(np.mean(np.cos(rad)))
            # South-facing: aspect between 135° and 225°
            south_mask = (valid >= 135) & (valid <= 225)
            cell["asp_south_frac"] = float(south_mask.sum() / len(valid))
        else:
            cell["asp_sin"] = 0.0
            cell["asp_cos"] = 0.0
            cell["asp_south_frac"] = 0.0

    log.info(f"  Aspect features computed for {len(cells)} cells")
    return cells


# ═══════════════════════════════════════════════════════════════════════════
# Land Cover Fractions (Phase 3)
# ═══════════════════════════════════════════════════════════════════════════

def _open_worldcover_tiles():
    """
    Open all available WorldCover tile files and return a list of
    (rasterio_dataset, bounds) for windowed reading.
    Falls back to single clipped raster if tiles dir doesn't exist.
    """
    tiles = []

    # Try individual tiles first (for MP-wide mode)
    if WORLDCOVER_TILES_DIR.exists():
        for tf in sorted(WORLDCOVER_TILES_DIR.glob("ESA_WorldCover_*.tif")):
            src = rasterio.open(tf)
            tiles.append((src, src.bounds))
        if tiles:
            log.info(f"  WorldCover: {len(tiles)} tiles loaded from {WORLDCOVER_TILES_DIR}")

    # Also include the Guna clipped raster if available
    if WORLDCOVER_PATH.exists() and not tiles:
        src = rasterio.open(WORLDCOVER_PATH)
        tiles.append((src, src.bounds))
        log.info(f"  WorldCover: using clipped raster {WORLDCOVER_PATH}")

    return tiles


def _find_tile_for_point(tiles, lon, lat):
    """Find the tile that contains a given lon/lat point."""
    for src, bounds in tiles:
        if bounds.left <= lon <= bounds.right and bounds.bottom <= lat <= bounds.top:
            return src
    return None


def add_cell_landcover(cells, grid_meta):
    """
    Compute ESA WorldCover 10m class fractions per cell.

    Classes: 10=tree, 20=shrub, 30=grass, 40=crop, 50=built, 60=bare, 80=water
    Derived: burnable_frac = tree + shrub + grass, forest_edge_len

    Supports multi-tile reading for MP-wide mode (windowed, no full load).
    Falls back gracefully if WorldCover is not available.
    """
    tiles = _open_worldcover_tiles()
    if not tiles:
        log.warning("WorldCover: no raster found — all land cover features = 0")
        for c in cells:
            c["lc_frac_tree"] = 0.0
            c["lc_frac_shrub"] = 0.0
            c["lc_frac_grass"] = 0.0
            c["lc_frac_crop"] = 0.0
            c["lc_frac_built"] = 0.0
            c["lc_frac_bare"] = 0.0
            c["lc_frac_water"] = 0.0
            c["lc_burnable_frac"] = 0.0
            c["lc_forest_edge_len"] = 0.0
        return cells

    log.info(f"Computing land cover fractions per cell ({len(cells)} cells)...")

    class_map = {10: "tree", 20: "shrub", 30: "grass", 40: "crop", 50: "built", 60: "bare", 80: "water"}
    half_dx = grid_meta["dx"] / 2
    half_dy = grid_meta["dy"] / 2
    n_hit = 0

    for ci, cell in enumerate(cells):
        lon, lat = cell["centroid_lon"], cell["centroid_lat"]
        src = _find_tile_for_point(tiles, lon, lat)

        if src is None:
            # No tile covers this cell — fill with zeros
            for class_name in class_map.values():
                cell[f"lc_frac_{class_name}"] = 0.0
            cell["lc_burnable_frac"] = 0.0
            cell["lc_forest_edge_len"] = 0.0
            continue

        n_hit += 1
        transform = src.transform
        H, W = src.height, src.width

        col_min = max(0, int((lon - half_dx - transform.c) / transform.a))
        col_max = min(W, int((lon + half_dx - transform.c) / transform.a) + 1)
        row_min = max(0, int((lat + half_dy - transform.f) / transform.e))
        row_max = min(H, int((lat - half_dy - transform.f) / transform.e) + 1)

        # Windowed read — only loads the pixels we need
        from rasterio.windows import Window
        win = Window(col_min, row_min, col_max - col_min, row_max - row_min)
        if win.width <= 0 or win.height <= 0:
            for class_name in class_map.values():
                cell[f"lc_frac_{class_name}"] = 0.0
            cell["lc_burnable_frac"] = 0.0
            cell["lc_forest_edge_len"] = 0.0
            continue

        patch = src.read(1, window=win)
        total = max(patch.size, 1)

        for class_val, class_name in class_map.items():
            cell[f"lc_frac_{class_name}"] = float((patch == class_val).sum() / total)

        cell["lc_burnable_frac"] = cell["lc_frac_tree"] + cell["lc_frac_shrub"] + cell["lc_frac_grass"]

        tree_mask = (patch == 10).astype(np.int8)
        if tree_mask.size > 1 and tree_mask.shape[0] > 1 and tree_mask.shape[1] > 1:
            edge_h = np.abs(np.diff(tree_mask, axis=0)).sum()
            edge_v = np.abs(np.diff(tree_mask, axis=1)).sum()
            cell["lc_forest_edge_len"] = float(edge_h + edge_v)
        else:
            cell["lc_forest_edge_len"] = 0.0

        if (ci + 1) % 5000 == 0:
            log.info(f"    Land cover: {ci+1}/{len(cells)} cells...")

    # Close tile handles
    for src, _ in tiles:
        src.close()

    log.info(f"  Land cover: {n_hit}/{len(cells)} cells had WorldCover data")
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

    # Load FIRMS — prefer consolidated file, then individual parquets
    mp_consolidated = ROOT / "data_lake" / "fire_detections" / "firms_mp_viirs" / "firms_mp_consolidated.parquet"
    firms_dirs = [
        FIRMS_DIR,
        ROOT / "data_lake" / "fire_detections" / "firms_mp_viirs",
    ]
    frames = []
    if mp_consolidated.exists():
        # Fast path: load pre-consolidated MP-wide data
        frames.append(pd.read_parquet(mp_consolidated))
        log.info(f"  Loaded MP consolidated: {len(frames[0]):,} rows")
    for fdir in firms_dirs:
        if not fdir.exists():
            continue
        for f in sorted(fdir.glob("*.parquet")):
            if f == mp_consolidated:
                continue  # already loaded
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

    # Vectorized grid assignment
    cols = ((firms["longitude"].values - x_start) / dx).astype(int)
    rows = ((firms["latitude"].values - y_start) / dy).astype(int)
    dates = firms["acq_date"].dt.date.values

    # Valid mask: within grid bounds
    valid = (rows >= 0) & (rows < n_rows) & (cols >= 0) & (cols < n_cols)
    log.info(f"  Detections within grid bounds: {valid.sum()}/{len(firms)}")

    direct_matched = 0
    for i in np.where(valid)[0]:
        r, c = int(rows[i]), int(cols[i])
        fire_date = dates[i]

        hit = cell_lookup.get((r, c))
        if hit is not None:
            direct_matched += 1

        # Temporal expansion: mark day T-expand ... T+expand
        fire_dates_list = [fire_date + timedelta(days=delta)
                           for delta in range(-expand_days, expand_days + 1)]

        # Spatial expansion: mark all cells within radius (circular)
        for dr in range(-expand_radius, expand_radius + 1):
            for dc in range(-expand_radius, expand_radius + 1):
                if dr * dr + dc * dc > expand_radius * expand_radius:
                    continue
                neighbor_id = cell_lookup.get((r + dr, c + dc))
                if neighbor_id is not None:
                    for fd in fire_dates_list:
                        fires_by_cell[neighbor_id].add(fd)

    total_fire_cell_days = sum(len(v) for v in fires_by_cell.values())
    log.info(f"  Direct matches: {direct_matched}/{len(firms)}")
    log.info(f"  Cells with fires (after expansion): {len(fires_by_cell)}")
    log.info(f"  Total cell-fire-days (expanded): {total_fire_cell_days}")
    log.info(f"  Expansion: radius={expand_radius} cells (~{expand_radius * grid_meta['cell_size_m']}m), "
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


def filter_ignition_dates(fires_by_cell, cells, grid_meta, clear_days=14):
    """
    Filter fire labels to keep only NEW IGNITIONS — fires with no prior fire
    within 5km in the preceding `clear_days` days.

    This removes spread/continuation labels, keeping only genuine new fire starts.
    Returns a new fires_by_cell dict with only ignition dates.
    """
    log.info(f"Filtering ignition-only labels (clear_days={clear_days}, radius=5km)...")

    # Build cell lookup for spatial proximity
    cell_lookup = {}
    for cell in cells:
        cell_lookup[cell["cell_id"]] = (cell["centroid_lat"], cell["centroid_lon"])

    # Build spatial neighbor sets within 5km (~10 cells at 500m)
    # At 24°N: 5km ≈ 0.0493° lon, 0.0452° lat
    radius_deg_lat = 5.0 / 110.6  # ~0.0452°
    radius_deg_lon = 5.0 / 101.4  # ~0.0493°

    # Build 5km neighbor index using vectorized distance computation
    cell_ids = [c["cell_id"] for c in cells]
    lats = np.array([c["centroid_lat"] for c in cells])
    lons = np.array([c["centroid_lon"] for c in cells])

    nearby_cells = defaultdict(list)
    for i in range(len(cells)):
        dlat = np.abs(lats - lats[i])
        dlon = np.abs(lons - lons[i])
        # Quick bounding box filter first
        mask = (dlat <= radius_deg_lat) & (dlon <= radius_deg_lon)
        mask[i] = False  # exclude self
        candidates = np.where(mask)[0]
        # Precise distance for candidates
        for j in candidates:
            dist_km = ((dlat[j] * 110.6) ** 2 + (dlon[j] * 101.4) ** 2) ** 0.5
            if dist_km <= 5.0:
                nearby_cells[cell_ids[i]].append(cell_ids[j])

    log.info(f"  Built 5km neighbor index: avg {np.mean([len(v) for v in nearby_cells.values()]):.0f} neighbors/cell")

    # For each cell-date, check if any nearby cell had fire in prior clear_days
    ignition_fires = defaultdict(set)
    total_fire_days = 0
    total_ignitions = 0

    for cid, fire_dates in fires_by_cell.items():
        for fd in fire_dates:
            total_fire_days += 1

            # Check: was there fire within 5km in the past clear_days?
            is_continuation = False
            # Check self (same cell, recent fire)
            for prev_fd in fire_dates:
                gap = (fd - prev_fd).days
                if 1 <= gap <= clear_days:
                    is_continuation = True
                    break

            if not is_continuation:
                # Check nearby cells
                for ncid in nearby_cells.get(cid, []):
                    nbr_dates = fires_by_cell.get(ncid, set())
                    for prev_fd in nbr_dates:
                        gap = (fd - prev_fd).days
                        if 1 <= gap <= clear_days:
                            is_continuation = True
                            break
                    if is_continuation:
                        break

            if not is_continuation:
                ignition_fires[cid].add(fd)
                total_ignitions += 1

    pct = total_ignitions / max(total_fire_days, 1) * 100
    log.info(f"  Total fire cell-days: {total_fire_days:,}")
    log.info(f"  New ignitions: {total_ignitions:,} ({pct:.1f}%)")
    log.info(f"  Spread/continuation removed: {total_fire_days - total_ignitions:,}")

    return ignition_fires


# ═══════════════════════════════════════════════════════════════════════════
# Weather Features (shared across all cells — single weather station)
# ═══════════════════════════════════════════════════════════════════════════

WEATHER_COLS = ["temp_c", "rh_pct", "wind_kmh", "precip_mm"]


def _enrich_weather_df(weather):
    """Add derived rolling/computed features to a weather DataFrame (indexed by date)."""
    weather["consecutive_dry_days"] = _compute_consecutive_dry(weather["precip_mm"])
    weather["precip_7d"] = weather["precip_mm"].rolling(7, min_periods=1).sum()
    weather["precip_14d"] = weather["precip_mm"].rolling(14, min_periods=1).sum()
    weather["precip_30d"] = weather["precip_mm"].rolling(30, min_periods=1).sum()
    weather["temp_7d_mean"] = weather["temp_c"].rolling(7, min_periods=1).mean()
    weather["rh_7d_min"] = weather["rh_pct"].rolling(7, min_periods=1).min()
    weather["wind_7d_max"] = weather["wind_kmh"].rolling(7, min_periods=1).max()

    # Fuel dryness proxy (Keetch-Byram style)
    weather["fuel_dryness"] = (
        weather["consecutive_dry_days"] * weather["temp_c"].clip(lower=0) / 40.0
    ).clip(upper=10.0)

    # ── v6: Vapor Pressure Deficit (kPa) — #1 missing feature per literature ──
    # VPD = saturation vapor pressure × (1 - RH/100)
    # Tetens formula: es = 0.6108 × exp(17.27 × T / (T + 237.3))
    temp = weather["temp_c"].clip(lower=-40, upper=60)
    es = 0.6108 * np.exp(17.27 * temp / (temp + 237.3))
    weather["vpd"] = (es * (1.0 - weather["rh_pct"].clip(0, 100) / 100.0)).clip(lower=0)
    weather["vpd_7d_max"] = weather["vpd"].rolling(7, min_periods=1).max()

    # ── v6: Diurnal Temperature Range — high DTR = dry atmosphere ──
    if "temp_max_c" in weather.columns and "temp_min_c" in weather.columns:
        weather["dtr"] = (weather["temp_max_c"] - weather["temp_min_c"]).clip(lower=0)
    else:
        weather["dtr"] = 0.0

    # ── v6: Precipitation deficit — deviation from 30-day climatological mean ──
    # Negative = drier than normal → higher fire risk
    precip_30d_clim = weather["precip_mm"].rolling(365, min_periods=30).mean() * 30
    weather["precip_deficit_30d"] = weather["precip_30d"] - precip_30d_clim.fillna(weather["precip_30d"])

    # ── v6: Extended variables (soil moisture, surface temp, solar radiation) ──
    if "soil_moisture_surface" in weather.columns:
        weather["sm_surface_7d_min"] = weather["soil_moisture_surface"].rolling(7, min_periods=1).min()
        weather["sm_rootzone_7d_min"] = weather["soil_moisture_rootzone"].rolling(7, min_periods=1).min()
        weather["sm_surface_30d_mean"] = weather["soil_moisture_surface"].rolling(30, min_periods=1).mean()
        # Soil moisture anomaly: deviation from rolling 365-day mean
        sm_clim = weather["soil_moisture_surface"].rolling(365, min_periods=30).mean()
        weather["sm_anomaly"] = weather["soil_moisture_surface"] - sm_clim.fillna(
            weather["soil_moisture_surface"])
    if "surface_temp_c" in weather.columns:
        weather["lst_7d_max"] = weather["surface_temp_c"].rolling(7, min_periods=1).max()
        # LST-air temp difference: higher = drier surface
        weather["lst_air_diff"] = weather["surface_temp_c"] - weather["temp_c"]
    if "solar_radiation" in weather.columns:
        weather["srad_7d_mean"] = weather["solar_radiation"].rolling(7, min_periods=1).mean()

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


def load_weather(aoi_mode="guna"):
    """Load gridded or single-station weather, compute FWI, and anomalies.

    aoi_mode="guna": uses 15-point Guna grid
    aoi_mode="mp": uses 247-point MP-wide grid (falls back to Guna if MP not available)

    Returns dict of grid_id -> (weather_df, clim_dict) plus grid_coords dict.
    """
    log.info("Loading weather data...")

    if aoi_mode == "mp" and MP_GRIDDED_WX_PATH.exists():
        log.info("  Loading MP-wide gridded weather...")
        return _load_gridded_weather(MP_GRIDDED_WX_PATH)
    elif GRIDDED_WX_PATH.exists():
        if aoi_mode == "mp":
            log.warning("  MP weather not found — falling back to Guna 15-point grid")
        return _load_gridded_weather(GRIDDED_WX_PATH)
    else:
        log.info("  No gridded weather — using single station")
        return _load_single_weather()


def _load_gridded_weather(wx_path=None):
    """Load multi-point gridded weather, optionally merging extended variables."""
    if wx_path is None:
        wx_path = GRIDDED_WX_PATH
    raw = pd.read_parquet(wx_path)
    raw["date"] = pd.to_datetime(raw["date"])
    grid_ids = sorted(raw["grid_id"].unique())
    log.info(f"  Gridded weather: {len(grid_ids)} stations, "
             f"{raw['date'].min().date()} to {raw['date'].max().date()}")

    # v6: Merge extended variables (soil moisture, surface temp, solar radiation) if available
    ext_path = wx_path.parent / wx_path.name.replace("gridded", "extended")
    if not ext_path.exists():
        ext_path = MP_EXTENDED_WX_PATH
    if ext_path.exists():
        ext = pd.read_parquet(ext_path)
        ext["date"] = pd.to_datetime(ext["date"])
        ext_cols = [c for c in ext.columns
                    if c not in raw.columns and c not in ("date", "grid_id", "grid_lat", "grid_lon")]
        if ext_cols:
            raw = raw.merge(ext[["date", "grid_id"] + ext_cols], on=["date", "grid_id"], how="left")
            log.info(f"  Extended weather merged: {ext_cols}")

    # Build grid point coordinates for nearest-neighbor lookup
    grid_coords = {}
    for gid in grid_ids:
        row = raw[raw["grid_id"] == gid].iloc[0]
        grid_coords[gid] = (row["grid_lat"], row["grid_lon"])

    # FWI cache for gridded data (named based on weather file)
    fwi_cache_name = wx_path.stem.replace("nasa_power_", "fwi_") + "_cache.parquet"
    fwi_cache = wx_path.parent / fwi_cache_name
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
    features["wx_precip_30d"] = float(row.get("precip_30d", 0))
    features["wx_temp_7d_mean"] = float(row.get("temp_7d_mean", 0))
    features["wx_rh_7d_min"] = float(row.get("rh_7d_min", 0))
    features["wx_wind_7d_max"] = float(row.get("wind_7d_max", 0))
    features["wx_fuel_dryness"] = float(row.get("fuel_dryness", 0))
    features["wx_heat_streak"] = float(row.get("heat_streak", 0))

    # v6: Vapor Pressure Deficit (kPa) — key fire weather variable
    features["wx_vpd"] = float(row.get("vpd", 0))
    features["wx_vpd_7d_max"] = float(row.get("vpd_7d_max", 0))
    # v6: Diurnal Temperature Range
    features["wx_dtr"] = float(row.get("dtr", 0))
    # v6: 30-day precipitation deficit (negative = drier than normal)
    features["wx_precip_deficit_30d"] = float(row.get("precip_deficit_30d", 0))

    # v6: Soil moisture (from extended POWER variables)
    features["wx_sm_surface"] = float(row.get("soil_moisture_surface", 0))
    features["wx_sm_rootzone"] = float(row.get("soil_moisture_rootzone", 0))
    features["wx_sm_surface_7d_min"] = float(row.get("sm_surface_7d_min", 0))
    features["wx_sm_rootzone_7d_min"] = float(row.get("sm_rootzone_7d_min", 0))
    features["wx_sm_surface_30d"] = float(row.get("sm_surface_30d_mean", 0))
    features["wx_sm_anomaly"] = float(row.get("sm_anomaly", 0))
    # v6: Land Surface Temperature proxy
    features["wx_lst"] = float(row.get("surface_temp_c", 0))
    features["wx_lst_7d_max"] = float(row.get("lst_7d_max", 0))
    features["wx_lst_air_diff"] = float(row.get("lst_air_diff", 0))
    # v6: Solar radiation
    features["wx_srad"] = float(row.get("solar_radiation", 0))
    features["wx_srad_7d"] = float(row.get("srad_7d_mean", 0))

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
# Lunar Phase (sinusoidal approximation — no external library needed)
# ═══════════════════════════════════════════════════════════════════════════

def _lunar_phase(d):
    """
    Approximate lunar illumination fraction (0.0 = new moon, 1.0 = full moon).
    Uses the synodic month (29.53059 days) with a known new moon reference.
    """
    # Reference new moon: 2000-01-06 18:14 UTC
    ref = date(2000, 1, 6)
    days_since = (d - ref).days
    synodic = 29.53059
    phase = (days_since % synodic) / synodic  # 0 = new, 0.5 = full
    # Convert to illumination: 0 at new, 1 at full
    illumination = 0.5 * (1 - np.cos(2 * np.pi * phase))
    return float(illumination)


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
    """Map each cell to its nearest weather grid point (vectorized).

    Returns dict: cell_id -> grid_id.
    If grid_coords is None (single station), all cells map to "default".
    """
    if grid_coords is None:
        return {c["cell_id"]: "default" for c in cells}

    grid_ids = list(grid_coords.keys())
    grid_lats = np.array([grid_coords[g][0] for g in grid_ids])
    grid_lons = np.array([grid_coords[g][1] for g in grid_ids])

    cell_lats = np.array([c["centroid_lat"] for c in cells])
    cell_lons = np.array([c["centroid_lon"] for c in cells])

    # Vectorized nearest-neighbor: (n_cells, n_grid) distance matrix
    # Process in chunks to avoid huge memory for 42K × 247
    mapping = {}
    chunk_size = 5000
    for start in range(0, len(cells), chunk_size):
        end = min(start + chunk_size, len(cells))
        clat = cell_lats[start:end, None]  # (chunk, 1)
        clon = cell_lons[start:end, None]
        dists = (clat - grid_lats[None, :]) ** 2 + (clon - grid_lons[None, :]) ** 2
        nearest = np.argmin(dists, axis=1)
        for i, idx in enumerate(nearest):
            mapping[cells[start + i]["cell_id"]] = grid_ids[idx]

    return mapping


# ═══════════════════════════════════════════════════════════════════════════
# Weekly Temporal Aggregation Helpers (v5)
# ═══════════════════════════════════════════════════════════════════════════

def generate_fire_season_weeks(start_year, end_year, weather_start, weather_end):
    """
    Generate fire-season ISO weeks as lists of dates.
    Returns list of (week_dates, mid_date, year) tuples.
    """
    from collections import OrderedDict
    # First generate all fire season dates
    all_dates = []
    for year in range(start_year, end_year):
        for month in FIRE_MONTHS:
            for day in range(1, 32):
                try:
                    d = date(year, month, day)
                    if weather_start <= d <= weather_end:
                        all_dates.append(d)
                except ValueError:
                    continue

    # Group into ISO weeks
    week_groups = OrderedDict()
    for d in all_dates:
        iso_year, iso_week, _ = d.isocalendar()
        key = (iso_year, iso_week)
        if key not in week_groups:
            week_groups[key] = []
        week_groups[key].append(d)

    # Return as list of (dates_list, mid_date, year)
    result = []
    for key, dates in week_groups.items():
        mid = dates[len(dates) // 2]
        result.append((dates, mid, mid.year))
    return result


def aggregate_weather_weekly(wx_cache, grid_id, week_dates):
    """Aggregate daily weather features to weekly summaries."""
    daily = [wx_cache.get((grid_id, d)) for d in week_dates]
    daily = [f for f in daily if f is not None]

    if not daily:
        mid = week_dates[len(week_dates) // 2]
        return wx_cache.get((grid_id, mid), {})

    last = daily[-1]
    mid_feat = daily[len(daily) // 2]
    agg = {}

    # Core weather: appropriate aggregations
    agg["wx_temp_c"] = float(np.mean([f.get("wx_temp_c", 0) for f in daily]))
    agg["wx_rh_pct"] = float(min(f.get("wx_rh_pct", 100) for f in daily))
    agg["wx_wind_kmh"] = float(max(f.get("wx_wind_kmh", 0) for f in daily))
    agg["wx_precip_mm"] = float(sum(f.get("wx_precip_mm", 0) for f in daily))

    # FWI indices: weekly max (worst fire weather day)
    for col in ["wx_ffmc", "wx_dmc", "wx_dc", "wx_isi", "wx_bui", "wx_fwi"]:
        agg[col] = float(max(f.get(col, 0) for f in daily))

    # Rolling features: use last day of week (most up-to-date)
    for col in ["wx_consecutive_dry", "wx_precip_7d", "wx_precip_14d", "wx_precip_30d",
                "wx_temp_7d_mean", "wx_rh_7d_min", "wx_wind_7d_max",
                "wx_fuel_dryness", "wx_heat_streak"]:
        agg[col] = float(last.get(col, 0))

    # v6: VPD — weekly max (worst drying stress day)
    agg["wx_vpd"] = float(max(f.get("wx_vpd", 0) for f in daily))
    agg["wx_vpd_7d_max"] = float(last.get("wx_vpd_7d_max", 0))
    # v6: DTR — weekly mean
    agg["wx_dtr"] = float(np.mean([f.get("wx_dtr", 0) for f in daily]))
    # v6: Precip deficit — last day (cumulative)
    agg["wx_precip_deficit_30d"] = float(last.get("wx_precip_deficit_30d", 0))

    # v6: Soil moisture — weekly min (driest day = worst fire risk)
    agg["wx_sm_surface"] = float(min(f.get("wx_sm_surface", 0) for f in daily))
    agg["wx_sm_rootzone"] = float(min(f.get("wx_sm_rootzone", 0) for f in daily))
    agg["wx_sm_surface_7d_min"] = float(last.get("wx_sm_surface_7d_min", 0))
    agg["wx_sm_rootzone_7d_min"] = float(last.get("wx_sm_rootzone_7d_min", 0))
    agg["wx_sm_surface_30d"] = float(last.get("wx_sm_surface_30d", 0))
    agg["wx_sm_anomaly"] = float(np.mean([f.get("wx_sm_anomaly", 0) for f in daily]))
    # v6: LST — weekly max
    agg["wx_lst"] = float(max(f.get("wx_lst", 0) for f in daily))
    agg["wx_lst_7d_max"] = float(last.get("wx_lst_7d_max", 0))
    agg["wx_lst_air_diff"] = float(max(f.get("wx_lst_air_diff", 0) for f in daily))
    # v6: Solar radiation — weekly mean
    agg["wx_srad"] = float(np.mean([f.get("wx_srad", 0) for f in daily]))
    agg["wx_srad_7d"] = float(last.get("wx_srad_7d", 0))

    # Anomalies: mean across the week
    for col in ["wx_anom_temp_c", "wx_anom_rh_pct", "wx_anom_wind_kmh", "wx_anom_precip_mm"]:
        vals = [f.get(col, 0) for f in daily]
        agg[col] = float(np.mean(vals))

    # NTFP/calendar features: use mid-week values
    for col in ["ntfp_tendu_season", "ntfp_mahua_peak", "ntfp_grazing_burn",
                "fire_season_intensity"]:
        agg[col] = mid_feat.get(col, 0)

    return agg


# ═══════════════════════════════════════════════════════════════════════════
# Dataset Construction (vectorized)
# ═══════════════════════════════════════════════════════════════════════════

def build_dataset(cell_size_m=500, fire_season_only=True, subsample_neg=10.0,
                   alphaearth_mode="none", alphaearth_pca=16,
                   label_mode="spread", clear_days=14, no_fire_lag=False,
                   temporal_agg="day", aoi_mode="guna"):
    """
    Build cell × period training dataset.

    For each cell × each period (day or week) in the fire season:
      features = weather + terrain + phenology + ignition + history + spatial
      label = 1 if FIRMS detected fire in that cell during that period

    temporal_agg: "day" (default) or "week" (v5 weekly aggregation)
    subsample_neg: keep 1-in-N negative samples (daily mode only).
    In weekly mode, hard negative sampling is used instead.
    """
    log.info("=" * 65)
    log.info("BUILDING PREDICTIVE FIRE RISK DATASET (25ha PATCH GRID)")
    log.info("=" * 65)

    # 1. Build grid
    cells, grid_meta = build_grid(cell_size_m, aoi_mode=aoi_mode)

    # 2. Compute terrain per cell
    cells = compute_cell_terrain(cells, grid_meta, aoi_mode=aoi_mode)

    # 3. Load FIRMS + assign to cells
    if label_mode == "ignition":
        # No spatial/temporal expansion for ignition mode — exact cell-day labels
        fires_by_cell_raw = load_firms_and_assign_cells(cells, grid_meta, expand_radius=0, expand_days=0)
        fires_by_cell = filter_ignition_dates(fires_by_cell_raw, cells, grid_meta, clear_days=clear_days)
        log.info(f"  Label mode: IGNITION (clear_days={clear_days})")
    else:
        fires_by_cell = load_firms_and_assign_cells(cells, grid_meta)
        log.info(f"  Label mode: SPREAD (default)")

    # 4. Add static features
    cells = add_cell_abm_ignition(cells)

    # 4b. Add AlphaEarth embeddings (if requested)
    cells = add_cell_alphaearth(cells, mode=alphaearth_mode, n_pca=alphaearth_pca)

    # 4c. Add human activity features (settlement dist, road dist, beat fire density, NTFP zones)
    cells = add_cell_human_activity(cells, grid_meta, aoi_mode=aoi_mode)

    # 4d. Add aspect features
    cells = add_cell_aspect(cells, grid_meta)

    # 4e. Add land cover fractions (if WorldCover raster available)
    cells = add_cell_landcover(cells, grid_meta)

    # Pre-compute historical fire features per year cutoff (prevents temporal leakage)
    hist_by_year = {}
    for yr in range(2014, 2027):
        hist_by_year[yr] = compute_historical_fire_features(fires_by_cell, yr)
    log.info(f"  Historical fire features computed for year cutoffs 2014-2026")

    # 5. Build neighbor map for spatial features
    neighbor_map = build_neighbor_map(cells)

    # 6. Load weather + NDVI
    weather_by_grid, grid_coords = load_weather(aoi_mode=aoi_mode)
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

    # Static feature columns from cells (terrain + ABM + AlphaEarth + human + aspect + landcover + location)
    static_prefixes = ("t_", "aef_", "ha_", "asp_", "lc_")
    static_names = {"abm_ignition", "centroid_lat", "centroid_lon"}
    static_cols = [k for k in cells[0].keys()
                   if (any(k.startswith(p) for p in static_prefixes) or k in static_names)
                   and k not in EXCLUDED_FEATURES]
    log.info(f"  Static features: {len(static_cols)} (after excluding {len(EXCLUDED_FEATURES)} harmful features)")

    # 8. Build sample periods (daily or weekly)
    if temporal_agg == "week":
        sample_weeks = generate_fire_season_weeks(2014, 2026, weather_start, weather_end)
        n_periods = len(sample_weeks)
        log.info(f"\nBuilding samples ({len(cells)} cells × {n_periods} weeks)...")
        log.info(f"  Weekly aggregation: {n_periods} weeks from {len(sample_dates)} fire-season days")
    else:
        sample_weeks = None
        n_periods = len(sample_dates)
        log.info(f"\nBuilding samples ({len(cells)} cells × {n_periods} days)...")

    log.info(f"  Raw combinations: {len(cells) * n_periods:,}")

    # Pre-compute has_ever_burned for hard negative sampling (v5)
    has_ever_burned = set(cid for cid, dates in fires_by_cell.items() if dates)
    log.info(f"  Cells with any historical fire: {len(has_ever_burned)}")

    if temporal_agg == "week":
        log.info(f"  Hard negative sampling: 1/5 (burned cells), 1/20 (never-burned)")
    else:
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

        if temporal_agg == "week":
            # ── Weekly mode: iterate over weeks ──
            for week_dates, mid_date, year in sample_weeks:
                # Label: 1 if ANY day in this week has fire in this cell
                label = 1 if any(d in fire_dates for d in week_dates) else 0

                # Hard negative sampling (train years only)
                if label == 0:
                    is_train_year = year <= 2023
                    if is_train_year:
                        if cid in has_ever_burned:
                            if rng.random() > 0.2:  # keep 1/5 hard negatives
                                n_negative_skip += 1
                                continue
                        else:
                            if rng.random() > 0.05:  # keep 1/20 easy negatives
                                n_negative_skip += 1
                                continue
                    n_negative_kept += 1
                else:
                    n_positive += 1

                row = {"cell_id": cid, "date": str(mid_date), "label": label}
                row.update(cell_static)

                # Aggregated weekly weather
                row.update(aggregate_weather_weekly(wx_cache, gid, week_dates))

                # Year-aware historical fire features (no leakage)
                hist = hist_by_year[year].get(cid, {
                    "hist_fire_days": 0, "hist_fire_freq": 0.0,
                    "hist_fire_years": 0, "hist_fire_year_frac": 0.0,
                })
                row.update(hist)

                doy = mid_date.timetuple().tm_yday
                row.update(ndvi_cache[min(doy, 365)])

                # v6: LFMC proxy — Live Fuel Moisture Content estimate
                # Based on empirical relationships: NDVI anomaly + recent rain - diurnal range
                ndvi_anom = row.get("ndvi_seasonal_position", 0.5) - 0.5  # deviation from mid-season
                lfmc_proxy = (50.0
                              + 100.0 * ndvi_anom
                              + 0.5 * row.get("wx_precip_30d", 0)
                              - 2.0 * row.get("wx_dtr", 0))
                row["lfmc_proxy"] = max(0.0, min(200.0, lfmc_proxy))

                # Temporal features (using mid-week date)
                row["doy"] = doy
                row["day_of_week"] = mid_date.weekday()
                row["days_to_peak"] = abs(doy - 111)
                row["lunar_phase"] = _lunar_phase(mid_date)
                row["week_of_year"] = mid_date.isocalendar()[1]

                # Fire lag features (conditionally included, using first day of week)
                if not no_fire_lag:
                    ref_date = week_dates[0]
                    past_fires = [fd for fd in fire_dates if fd < ref_date]
                    row["days_since_last_fire"] = (ref_date - max(past_fires)).days if past_fires else 999

                    recent = [fd for fd in fire_dates if 0 < (ref_date - fd).days <= 7]
                    row["fire_last_7d"] = len(recent)

                    nbr_recent = [fd for fd in nbr_fire_dates if 0 < (ref_date - fd).days <= 7]
                    row["neighbor_fire_7d"] = len(nbr_recent)

                    yesterday = ref_date - timedelta(days=1)
                    row["neighbor_fire_yesterday"] = 1 if yesterday in nbr_fire_dates else 0

                rows.append(row)

        else:
            # ── Daily mode (original v4 behavior) ──
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

                # v6: LFMC proxy
                ndvi_anom = row.get("ndvi_seasonal_position", 0.5) - 0.5
                lfmc_proxy = (50.0
                              + 100.0 * ndvi_anom
                              + 0.5 * row.get("wx_precip_30d", 0)
                              - 2.0 * row.get("wx_dtr", 0))
                row["lfmc_proxy"] = max(0.0, min(200.0, lfmc_proxy))

                # Temporal features
                row["doy"] = doy
                row["month"] = d.month
                row["is_weekend"] = 1 if d.weekday() >= 5 else 0

                # ── v4 calendar features ──
                row["day_of_week"] = d.weekday()  # 0=Mon ... 6=Sun
                row["is_peak_doy"] = 1 if 101 <= doy <= 121 else 0  # Apr 11 - May 1
                row["days_to_peak"] = abs(doy - 111)  # distance to peak DOY
                row["lunar_phase"] = _lunar_phase(d)  # 0.0=new, 1.0=full

                # ── Fire lag features (conditionally included) ──
                if not no_fire_lag:
                    past_fires = [fd for fd in fire_dates if fd < d]
                    row["days_since_last_fire"] = (d - max(past_fires)).days if past_fires else 999

                    recent = [fd for fd in fire_dates if 0 < (d - fd).days <= 7]
                    row["fire_last_7d"] = len(recent)

                    nbr_recent = [fd for fd in nbr_fire_dates if 0 < (d - fd).days <= 7]
                    row["neighbor_fire_7d"] = len(nbr_recent)

                    yesterday = d - timedelta(days=1)
                    row["neighbor_fire_yesterday"] = 1 if yesterday in nbr_fire_dates else 0

                rows.append(row)

        if (ci + 1) % 500 == 0:
            log.info(f"  Processed {ci+1}/{len(cells)} cells...")

    df = pd.DataFrame(rows)
    log.info(f"\n  Total samples: {len(df):,}")
    log.info(f"  Positive (fire): {n_positive:,} ({n_positive/max(len(df),1)*100:.3f}%)")
    log.info(f"  Negative kept: {n_negative_kept:,}")
    log.info(f"  Negative skipped: {n_negative_skip:,}")
    log.info(f"  Event rate: {n_positive/max(len(df),1)*100:.4f}%")

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
    return [c for c in df.columns if c not in skip and c not in EXCLUDED_FEATURES]


def train_model(train_df, val_df, test_df, feature_cols, tag="v1", label_mode="spread"):
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

    if label_mode == "ignition":
        # v5 ignition params: tuned for 2km weekly dataset (~400K samples, ~900 positives)
        scale_pos_weight = min(raw_weight, 50.0)  # lower cap — better base rate with weekly agg
        params = {
            "objective": "binary",
            "metric": "auc",
            "n_estimators": 3000,
            "max_depth": 6,          # slightly deeper (more data per leaf now)
            "num_leaves": 63,        # 2^6 - 1
            "learning_rate": 0.01,   # moderate (more data to learn from)
            "subsample": 0.7,
            "colsample_bytree": 0.7,
            "scale_pos_weight": scale_pos_weight,
            "min_child_samples": 50, # moderate (more positives available)
            "min_child_weight": 5.0,
            "reg_alpha": 1.0,
            "reg_lambda": 5.0,
            "max_bin": 255,          # more bins OK with more data
            "random_state": 42,
            "verbose": -1,
            "n_jobs": -1,
        }
        log.info(f"\n  IGNITION v5 CONFIG: 2km weekly, deeper trees, moderate regularization")
    else:
        scale_pos_weight = min(raw_weight, 200.0)
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

    log.info(f"\nscale_pos_weight = {scale_pos_weight:.1f} (raw={raw_weight:.0f}, "
             f"{n_pos} pos / {n_neg} neg)")
    log.info(f"Training LightGBM ({len(feature_cols)} features, mode={label_mode})...")

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

    # ── Ignition-specific evaluation (Phase 8) ──
    if label_mode == "ignition":
        for name, X, y, split_df in [("val", X_val, y_val, val_df), ("test", X_test, y_test, test_df)]:
            probs = model.predict(X)
            ign_results = evaluate_ignition(y, probs, split_df, name)
            results[f"{name}_ignition"] = ign_results

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


def _fbeta_score(y, preds, beta=2.0):
    """Compute F-beta score (beta=2 weights recall 4x more than precision)."""
    prec = precision_score(y, preds, zero_division=0)
    rec = recall_score(y, preds, zero_division=0)
    if prec + rec == 0:
        return 0.0
    return float((1 + beta**2) * prec * rec / (beta**2 * prec + rec))


def _brier_skill_score(y, probs):
    """Brier Skill Score: 1 = perfect, 0 = climatology, <0 = worse than climatology."""
    brier = float(np.mean((probs - y) ** 2))
    clim = float(np.mean(y))
    brier_clim = clim * (1 - clim)
    if brier_clim == 0:
        return 0.0
    return 1.0 - brier / brier_clim


def evaluate(y, probs, name):
    """Evaluate with threshold sweep + operational top-K metric + v6 metrics."""
    auc = roc_auc_score(y, probs) if len(np.unique(y)) > 1 else 0.0
    ap = average_precision_score(y, probs) if len(np.unique(y)) > 1 else 0.0

    best_f1, best_f1_thr = 0, 0.5
    best_f2, best_f2_thr = 0, 0.5
    sweep = []
    for thr in np.arange(0.005, 0.50, 0.005):
        preds = (probs >= thr).astype(int)
        f1 = f1_score(y, preds, zero_division=0)
        f2 = _fbeta_score(y, preds, beta=2.0)
        prec = precision_score(y, preds, zero_division=0)
        rec = recall_score(y, preds, zero_division=0)
        sweep.append({"threshold": round(float(thr), 3), "f1": f1, "f2": f2,
                       "precision": prec, "recall": rec})
        if f1 > best_f1:
            best_f1, best_f1_thr = f1, thr
        if f2 > best_f2:
            best_f2, best_f2_thr = f2, thr

    # v6: Brier Skill Score (calibration quality)
    bss = _brier_skill_score(y, probs)

    log.info(f"\n{'='*60}")
    log.info(f"{name.upper()} RESULTS")
    log.info(f"{'='*60}")
    log.info(f"  AUC-ROC:     {auc:.4f}")
    log.info(f"  AUC-PR:      {ap:.4f}")
    log.info(f"  Best F1:     {best_f1:.4f} @ threshold={best_f1_thr:.3f}")
    log.info(f"  Best F2:     {best_f2:.4f} @ threshold={best_f2_thr:.3f}  (recall-weighted)")
    log.info(f"  Brier SS:    {bss:.4f}  (>0 = better than climatology)")

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
        "best_f1_threshold": float(best_f1_thr),
        "best_f2": float(best_f2),
        "best_f2_threshold": float(best_f2_thr),
        "brier_skill_score": float(bss),
        "n_samples": len(y),
        "n_fire": n_fire,
        "sweep": sweep[:20],
    }


def evaluate_ignition(y, probs, split_df, name):
    """
    Ignition-specific evaluation metrics:
    1. Spatial concentration: "Alert top N% cells to capture X% ignitions"
    2. Patrol efficiency: "If officers patrol top-K cells/week, how many fires caught?"
    3. Beat-level aggregation: Per-beat precision/recall
    4. Cross-year stability: Per-year AUC breakdown
    """
    log.info(f"\n{'='*60}")
    log.info(f"{name.upper()} — IGNITION-SPECIFIC METRICS")
    log.info(f"{'='*60}")

    results = {}
    n_fire = int(y.sum())

    # ── 1. Spatial concentration curve ──
    if n_fire > 0:
        sorted_idx = np.argsort(-probs)
        n_total = len(y)
        concentration = []
        for pct in [5, 10, 15, 20, 25, 30, 40, 50]:
            k = max(1, int(n_total * pct / 100))
            captured = int(y[sorted_idx[:k]].sum())
            capture_pct = captured / n_fire * 100
            concentration.append({"cells_pct": pct, "k": k,
                                   "captured": captured, "capture_pct": round(capture_pct, 1)})
            log.info(f"  Alert top {pct:2d}% cells ({k:5d}) → captures {captured}/{n_fire} "
                     f"= {capture_pct:.1f}% ignitions")

        results["spatial_concentration"] = concentration

        # Target: 80% ignitions in top 20% cells
        top20_k = max(1, int(n_total * 0.20))
        top20_capture = int(y[sorted_idx[:top20_k]].sum())
        results["top20_capture_pct"] = round(top20_capture / n_fire * 100, 1)
        log.info(f"\n  TARGET: 80% in top 20% → ACTUAL: {results['top20_capture_pct']:.1f}%")

    # ── 2. Patrol efficiency (v5) ──
    if n_fire > 0:
        sorted_idx = np.argsort(-probs)
        log.info(f"\n  PATROL EFFICIENCY (weekly):")
        patrol_results = []
        for k in [50, 100, 200, 500]:
            if k > n_total:
                continue
            top_k_fires = int(y[sorted_idx[:k]].sum())
            efficiency = top_k_fires / k if k > 0 else 0
            capture_rate = top_k_fires / n_fire * 100
            patrol_results.append({
                "patrol_cells": k, "fires_caught": top_k_fires,
                "capture_pct": round(capture_rate, 1),
                "efficiency": round(efficiency, 4),
            })
            log.info(f"    Patrol {k:4d} cells → catch {top_k_fires}/{n_fire} fires "
                     f"({capture_rate:.1f}%), efficiency={efficiency:.4f}")
        results["patrol_efficiency"] = patrol_results

    # ── 3. Cross-year stability ──
    if "date" in split_df.columns:
        years = pd.to_datetime(split_df["date"]).dt.year
        unique_years = sorted(years.unique())
        if len(unique_years) > 1:
            log.info(f"\n  CROSS-YEAR STABILITY:")
            year_results = []
            for yr in unique_years:
                mask = (years == yr).values
                yr_y = y[mask]
                yr_probs = probs[mask]
                yr_fire = int(yr_y.sum())
                if yr_fire > 0 and len(np.unique(yr_y)) > 1:
                    yr_auc = roc_auc_score(yr_y, yr_probs)
                    yr_ap = average_precision_score(yr_y, yr_probs)
                    year_results.append({
                        "year": int(yr), "n_samples": int(mask.sum()),
                        "n_fire": yr_fire, "auc_roc": round(float(yr_auc), 4),
                        "auc_pr": round(float(yr_ap), 4),
                    })
                    log.info(f"    {yr}: {mask.sum():6d} samples, {yr_fire:3d} fires, "
                             f"AUC-ROC={yr_auc:.4f}, AUC-PR={yr_ap:.4f}")
                else:
                    log.info(f"    {yr}: {mask.sum():6d} samples, {yr_fire:3d} fires (too few for AUC)")
            results["cross_year"] = year_results

    # ── 4. Beat-level aggregation ──
    if "cell_id" in split_df.columns:
        beat_col = "beat" if "beat" in split_df.columns else None

        if beat_col:
            beat_results = []
            for beat, grp in split_df.groupby(beat_col):
                idx = grp.index
                b_y = y[idx] if hasattr(idx, '__len__') else y
                b_probs = probs[idx] if hasattr(idx, '__len__') else probs
                b_fire = int(b_y.sum())
                if b_fire > 0 and len(b_y) > 0:
                    b_pred = (b_probs >= 0.1).astype(int)
                    b_prec = precision_score(b_y, b_pred, zero_division=0)
                    b_rec = recall_score(b_y, b_pred, zero_division=0)
                    beat_results.append({
                        "beat": beat, "n_samples": len(b_y), "n_fire": b_fire,
                        "precision": round(float(b_prec), 3), "recall": round(float(b_rec), 3),
                    })

            if beat_results:
                beat_results.sort(key=lambda x: x["n_fire"], reverse=True)
                log.info(f"\n  Beat-level metrics (top 10 by fire count):")
                for br in beat_results[:10]:
                    log.info(f"    {br['beat']:25s} fires={br['n_fire']:3d} "
                             f"prec={br['precision']:.3f} rec={br['recall']:.3f}")
                results["beat_metrics"] = beat_results[:20]

    return results


# ═══════════════════════════════════════════════════════════════════════════
# Inference: Predict Tomorrow's Risk Map
# ═══════════════════════════════════════════════════════════════════════════

def predict_tomorrow(model_path=None, target_date=None, alphaearth_mode="none",
                     alphaearth_pca=16, no_fire_lag=False):
    """
    Generate a risk map for tomorrow (or target_date).
    Returns a DataFrame of cell_id, lat, lon, risk_score, risk_level.

    When no_fire_lag=True, fire lag features are omitted (ignition model).
    """
    if model_path is None:
        # Find the latest model directory
        model_dirs = sorted(OUT_DIR.glob("predictive_*/model.lgbm"), key=lambda p: p.stat().st_mtime)
        model_path = model_dirs[-1] if model_dirs else OUT_DIR / "predictive_v1" / "model.lgbm"

    model = lgb.Booster(model_file=str(model_path))

    if target_date is None:
        target_date = date.today() + timedelta(days=1)

    log.info(f"Predicting fire risk for {target_date} (no_fire_lag={no_fire_lag})...")

    # Rebuild grid + features (could be cached in production)
    cells, grid_meta = build_grid()
    cells = compute_cell_terrain(cells, grid_meta)
    cells = add_cell_abm_ignition(cells)
    cells = add_cell_alphaearth(cells, mode=alphaearth_mode, n_pca=alphaearth_pca)
    cells = add_cell_human_activity(cells, grid_meta, aoi_mode="mp")
    cells = add_cell_aspect(cells, grid_meta)
    cells = add_cell_landcover(cells, grid_meta)

    # Load recent FIRMS for lag features (still needed for historical features)
    fires_by_cell = load_firms_and_assign_cells(cells, grid_meta)
    # Compute historical fire features using all available data
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

    static_prefixes = ("t_", "aef_", "ha_", "asp_", "lc_")
    static_names = {"abm_ignition", "hist_fire_days", "hist_fire_freq",
                    "hist_fire_years", "hist_fire_year_frac",
                    "centroid_lat", "centroid_lon"}
    static_cols = [k for k in cells[0].keys()
                   if any(k.startswith(p) for p in static_prefixes) or k in static_names]

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
        row.update(wx_by_grid[gid])
        row.update(ndvi)
        row["doy"] = doy
        row["month"] = target_date.month
        row["is_weekend"] = 1 if target_date.weekday() >= 5 else 0

        # v4 calendar features
        row["day_of_week"] = target_date.weekday()
        row["is_peak_doy"] = 1 if 101 <= doy <= 121 else 0
        row["days_to_peak"] = abs(doy - 111)
        row["lunar_phase"] = _lunar_phase(target_date)

        # Fire lag features (conditionally included)
        if not no_fire_lag:
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
    # Use model's own feature names for correct alignment
    model_features = model.feature_name()
    missing = [f for f in model_features if f not in pred_df.columns]
    for f in missing:
        pred_df[f] = 0.0
    X = pred_df[model_features].values.astype(np.float32)
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
# v6: Multi-Model Ensemble (LightGBM + XGBoost + CatBoost)
# ═══════════════════════════════════════════════════════════════════════════

def train_ensemble(train_df, val_df, test_df, feature_cols, tag="v6",
                   label_mode="spread", ensemble_mode="lgbm+xgb+cat"):
    """Train multiple models and average their predictions."""
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
    scale_pw = min(raw_weight, 50.0) if label_mode == "ignition" else min(raw_weight, 200.0)

    models_to_train = ensemble_mode.split("+")
    all_probs = {}  # name -> {val: probs, test: probs}

    # ── 1. LightGBM ──
    if "lgbm" in models_to_train:
        log.info(f"\n{'='*60}")
        log.info("Training LightGBM...")
        lgbm_params = {
            "objective": "binary", "metric": "auc",
            "max_depth": 6, "num_leaves": 63, "learning_rate": 0.01,
            "subsample": 0.7, "colsample_bytree": 0.7,
            "scale_pos_weight": scale_pw,
            "min_child_samples": 50, "min_child_weight": 5.0,
            "reg_alpha": 1.0, "reg_lambda": 5.0,
            "max_bin": 255, "random_state": 42, "verbose": -1, "n_jobs": -1,
        }
        train_data = lgb.Dataset(X_train, label=y_train, feature_name=feature_cols)
        val_data = lgb.Dataset(X_val, label=y_val, feature_name=feature_cols, reference=train_data)
        lgbm_model = lgb.train(
            lgbm_params, train_data, num_boost_round=3000,
            valid_sets=[train_data, val_data], valid_names=["train", "val"],
            callbacks=[lgb.early_stopping(150, verbose=True), lgb.log_evaluation(200)],
        )
        lgbm_model.save_model(str(out_dir / "model_lgbm.lgbm"))
        # Also save as default model for inference compatibility
        lgbm_model.save_model(str(out_dir / "model.lgbm"))
        all_probs["lgbm"] = {"val": lgbm_model.predict(X_val), "test": lgbm_model.predict(X_test)}
        log.info(f"  LightGBM: {lgbm_model.num_trees()} trees")

        # Feature importance from LightGBM
        importance = pd.DataFrame({
            "feature": feature_cols,
            "importance": lgbm_model.feature_importance(importance_type="gain"),
        }).sort_values("importance", ascending=False)
        importance.to_csv(out_dir / "feature_importance.csv", index=False)

    # ── 2. XGBoost ──
    if "xgb" in models_to_train:
        import xgboost as xgb
        log.info(f"\n{'='*60}")
        log.info("Training XGBoost...")
        xgb_params = {
            "objective": "binary:logistic", "eval_metric": "aucpr",
            "max_depth": 6, "learning_rate": 0.01,
            "subsample": 0.7, "colsample_bytree": 0.7,
            "scale_pos_weight": scale_pw,
            "min_child_weight": 5, "reg_alpha": 1.0, "reg_lambda": 5.0,
            "random_state": 42, "n_jobs": -1, "tree_method": "hist",
        }
        dtrain = xgb.DMatrix(X_train, label=y_train, feature_names=feature_cols)
        dval = xgb.DMatrix(X_val, label=y_val, feature_names=feature_cols)
        dtest = xgb.DMatrix(X_test, label=y_test, feature_names=feature_cols)
        xgb_model = xgb.train(
            xgb_params, dtrain, num_boost_round=3000,
            evals=[(dtrain, "train"), (dval, "val")],
            early_stopping_rounds=150, verbose_eval=200,
        )
        xgb_model.save_model(str(out_dir / "model_xgb.json"))
        all_probs["xgb"] = {"val": xgb_model.predict(dval), "test": xgb_model.predict(dtest)}
        log.info(f"  XGBoost: {xgb_model.best_iteration} best iteration")

    # ── 3. CatBoost ──
    if "cat" in models_to_train:
        from catboost import CatBoostClassifier, Pool
        log.info(f"\n{'='*60}")
        log.info("Training CatBoost...")
        cat_model = CatBoostClassifier(
            loss_function="Logloss", eval_metric="AUC",
            depth=6, learning_rate=0.01, iterations=3000,
            l2_leaf_reg=5.0, random_seed=42,
            auto_class_weights="SqrtBalanced",
            early_stopping_rounds=150, verbose=200,
        )
        train_pool = Pool(X_train, label=y_train, feature_names=feature_cols)
        val_pool = Pool(X_val, label=y_val, feature_names=feature_cols)
        cat_model.fit(train_pool, eval_set=val_pool)
        cat_model.save_model(str(out_dir / "model_catboost.cbm"))
        all_probs["cat"] = {
            "val": cat_model.predict_proba(X_val)[:, 1],
            "test": cat_model.predict_proba(X_test)[:, 1],
        }
        log.info(f"  CatBoost: {cat_model.get_best_iteration()} best iteration")

    # ── Ensemble: simple average ──
    log.info(f"\n{'='*60}")
    log.info(f"ENSEMBLE ({' + '.join(all_probs.keys())}): averaging {len(all_probs)} models")
    log.info(f"{'='*60}")

    ens_val = np.mean([all_probs[m]["val"] for m in all_probs], axis=0)
    ens_test = np.mean([all_probs[m]["test"] for m in all_probs], axis=0)

    # Evaluate each model + ensemble
    results = {}
    for model_name in all_probs:
        for split_name, y, probs in [("val", y_val, all_probs[model_name]["val"]),
                                       ("test", y_test, all_probs[model_name]["test"])]:
            key = f"{model_name}_{split_name}"
            results[key] = evaluate(y, probs, f"{model_name} {split_name}")

    # Ensemble results
    for split_name, y, probs in [("val", y_val, ens_val), ("test", y_test, ens_test)]:
        key = f"ensemble_{split_name}"
        results[key] = evaluate(y, probs, f"ENSEMBLE {split_name}")

    # Ignition-specific evaluation on ensemble
    if label_mode == "ignition":
        for split_name, y, probs, split_df in [("val", y_val, ens_val, val_df),
                                                  ("test", y_test, ens_test, test_df)]:
            ign_results = evaluate_ignition(y, probs, split_df, f"ENSEMBLE {split_name}")
            results[f"ensemble_{split_name}_ignition"] = ign_results

    # Save
    with open(out_dir / "results.json", "w") as f:
        json.dump(results, f, indent=2)

    log.info(f"\nSaved ensemble to {out_dir}")
    return results


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
    parser.add_argument("--alphaearth", type=str, default="none",
                        choices=["none", "raw64", "pca16"],
                        help="AlphaEarth embedding mode: none, raw64, pca16")
    parser.add_argument("--alphaearth-pca", type=int, default=16,
                        help="Number of PCA components for AlphaEarth (default 16)")
    parser.add_argument("--label-mode", type=str, default="spread",
                        choices=["spread", "ignition"],
                        help="Label mode: spread (default, v3 compat) or ignition (v4, new ignitions only)")
    parser.add_argument("--clear-days", type=int, default=14,
                        help="Days of no nearby fire to qualify as new ignition (default 14)")
    parser.add_argument("--no-fire-lag-features", action="store_true", default=False,
                        help="Drop all fire lag features (neighbor_fire_*, days_since_last_fire)")
    parser.add_argument("--temporal-agg", type=str, default="day",
                        choices=["day", "week"],
                        help="Temporal aggregation: day (default) or week (v5 weekly)")
    parser.add_argument("--aoi", type=str, default="guna",
                        choices=["guna", "mp"],
                        help="AOI mode: guna (Guna Division only) or mp (all MP forests)")
    parser.add_argument("--ensemble", type=str, default="lgbm",
                        choices=["lgbm", "lgbm+xgb", "lgbm+xgb+cat"],
                        help="Model ensemble: lgbm (default), lgbm+xgb, lgbm+xgb+cat")
    args = parser.parse_args()

    if args.predict:
        target = datetime.strptime(args.predict, "%Y-%m-%d").date()
        pred_df = predict_tomorrow(target_date=target,
                                   alphaearth_mode=args.alphaearth,
                                   alphaearth_pca=args.alphaearth_pca,
                                   no_fire_lag=args.no_fire_lag_features)
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
        alphaearth_mode=args.alphaearth,
        alphaearth_pca=args.alphaearth_pca,
        label_mode=args.label_mode,
        clear_days=args.clear_days,
        no_fire_lag=args.no_fire_lag_features,
        temporal_agg=args.temporal_agg,
        aoi_mode=args.aoi,
    )

    # Split
    log.info("\nTemporal split (train<=2023, val=2024, test=2025)...")
    train, val, test = temporal_split(df)

    # Train
    feature_cols = get_feature_cols(df)
    log.info(f"\nFeatures ({len(feature_cols)}):")
    for fc in feature_cols:
        log.info(f"  {fc}")

    if args.ensemble != "lgbm":
        results = train_ensemble(train, val, test, feature_cols, tag=args.tag,
                                 label_mode=args.label_mode, ensemble_mode=args.ensemble)
    else:
        model, results, importance = train_model(train, val, test, feature_cols, tag=args.tag,
                                                  label_mode=args.label_mode)

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
    log.info(f"Grid: {len(cells)} cells × {args.cell_size}m, temporal={args.temporal_agg}, aoi={args.aoi}")
    if args.ensemble != "lgbm":
        # Ensemble results use keys like "ensemble_val", "ensemble_test"
        val_key = "ensemble_val" if "ensemble_val" in results else next(k for k in results if k.endswith("_val"))
        test_key = "ensemble_test" if "ensemble_test" in results else next(k for k in results if k.endswith("_test"))
        log.info(f"Val  AUC: {results[val_key]['auc_roc']:.4f}")
        log.info(f"Test AUC: {results[test_key]['auc_roc']:.4f}")
    else:
        log.info(f"Val  AUC: {results['val']['auc_roc']:.4f}")
        log.info(f"Test AUC: {results['test']['auc_roc']:.4f}")


if __name__ == "__main__":
    main()
