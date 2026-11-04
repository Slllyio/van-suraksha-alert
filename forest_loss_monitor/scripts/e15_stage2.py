"""Second-stage filter on mapped pixels: real loss vs farmland, mine, water or no change, using local embeddings at labelled points.
Trained on every labelled mapped point from calibration, extra chips and validation (these then cannot validate the final map).
Held-out tests: 30 km blocks and whole tiles. Usage: e15_stage2.py eval | fit"""
import json
import sys

import numpy as np
import pandas as pd
import rasterio
from sklearn.ensemble import RandomForestClassifier as RF
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score as ap, precision_recall_curve as prc
from sklearn.model_selection import GroupKFold, LeaveOneGroupOut
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from common import *
from e6_fetch_embeddings import EMB_DIR

LAST = 2025
F = OUT / "calibration_emb" / "stage2_points.parquet"
MODEL = ROOT / "scripts" / "model_stage2.json"


def all_points():
    parts = []
    for name, sub in (("calibration", "calib_labels.csv"), ("calibration_emb", "calib_labels.csv"), ("calibration_extra", "calib_labels.csv")):
        p = pd.read_csv(OUT / name / sub)[["sample_id", "x", "y", "map_year", "label"]].assign(src=name)
        parts.append(p)
    k = pd.read_csv(OUT / "validation" / "validation_key_DO_NOT_OPEN_BEFORE_LABELLING.csv")
    v = k.merge(pd.read_csv(OUT / "validation" / "prelabels.csv"), on="sample_id")[["sample_id", "x", "y", "map_year", "label", "stratum"]].assign(src="validation")
    d = pd.concat(parts + [v], ignore_index=True)
    return d[d.map_year.between(2018, LAST)].reset_index(drop=True)


def attach(d):
    """Embeddings and tree values read from the local files; no GEE."""
    t = pd.read_csv(WORK / "tiles.csv", keep_default_na=False)
    g = json.load(open(WORK / "grid.json"))
    with rasterio.open(WORK / "zone_beat.tif") as s:
        full = s.read(1)
    d = d.copy()
    d["col"] = ((d.x - g["x0"]) / RES).astype(int)
    d["row"] = ((g["y1"] - d.y) / RES).astype(int)
    cols = [f"{k}{i}" for k in "pcn" for i in range(64)]
    X = np.full((len(d), len(cols)), np.nan, "float32")
    tile = np.empty(len(d), object)
    for s in t.itertuples():
        i = np.flatnonzero((d.row >= s.row) & (d.row < s.row + s.h) & (d.col >= s.col) & (d.col < s.col + s.w))
        if not len(i):
            continue
        tile[i] = s.tile
        m = full[s.row:s.row + s.h, s.col:s.col + s.w] > 0
        idx = np.cumsum(m.ravel()).reshape(m.shape) - 1
        cache = {}
        for j in i:
            r, c, y = d.row[j] - s.row, d.col[j] - s.col, int(d.map_year[j])
            if not m[r, c]:
                continue
            for b, yy in enumerate((y - 1, y, min(y + 1, LAST))):
                if yy not in cache:
                    cache[yy] = np.load(EMB_DIR / f"{s.tile}_{yy}.npz")["vals"]
                X[j, b * 64:(b + 1) * 64] = cache[yy][idx[r, c]] / 127
    out = pd.concat([d.assign(tile=tile), pd.DataFrame(X, columns=cols)], axis=1).dropna(subset=["p0"]).reset_index(drop=True)
    out.to_parquet(F)
    return out


def design(m, kind):
    p, c, n = m[[f"p{i}" for i in range(64)]].values, m[[f"c{i}" for i in range(64)]].values, m[[f"n{i}" for i in range(64)]].values
    pn, pc = 1 - (p * n).sum(1, keepdims=True), 1 - (p * c).sum(1, keepdims=True)
    return {"change": np.hstack([c - p, n - p, pc, pn]), "base+change": np.hstack([p, c - p, n - p, pc, pn]), "base": p, "all": np.hstack([p, c, n, c - p, n - p, pc, pn])}[kind]


def logit():
    return make_pipeline(StandardScaler(), LogisticRegression(C=0.03, max_iter=4000, class_weight="balanced"))


def rf():
    return RF(600, min_samples_leaf=2, max_features="sqrt", class_weight="balanced", random_state=0, n_jobs=-1)


def cv(mk, X, y, splits):
    s = np.zeros(len(y))
    for a, b in splits:
        s[b] = mk().fit(X[a], y[a]).predict_proba(X[b])[:, 1]
    return s


def report(y, s, name, base=None):
    P, R, _ = prc(y, s)
    f = 2 * P * R / (P + R + 1e-9)
    i = int(np.argmax(f))
    print(f"{name:34s} AP {ap(y, s):.3f} F1 {f[i]:.2f} (P {P[i]:.2f} R {R[i]:.2f}) P@R.5 {P[R >= .5].max():.2f} P@R.7 {P[R >= .7].max():.2f} P@R.85 {P[R >= .85].max():.2f}")


def main():
    d = attach(all_points())
    y = d.label.isin(list("LD")).astype(int).values
    print(len(d), "points", int(y.sum()), "real", d.src.value_counts().to_dict(), "tiles", d.tile.nunique(), "base rate %.2f" % y.mean())
    blocks = (d.x // 30000).astype(int).astype(str) + "_" + (d.y // 30000).astype(int).astype(str)
    sp_blk = list(GroupKFold(5).split(d, y, blocks))
    sp_tile = list(GroupKFold(5).split(d, y, d.tile))
    v = (d.src == "validation").values
    for kind in ("change", "base", "base+change", "all"):
        X = design(d, kind)
        for mk, nm in ((logit, "logit"), (rf, "RF")):
            for sp, sn in ((sp_blk, "blocks"), (sp_tile, "tiles")):
                s = cv(mk, X, y, sp)
                report(y, s, f"{kind} {nm} {sn}")
                if v.sum() and sn == "tiles":
                    report(y[v], s[v], f"   only validation pts ({v.sum()})")


if __name__ == "__main__":
    main()
