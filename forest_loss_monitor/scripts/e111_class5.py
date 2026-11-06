"""Yearly 5-class land cover for all Guna ranges, so that active crop and fallow are counted apart. Classes from the owner's 2022 Bamori polygons: 0 crop, 1 crop fallow, 2 bare, 3 forest, 4 dense forest.
A multinomial logistic model on the 2022 AlphaEarth embedding; each other year's 64 bands are first z-matched to 2022 (mean and sd over 2,000 random Guna forest pixels, no labels), which is linear
and so is folded into the per-year coefficients on Earth Engine. Output per range: class per year 2017-2025, uint8, same chunks as e109. Usage: e111_class5.py fit | map [Range]"""
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
from shapely.geometry import box
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import GroupKFold

from common import *
from e33_map10m import init_retry
from e75_cc_fetch import COL
from e105_cc_cropmask import S, retry
from e109_newcrop import CHUNK, grid_of

YS = list(range(2017, 2026))
M5 = WORK / "class5_model.json"
C5 = WORK / "class5"
ORDER = ["c", "c2", "b", "f", "df"]


def year_stats():
    """Mean and sd of each band per year over the unlabelled pool (box means at 10 m)."""
    e = pd.DataFrame([json.loads(l) for l in open(WORK / "cc_pool_25.jsonl")]).dropna()
    A = np.stack([e[[f"y{y}_{i:02d}" for i in range(64)]].values for y in YS], axis=1)
    return A.mean(axis=0), A.std(axis=0)


def fit():
    d = pd.read_csv(S).dropna()
    B = [f"A{i:02d}" for i in range(64)]
    X, y, g = d[B].values, d.cls.map(ORDER.index).values, d.pid.values
    pred = np.zeros(len(d), int)
    for tr, te in GroupKFold(5).split(X, y, g):
        pred[te] = LogisticRegression(C=1.0, max_iter=5000).fit(X[tr], y[tr]).predict(X[te])
    print("held-out polygon pixel accuracy", round((pred == y).mean(), 3))
    print(pd.crosstab(pd.Series(y, name="true").map(dict(enumerate(ORDER))), pd.Series(pred, name="pred").map(dict(enumerate(ORDER)))).to_string())
    pp = pd.DataFrame(dict(pid=g, y=y, p=pred)).groupby("pid").agg(y=("y", "first"), p=("p", lambda s: s.mode().iloc[0]))
    print("held-out polygon accuracy", round((pp.y == pp.p).mean(), 3))
    m = LogisticRegression(C=1.0, max_iter=5000).fit(X, y)
    mu, sd = year_stats()
    k22 = YS.index(2022)
    per_year = {}
    for k, yv in enumerate(YS):
        a = sd[k22] / np.maximum(sd[k], 1e-6)          # x' = (x - mu_y) * a + mu_22
        per_year[yv] = dict(coef=(m.coef_ * a).tolist(), intercept=(m.intercept_ + m.coef_ @ (mu[k22] - mu[k] * a)).tolist())
    json.dump(dict(bands=B, years=per_year), open(M5, "w"))
    print("largest band-mean shift vs 2022, in sd units, by year:", {y: round(float(np.abs((mu[k] - mu[k22]) / sd[k22]).max()), 2) for k, y in enumerate(YS)})


def image():
    m = json.load(open(M5))
    out = []
    for y in YS:
        im = ee.ImageCollection(COL).filterDate(f"{y}-01-01", f"{y + 1}-01-01").mosaic().select(m["bands"])
        q = m["years"][str(y)]
        logits = ee.Image.cat([im.multiply(ee.Image.constant(c)).reduce(ee.Reducer.sum()).add(b) for c, b in zip(q["coef"], q["intercept"])])
        out.append(logits.toArray().arrayArgmax().arrayGet(0).rename(f"k{y}"))
    return ee.Image.cat(out).toUint8().reproject(ee.Projection(WKT).atScale(10))


def mapfetch(only=None):
    init_retry()
    beats = gpd.read_parquet(WORK / "beats_albers.parquet")
    beats = beats[beats.Division == "Guna"]
    img = image()
    for rng in ["Bamori"] + [r for r in sorted(beats.Range.unique()) if r != "Bamori"]:
        if only and rng != only:
            continue
        b = beats[beats.Range == rng]
        g = grid_of(b)
        d = C5 / rng
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
            np.save(d / f"{i}_{j}.npy", np.stack([a[f"k{y}"] for y in YS]).astype("uint8"))
            if n % 10 == 0:
                print(rng, n + 1, "of", len(jobs), round(time.time() - t0), "s", flush=True)
        print(rng, "DONE", flush=True)
    print("FINISHED")


if __name__ == "__main__":
    dict(fit=fit, map=lambda: mapfetch(ARGS[1] if len(ARGS) > 1 else None))[ARGS[0]]()
