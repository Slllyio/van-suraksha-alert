"""Batch historical validation: Cell2Fire vs level-set over multiple real fires.

For each fire:
1. Isolate the connected burn-scar cluster touching the FIRMS pixel.
2. Infer wind direction from the cluster's elongation (FIRMS -> centroid).
3. Pull NASA POWER daily weather for the fire date.
4. Run both spread engines with identical inputs.
5. Rasterize each 24h polygon onto the burn-scar grid.
6. Compute IoU / precision / recall / F1 / area_error.

Aggregate statistics across all fires and print a comparison table.

Candidates were selected from data_lake/burn_scars/fire_links.csv by
requiring: spatial_hit, burn_area >= 5 ha, days_gap <= 15, and the FIRMS
pixel in a burnable WorldCover class (not in the 49% nodata region).
"""
from __future__ import annotations

import json
import logging
import math
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import src.utils.proj_fix  # noqa: F401  must precede rasterio

import rasterio  # noqa: E402
from rasterio.features import rasterize  # noqa: E402
from rasterio.warp import transform as warp_transform  # noqa: E402
from scipy import ndimage as ndi  # noqa: E402
from shapely.geometry import MultiPolygon, Polygon, shape  # noqa: E402

from src.analysis.spread_predictor import SpreadPredictor  # noqa: E402

logging.basicConfig(level=logging.ERROR, format="%(levelname)s %(name)s: %(message)s")
log = logging.getLogger("batch_validate")
log.setLevel(logging.INFO)


# ----------------------------- Fire fixtures -------------------------------
# Selected after filtering fire_links.csv for spatial_hit + burnable WorldCover
# centre + days_gap <= 15. See companion multi_fire_validation.md for provenance.
FIRES = [
    {
        "id": "2018-04-19_guna_grass",
        "fire_lat": 24.19155,
        "fire_lon": 76.97570,
        "frp_mw": 5.76,
        "fire_date": "2018-04-19",
        "scene_date": "2018-04-20",
        "tile": "T43QFG",
    },
    {
        "id": "2017-10-30_guna_crop",
        "fire_lat": 24.33403,
        "fire_lon": 76.95834,
        "frp_mw": 1.92,
        "fire_date": "2017-10-30",
        "scene_date": "2017-11-01",
        "tile": "T43QFG",
    },
    {
        "id": "2024-04-03_grass_N",
        "fire_lat": 24.31380,
        "fire_lon": 77.25567,
        "frp_mw": 19.93,
        "fire_date": "2024-04-03",
        "scene_date": "2024-04-05",
        "tile": "T43QGG",
    },
    {
        "id": "2018-10-14_crop",
        "fire_lat": 24.30194,
        "fire_lon": 77.41757,
        "frp_mw": 1.59,
        "fire_date": "2018-10-14",
        "scene_date": "2018-10-17",
        "tile": "T43QGG",
    },
    {
        "id": "2024-04-03_grass_S",
        "fire_lat": 24.11836,
        "fire_lon": 77.28254,
        "frp_mw": 13.58,
        "fire_date": "2024-04-03",
        "scene_date": "2024-04-08",
        "tile": "T43QGG",
    },
    {
        "id": "2025-04-19_grass",
        "fire_lat": 24.25959,
        "fire_lon": 76.92696,
        "frp_mw": 9.33,
        "fire_date": "2025-04-19",
        "scene_date": "2025-05-03",
        "tile": "T43QFG",
    },
]


# ----------------------------- Utilities -----------------------------------
def find_burn_scar(tile: str, scene_date: str) -> Optional[Path]:
    """Find the HLS burn scar .tif for a given tile and scene date."""
    y, m, d = scene_date.split("-")
    scene_dir = ROOT / "data_lake" / "burn_scars" / "hls_s30" / tile / y / m / d
    if not scene_dir.exists():
        return None
    tifs = list(scene_dir.glob("burnscar_HLS.S30.*.tif"))
    return tifs[0] if tifs else None


