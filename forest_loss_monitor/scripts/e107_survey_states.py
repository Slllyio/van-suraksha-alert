"""Survey-calibrated state models C (LightGBM on HLS seasonal features, 2015) and B (MLP on AlphaEarth embeddings, 2017 embedding as the 2015 proxy).
Leave-one-range-out CV (8 folds): per-class accuracy and confusion per held-out range. Then a final model on all ranges is applied to every year 2017-2025
(HLS years z-matched per band to 2015 over all Guna beat pixels), giving yearly state rasters (1 forest, 2 open, 3 farm, 0 none) on the 30 m grid.
No tuning on test labels: fixed hyper-parameters, chosen before any scoring. Writes work/survey_model/states_{C,B}.npz and outputs/final/survey_model/cv_{C,B}.csv.
Usage: e107_survey_states.py C | B | Cc (C trained on cleaned labels, tested on the original labels)"""
import sys

import lightgbm as lgb
import numpy as np
import pandas as pd
from sklearn.metrics import confusion_matrix
from sklearn.neural_network import MLPClassifier
from sklearn.preprocessing import StandardScaler

from common import *
from e106_survey_data import NAMES, SM, emb, hls

OD = OUT / "final" / "survey_model"
YEARS = list(range(2017, 2026))
PER_CID_TRAIN, PER_CID_TEST = 150, 300
SEED = 7


def feats(a):
    """Per pixel features from an 18-band HLS stack: 6 bands x 3 seasons plus NDVI, NBR, BSI per season and seasonal differences."""
    x = a.astype("float32")
    x[a == -9999] = np.nan
    out = [x]
    idx = []
    for k in range(3):
        b2, b4, b5, b6, b7 = (x[6 * k + i] for i in (0, 2, 3, 4, 5))
        nd = (b5 - b4) / (b5 + b4)
        nbr = (b5 - b7) / (b5 + b7)
        bsi = ((b6 + b4) - (b5 + b2)) / ((b6 + b4) + (b5 + b2))
        idx += [nd, nbr, bsi]
    out.append(np.stack(idx))
    out.append(np.stack([idx[0] - idx[3], idx[6] - idx[3], idx[0] - idx[6]]))     # rabi-summer, post-summer, rabi-post NDVI
    return np.concatenate(out)


def zmatch(a, ref, m):
    """Match each band's mean/std over mask m to the reference year (2015)."""
    b = a.astype("float32").copy()
    for i in range(a.shape[0]):
        x, r = b[i][m & (a[i] != -9999)], ref[i][m & (ref[i] != -9999)].astype("float32")
        if len(x) and len(r):
            b[i] = np.where(a[i] == -9999, -9999, (b[i] - x.mean()) / (x.std() + 1e-6) * r.std() + r.mean())
    return b.round().astype("int16")


def sample(lab, cid, rng, n, seed):
    rs = np.random.default_rng(seed)
    r, c = np.nonzero(lab > 0)
    d = pd.DataFrame(dict(r=r, c=c, cid=cid[r, c]))
    d = d.groupby("cid", group_keys=False).apply(lambda q: q.sample(min(len(q), n), random_state=int(rs.integers(1e9))))
    return d.r.values, d.c.values


def model(kind):
    if kind in ("C", "Cc"):
        return lgb.LGBMClassifier(n_estimators=400, learning_rate=.05, num_leaves=63, subsample=.8, subsample_freq=1, colsample_bytree=.8, random_state=SEED, verbose=-1)
    return MLPClassifier(hidden_layer_sizes=(128, 64), early_stopping=True, max_iter=200, random_state=SEED)


def design(kind):
    """Returns a function giving the feature matrix for pixel rows/cols in a given year (None = the training/2015 year)."""
    if kind in ("C", "Cc"):
        F15 = feats(hls(2015))
        return lambda r, c, F=F15: F[:, r, c].T
    z = np.load(SM / "labels30.npz")["zone"]
    R, C, V = emb(2017, z)
    lut = -np.ones(z.shape, "int64")
    lut[R, C] = np.arange(len(R))
    def f(r, c):
        i = lut[r, c]
        out = np.full((len(r), 64), np.nan, "float32")
        out[i >= 0] = V[i[i >= 0]] / 127.
        return out
    return f


