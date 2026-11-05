"""One table for scrub-to-farm, the miss analysis, the time-series filter and the recall levers: every input of the rule and the yearly series at each
10 m pixel of the 50 m box around a labelled point, the same box used to score the map. Later tests run locally with no Earth Engine calls.
Guna points first, then the random 300, round 2, round 1. Resumable. Usage: e47_px.py [threads]"""
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor

import ee
import pandas as pd

from common import *
from e32_enetra10m import A_EARLY, A_LATE, B_EARLY, B_LATE, DW, S2, dw_mean, ndvi_mean
from e33_map10m import init_retry
from e39_conversion import ndvi
from e46_s2f import all_points

F = WORK / "s2f_px.jsonl"
YS = list(range(2017, 2026))
PROB_MAX = 40
BATCH = 12


def leaf(y, a):
    """Leaf-on NDVI, NBR, BSI, cloud-masked with s2cloudless."""
    s2 = ee.ImageCollection(S2).filterBounds(a).filterDate(f"{y}-10-01", f"{y}-12-01")
    pr = ee.ImageCollection("COPERNICUS/S2_CLOUD_PROBABILITY").filterBounds(a).filterDate(f"{y}-10-01", f"{y}-12-01")
    j = ee.ImageCollection(ee.Join.saveFirst("p").apply(s2, pr, ee.Filter.equals(leftField="system:index", rightField="system:index")))

    def f(i):
        i = ee.Image(i)
        bsi = i.expression("((b('B11')+b('B4'))-(b('B8')+b('B2')))/((b('B11')+b('B4'))+(b('B8')+b('B2')))").rename("b")
        return ee.Image.cat(i.normalizedDifference(["B8", "B4"]).rename("n"), i.normalizedDifference(["B8", "B12"]).rename("r"), bsi).toFloat().updateMask(ee.Image(i.get("p")).select("probability").lt(PROB_MAX))
    return j.map(f).median().rename([f"ln{y}", f"lr{y}", f"lb{y}"])


def stack(a):
    b = []
    for y in YS:
        d = dw_mean(a, y, y)
        b += [ndvi(a, y, 1, 3).rename(f"r{y}"), ndvi(a, y, 4, 5).rename(f"d{y}"), leaf(y, a), d.select("trees").rename(f"t{y}"), d.select("crops").rename(f"c{y}")]
    ea, la, eb, lb = dw_mean(a, *A_EARLY), dw_mean(a, *A_LATE), dw_mean(a, *B_EARLY), dw_mean(a, *B_LATE)
    for nm, w in (("ea", ea), ("eb", eb)):
        b += [w.select("trees").rename(f"{nm}_t"), w.select("shrub_and_scrub").rename(f"{nm}_s"), w.select("crops").rename(f"{nm}_c")]
    for nm, w in (("la", la), ("lb", lb)):
        b += [w.select("trees").rename(f"{nm}_t"), w.select("crops").rename(f"{nm}_c"), w.select("bare").rename(f"{nm}_b"), w.select("built").rename(f"{nm}_u"), w.select("shrub_and_scrub").rename(f"{nm}_s")]
    b += [dw_mean(a, A_EARLY[0], A_EARLY[1], (8, 10)).select("trees").rename("mon0"), dw_mean(a, 2024, 2024, (8, 10)).select("trees").rename("mon24")]
    for nm, w in (("nea", A_EARLY), ("nla", A_LATE), ("neb", B_EARLY), ("nlb", B_LATE)):
        b.append(ndvi_mean(a, *w).rename(nm))
    b.append(ee.Image("JRC/GSW1_4/GlobalSurfaceWater").select("occurrence").unmask(0).rename("water"))
    return ee.Image.cat(b).unmask(-9).toFloat()


def call(part):
    p = ee.Projection(WKT)
    fc = ee.FeatureCollection([ee.Feature(ee.Geometry.Rectangle([x - 25, y - 25, x + 25, y + 25], p, False), dict(pid=int(i))) for x, y, i in zip(part.x, part.y, part.pid)])
    a = fc.geometry().bounds(100, "EPSG:4326")
    return [f["properties"] for f in stack(a).reduceRegions(fc, ee.Reducer.toList(), crs=WKT, scale=10, tileScale=8).getInfo()["features"]]


def run(part):
    wait = 30
    while True:
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
                print("failed", int(part.pid.iloc[0]), msg[:160], flush=True)
                return []


def rank(p):
    return 0 if p >= 600000 else 1 if p >= 500000 else 2 if p >= 200000 else 3


def main():
    init_retry()
    th = int(sys.argv[1]) if len(sys.argv) > 1 else 2
    d = all_points()
    seen = set()
    if F.exists():
        seen = {json.loads(l)["pid"] for l in open(F)}
    d = d[~d.pid.isin(seen)].assign(o=lambda q: q.pid.map(rank), ry=lambda q: (q.y // 30000).astype(int), rx=lambda q: (q.x // 30000).astype(int)).sort_values(["o", "ry", "rx"])
    jobs = []
    for _, g in d.groupby("o", sort=True):
        jobs += [g.iloc[i:i + BATCH] for i in range(0, len(g), BATCH)]
    print("points", len(d), "batches", len(jobs), flush=True)
    n, t0 = 0, time.time()
    with ThreadPoolExecutor(th) as ex, open(F, "a") as out:
        for r in ex.map(run, jobs):
            for row in r:
                row = {k: ([round(x, 3) for x in v] if isinstance(v, list) else v) for k, v in row.items()}
                out.write(json.dumps(row) + "\n")
            out.flush()
            n += len(r)
            print(n, int(time.time() - t0), "s", flush=True)
    print("FINISHED")


if __name__ == "__main__":
    main()