def build_ground_truth(
    burn_path: Path,
    fire_lat: float,
    fire_lon: float,
    max_radius_m: float = 3000.0,
) -> Optional[tuple]:
    """Return (mask, transform, crs, cluster_info) for the local burn footprint.

    Crops the connected-component search to a circle of ``max_radius_m`` around
    the FIRMS pixel so that tile-wide stubble-burn events don't get merged into
    one giant "cluster". For a 24h fire in grass/crop fuel, 3 km is an
    upper bound on plausible spread distance.
    """
    with rasterio.open(burn_path) as ds:
        xs, ys = warp_transform("EPSG:4326", ds.crs, [fire_lon], [fire_lat])
        try:
            row, col = ds.index(xs[0], ys[0])
        except Exception:
            return None
        if not (0 <= row < ds.height and 0 <= col < ds.width):
            return None
        arr = ds.read(1)
        # Crop to a max_radius_m circle around the FIRMS pixel to prevent
        # tile-wide stubble burns from forming one giant component.
        px_radius = int(max_radius_m / 30.0)
        yy, xx = np.ogrid[: arr.shape[0], : arr.shape[1]]
        within_radius = (yy - row) ** 2 + (xx - col) ** 2 <= px_radius**2
        local = (arr > 0) & within_radius
        lbl, _ = ndi.label(local, structure=np.ones((3, 3), dtype=int))
        cid = int(lbl[row, col])
        if cid == 0:
            nz = np.argwhere(local)
            if len(nz) == 0:
                return None
            dists = np.sqrt((nz[:, 0] - row) ** 2 + (nz[:, 1] - col) ** 2)
            idx = int(np.argmin(dists))
            if dists[idx] * 30 > 500:
                return None
            cid = int(lbl[nz[idx][0], nz[idx][1]])
        cluster = (lbl == cid).astype(np.uint8)

        # Compute centroid + wind direction from elongation
        rs, cs = np.where(cluster > 0)
        centroid_row = rs.mean()
        centroid_col = cs.mean()
        d_row = centroid_row - row
        d_col = centroid_col - col
        # Angle from FIRMS to centroid (degrees from north, clockwise)
        dx = d_col * 30.0
        dy = -d_row * 30.0
        azimuth_to = math.degrees(math.atan2(dx, dy)) % 360.0
        wind_from = (azimuth_to + 180.0) % 360.0
        info = {
            "cluster_id": cid,
            "n_px": int(cluster.sum()),
            "area_ha": float(cluster.sum() * 0.09),
            "centroid_offset_m": (float(d_col * 30.0), float(-d_row * 30.0)),  # (E,N)
            "wind_from_deg": wind_from,
            "ignition_rowcol": (int(row), int(col)),
        }
        return cluster, ds.transform, ds.crs, info


def rasterize_polygon_to_grid(
    geojson_poly: dict, ref_transform, ref_shape, ref_crs
) -> np.ndarray:
    if not geojson_poly or not geojson_poly.get("coordinates"):
        return np.zeros(ref_shape, dtype=np.uint8)
    geom = shape(geojson_poly)
    if geom.is_empty:
        return np.zeros(ref_shape, dtype=np.uint8)
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
    utm_polys = []
    for ring in rings:
        lons = [c[0] for c in ring]
        lats = [c[1] for c in ring]
        xs, ys = warp_transform("EPSG:4326", ref_crs, lons, lats)
        utm_polys.append(Polygon(zip(xs, ys)))
    geom_utm = utm_polys[0] if len(utm_polys) == 1 else MultiPolygon(utm_polys)
    return rasterize(
        [(geom_utm, 1)],
        out_shape=ref_shape,
        transform=ref_transform,
        fill=0,
        dtype=np.uint8,
        all_touched=True,
    )


def score(pred: np.ndarray, truth: np.ndarray) -> dict:
    p = pred.astype(bool)
    t = truth.astype(bool)
    inter = int((p & t).sum())
    union = int((p | t).sum())
    pred_ha = float(p.sum() * 0.09)
    truth_ha = float(t.sum() * 0.09)
    tp = inter
    fp = int((p & ~t).sum())
    fn = int((~p & t).sum())
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
    return {
        "pred_ha": round(pred_ha, 2),
        "truth_ha": round(truth_ha, 2),
        "ratio": round(pred_ha / truth_ha, 3) if truth_ha else None,
        "iou": round(inter / union, 4) if union else 0.0,
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
    }


def load_weather(fire_date: str) -> Optional[dict]:
    """Pull NASA POWER daily weather for a given date."""
    wp = ROOT / "data_lake" / "fire_weather" / "nasa_power_2013_2025.parquet"
    df = pd.read_parquet(wp)
    df["date_str"] = df["date"].astype(str).str[:10]
    row = df[df["date_str"] == fire_date]
    if len(row) == 0:
        return None
    r = row.iloc[0]
    return {
        "temp_c": float(r["temp_c"]),
        "rh_pct": float(r["rh_pct"]),
        "wind_kmh": float(r["wind_kmh"]),
    }


