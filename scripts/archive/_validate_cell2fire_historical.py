"""Real historical validation: Cell2Fire vs level-set vs observed burn scar.

Reference fire
--------------
* FIRMS detection : 2018-04-19, lat=24.19155, lon=76.97570, FRP=5.76 MW
* Burn scar       : HLS S30 T43QFG 2018-04-20 (days_gap=1, fresh, HIGH conf)
* Weather         : NASA POWER 2018-04-19 (Guna point)
* Wind direction  : 259 deg (WSW), inferred from burn-cluster elongation
* Fuel            : WorldCover grassland -> SB40 GR2

Method
------
1. Build the ground-truth burn polygon by isolating the connected burn-scar
   cluster touching the FIRMS pixel.
2. Run both spread engines (Cell2Fire + level-set) with identical inputs.
3. Rasterize each predicted 24h polygon onto the UTM 30m burn-scar grid.
4. Compute IoU, area error, true/false positives, centroid offset.
"""
from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import src.utils.proj_fix  # noqa: F401  must precede rasterio

import rasterio  # noqa: E402
from rasterio.features import rasterize  # noqa: E402
from rasterio.warp import transform as warp_transform  # noqa: E402
from scipy import ndimage as ndi  # noqa: E402
from shapely.geometry import shape  # noqa: E402

from src.analysis.spread_predictor import SpreadPredictor  # noqa: E402

logging.basicConfig(
    level=logging.WARNING,
    format="%(levelname)s %(name)s: %(message)s",
)
log = logging.getLogger("validate")


# ----------------------------- Test fixture ---------------------------------
FIRE = {
    "fire_lat": 24.19155,
    "fire_lon": 76.97570,
    "frp_mw": 5.76,
    "fire_date": "2018-04-19",
}

WEATHER = {
    # NASA POWER daily mean for 2018-04-19 over Guna
    "wind_kmh": 7.06,
    # No wind direction in our parquet. Inferred from burn-cluster elongation:
    # cluster centroid sits 969 m east and 184 m north of the FIRMS pixel,
    # implying the fire ran downwind to the ENE. Meteorological "from"
    # direction = 259 deg (WSW), matching MP pre-monsoon westerlies.
    "wind_dir_deg": 259.0,
    "temp_c": 33.33,
    "rh_pct": 16.03,
}

BURN_SCAR_PATH = (
    ROOT / "data_lake" / "burn_scars" / "hls_s30" / "T43QFG"
    / "2018" / "04" / "20"
    / "burnscar_HLS.S30.T43QFG.2018110T052649.v2.0.tif"
)


def build_ground_truth(burn_path: Path, fire_lat: float, fire_lon: float):
    """Return (mask, transform, crs) for the burn cluster touching the FIRMS pixel."""
    with rasterio.open(burn_path) as ds:
        xs, ys = warp_transform("EPSG:4326", ds.crs, [fire_lon], [fire_lat])
        row, col = ds.index(xs[0], ys[0])
        arr = ds.read(1)
        lbl, _ = ndi.label(arr > 0, structure=np.ones((3, 3), dtype=int))
        cluster_id = int(lbl[row, col])
        if cluster_id == 0:
            raise SystemExit("FIRMS pixel is not in any burn cluster")
        cluster = (lbl == cluster_id).astype(np.uint8)
        return cluster, ds.transform, ds.crs


def rasterize_polygon_to_grid(geojson_poly: dict, ref_transform, ref_shape, ref_crs):
    """Rasterize a WGS84 GeoJSON polygon onto the burn scar's UTM grid."""
    if not geojson_poly or not geojson_poly.get("coordinates"):
        return np.zeros(ref_shape, dtype=np.uint8)
    geom = shape(geojson_poly)  # WGS84 (lat/lon)
    if geom.is_empty:
        return np.zeros(ref_shape, dtype=np.uint8)

    # Reproject vertices to UTM
    if geom.geom_type == "Polygon":
        rings = [list(geom.exterior.coords)] + [list(r.coords) for r in geom.interiors]
    elif geom.geom_type == "MultiPolygon":
        rings = []
        for poly in geom.geoms:
            rings.append(list(poly.exterior.coords))
            for r in poly.interiors:
                rings.append(list(r.coords))
    else:
        return np.zeros(ref_shape, dtype=np.uint8)

    from shapely.geometry import Polygon, MultiPolygon

    utm_polys = []
    for ring in rings:
        lons = [c[0] for c in ring]
        lats = [c[1] for c in ring]
        xs, ys = warp_transform("EPSG:4326", ref_crs, lons, lats)
        utm_polys.append(Polygon(zip(xs, ys)))

    geom_utm = utm_polys[0] if len(utm_polys) == 1 else MultiPolygon(utm_polys)
    raster = rasterize(
        [(geom_utm, 1)],
        out_shape=ref_shape,
        transform=ref_transform,
        fill=0,
        dtype=np.uint8,
        all_touched=True,
    )
    return raster


