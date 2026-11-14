"""Old-field filter, round 2: retrain with the blind-labelled MP spots (e116) next to the Guna 2015 survey samples (e114), and test simple fixes on the spots before remapping.
Spot labels: A (already a field in 2017) = old field 1; F, C, N = 0; U skipped. Checks are leave-one-division-out, so a division's spots never tune its own filter.
Usage: e117_oldfield2.py sample | fit | fetch <Division> | tables <Division>"""
import io
import json
import sys
import time

sys.path.insert(0, "E:/FIRE/forest_loss_monitor/scripts")
ARGS = sys.argv[1:]
sys.argv = sys.argv[:1]

import ee
import geopandas as gpd
import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score
from shapely.geometry import box

from common import *
from e33_map10m import init_retry
from e105_cc_cropmask import retry
from e114_oldfield import DER, E, LS, S as GUNA_S, derived, features

DIVS = ["Shivpuri", "Sheopur", "Sehore", "Vidisha"]
GT = ROOT / "ground_truth"
SP = WORK / "oldfield2_spots.csv"
M2 = WORK / "oldfield2_model.json"
MPD = WORK / "mp_newfarm"
COLS = E + LS + DER
W_SPOT = 20                     # each labelled MP spot counts as 20 Guna survey samples


def spots():
    parts = []
    for d in DIVS:
        k = pd.read_csv(GT / f"mp_blind_{d}_key_DO_NOT_OPEN_BEFORE_LABELLING.csv").merge(pd.read_csv(GT / f"mp_blind_{d}_labels.csv"), on="code")
        parts.append(k.assign(div=d))
    k = pd.concat(parts, ignore_index=True)
    return k[k.label != "U"].assign(old=lambda q: (q.label == "A").astype(int))


def crop_at(k):
    """Crop probability 2017-25 and old-field probability already downloaded for the map, at each spot."""
    out = []
    for d, q in k.groupby("div"):
        g = json.load(open(MPD / d / "grid.json"))
        tiles = {f.stem: np.load(f) for f in (MPD / d).glob("*_*.npy") if f.stem[0].isdigit()}
        for r in q.itertuples():
            i, j = int((g["y1"] - r.y_m) // 30), int((r.x - g["x0"]) // 30)
            a = tiles[f"{i // 256 * 256}_{j // 256 * 256}"]
            out.append(dict(idx=r.Index, **{f"p{n}": a[n, i % 256, j % 256] / 200 for n in range(10)}))
    return pd.DataFrame(out).set_index("idx")


def sample():
    init_retry()
    k = spots()
    img = features()
    proj = ee.Projection(WKT)
    fc = ee.FeatureCollection([ee.Feature(ee.Geometry.Point([x, y], proj), dict(i=int(n))) for n, x, y in zip(k.index, k.x, k.y_m)])
    rows = [f["properties"] for f in retry(lambda: img.sampleRegions(fc, scale=30, tileScale=4).getInfo())["features"]]
    f = pd.DataFrame(rows).set_index("i")
    k.join(f).join(crop_at(k)).to_csv(SP)
    print(len(k), "spots sampled")


def fit():
    k = derived(pd.read_csv(SP, index_col=0).dropna(subset=E))
    g = derived(pd.read_csv(GUNA_S).dropna(subset=E))
    print("spots", len(k), k.groupby(["div", "label"]).size().unstack(fill_value=0).to_string())
    print("old model on spots: AUC", round(roc_auc_score(k.old, k.p9), 3))
    pr = pd.Series(np.nan, index=k.index)
    for d in DIVS:
        tr, te = k[k["div"] != d], k[k["div"] == d]
        X = pd.concat([g[COLS], tr[COLS]]).fillna(-1).values
        y = np.r_[g.old.values, tr.old.values]
        w = np.r_[np.ones(len(g)), np.full(len(tr), W_SPOT)]
        pr[te.index] = LogisticRegression(C=1.0, max_iter=5000).fit(X, y, sample_weight=w).predict_proba(te[COLS].fillna(-1).values)[:, 1]
    k["p_new"] = pr
    k["crop_before_max"] = k[["p0", "p1", "p2"]].max(axis=1)
    print("new model on spots, leave-one-division-out: AUC", round(roc_auc_score(k.old, k.p_new), 3), "| 2017-19 max crop prob: AUC", round(roc_auc_score(k.old, k.crop_before_max), 3))

    def score(drop, name):
        kept = ~drop
        w = k.label.map(dict(F=1, C=0, N=0, A=0))
        print(f"{name:42s} removes {drop[k.label == 'A'].mean():.0%} of already-fields, {drop[k.label == 'N'].mean():.0%} of no-field, keeps {kept[k.label == 'F'].mean():.0%} of new fields | precision of kept {(w[kept]).mean():.0%}")

    score(pd.Series(False, index=k.index), "current map")
    for t in (.3, .4, .5, .6):
        score(k.p_new >= t, f"retrained filter, threshold {t}")
    for t in (.3, .4):
        score(k.crop_before_max >= t, f"2017-19 crop prob max >= {t}")
        score((k.crop_before_max >= t) | (k.p_new >= .5), f"both (crop {t} or retrained .5)")
    X = pd.concat([g[COLS], k[COLS]]).fillna(-1).values
    y = np.r_[g.old.values, k.old.values]
    w = np.r_[np.ones(len(g)), np.full(len(k), W_SPOT)]
    m = LogisticRegression(C=1.0, max_iter=5000).fit(X, y, sample_weight=w)
    json.dump(dict(bands=COLS, coef=m.coef_[0].tolist(), intercept=float(m.intercept_[0])), open(M2, "w"))
    k.to_csv(SP)


if __name__ == "__main__":
    dict(sample=sample, fit=fit)[ARGS[0]]()
