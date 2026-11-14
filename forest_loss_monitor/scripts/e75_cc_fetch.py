"""AlphaEarth annual embeddings 2017-2025, mean over a 50 m box at each change/no-change point, the box the owner judged. One thread, small batches, resumable. Usage: e75_cc_fetch.py [half_box_m]; 250 fetches the surroundings at 30 m, for comparing a point with its neighbourhood."""
import sys
sys.path.insert(0, "E:/FIRE/forest_loss_monitor/scripts")
import json
import time

import ee
import pandas as pd

from common import *
from e33_map10m import init_retry

GT = ROOT / "ground_truth"
HALF = int(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1].isdigit() else 25
F = WORK / ("cc_emb.jsonl" if HALF == 25 else f"cc_emb_{HALF}.jsonl")
SCALE = 10 if HALF == 25 else 30
YS = list(range(2017, 2026))
COL = "GOOGLE/SATELLITE_EMBEDDING/V1/ANNUAL"
BATCH = 20
ORDER = ["new_flag", "bamori_fp", "recall_kit", "recent_new", "felling", "reference", "random", "bamori_tp"]


def stack():
    return ee.Image.cat([ee.ImageCollection(COL).filterDate(f"{y}-01-01", f"{y + 1}-01-01").mosaic().rename([f"y{y}_{i:02d}" for i in range(64)]) for y in YS]).toFloat()


def run(part):
    p = ee.Projection(WKT)
    fc = ee.FeatureCollection([ee.Feature(ee.Geometry.Rectangle([x - HALF, y - HALF, x + HALF, y + HALF], p, False), dict(cid=int(i))) for x, y, i in zip(part.x, part.y_m, part.cid)])
    wait, msg = 30, ""
    for _ in range(12):
        try:
            return [f["properties"] for f in stack().reduceRegions(fc, ee.Reducer.mean(), crs=WKT, scale=SCALE, tileScale=4).getInfo()["features"]]
        except Exception as e:
            msg = str(e)[:150]
            time.sleep(wait if "Too Many" in msg else 5)
            wait = min(wait * 2, 600)
    print("failed", msg, flush=True)
    return []


def main():
    init_retry()
    d = pd.read_csv(GT / "guna_cc_labels.csv")
    seen = {json.loads(l)["cid"] for l in open(F)} if F.exists() else set()
    d = d[~d.cid.isin(seen)].assign(o=lambda q: q.set.map(ORDER.index), ry=lambda q: (q.y_m // 10000).astype(int)).sort_values(["o", "ry", "x"])
    n, t0 = 0, time.time()
    with open(F, "a") as out:
        for i in range(0, len(d), BATCH):
            for row in run(d.iloc[i:i + BATCH]):
                out.write(json.dumps({k: round(v, 4) if isinstance(v, float) else v for k, v in row.items()}) + "\n")
                n += 1
            out.flush()
            print(n, "of", len(d), round(time.time() - t0), "s", flush=True)
    print("FINISHED")


if __name__ == "__main__":
    main()
