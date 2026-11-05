"""Diagnosis: is the near-zero recall on the Guna labels an alignment bug, the rules, or no signal at these points?"""
import json

import numpy as np
import pandas as pd
import rasterio
from sklearn.metrics import average_precision_score, roc_auc_score

import anomalies
from common import *
from e8_classify import YEARS8, tree_at

GT = ROOT / "ground_truth"
df = pd.read_csv(GT / "guna_labels.csv")
c = np.load(WORK / "classified.npz")
with rasterio.open(WORK / "zone_beat.tif") as s:
    zb = s.read(1)
b = pd.read_csv(OUT / "beat_lookup.csv")
ids = b.loc[b.Division == "Guna", "zone_id"].values
mask = np.isin(zb, ids)
print("Guna division forest ha", round(mask.sum() * PX_HA), "mapped main ha", round((mask & c["cls"] > 0).sum() * PX_HA), "mapped clearing+partial ha", round(((c["cls"] == 1) | (c["cls"] == 2))[mask].sum() * PX_HA))
water = np.load(WORK / "water.npy")
print("label points in water mask", df.groupby("source").apply(lambda g: round(float(water[g.row, g.col].mean()), 3)).to_dict())
t = pd.read_csv(WORK / "tiles.csv", keep_default_na=False)
off, names0 = anomalies.load("v3")
rows = []
for s in t.itertuples():
    i = df.index[(df.row >= s.row) & (df.row < s.row + s.h) & (df.col >= s.col) & (df.col < s.col + s.w)]
    if not len(i):
        continue
    with rasterio.open(WORK / "emb_v3" / f"{s.tile}.tif") as src:
        names = list(src.descriptions)
        arr = src.read() - anomalies.tile_offset(off, s)
    zi = [k for k, n in enumerate(names) if n.startswith("z")]
    ti = [k for k, n in enumerate(names) if n.startswith("tree")]
    z, tr = arr[zi], arr[ti]
    yod = np.array(YEARS8)[z.argmax(0)]
    pre, post = tree_at(tr, yod, (-2, -1)).astype("int32"), tree_at(tr, yod, (1, 2)).astype("int32")
    top, drop = z.max(0), pre - post
    # the best 3x3 value near the point, to allow for location error
    for k in i:
        r, cc = df.row[k] - s.row, df.col[k] - s.col
        rr = np.clip([r - 1, r + 2], 0, top.shape[0])
        rc = np.clip([cc - 1, cc + 2], 0, top.shape[1])
        rows.append(dict(gid=df.gid[k], z=top[r, cc] / 1000, z3=top[rr[0]:rr[1], rc[0]:rc[1]].max() / 1000, drop=drop[r, cc] / 1e4,
                         drop3=drop[rr[0]:rr[1], rc[0]:rc[1]].max() / 1e4, pre=pre[r, cc] / 1e4, yod=yod[r, cc]))
    print("tile", s.tile, "forest z p50/p90/p99", np.percentile(top[zb[s.row:s.row + s.h, s.col:s.col + s.w] > 0], [50, 90, 99]).round(0).tolist(), flush=True)
d = df.merge(pd.DataFrame(rows), on="gid")
d.to_csv(GT / "guna_scores_v3.csv", index=False)
ref = d[d.source == "blind_reference"]
print("reference z quantiles by label", ref.groupby("label").z.quantile([.1, .5, .9]).round(2).to_dict())
print("reference drop by label", ref.groupby("label")["drop"].quantile([.1, .5, .9]).round(2).to_dict())
print("AUC score", round(roc_auc_score(ref.label, ref.z), 3), "z3", round(roc_auc_score(ref.label, ref.z3), 3), "drop", round(roc_auc_score(ref.label, ref["drop"]), 3), "AP", round(average_precision_score(ref.label, ref.z), 3), "base", round(ref.label.mean(), 3))
print("within flagged stratum AUC", round(roc_auc_score(ref[ref.stratum == "flagged"].label, ref[ref.stratum == "flagged"].z), 3))
th = json.load(open("thresholds_emb.json"))
print("core rule pass at point", int(((ref.z >= th["core_z"]) & (ref["drop"] >= th["core_tree_drop"])).sum()), "real among", int((((ref.z >= th["core_z"]) & (ref["drop"] >= th["core_tree_drop"])) & (ref.label == 1)).sum()))
for src, g in d[d.source != "blind_reference"].groupby("source"):
    print(src, "z p50", round(g.z.median(), 2), "pass core", round(float(((g.z >= th["core_z"]) & (g["drop"] >= th["core_tree_drop"])).mean()), 3))
print("area of real reference points in map", ref.groupby("label")[["z", "drop", "pre"]].median().round(2).to_dict())