# ----------------------------- Main -----------------------------------------
def validate_one(fire: dict) -> dict:
    """Run full validation on a single fire."""
    out = {"id": fire["id"], "fire": fire, "ok": False, "reason": None}

    burn_path = find_burn_scar(fire["tile"], fire["scene_date"])
    if not burn_path:
        out["reason"] = f"burn scar missing: {fire['tile']}/{fire['scene_date']}"
        return out

    gt = build_ground_truth(burn_path, fire["fire_lat"], fire["fire_lon"])
    if gt is None:
        out["reason"] = "could not find burn cluster near FIRMS pixel"
        return out
    truth, transform, crs, info = gt
    out["ground_truth"] = info

    if info["area_ha"] < 5:
        out["reason"] = f"cluster too small: {info['area_ha']} ha"
        return out

    weather_base = load_weather(fire["fire_date"])
    if weather_base is None:
        out["reason"] = f"no NASA POWER weather for {fire['fire_date']}"
        return out

    weather = {
        **weather_base,
        "wind_dir_deg": info["wind_from_deg"],
    }
    out["weather"] = weather

    fire_detection = {
        "fire_lat": fire["fire_lat"],
        "fire_lon": fire["fire_lon"],
        "frp_mw": fire["frp_mw"],
    }

    try:
        phys_pred = SpreadPredictor(engine="physics")
        phys_result = phys_pred.predict(fire_detection, weather)
    except Exception as e:
        out["reason"] = f"physics predict failed: {e}"
        return out

    try:
        c2f_pred = SpreadPredictor(engine="cell2fire")
        c2f_result = c2f_pred.predict(fire_detection, weather)
    except Exception as e:
        out["reason"] = f"cell2fire predict failed: {e}"
        return out

    out["physics_mode"] = phys_result.get("mode")
    out["cell2fire_mode"] = c2f_result.get("mode")

    scores = {}
    for label, result in [("level-set", phys_result), ("cell2fire", c2f_result)]:
        for h in (6, 12, 24):
            poly = result.get(f"spread_{h}h", {}).get("polygon")
            pred_raster = rasterize_polygon_to_grid(poly, transform, truth.shape, crs)
            s = score(pred_raster, truth)
            scores[f"{label}_{h}h"] = s
    out["scores"] = scores
    out["ok"] = True
    return out


def main() -> int:
    print("=== BATCH HISTORICAL VALIDATION ===")
    print(f"Candidates: {len(FIRES)}")
    print()

    all_results = []
    for i, fire in enumerate(FIRES, 1):
        print(f"[{i}/{len(FIRES)}] {fire['id']}...", flush=True)
        r = validate_one(fire)
        all_results.append(r)
        if not r["ok"]:
            print(f"  SKIPPED: {r['reason']}")
            continue
        gt = r["ground_truth"]
        print(
            f"  truth={gt['area_ha']:.1f}ha  wind={r['weather']['wind_dir_deg']:.0f}deg  "
            f"temp={r['weather']['temp_c']:.1f}C  rh={r['weather']['rh_pct']:.0f}%  "
            f"wind={r['weather']['wind_kmh']:.1f}km/h  "
            f"c2f_mode={r['cell2fire_mode']}"
        )
        for h in (6, 12, 24):
            ls = r["scores"][f"level-set_{h}h"]
            c2f = r["scores"][f"cell2fire_{h}h"]
            print(
                f"    {h:>2}h  level-set: {ls['pred_ha']:7.1f}ha "
                f"ratio={ls['ratio']!s:>6} iou={ls['iou']:.3f} p={ls['precision']:.3f} r={ls['recall']:.3f}  |  "
                f"cell2fire: {c2f['pred_ha']:7.1f}ha "
                f"ratio={c2f['ratio']!s:>6} iou={c2f['iou']:.3f} p={c2f['precision']:.3f} r={c2f['recall']:.3f}"
            )

    # Aggregate stats over successful runs
    ok_runs = [r for r in all_results if r["ok"]]
    print()
    print("=" * 60)
    print(f"AGGREGATE ({len(ok_runs)} / {len(FIRES)} fires)")
    print("=" * 60)
    if ok_runs:
        for h in (6, 12, 24):
            ls_iou = [r["scores"][f"level-set_{h}h"]["iou"] for r in ok_runs]
            ls_ratio = [
                r["scores"][f"level-set_{h}h"]["ratio"]
                for r in ok_runs
                if r["scores"][f"level-set_{h}h"]["ratio"] is not None
            ]
            ls_prec = [r["scores"][f"level-set_{h}h"]["precision"] for r in ok_runs]
            ls_rec = [r["scores"][f"level-set_{h}h"]["recall"] for r in ok_runs]
            c2_iou = [r["scores"][f"cell2fire_{h}h"]["iou"] for r in ok_runs]
            c2_ratio = [
                r["scores"][f"cell2fire_{h}h"]["ratio"]
                for r in ok_runs
                if r["scores"][f"cell2fire_{h}h"]["ratio"] is not None
            ]
            c2_prec = [r["scores"][f"cell2fire_{h}h"]["precision"] for r in ok_runs]
            c2_rec = [r["scores"][f"cell2fire_{h}h"]["recall"] for r in ok_runs]
            print(f"\n-- Horizon {h}h --")
            print(
                f"  level-set  median IoU={np.median(ls_iou):.3f}  "
                f"mean ratio={np.mean(ls_ratio):.2f}  "
                f"median prec={np.median(ls_prec):.3f}  "
                f"median recall={np.median(ls_rec):.3f}"
            )
            print(
                f"  cell2fire  median IoU={np.median(c2_iou):.3f}  "
                f"mean ratio={np.mean(c2_ratio):.2f}  "
                f"median prec={np.median(c2_prec):.3f}  "
                f"median recall={np.median(c2_rec):.3f}"
            )

    out_path = ROOT / "data_lake" / "outputs_sample" / "cell2fire_batch_validation.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(all_results, indent=2, default=str))
    print()
    print(f"Saved: {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
