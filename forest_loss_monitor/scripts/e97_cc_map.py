"""Bamori map of the embedding change model. Builds the model's 22 inputs for every 10 m pixel on Earth Engine (best-break statistic per pixel, against itself and against the surrounding
500 m, summarised over the 5 x 5 pixel box around it, as at the labelled points), downloads them in chunks, and scores them locally with the saved model.
Usage: e97_cc_map.py check | fetch | score"""
import io
import json
import sys
import time

sys.path.insert(0, "E:/FIRE/forest_loss_monitor/scripts")

import ee
import geopandas as gpd
import joblib
import numpy as np
import pandas as pd

from common import *
from e33_map10m import init_retry
from e75_cc_fetch import COL
from e76_cc_train import YS, load
from e77_cc_local import wide

RANGE = "E:/e_Netra/data/aoi/guna_range_bamori.geojson"
D = WORK / "cc_map_bamori"
CHUNK = 256
MODEL = OUT / "interim" / "report" / "guna_cc_model.joblib"     # written by e84 on this machine, so loading it is safe
NAMES = ["t_med", "t_q75", "t_q90", "t_max", "lt_med", "lt_q75", "lt_q90", "lt_max", "s_med", "s_q75", "s_q90", "s_max", "ls_med", "ls_q75", "ls_q90", "ls_max", "f3", "f4", "f5", "lf3", "brk", "noise"]


def shifts():
    d, A = load()
    W = wide(d)
    r = (d.set == "random").values
    m, mw = A[r].mean(axis=0), W[r].mean(axis=0)
    return m - m.mean(axis=0), mw - mw.mean(axis=0)


def best_break(ims):
    """Per pixel: t, step, break index and noise of the strongest single break, as in e76.step_feats."""
    T = len(ims)
    out = []
    for b in range(1, T):
        pre, post = ee.ImageCollection(ims[:b]).mean(), ee.ImageCollection(ims[b:]).mean()
        step = post.subtract(pre).pow(2).reduce(ee.Reducer.sum()).sqrt()
        sse = ee.ImageCollection([ims[j].subtract(pre if j < b else post).pow(2).reduce(ee.Reducer.sum()) for j in range(T)]).sum()
        noise = sse.divide(T - 2).sqrt()
        t = step.divide(noise.add(.01)).multiply((b * (T - b) / T) ** .5)
        out.append(ee.Image.cat(t.rename("t"), step.rename("step"), ee.Image.constant(b).toFloat().rename("brk"), noise.rename("noise")))
    return ee.ImageCollection(out).qualityMosaic("t")


def features(sh, wsh):
    p10 = ee.Projection(WKT).atScale(10)
    raw = [ee.ImageCollection(COL).filterDate(f"{y}-01-01", f"{y + 1}-01-01").mosaic().toFloat() for y in YS]
    X = [im.subtract(ee.Image.constant(sh[i].tolist())) for i, im in enumerate(raw)]
    ring = [im.reproject(ee.Projection(WKT).atScale(30)).reduceNeighborhood(ee.Reducer.mean(), ee.Kernel.square(8)).subtract(ee.Image.constant(wsh[i].tolist())) for i, im in enumerate(raw)]
    box = best_break(X)
    loc = best_break([x.subtract(r) for x, r in zip(X, ring)])
    k5 = ee.Kernel.square(2)
    pct = ee.Reducer.percentile([50, 75, 90, 100])
    q = lambda im, nm: im.reduceNeighborhood(pct, k5).rename([f"{nm}_med", f"{nm}_q75", f"{nm}_q90", f"{nm}_max"])
    frac = ee.Image.cat(box.select("t").gt(3), box.select("t").gt(4), box.select("t").gt(5), loc.select("t").gt(3)).toFloat().reduceNeighborhood(ee.Reducer.mean(), k5).rename(["f3", "f4", "f5", "lf3"])
    top = box.select(["t", "brk", "noise"]).reduceNeighborhood(ee.Reducer.max(3), k5).rename(["tmax_", "brk", "noise"]).select(["brk", "noise"])
    img = ee.Image.cat(q(box.select("t"), "t"), q(loc.select("t"), "lt"), q(box.select("step"), "s"), q(loc.select("step"), "ls"), frac, top)
    return img.select(NAMES).toFloat().reproject(p10)


