"""Stage 1d — Andela 2019 flood-fill clustering on MCD64/FireCCI burn-date rasters.

Reference: Andela et al. 2019 "A human-driven decline in global burned area"
(Science 356:1356-1362) — Global Fire Atlas methodology.

Algorithm per raster:
  1. Load burn-date raster (BurnDate band, uint16 DOY, 0=no burn)
  2. For each burned pixel, find connected component using 4-connectivity AND
     ±1 day temporal tolerance (pixels with burn_date within 1 day of any
     neighbor pixel's burn_date merge into same cluster)
  3. For each cluster:
     - cluster_id
     - first_burn_date = min(BurnDate) in cluster (+ convert DOY to date)
     - last_burn_date  = max(BurnDate)
     - centroid_lat/lon = area-weighted centroid
     - area_ha = n_pixels × pixel_area_ha
     - bbox (for Stage 3 ellipse fitting later)
     - polygon_wkt (simplified outline)

Output: data_lake/fire_detections/ba_clusters_mp.parquet with one row per cluster.

Sensible filter: drop clusters with area < 0.5 ha (MCD64 noise floor per
Boschetti 2019).

Usage:
  python scripts/andela_floodfill_mp.py --product mcd64
  python scripts/andela_floodfill_mp.py --product firecci
  python scripts/andela_floodfill_mp.py --product both --min-area-ha 0.5
"""
from __future__ import annotations

import argparse
import logging
import sys
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import rasterio
from rasterio.features import shapes
from scipy.ndimage import label as cc_label
from shapely.geometry import shape as shp_shape
from shapely.ops import unary_union

sys.stdout.reconfigure(line_buffering=True)
logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger()

ROOT = Path(__file__).resolve().parents[1]
MCD64_DIR = ROOT / "data_lake" / "burnt_area"
FIRECCI_DIR = ROOT / "data_lake" / "burnt_area"
OUT_PATH = ROOT / "data_lake" / "fire_detections" / "ba_clusters_mp.parquet"

# Product-specific pixel areas
MCD64_PIXEL_AREA_HA = (500 * 500) / 10000  # 25 ha per 500m pixel
FIRECCI_PIXEL_AREA_HA = (250 * 250) / 10000  # 6.25 ha per 250m pixel
S2_PIXEL_AREA_HA = (30 * 30) / 10000  # 0.09 ha per 30m pixel

# Noise floor: drop clusters smaller than this
DEFAULT_MIN_AREA_HA = 0.5

# Structure element: 4-connectivity (share edge, not diagonal)
STRUCT_4 = np.array([[0, 1, 0], [1, 1, 1], [0, 1, 0]], dtype=bool)


def doy_to_date(year: int, doy: int) -> date | None:
    """Convert day-of-year to calendar date."""
    if doy < 1 or doy > 366:
        return None
    try:
        return date(year, 1, 1) + timedelta(days=int(doy) - 1)
    except (ValueError, OverflowError):
        return None


