"""New cropland inside recorded forest, Guna division: any land that was not cropped in 2017-19 and is cropped in 2023-25, whatever it was before (forest, scrub, bare or fallow).
Cropland comes from the classifier of e105 (owner's 2022 Bamori polygons on AlphaEarth embeddings), applied to each year 2017-2025 separately.
Usage: e109_newcrop.py points | map [Range] | tables"""
import io
import json
import sys
import time

sys.path.insert(0, "E:/FIRE/forest_loss_monitor/scripts")
ARGS = sys.argv[1:]
sys.argv = sys.argv[:1]

import ee
import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio
from scipy.ndimage import label
from shapely.geometry import box

from common import *
from e33_map10m import init_retry
from e75_cc_fetch import COL
from e105_cc_cropmask import M, retry

YS = list(range(2017, 2026))
GT = ROOT / "ground_truth"
NC = WORK / "newcrop"
P = WORK / "newcrop_points.csv"
OUTD = OUT / "guna_newcrop"
CHUNK = 256


def yearly():
    """Crop probability per year, 9 bands, as bytes (x200)."""
    m = json.load(open(M))
    out = []
    for y in YS:
        z = ee.ImageCollection(COL).filterDate(f"{y}-01-01", f"{y + 1}-01-01").mosaic().select(m["bands"]).multiply(ee.Image.constant(m["coef"])).reduce(ee.Reducer.sum()).add(m["intercept"])
        out.append(ee.Image(1).divide(ee.Image(1).add(z.multiply(-1).exp())).rename(f"c{y}"))
    return ee.Image.cat(out).toFloat()


def points():
    init_retry()
    from e76_cc_train import load
    d, _ = load()
    parts = [d[["cid", "x", "y_m"]]]
    for f in ("bamori_map_labelled.csv",):
        parts.append(pd.read_csv(GT / f)[["cid", "x", "y_m"]])
    for key in ("bamori_round2", "bamori_round3"):
        parts.append(pd.read_csv(GT / f"{key}_key_DO_NOT_OPEN_BEFORE_LABELLING.csv")[["cid", "x", "y_m"]])
    q = pd.concat(parts, ignore_index=True)
    im = yearly()
    p = ee.Projection(WKT)
    rows = []
    for i in range(0, len(q), 100):
        part = q.iloc[i:i + 100]
        fc = ee.FeatureCollection([ee.Feature(ee.Geometry.Rectangle([x - 25, y - 25, x + 25, y + 25], p, False), dict(cid=int(c))) for x, y, c in zip(part.x, part.y_m, part.cid)])
        rows += [f["properties"] for f in retry(lambda: im.reduceRegions(fc, ee.Reducer.mean(), crs=WKT, scale=10).getInfo()["features"])]
        print(len(rows), "of", len(q), flush=True)
    pd.DataFrame(rows).to_csv(P, index=False)


def grid_of(b):
    x0, y0, x1, y1 = b.total_bounds
    x0, y1 = np.floor(x0 / 30) * 30, np.ceil(y1 / 30) * 30
    return dict(x0=float(x0), y1=float(y1), nx=int(np.ceil((x1 - x0) / 10)), ny=int(np.ceil((y1 - y0) / 10)))


def mapfetch(only=None):
    init_retry()
    beats = gpd.read_parquet(WORK / "beats_albers.parquet")
    beats = beats[beats.Division == "Guna"]
    img = yearly().multiply(200).round().toUint8().reproject(ee.Projection(WKT).atScale(10))
    for rng in sorted(beats.Range.unique()):
        if only and rng != only:
            continue
        b = beats[beats.Range == rng]
        g = grid_of(b)
        d = NC / rng
        d.mkdir(parents=True, exist_ok=True)
        json.dump(g, open(d / "grid.json", "w"))
        poly = b.union_all()
        jobs = [(i, j) for i in range(0, g["ny"], CHUNK) for j in range(0, g["nx"], CHUNK)
                if box(g["x0"] + j * 10, g["y1"] - (i + CHUNK) * 10, g["x0"] + (j + CHUNK) * 10, g["y1"] - i * 10).intersects(poly) and not (d / f"{i}_{j}.npy").exists()]
        print(rng, "chunks", len(jobs), flush=True)
        t0 = time.time()
        for n, (i, j) in enumerate(jobs):
            h, w = min(CHUNK, g["ny"] - i), min(CHUNK, g["nx"] - j)
            raw = retry(lambda: ee.data.computePixels(dict(expression=img, fileFormat="NPY", grid=dict(dimensions=dict(width=w, height=h), crsWkt=WKT,
                                                         affineTransform=dict(scaleX=10, shearX=0, translateX=g["x0"] + j * 10, shearY=0, scaleY=-10, translateY=g["y1"] - i * 10)))))
            a = np.load(io.BytesIO(raw))
            np.save(d / f"{i}_{j}.npy", np.stack([a[f"c{y}"] for y in YS]).astype("uint8"))
            if n % 10 == 0:
                print(rng, n + 1, "of", len(jobs), round(time.time() - t0), "s", flush=True)
        print(rng, "DONE", flush=True)
    print("FINISHED")


if __name__ == "__main__":
    dict(points=points, map=lambda: mapfetch(ARGS[1] if len(ARGS) > 1 else None))[ARGS[0]]()
