"""New stage-1 flags in background tree cover, for labelling. Scores the 2,000 random Guna forest pixels of the pool with the per-pixel embedding break (max over the 50 m box, as a map would) and
Dynamic World tree cover 2017-19. Keeps 100 at random among those with break >= 1.9 (the stage-1 bar from e85) and tree cover >= 0.30, at least 300 m from any labelled point.
Appends them to ground_truth/guna_cc_labels.csv as set 'new_flag' with y = -1 (unlabelled). Usage: e92_cc_newflags.py score | select"""
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
from e80_cc_pool import POOL
from e85_cc_area import shift_of, t_image

GT = ROOT / "ground_truth"
F = WORK / "cc_pool_t.jsonl"
BAR, TREES, N, SEED, BATCH = 1.9, .30, 100, 20261108, 20


def score():
    init_retry()
    _, _, shift = shift_of()
    d = pd.read_csv(POOL)
    seen = {json.loads(l)["cid"] for l in open(F)} if F.exists() else set()
    d = d[~d.cid.isin(seen)].assign(ry=lambda q: (q.y_m // 10000).astype(int)).sort_values(["ry", "x"])
    p = ee.Projection(WKT)
    t = t_image(shift)
    with open(F, "a") as o:
        for i in range(0, len(d), BATCH):
            part = d.iloc[i:i + BATCH]
            fc = ee.FeatureCollection([ee.Feature(ee.Geometry.Rectangle([x - 25, y - 25, x + 25, y + 25], p, False), dict(cid=int(c))) for x, y, c in zip(part.x, part.y_m, part.cid)])
            im = t.addBands(dw_mean(fc.geometry().bounds(100, "EPSG:4326"), 2017, 2019).select("trees"))
            wait = 30
            for _ in range(8):
                try:
                    for f in im.reduceRegions(fc, ee.Reducer.max().combine(ee.Reducer.mean(), sharedInputs=True), crs=WKT, scale=10, tileScale=8).getInfo()["features"]:
                        o.write(json.dumps(f["properties"]) + "\n")
                    break
                except Exception as e:
                    print("retry", str(e)[:120], flush=True)
                    time.sleep(wait)
                    wait = min(wait * 2, 600)
            o.flush()
            print(min(i + BATCH, len(d)), "of", len(d), flush=True)
    print("FINISHED")


def select():
    s = pd.DataFrame([json.loads(l) for l in open(F)]).drop_duplicates("cid").merge(pd.read_csv(POOL), on="cid")
    L = pd.read_csv(GT / "guna_cc_labels.csv")
    assert "new_flag" not in set(L.set), "already appended"
    print("pool", len(s), "tree cover >= .30:", int((s.trees_mean >= TREES).sum()), "of those flagged:", int(((s.trees_mean >= TREES) & (s.t_max >= BAR)).sum()), "all flagged:", int((s.t_max >= BAR).sum()))
    c = s[(s.trees_mean >= TREES) & (s.t_max >= BAR)]
    far = [((L[["x", "y_m"]].values - [x, y]) ** 2).sum(axis=1).min() >= 300 ** 2 for x, y in zip(c.x, c.y_m)]
    c = c[far].sample(min(N, int(np.sum(far))), random_state=SEED)
    lk = pd.read_csv(OUT / "beat_lookup.csv").set_index("zone_id").Beat
    import rasterio
    with rasterio.open(WORK / "zone_beat.tif") as src:
        z, tr = src.read(1), src.transform
    beat = lk.reindex(z[((tr.f - c.y_m.values) / -tr.e).astype(int), ((c.x.values - tr.c) / tr.a).astype(int)]).values
    new = pd.DataFrame(dict(cid=L.cid.max() + 1 + np.arange(len(c)), set="new_flag", id=[f"NEW_{i:03d}" for i in range(len(c))], y=-1, cls="unlabelled", stratum="", year=np.nan, x=c.x.values, y_m=c.y_m.values, beat=beat, ha=np.nan))
    pd.concat([L, new], ignore_index=True).to_csv(GT / "guna_cc_labels.csv", index=False)
    print("appended", len(new), "break median", round(c.t_max.median(), 2), "tree cover median", round(c.trees_mean.median(), 2))


if __name__ == "__main__":
    score() if sys.argv[1] == "score" else select()
