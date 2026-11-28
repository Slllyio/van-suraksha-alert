"""AlphaEarth annual 64-d embeddings 2017-2024 at every labelled point, saved as one row per point. Resumable. Usage: e64_emb_points.py [threads]"""
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor

import ee
import pandas as pd

from common import *
from e33_map10m import init_retry
from e46_s2f import all_points

F = WORK / "emb_points.jsonl"
YS = list(range(2017, 2025))
COL = "GOOGLE/SATELLITE_EMBEDDING/V1/ANNUAL"
BATCH = 20


def stack():
    b = []
    for y in YS:
        im = ee.ImageCollection(COL).filterDate(f"{y}-01-01", f"{y + 1}-01-01").mosaic()
        b.append(im.rename([f"y{y}_{i:02d}" for i in range(64)]))
    return ee.Image.cat(b).toFloat()


def run(part):
    p = ee.Projection(WKT)
    fc = ee.FeatureCollection([ee.Feature(ee.Geometry.Point([float(x), float(y)], p), dict(pid=int(i))) for x, y, i in zip(part.x, part.y, part.pid)])
    wait = 30
    for _ in range(12):
        try:
            return [f["properties"] for f in stack().reduceRegions(fc, ee.Reducer.first(), crs=WKT, scale=10, tileScale=4).getInfo()["features"]]
        except Exception as e:
            msg = str(e)[:150]
            if "Too Many" in msg:
                time.sleep(wait)
                wait = min(wait * 2, 600)
            else:
                time.sleep(5)
    print("failed", msg, flush=True)
    return []


def main():
    init_retry()
    th = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    d = all_points()
    s = pd.read_csv(WORK / "sweep_selected.csv")[["pid", "x", "y"]] if (WORK / "sweep_selected.csv").exists() else d.iloc[:0]
    d = pd.concat([d, s], ignore_index=True)
    seen = {json.loads(l)["pid"] for l in open(F)} if F.exists() else set()
    d = d[~d.pid.isin(seen)].assign(ry=lambda q: (q.y // 30000).astype(int), rx=lambda q: (q.x // 30000).astype(int)).sort_values(["ry", "rx"])
    n = 0
    with ThreadPoolExecutor(th) as ex, open(F, "a") as out:
        for r in ex.map(run, [d.iloc[i:i + BATCH] for i in range(0, len(d), BATCH)]):
            for row in r:
                out.write(json.dumps({k: round(v, 4) if isinstance(v, float) else v for k, v in row.items()}) + "\n")
            out.flush()
            n += len(r)
            print(n, flush=True)
    print("FINISHED")


if __name__ == "__main__":
    main()