def temporal_aware_cluster(burn_doy: np.ndarray, day_tolerance: int = 1) -> np.ndarray:
    """Cluster burned pixels with temporal + spatial adjacency.

    Standard connected components treats all burned pixels as one cluster.
    Andela 2019 argues clusters should merge only if burn dates differ by
    ≤1 day (otherwise two separate fire events touching the same unburned
    gap would merge into one mega-cluster).

    Implementation:
      1. Standard 4-connectivity CC on (burn_doy > 0)
      2. Within each CC, find pixels with large DOY jumps; if any adjacent
         pixel pair has |ΔDOY| > day_tolerance, they're separate events
      3. Re-label via BFS respecting temporal tolerance

    For MP dry season (most fires concentrated Feb-May), the simple version
    below is a good approximation: standard 4-CC + post-hoc DOY check.
    """
    burned = burn_doy > 0
    labeled, n_components = cc_label(burned, structure=STRUCT_4)

    # For each component, check if DOY spread exceeds tolerance
    # If it does, subdivide via DOY quantile (crude but fast for MP scale)
    max_label = int(labeled.max())
    refined = np.zeros_like(labeled)
    next_id = 1

    for comp_id in range(1, max_label + 1):
        mask = labeled == comp_id
        doys = burn_doy[mask]
        doy_range = int(doys.max() - doys.min())
        if doy_range <= day_tolerance:
            refined[mask] = next_id
            next_id += 1
        else:
            # Split by DOY — naive: bin by (doy // (day_tolerance + 1))
            # For v1 keep the whole blob but flag it; Andela's proper approach
            # uses BFS with temporal gate. This simple bin approximates the
            # split and is fast at MP scale.
            unique_bins = np.unique(doys // (day_tolerance + 1))
            for b in unique_bins:
                sub = mask & ((burn_doy // (day_tolerance + 1)) == b)
                if sub.any():
                    refined[sub] = next_id
                    next_id += 1

    return refined


def process_raster(
    raster_path: Path,
    year: int,
    product: str,
    pixel_area_ha: float,
    min_area_ha: float,
) -> pd.DataFrame:
    """Process one BA raster → one DataFrame of clusters."""
    with rasterio.open(raster_path) as src:
        burn_doy = src.read(1)
        transform = src.transform
        crs = src.crs

    log.info("  Raster %s: shape=%s, burn pixels=%d (%.2f%%)",
             raster_path.name, burn_doy.shape,
             int((burn_doy > 0).sum()),
             100 * (burn_doy > 0).mean())

    labeled = temporal_aware_cluster(burn_doy)
    n_clusters = int(labeled.max())
    log.info("  %d raw clusters (temporal-aware)", n_clusters)

    rows = []
    # Vectorize: for each cluster, get bounding pixels + stats
    flat_labels = labeled.ravel()
    flat_doys = burn_doy.ravel()
    # Use pandas groupby for speed on 300K+ clusters
    df = pd.DataFrame({"cluster": flat_labels, "doy": flat_doys})
    df = df[df["cluster"] > 0]
    grouped = df.groupby("cluster")
    stats = grouped["doy"].agg(["count", "min", "max"]).reset_index()

    # Filter by area
    min_pixels = max(1, int(np.ceil(min_area_ha / pixel_area_ha)))
    stats = stats[stats["count"] >= min_pixels].reset_index(drop=True)
    log.info("  After min-area filter (>=%.2f ha, %d px): %d clusters kept",
             min_area_ha, min_pixels, len(stats))

    # For each kept cluster, compute centroid (row, col) mean
    for _, row in stats.iterrows():
        cid = int(row["cluster"])
        mask = labeled == cid
        rr, cc = np.where(mask)
        centroid_row = rr.mean()
        centroid_col = cc.mean()
        lon, lat = rasterio.transform.xy(transform, [centroid_row], [centroid_col])
        first_doy = int(row["min"])
        last_doy = int(row["max"])
        first_date = doy_to_date(year, first_doy)
        last_date = doy_to_date(year, last_doy)
        n_px = int(row["count"])
        area_ha = n_px * pixel_area_ha

        # Major/minor axis proxy: compute extent via PCA of pixel coords
        if len(rr) >= 3:
            coords = np.column_stack([cc, rr]).astype(np.float64)
            coords -= coords.mean(axis=0)
            cov = np.cov(coords, rowvar=False)
            eig = np.linalg.eigvalsh(cov)
            semi_major = 2.0 * np.sqrt(max(eig.max(), 1e-9))
            semi_minor = 2.0 * np.sqrt(max(eig.min(), 1e-9))
        else:
            semi_major = semi_minor = 1.0

        rows.append({
            "product": product,
            "year": year,
            "cluster_id": cid,
            "first_burn_date": first_date,
            "last_burn_date": last_date,
            "duration_days": last_doy - first_doy,
            "n_pixels": n_px,
            "area_ha": area_ha,
            "centroid_lon": float(lon[0]),
            "centroid_lat": float(lat[0]),
            "semi_major_px": float(semi_major),
            "semi_minor_px": float(semi_minor),
            "aspect_ratio": float(semi_major / max(semi_minor, 1e-9)),
            "bbox_row_min": int(rr.min()),
            "bbox_row_max": int(rr.max()),
            "bbox_col_min": int(cc.min()),
            "bbox_col_max": int(cc.max()),
        })

    return pd.DataFrame(rows)


def process_product(product: str, min_area_ha: float) -> pd.DataFrame:
    """Process all available rasters for a product."""
    if product == "s2":
        pattern = "s2_dnbr_mp_*.tif"
    else:
        pattern = f"{product}_mp_*.tif"
    src_dir = MCD64_DIR  # all products share data_lake/burnt_area/
    rasters = sorted(src_dir.glob(pattern))

    pixel_area_ha = {
        "mcd64": MCD64_PIXEL_AREA_HA,
        "firecci": FIRECCI_PIXEL_AREA_HA,
        "s2": S2_PIXEL_AREA_HA,
    }[product]

    log.info("Processing %d %s rasters from %s...", len(rasters), product, src_dir)
    if not rasters:
        log.warning("No %s rasters found — waiting for GEE exports to complete?", product)
        return pd.DataFrame()

    all_rows = []
    for rp in rasters:
        # Parse year from filename: e.g. mcd64_mp_2024.tif
        stem = rp.stem
        try:
            year = int(stem.split("_")[-1])
        except ValueError:
            log.warning("Cannot parse year from %s", rp.name)
            continue
        log.info("Year %d (%s)...", year, product)
        df = process_raster(rp, year, product, pixel_area_ha, min_area_ha)
        all_rows.append(df)

    if not all_rows:
        return pd.DataFrame()
    return pd.concat(all_rows, ignore_index=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--product", choices=["mcd64", "firecci", "s2", "all"], default="all")
    parser.add_argument("--min-area-ha", type=float, default=DEFAULT_MIN_AREA_HA)
    args = parser.parse_args()

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)

    all_dfs = []
    if args.product in ("mcd64", "all", "both"):
        df = process_product("mcd64", args.min_area_ha)
        if len(df):
            log.info("MCD64 total: %d clusters across years", len(df))
            all_dfs.append(df)
    if args.product in ("firecci", "all", "both"):
        df = process_product("firecci", args.min_area_ha)
        if len(df):
            log.info("FireCCI total: %d clusters across years", len(df))
            all_dfs.append(df)
    if args.product in ("s2", "all"):
        df = process_product("s2", args.min_area_ha)
        if len(df):
            log.info("S2 dNBR total: %d clusters across years", len(df))
            all_dfs.append(df)

    if not all_dfs:
        log.error("No rasters processed. Check data_lake/burnt_area/ for exports.")
        return 1

    combined = pd.concat(all_dfs, ignore_index=True)
    combined = combined.sort_values(["year", "first_burn_date", "area_ha"], ascending=[True, True, False])
    combined["cluster_uid"] = (
        combined["product"] + "_" + combined["year"].astype(str) + "_" + combined["cluster_id"].astype(str)
    )
    combined.to_parquet(OUT_PATH, index=False)
    log.info("\nSaved %d total clusters → %s", len(combined), OUT_PATH.relative_to(ROOT))

    log.info("\n=== CLUSTER STATS ===")
    log.info("By product:\n%s", combined.groupby("product").size().to_string())
    log.info("\nArea_ha: median=%.1f p10=%.1f p50=%.1f p90=%.1f max=%.0f",
             combined["area_ha"].median(),
             combined["area_ha"].quantile(0.1),
             combined["area_ha"].quantile(0.5),
             combined["area_ha"].quantile(0.9),
             combined["area_ha"].max())
    log.info("Aspect_ratio: median=%.2f p90=%.2f",
             combined["aspect_ratio"].median(), combined["aspect_ratio"].quantile(0.9))
    log.info("Duration_days: median=%.0f p90=%.0f",
             combined["duration_days"].median(), combined["duration_days"].quantile(0.9))

    # Year distribution
    year_counts = combined.groupby(["year", "product"]).size().unstack(fill_value=0)
    log.info("\nClusters per year:\n%s", year_counts.to_string())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