def check():
    """Same features computed by this image at the labelled points vs the training features."""
    init_retry()
    sh, wsh = shifts()
    img = features(sh, wsh)
    d, A = load()
    from e83_cc_pxmodel import px_features
    scal = px_features(d, A, wide(d))[0]
    k = d[d.set == "reference"].sample(30, random_state=1)
    p = ee.Projection(WKT)
    fc = ee.FeatureCollection([ee.Feature(ee.Geometry.Point([float(x), float(y)], p), dict(cid=int(c))) for x, y, c in zip(k.x, k.y_m, k.cid)])
    wait = 30
    for _ in range(12):
        try:
            rows = img.reduceRegions(fc, ee.Reducer.first(), crs=WKT, scale=10, tileScale=8).getInfo()["features"]
            break
        except Exception as e:
            print("retry", str(e)[:80], flush=True)
            time.sleep(wait)
            wait = min(wait * 2, 600)
    g = pd.DataFrame([r["properties"] for r in rows]).set_index("cid").reindex(k.cid)[NAMES]
    t = scal[k.index.values]
    out = pd.DataFrame(dict(feature=NAMES, corr=[round(np.corrcoef(g[c], t[:, i])[0, 1], 3) for i, c in enumerate(NAMES)], map_mean=g.mean().round(3).values, train_mean=t.mean(axis=0).round(3)))
    print(out.to_string())
    M = joblib.load(MODEL)["scalars"]["model"]
    s1, s2 = M.decision_function(g.values), M.decision_function(t)
    print("model score correlation", round(np.corrcoef(s1, s2)[0, 1], 3), "flag agreement at stage 1:", round(((s1 >= -2.143) == (s2 >= -2.143)).mean(), 3))


def grid():
    r = gpd.read_file(RANGE).to_crs(PROJ4)
    x0, y0, x1, y1 = r.total_bounds
    x0, y1 = np.floor(x0 / 30) * 30, np.ceil(y1 / 30) * 30
    nx, ny = int(np.ceil((x1 - x0) / 10)), int(np.ceil((y1 - y0) / 10))
    return r, x0, y1, nx, ny


def fetch():
    init_retry()
    D.mkdir(parents=True, exist_ok=True)
    sh, wsh = shifts()
    img = features(sh, wsh)
    r, x0, y1, nx, ny = grid()
    from shapely.geometry import box
    poly = r.union_all()
    jobs = [(i, j) for i in range(0, ny, CHUNK) for j in range(0, nx, CHUNK)
            if box(x0 + j * 10, y1 - (i + CHUNK) * 10, x0 + (j + CHUNK) * 10, y1 - i * 10).intersects(poly) and not (D / f"{i}_{j}.npy").exists()]
    print("chunks to fetch", len(jobs), flush=True)
    t0 = time.time()
    for n, (i, j) in enumerate(jobs):
        h, w = min(CHUNK, ny - i), min(CHUNK, nx - j)
        wait = 30
        for _ in range(8):
            try:
                raw = ee.data.computePixels(dict(expression=img, fileFormat="NPY", grid=dict(dimensions=dict(width=w, height=h), crsWkt=WKT,
                                                 affineTransform=dict(scaleX=10, shearX=0, translateX=x0 + j * 10, shearY=0, scaleY=-10, translateY=y1 - i * 10))))
                a = np.load(io.BytesIO(raw))
                np.save(D / f"{i}_{j}.npy", np.stack([a[c] for c in NAMES]).astype("float32"))
                break
            except Exception as e:
                print("retry", i, j, str(e)[:120], flush=True)
                time.sleep(wait)
                wait = min(wait * 2, 600)
        print(n + 1, "of", len(jobs), round(time.time() - t0), "s", flush=True)
    json.dump(dict(x0=float(x0), y1=float(y1), nx=nx, ny=ny, chunk=CHUNK), open(D / "grid.json", "w"))
    print("FINISHED")


if __name__ == "__main__":
    dict(check=check, fetch=fetch)[sys.argv[1]]()
