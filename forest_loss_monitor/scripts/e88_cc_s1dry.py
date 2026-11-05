"""Second signal for losses with flat Oct-Nov greenness: Sentinel-1 VV and VH (dry season Mar-May and leaf-on Oct-Nov) and Sentinel-2 NDVI, NBR and NDMI for Jan-Feb and Mar-May,
yearly 2017-2025, mean over the 50 m box at each change/no-change point. One thread, resumable. Usage: e88_cc_s1dry.py"""
import json
import sys
import time

sys.path.insert(0, "E:/FIRE/forest_loss_monitor/scripts")

import ee
import pandas as pd

from common import *
from e32_enetra10m import S2
from e33_map10m import init_retry
from e75_cc_fetch import ORDER

GT = ROOT / "ground_truth"
F = WORK / "cc_s1dry.jsonl"
YS = list(range(2017, 2026))
BATCH = 15
S1_WIN = {"dry": ("03-01", "06-01"), "leaf": ("10-01", "12-01")}
S2_WIN = {"jf": ("01-01", "03-01"), "mm": ("03-01", "06-01")}


def s2_season(a, y, w):
    def f(i):
        s = i.select("SCL")
        bad = s.eq(1).Or(s.eq(3)).Or(s.eq(8)).Or(s.eq(9)).Or(s.eq(10))
        return ee.Image.cat(i.normalizedDifference(["B8", "B4"]), i.normalizedDifference(["B8", "B12"]), i.normalizedDifference(["B8", "B11"])).updateMask(bad.Not())
    c = ee.ImageCollection(S2).filterBounds(a).filterDate(f"{y}-{S2_WIN[w][0]}", f"{y}-{S2_WIN[w][1]}").map(f)
    return c.median().rename([f"{w}_n{y}", f"{w}_r{y}", f"{w}_m{y}"])


def s1_season(a, y, w):
    c = (ee.ImageCollection("COPERNICUS/S1_GRD").filterBounds(a).filterDate(f"{y}-{S1_WIN[w][0]}", f"{y}-{S1_WIN[w][1]}").filter(ee.Filter.eq("instrumentMode", "IW"))
         .filter(ee.Filter.listContains("transmitterReceiverPolarisation", "VH")).filter(ee.Filter.eq("orbitProperties_pass", "DESCENDING")).select(["VV", "VH"]))
    return c.median().rename([f"{w}_vv{y}", f"{w}_vh{y}"])


def call(part):
    p = ee.Projection(WKT)
    fc = ee.FeatureCollection([ee.Feature(ee.Geometry.Rectangle([x - 25, y - 25, x + 25, y + 25], p, False), dict(cid=int(i))) for x, y, i in zip(part.x, part.y_m, part.cid)])
    a = fc.geometry().bounds(100, "EPSG:4326")
    b = []
    for y in YS:
        b += [s1_season(a, y, w) for w in S1_WIN] + [s2_season(a, y, w) for w in S2_WIN]
    return [f["properties"] for f in ee.Image.cat(b).unmask(-99).toFloat().reduceRegions(fc, ee.Reducer.mean(), crs=WKT, scale=10, tileScale=8).getInfo()["features"]]


def run(part):
    wait = 30
    for _ in range(10):
        try:
            return call(part)
        except Exception as e:
            msg = str(e)
            if "Too Many" in msg:
                time.sleep(wait)
                wait = min(wait * 2, 600)
            elif len(part) > 1:
                m = len(part) // 2
                return run(part.iloc[:m]) + run(part.iloc[m:])
            else:
                print("failed", int(part.cid.iloc[0]), msg[:160], flush=True)
                return []
    return []


def main():
    init_retry()
    d = pd.read_csv(GT / "guna_cc_labels.csv")
    seen = {json.loads(l)["cid"] for l in open(F)} if F.exists() else set()
    d = d[~d.cid.isin(seen)].assign(o=lambda q: q.set.map(ORDER.index), ry=lambda q: (q.y_m // 10000).astype(int)).sort_values(["ry", "x"])
    d = pd.concat([d[d.set == "reference"], d[d.set != "reference"]])
    n, t0 = 0, time.time()
    with open(F, "a") as out:
        for i in range(0, len(d), BATCH):
            for row in run(d.iloc[i:i + BATCH]):
                out.write(json.dumps({k: round(v, 3) if isinstance(v, float) else v for k, v in row.items()}) + "\n")
                n += 1
            out.flush()
            print(n, "of", len(d), round(time.time() - t0), "s", flush=True)
    print("FINISHED")


if __name__ == "__main__":
    main()
