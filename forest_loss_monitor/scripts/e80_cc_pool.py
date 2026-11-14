"""Unlabelled Guna forest pool: embeddings at 50 m and 500 m at 2,000 random pixels, to learn how much a pixel of a given kind changes from year to year when nothing happens. Not used as labels. Usage: e80_cc_pool.py 25|250"""
import json
import sys

sys.path.insert(0, "E:/FIRE/forest_loss_monitor/scripts")

import numpy as np
import pandas as pd
import rasterio

import e75_cc_fetch as f
from common import *
from e33_map10m import init_retry

N, SEED, CID0 = 2000, 20261107, 100000
POOL = ROOT / "ground_truth" / "guna_cc_pool.csv"


def sample():
    if POOL.exists():
        return pd.read_csv(POOL)
    lk = pd.read_csv(OUT / "beat_lookup.csv")
    with rasterio.open(WORK / "zone_beat.tif") as s:
        z, tr = s.read(1), s.transform
    rr, cc = np.nonzero(np.isin(z, lk[lk.Division == "Guna"].zone_id.values))
    i = np.random.default_rng(SEED).choice(len(rr), N, replace=False)
    d = pd.DataFrame(dict(cid=CID0 + np.arange(N), x=tr.c + (cc[i] + .5) * tr.a, y_m=tr.f + (rr[i] + .5) * tr.e))
    d.to_csv(POOL, index=False)
    return d


def main():
    init_retry()
    out = WORK / f"cc_pool_{f.HALF}.jsonl"
    d = sample()
    seen = {json.loads(l)["cid"] for l in open(out)} if out.exists() else set()
    d = d[~d.cid.isin(seen)].assign(ry=lambda q: (q.y_m // 10000).astype(int)).sort_values(["ry", "x"])
    n = 0
    with open(out, "a") as o:
        for i in range(0, len(d), f.BATCH):
            for row in f.run(d.iloc[i:i + f.BATCH]):
                o.write(json.dumps({k: round(v, 4) if isinstance(v, float) else v for k, v in row.items()}) + "\n")
                n += 1
            o.flush()
            print(n, "of", len(d), flush=True)
    print("FINISHED")


if __name__ == "__main__":
    main()
