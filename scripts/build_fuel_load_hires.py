"""
Bake high-resolution fuel-load layer (real CCI biomass + WC class).

Replaces the v17-grid (2 km) `fuel_load_v17.json` aggregation with a
much finer 500 m grid (~16x denser) AND swaps the t/ha source from
"WC class lookup × Reddy et al reference" to **actual measured biomass
from ESA CCI AGB v6** (100 m native, 2022). This is the user's
"option 3" — real biomass from spaceborne LiDAR fusion, not a
generic per-class constant.

Pipeline:
  1. Download CCI AGB 2022 for MP AOI via GEE getDownloadURL (~50 MB).
  2. Generate 500 m grid points within MP forest beats (using the
     existing `_forest_clip_helper.filter_records_to_forest`).
  3. For each grid point, sample:
        - CCI AGB raster value -> fuel_load_t_per_ha (REAL biomass)
        - WorldCover 10 m raster -> sb40_dominant (mode of 50x50 px window)
        - WC tree fraction -> canopy_frac
  4. Atomic-write outputs/dashboard_feed/fuel_load_hires.json

Output schema matches `fuel_load_v17.json` so the existing portal
fetcher + layer code work unchanged. Frontend just gets denser, more
accurate dots.

Per the user feedback memory `feedback_clip_to_forest.md`, the result
is forest-clipped before write.
"""

from __future__ import annotations

import json
import os
import sys
import urllib.request
from collections import Counter
from pathlib import Path

import ee
import numpy as np
import rasterio
from rasterio.windows import from_bounds

sys.stdout.reconfigure(encoding="utf-8")

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))
from _forest_clip_helper import filter_records_to_forest  # noqa: E402

WC_TILE_DIR = REPO_ROOT / "data_lake" / "land_cover" / "worldcover_expanded"
CCI_LOCAL = REPO_ROOT / "data_lake" / "biomass" / "cci_agb_2022_mp_100m.tif"
OUT = REPO_ROOT / "outputs" / "dashboard_feed" / "fuel_load_hires.json"

# Higher-res grid — 500 m spacing in degrees (~0.0045°)
GRID_STEP_DEG = 0.0045

MP_LAT_MIN, MP_LAT_MAX = 21.0, 27.0
MP_LON_MIN, MP_LON_MAX = 74.0, 83.0

# WorldCover -> SB40 short-name + reference t/ha (kept for fallback when
# CCI is missing / null / over water).
WC_TO_SB40 = {
    10: "TL2",  20: "SH2",  30: "GR2",  40: "GR1",
    50: "NB1",  60: "NB9",  70: "NB9",  80: "NB8",
    90: "GR1",  95: "NB9", 100: "NB9",
}
WC_REF_T_HA = {
    10: 15.0, 20: 8.0, 30: 3.5, 40: 12.0,
    50: 0.0,  60: 1.0, 70: 0.0, 80: 0.0,
    90: 3.0,  95: 5.0, 100: 0.0,
}
WC_TREE = 10


def _write_atomic_json(target: Path, payload: dict) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(target.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(payload, f, separators=(",", ":"))
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, target)


