"""Accumulated change 2017-2025 per 10 m pixel in a 300 m window around each labelled point, for testing whether slow change adds up to patches a start-to-end comparison can see.
Bands: e2 = distance between the 2017-18 and 2024-25 mean embeddings; e3 = 2017-19 vs 2023-25; tr = strength of a straight-line trend through all 9 years (size of the fitted change over
its residual scatter); dw = fall in Dynamic World tree probability 2017-18 to 2024-25. Year-wide shift removed as in e85. One thread, resumable. Usage: e100_cc_cumwin.py"""
import json
import sys
import time

sys.path.insert(0, "E:/FIRE/forest_loss_monitor/scripts")

import ee
import numpy as np
import pandas as pd

from common import *
from e32_enetra10m import dw_mean
from e33_map10m import init_retry
from e75_cc_fetch import COL, ORDER
from e76_cc_train import YS, load

F = WORK / "cc_cumwin.jsonl"
HALF, BATCH = 150, 12


def image(shift, aoi):
    T = len(YS)
    X = [ee.ImageCollection(COL).filterDate(f"{y}-01-01", f"{y + 1}-01-01").mosaic().toFloat().subtract(ee.Image.constant(shift[i].tolist())) for i, y in enumerate(YS)]
    mean = lambda a: ee.ImageCollection(a).mean()
    norm = lambda im: im.pow(2).reduce(ee.Reducer.sum()).sqrt()
    e2 = norm(mean(X[7:]).subtract(mean(X[:2])))
    e3 = norm(mean(X[6:]).subtract(mean(X[:3])))
    tc = np.arange(T) - (T - 1) / 2
    slope = ee.ImageCollection([X[j].multiply(float(tc[j])) for j in range(T)]).sum().divide(float((tc ** 2).sum()))
    mu = mean(X)
    sse = ee.ImageCollection([X[j].subtract(mu).subtract(slope.multiply(float(tc[j]))).pow(2).reduce(ee.Reducer.sum()) for j in range(T)]).sum()
    tr = norm(slope).multiply(T - 1).divide(sse.divide(T - 2).sqrt().add(.01))
    dw = dw_mean(aoi, 2017, 2018).select("trees").subtract(dw_mean(aoi, 2024, 2025).select("trees"))
    return ee.Image.cat(e2.rename("e2"), e3.rename("e3"), tr.rename("tr"), dw.rename("dw")).unmask(-9).toFloat().addBands(ee.Image.pixelCoordinates(ee.Projection(WKT)).rename(["px", "py"]))


def main():
    init_retry()
    d, A = load()
    m = A[(d.set == "random").values].mean(axis=0)
    shift = m - m.mean(axis=0)
    seen = {json.loads(l)["cid"] for l in open(F)} if F.exists() else set()
    q = d[~d.cid.isin(seen)].assign(o=lambda z: z.set.map(ORDER.index), ry=lambda z: (z.y_m // 10000).astype(int)).sort_values(["ry", "x"])
    q = pd.concat([q[q.set == "reference"], q[q.set != "reference"]])
    p = ee.Projection(WKT)
    t0 = time.time()
    with open(F, "a") as o:
        for i in range(0, len(q), BATCH):
            part = q.iloc[i:i + BATCH]
            fc = ee.FeatureCollection([ee.Feature(ee.Geometry.Rectangle([x - HALF, y - HALF, x + HALF, y + HALF], p, False), dict(cid=int(c))) for x, y, c in zip(part.x, part.y_m, part.cid)])
            im = image(shift, fc.geometry().bounds(100, "EPSG:4326"))
            wait = 30
            for _ in range(10):
                try:
                    for f in im.reduceRegions(fc, ee.Reducer.toList(), crs=WKT, scale=10, tileScale=8).getInfo()["features"]:
                        r = f["properties"]
                        o.write(json.dumps(dict(cid=r["cid"], px=[round(v) for v in r["px"]], py=[round(v) for v in r["py"]], **{b: [round(v, 3) for v in r[b]] for b in ("e2", "e3", "tr", "dw")})) + "\n")
                    break
                except Exception as e:
                    print("retry", str(e)[:100], flush=True)
                    time.sleep(wait)
                    wait = min(wait * 2, 600)
            o.flush()
            print(min(i + BATCH, len(q)), "of", len(q), round(time.time() - t0), "s", flush=True)
    print("FINISHED")


if __name__ == "__main__":
    main()