def cv(kind):
    L = np.load(SM / "labels30.npz")
    lab, cid, rng = L["lab"], L["cid"], L["rng"]
    ranges = pd.read_csv(SM / "ranges.csv", index_col=0).iloc[:, 0].to_dict()
    X = design(kind)
    ltr = np.load(SM / "clean_lab.npy") if kind == "Cc" else lab
    tr_r, tr_c = sample(ltr, cid, rng, PER_CID_TRAIN, SEED)
    te_r, te_c = sample(lab, cid, rng, PER_CID_TEST, SEED + 1)
    Xtr, ytr, gtr = X(tr_r, tr_c), ltr[tr_r, tr_c], rng[tr_r, tr_c]
    Xte, yte, gte = X(te_r, te_c), lab[te_r, te_c], rng[te_r, te_c]
    if kind == "B":
        ok = ~np.isnan(Xtr).any(1)
        Xtr, ytr, gtr = Xtr[ok], ytr[ok], gtr[ok]
        ok = ~np.isnan(Xte).any(1)
        Xte, yte, gte = Xte[ok], yte[ok], gte[ok]
    rows, pred = [], np.zeros(len(yte), "uint8")
    for g, nm in ranges.items():
        m = model(kind)
        if kind == "B":
            sc = StandardScaler().fit(Xtr[gtr != g])
            m.fit(sc.transform(Xtr[gtr != g]), ytr[gtr != g])
            p = m.predict(sc.transform(Xte[gte == g]))
        else:
            m.fit(Xtr[gtr != g], ytr[gtr != g])
            p = m.predict(Xte[gte == g])
        pred[gte == g] = p
        cm = confusion_matrix(yte[gte == g], p, labels=[1, 2, 3])
        rows.append(dict(held_out=nm, n=int((gte == g).sum()), overall=round(float((p == yte[gte == g]).mean()), 3),
                         **{f"recall_{NAMES[k]}": round(cm[k - 1, k - 1] / max(cm[k - 1].sum(), 1), 3) for k in (1, 2, 3)},
                         **{f"precision_{NAMES[k]}": round(cm[k - 1, k - 1] / max(cm[:, k - 1].sum(), 1), 3) for k in (1, 2, 3)},
                         confusion_rows_true_cols_pred=cm.tolist()))
    cm = confusion_matrix(yte, pred, labels=[1, 2, 3])
    rows.append(dict(held_out="ALL (pooled held-out)", n=len(yte), overall=round(float((pred == yte).mean()), 3),
                     **{f"recall_{NAMES[k]}": round(cm[k - 1, k - 1] / max(cm[k - 1].sum(), 1), 3) for k in (1, 2, 3)},
                     **{f"precision_{NAMES[k]}": round(cm[k - 1, k - 1] / max(cm[:, k - 1].sum(), 1), 3) for k in (1, 2, 3)}, confusion_rows_true_cols_pred=cm.tolist()))
    r = pd.DataFrame(rows)
    OD.mkdir(parents=True, exist_ok=True)
    r.to_csv(OD / f"cv_{kind}.csv", index=False)
    pd.set_option("display.width", 250)
    print(r.drop(columns="confusion_rows_true_cols_pred").to_string())
    print("pooled confusion (rows true forest/open/farm, cols predicted):\n", cm)
    # final model on all ranges
    m = model(kind)
    sc = None
    if kind == "B":
        sc = StandardScaler().fit(Xtr)
        m.fit(sc.transform(Xtr), ytr)
    else:
        m.fit(Xtr, ytr)
    return m, sc


def states(kind, m, sc):
    L = np.load(SM / "labels30.npz")
    zone = L["zone"]
    r, c = np.nonzero(zone > 0)
    out = {}
    if kind in ("C", "Cc"):
        ref = hls(2015)
        for y in [2015] + YEARS:
            a = ref if y == 2015 else zmatch(hls(y), ref, zone > 0)
            F = feats(a)[:, r, c].T
            s = np.zeros(zone.shape, "uint8")
            s[r, c] = m.predict(F)
            out[f"s{y}"] = s
            print(kind, y, {NAMES[k]: int((s == k).sum()) for k in (1, 2, 3)}, flush=True)
    else:
        for y in YEARS:
            R, C, V = emb(y, zone)
            s = np.zeros(zone.shape, "uint8")
            s[R, C] = m.predict(sc.transform(V / 127.))
            out[f"s{y}"] = s
            print(kind, y, {NAMES[k]: int((s == k).sum()) for k in (1, 2, 3)}, flush=True)
        out["s2015"] = out["s2017"]          # proxy: 2017 embedding stands for the 2015 state
    np.savez_compressed(SM / f"states_{kind}.npz", **out)


if __name__ == "__main__":
    k = sys.argv[1]
    states(k, *cv(k))