def download_cci_agb_for_mp() -> None:
    """Download CCI AGB 2022 mosaic for MP AOI in 6 chunks (each <50 MB
    GEE download limit), then merge via rasterio."""
    if CCI_LOCAL.exists() and CCI_LOCAL.stat().st_size > 1_000_000:
        print(f"[CCI] cached: {CCI_LOCAL} ({CCI_LOCAL.stat().st_size / 1e6:.1f} MB)")
        return
    print("[CCI] initializing Earth Engine…")
    ee.Initialize(project="van-suraksha-alert")
    ic = ee.ImageCollection("projects/sat-io/open-datasets/ESA/ESA_CCI_AGB")
    img = ic.filter(ee.Filter.stringContains("system:index", "2022")).first()
    if img is None:
        img = ic.sort("system:index", False).first()
    band = img.select("AGB")

    # Split MP AOI into 2x3 = 6 chunks (each ~3°x2° → ~33 MB at 100m).
    chunks = []
    for i, lat0 in enumerate(np.arange(MP_LAT_MIN, MP_LAT_MAX, 2.0)):
        for j, lon0 in enumerate(np.arange(MP_LON_MIN, MP_LON_MAX, 3.0)):
            lat1 = min(lat0 + 2.0, MP_LAT_MAX)
            lon1 = min(lon0 + 3.0, MP_LON_MAX)
            chunks.append((i, j, lat0, lat1, lon0, lon1))
    print(f"[CCI] splitting into {len(chunks)} chunks")

    chunk_paths = []
    CCI_LOCAL.parent.mkdir(parents=True, exist_ok=True)
    for i, j, lat0, lat1, lon0, lon1 in chunks:
        chunk_path = CCI_LOCAL.parent / f"_cci_chunk_{i}_{j}.tif"
        if chunk_path.exists() and chunk_path.stat().st_size > 1_000_000:
            print(f"  chunk {i},{j} cached: {chunk_path.name}")
            chunk_paths.append(chunk_path)
            continue
        aoi = ee.Geometry.Rectangle([lon0, lat0, lon1, lat1])
        url = band.getDownloadURL({
            "scale": 100, "region": aoi, "crs": "EPSG:4326",
            "format": "GEO_TIFF", "filePerBand": False,
        })
        print(f"  chunk {i},{j} downloading {lat0:.1f}-{lat1:.1f}N {lon0:.1f}-{lon1:.1f}E…")
        urllib.request.urlretrieve(url, chunk_path)
        sz = chunk_path.stat().st_size / 1e6
        print(f"    saved {chunk_path.name} ({sz:.1f} MB)")
        chunk_paths.append(chunk_path)

    # Merge chunks via rasterio
    print("[CCI] merging chunks…")
    from rasterio.merge import merge
    src_files = [rasterio.open(p) for p in chunk_paths]
    mosaic, out_transform = merge(src_files)
    out_meta = src_files[0].meta.copy()
    out_meta.update({
        "driver": "GTiff",
        "height": mosaic.shape[1],
        "width": mosaic.shape[2],
        "transform": out_transform,
        "crs": src_files[0].crs,
        "count": 1,
    })
    with rasterio.open(CCI_LOCAL, "w", **out_meta) as dst:
        dst.write(mosaic)
    for s in src_files:
        s.close()
    sz = CCI_LOCAL.stat().st_size / 1e6
    print(f"[CCI] merged {CCI_LOCAL} ({sz:.1f} MB)")


def build_grid_points() -> list[dict]:
    """Generate 500 m grid points across the MP AOI. NOT yet forest-clipped."""
    points = []
    lats = np.arange(MP_LAT_MIN, MP_LAT_MAX, GRID_STEP_DEG)
    lons = np.arange(MP_LON_MIN, MP_LON_MAX, GRID_STEP_DEG)
    print(f"[grid] {len(lats)} rows x {len(lons)} cols = {len(lats) * len(lons):,} candidate cells")
    for lat in lats:
        for lon in lons:
            points.append({"lat": round(float(lat), 6), "lon": round(float(lon), 6)})
    return points


def _open_wc_tile_for(lat: float, lon: float, tile_handles: dict) -> rasterio.DatasetReader | None:
    """Return the WC tile dataset that covers this lat/lon. Caches handles."""
    for tile_path in WC_TILE_DIR.glob("ESA_WorldCover_10m_2021_v200_*_Map.tif"):
        # Lazy-open
        if tile_path not in tile_handles:
            tile_handles[tile_path] = rasterio.open(tile_path)
        ds = tile_handles[tile_path]
        b = ds.bounds
        if b.left <= lon < b.right and b.bottom <= lat < b.top:
            return ds
    return None


def sample_wc_at(ds: rasterio.DatasetReader, lat: float, lon: float, half_deg: float = 0.0022) -> tuple[str, float]:
    """Sample a 50x50 px window centered on (lat, lon) and return
    (sb40_name, canopy_frac). half_deg ~ 0.0022 = 250 m — half the grid
    spacing so windows tile without overlap."""
    win = from_bounds(lon - half_deg, lat - half_deg, lon + half_deg, lat + half_deg, ds.transform)
    arr = ds.read(1, window=win, boundless=False, fill_value=0)
    flat = arr.ravel()
    flat = flat[flat != 0]
    if flat.size == 0:
        return ("NB9", 0.0)
    cls_counts = Counter(int(v) for v in flat)
    dominant_wc = cls_counts.most_common(1)[0][0]
    return (
        WC_TO_SB40.get(dominant_wc, "NB9"),
        float((flat == WC_TREE).mean()),
    )


def sample_cci_at(ds: rasterio.DatasetReader, lat: float, lon: float) -> float:
    """Sample CCI AGB raster at (lat, lon). Returns t/ha or NaN if outside."""
    try:
        # Convert lon/lat to row/col
        win = from_bounds(lon - 0.0005, lat - 0.0005, lon + 0.0005, lat + 0.0005, ds.transform)
        arr = ds.read(1, window=win, boundless=False, fill_value=0)
        flat = arr.ravel()
        flat = flat[flat > 0]
        if flat.size == 0:
            return float("nan")
        return float(flat.mean())
    except (ValueError, rasterio.errors.WindowError):
        return float("nan")