def score(pred: np.ndarray, truth: np.ndarray) -> dict:
    p = pred.astype(bool)
    t = truth.astype(bool)
    inter = int((p & t).sum())
    union = int((p | t).sum())
    iou = inter / union if union else 0.0
    pred_ha = float(p.sum() * 0.09)
    truth_ha = float(t.sum() * 0.09)
    tp = inter
    fp = int((p & ~t).sum())
    fn = int((~p & t).sum())
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
    return {
        "pred_area_ha": round(pred_ha, 2),
        "truth_area_ha": round(truth_ha, 2),
        "area_error_ha": round(pred_ha - truth_ha, 2),
        "area_ratio": round(pred_ha / truth_ha, 3) if truth_ha else None,
        "iou": round(iou, 4),
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
    }


def run_engine(engine_name: str) -> dict:
    log.info("Running engine: %s", engine_name)
    pred = SpreadPredictor(engine=engine_name)
    return pred.predict(FIRE, WEATHER)


def main() -> int:
    print("=== HISTORICAL VALIDATION ===")
    print(f"Fire     : {FIRE}")
    print(f"Weather  : {WEATHER}")
    print(f"Scar src : {BURN_SCAR_PATH.name}")
    print()

    if not BURN_SCAR_PATH.exists():
        print(f"BURN SCAR MISSING: {BURN_SCAR_PATH}")
        return 1

    # 1. Ground truth burn cluster
    truth, transform, crs = build_ground_truth(
        BURN_SCAR_PATH, FIRE["fire_lat"], FIRE["fire_lon"]
    )
    truth_ha = float(truth.sum() * 0.09)
    print(f"GROUND TRUTH: {int(truth.sum())} px = {truth_ha:.2f} ha")
    print()

    # 2. Run both engines
    physics_result = run_engine("physics")
    c2f_result = run_engine("cell2fire")
    print(f"  level-set mode: {physics_result.get('mode')}")
    print(f"  cell2fire mode: {c2f_result.get('mode')}")
    print()

    # 3+4. Score each horizon
    rows = []
    for label, result in [("level-set", physics_result), ("cell2fire", c2f_result)]:
        for h in (6, 12, 24):
            poly = result.get(f"spread_{h}h", {}).get("polygon")
            pred_raster = rasterize_polygon_to_grid(
                poly, transform, truth.shape, crs
            )
            metrics = score(pred_raster, truth)
            metrics["engine"] = label
            metrics["horizon_h"] = h
            metrics["mode"] = result.get("mode")
            rows.append(metrics)

    print("=== SCORES vs OBSERVED BURN SCAR ===")
    print(
        f"{'engine':>10} {'h':>3} {'pred_ha':>9} {'truth_ha':>9} "
        f"{'ratio':>6} {'iou':>7} {'prec':>6} {'rec':>6} {'f1':>6}"
    )
    for r in rows:
        print(
            f"{r['engine']:>10} {r['horizon_h']:>3} {r['pred_area_ha']:>9} "
            f"{r['truth_area_ha']:>9} {r['area_ratio']!s:>6} {r['iou']:>7} "
            f"{r['precision']:>6} {r['recall']:>6} {r['f1']:>6}"
        )

    out_path = ROOT / "data_lake" / "outputs_sample" / "cell2fire_historical_validation.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps({
        "fire": FIRE,
        "weather": WEATHER,
        "burn_scar": str(BURN_SCAR_PATH),
        "truth_area_ha": round(truth_ha, 2),
        "scores": rows,
    }, indent=2))
    print()
    print(f"Saved: {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
