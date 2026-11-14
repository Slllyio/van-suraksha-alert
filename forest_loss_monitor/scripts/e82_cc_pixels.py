"""Is the box mean hiding small losses? Embeddings of every 10 m pixel in the 50 m box at all change/no-change points: compares the strongest pixels with the box mean. One thread. Usage: e82_cc_pixels.py fetch | test"""
import json
import sys
import time

sys.path.insert(0, "E:/FIRE/forest_loss_monitor/scripts")

import ee
import numpy as np
import pandas as pd
from sklearn.metrics import roc_auc_score

from common import *
from e33_map10m import init_retry
from e75_cc_fetch import ORDER, stack
from e76_cc_train import GT, YS, load, ref_w, step_feats

F = WORK / "cc_emb_px.jsonl"
BATCH = 6


def fetch():
    init_retry()
    d = pd.read_csv(GT / "guna_cc_labels.csv")
    seen = {json.loads(l)["cid"] for l in open(F)} if F.exists() else set()
    d = d[~d.cid.isin(seen)].assign(o=lambda q: q.set.map(ORDER.index), ry=lambda q: (q.y_m // 10000).astype(int)).sort_values(["o", "ry", "x"])
    p = ee.Projection(WKT)
    with open(F, "a") as o:
        for i in range(0, len(d), BATCH):
            part = d.iloc[i:i + BATCH]
            fc = ee.FeatureCollection([ee.Feature(ee.Geometry.Rectangle([x - 25, y - 25, x + 25, y + 25], p, False), dict(cid=int(c))) for x, y, c in zip(part.x, part.y_m, part.cid)])
            for t in range(6):
                try:
                    for f in stack().reduceRegions(fc, ee.Reducer.toList(), crs=WKT, scale=10, tileScale=8).getInfo()["features"]:
                        o.write(json.dumps({k: [round(x, 3) for x in v] if isinstance(v, list) else v for k, v in f["properties"].items()}) + "\n")
                    break
                except Exception as e:
                    print("retry", str(e)[:120], flush=True)
                    time.sleep(20)
            o.flush()
            print(i + len(part), "of", len(d), flush=True)
    print("FINISHED")


def test():
    d, A = load()
    rnd = A[(d.set == "random").values].mean(axis=0)
    shift = rnd - rnd.mean(axis=0)
    box, _, _ = step_feats(A - shift)
    k = d.index[d.set == "reference"]
    w = pd.Series(ref_w(d), index=d.index)
    out = []
    for l in open(F):
        r = json.loads(l)
        cid = r.pop("cid")
        X = np.array([[r[f"y{y}_{i:02d}"] for i in range(64)] for y in YS]).transpose(2, 0, 1)
        X = X / np.linalg.norm(X, axis=2, keepdims=True) - shift
        s, _, _ = step_feats(X)
        out.append(dict(cid=cid, n=len(X), t_max=s.t.max(), t_q90=s.t.quantile(.9), t_q75=s.t.quantile(.75), t_med=s.t.median(), step_max=s.step.max(), step_q75=s.step.quantile(.75), step_med=s.step.median()))
    q = pd.DataFrame(out).merge(d[["cid", "y", "stratum", "id"]], on="cid").merge(pd.DataFrame(dict(cid=d.cid, box_t=box.t, box_step=box.step, w=w)), on="cid")
    bg, fl = q.stratum == "background", q.stratum == "flagged"
    for c in ("box_t", "box_step", "t_med", "t_q75", "t_q90", "t_max", "step_med", "step_q75", "step_max"):
        print(f"{c:10s} all {roc_auc_score(q.y, q[c], sample_weight=q.w):.3f} background {roc_auc_score(q.y[bg], q[c][bg]):.3f} flagged {roc_auc_score(q.y[fl], q[c][fl]):.3f}")
    n = q[bg & (q.y == 0)]
    print(q[bg & (q.y == 1)].assign(pct_t_q90=lambda z: [round(100 * (n.t_q90 < v).mean()) for v in z.t_q90], pct_box=lambda z: [round(100 * (n.box_t < v).mean()) for v in z.box_t])[["id", "n", "pct_box", "pct_t_q90"]].to_string())


if __name__ == "__main__":
    fetch() if sys.argv[1] == "fetch" else test()