def main() -> None:
    download_cci_agb_for_mp()
    points = build_grid_points()
    print(f"[clip] forest-clipping {len(points):,} grid points…")
    points = filter_records_to_forest(points)
    print(f"[clip] kept {len(points):,} forest grid points")

    print(f"[CCI] opening {CCI_LOCAL.name}")
    cci_ds = rasterio.open(CCI_LOCAL)
    print(f"  CCI bounds: {cci_ds.bounds}, shape: {cci_ds.shape}, res: {cci_ds.res}")

    wc_handles: dict[Path, rasterio.DatasetReader] = {}
    records = []
    skipped_no_wc = 0
    skipped_no_cci = 0
    for i, p in enumerate(points):
        if i % 5000 == 0 and i > 0:
            print(f"  {i:>7,}/{len(points):,} sampled  ({len(records):,} kept · {skipped_no_wc:,} no-wc · {skipped_no_cci:,} no-cci)")
        lat, lon = p["lat"], p["lon"]
        wc_ds = _open_wc_tile_for(lat, lon, wc_handles)
        if wc_ds is None:
            skipped_no_wc += 1
            continue
        sb40, canopy = sample_wc_at(wc_ds, lat, lon)
        cci_t_ha = sample_cci_at(cci_ds, lat, lon)
        # Fall back to WC reference load when CCI is missing/zero
        if not np.isfinite(cci_t_ha) or cci_t_ha <= 0:
            skipped_no_cci += 1
            # Still keep the record using WC reference — useful for grass / shrub
            # cells where CCI may be undersampled.
            wc_class = next((k for k, v in WC_TO_SB40.items() if v == sb40), 30)
            cci_t_ha = WC_REF_T_HA.get(wc_class, 0.0)
            source = "wc_ref"
        else:
            source = "cci"
        records.append({
            "cell_id": f"hr_{lat:.5f}_{lon:.5f}",
            "lat": lat,
            "lon": lon,
            "fuel_load_t_per_ha": round(cci_t_ha, 2),
            "sb40_dominant": sb40,
            "canopy_frac": round(canopy, 3),
            "water_frac": 0.0,
            "source": source,
        })

    for ds in wc_handles.values():
        ds.close()
    cci_ds.close()

    records.sort(key=lambda r: r["fuel_load_t_per_ha"], reverse=True)

    summary = {
        "min": round(min(r["fuel_load_t_per_ha"] for r in records), 2),
        "max": round(max(r["fuel_load_t_per_ha"] for r in records), 2),
        "mean": round(sum(r["fuel_load_t_per_ha"] for r in records) / max(1, len(records)), 2),
        "p50": round(sorted(r["fuel_load_t_per_ha"] for r in records)[len(records) // 2], 2),
    }
    sb40_dist = Counter(r["sb40_dominant"] for r in records).most_common()
    src_dist = Counter(r["source"] for r in records).most_common()

    payload = {
        "metadata": {
            "source_cci": "ESA CCI AGB v6, 2022, 100 m",
            "source_wc": "ESA WorldCover 10 m 2021 v200",
            "grid_step_deg": GRID_STEP_DEG,
            "grid_step_m_approx": int(GRID_STEP_DEG * 111000),
            "n_records": len(records),
            "fuel_load_summary_t_per_ha": summary,
            "sb40_distribution": dict(sb40_dist),
            "source_distribution": dict(src_dist),
            "forest_clipped": True,
            "disclaimer": (
                "fuel_load_t_per_ha values come from ESA CCI AGB v6 (real "
                "above-ground biomass measured via GEDI + Sentinel-1 + "
                "Sentinel-2 fusion) where available. WC reference loads are "
                "used as fallback for grass/shrub cells with CCI=0 (CCI "
                "tends to undersample non-forest biomass)."
            ),
        },
        "records": records,
    }
    _write_atomic_json(OUT, payload)
    sz = OUT.stat().st_size / 1e6
    print()
    print(f"Wrote {OUT.name} ({sz:.2f} MB) — {len(records):,} records at ~{int(GRID_STEP_DEG * 111000)} m grid")
    print(f"  fuel_load t/ha — min: {summary['min']} · p50: {summary['p50']} · mean: {summary['mean']} · max: {summary['max']}")
    print(f"  SB40 distribution: {dict(sb40_dist)}")
    print(f"  Source distribution: {dict(src_dist)}")


if __name__ == "__main__":
    main()
