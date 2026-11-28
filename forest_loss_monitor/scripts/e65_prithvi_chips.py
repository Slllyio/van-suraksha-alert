"""HLS v002 chips for frozen Prithvi: 225 px at 30 m around labelled points, Oct-Nov 2018 and 2024, cloud-masked median, 6 bands. Guna first, fellings and Bamori next, then round 2. Resumable.
Usage: e65_prithvi_chips.py [threads]"""
import sys
import time
from concurrent.futures import ThreadPoolExecutor

import ee
import numpy as np
import pandas as pd

from common import *
from e33_map10m import init_retry
from e46_s2f import all_points

D = WORK / "prithvi_chips"
HALF = 112 * 30
BANDS = ["b", "g", "r", "n", "s1", "s2"]


def comp(r4, y):
    a, b = f"{y}-10-01", f"{y}-12-01"
    L = ee.ImageCollection("NASA/HLS/HLSL30/v002").filterBounds(r4).filterDate(a, b).select(["B2", "B3", "B4", "B5", "B6", "B7", "Fmask"], BANDS + ["f"])
    S = ee.ImageCollection("NASA/HLS/HLSS30/v002").filterBounds(r4).filterDate(a, b).select(["B2", "B3", "B4", "B8A", "B11", "B12", "Fmask"], BANDS + ["f"])
    return L.merge(S).map(lambda i: i.updateMask(i.select("f").bitwiseAnd(0b1110).eq(0)).select(BANDS)).median().multiply(10000).unmask(0).toInt16()


def chip(s):
    f = D / f"{s.pid}.npz"
    if f.exists():
        return
    roi = ee.Geometry.Rectangle([s.x - HALF, s.y - HALF, s.x + HALF, s.y + HALF], ee.Projection(WKT), False)
    r4 = roi.transform("EPSG:4326", 10)
    out = {}
    for y in (2018, 2024):
        wait = 30
        for _ in range(10):
            try:
                a = comp(r4, y).reproject(ee.Projection(WKT).atScale(30)).sampleRectangle(region=roi, defaultValue=0).getInfo()["properties"]
                out[f"y{y}"] = np.stack([np.array(a[b], "int16") for b in BANDS])
                break
            except Exception as e:
                msg = str(e)[:120]
                time.sleep(wait if "Too Many" in msg else 5)
                wait = min(wait * 2, 300)
        else:
            print("failed", s.pid, msg, flush=True)
            return
    np.savez_compressed(f, **out)


def rank(p):
    return 0 if 500000 <= p < 600000 else 2 if p >= 600000 else 1 if p >= 200000 else 3


def main():
    init_retry()
    D.mkdir(parents=True, exist_ok=True)
    g = pd.read_csv(ROOT / "ground_truth" / "guna_labels.csv").assign(pid=lambda d: d.gid + 500000)
    ref = set(g[g.source == "blind_reference"].pid)
    d = all_points()
    d = d[d.pid < 600000]
    d["o"] = d.pid.map(lambda p: -1 if p in ref else rank(p))
    d = d[d.o <= 1].sort_values(["o", "pid"])
    print("points", len(d), flush=True)
    with ThreadPoolExecutor(int(sys.argv[1]) if len(sys.argv) > 1 else 1) as ex:
        for i, _ in enumerate(ex.map(chip, d.itertuples())):
            if i % 20 == 0:
                print(i, flush=True)
    print("FINISHED")


if __name__ == "__main__":
    main()
