"""Second round of the Guna change/no-change model: local contrast against the surrounding 500 m, PCA of the change vector fitted inside each training fold, and label-set weights.
Compares by weighted AUC and by the precision reached at fixed recall on out-of-fold scores (the threshold is read off the curve here, so e78 confirms any winner with nested thresholds). Usage: e77_cc_local.py"""
import json
import sys
import warnings

import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.decomposition import PCA
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import StratifiedGroupKFold
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from e76_cc_train import FOLDS, REPORT, WORK, YS, load, ref_w, regional, step_feats, wpr

warnings.filterwarnings("ignore")
REPEATS = 5
BOX, WIDE = 50 ** 2, 500 ** 2
RECALLS = (.5, .7, .8, .9)


def wide(d):
    e = pd.DataFrame([json.loads(l) for l in open(WORK / "cc_emb_250.jsonl")]).drop_duplicates("cid").set_index("cid").reindex(d.cid)
    return np.stack([e[[f"y{y}_{i:02d}" for i in range(64)]].values for y in YS], axis=1).astype("float64")


def blocks(A, W):
    """Feature blocks: scalars, and 64-d vectors reduced by PCA inside the fold."""
    ring = (W * WIDE - A * BOX) / (WIDE - BOX)
    s, pre, post = step_feats(A)
    ls, lpre, lpost = step_feats(A - ring)
    return {"step": s.values, "local step": ls.values, "change": post - pre, "local change": lpost - lpre, "before": pre, "after": post}


def design(B, parts):
    """Stack the blocks; returns the matrix and which columns get PCA."""
    cols, slices, at = [], {}, 0
    for p in parts:
        cols.append(B[p])
        slices[p] = list(range(at, at + B[p].shape[1]))
        at += B[p].shape[1]
    scal = [i for p in parts if "step" in p for i in slices[p]]
    vec = [slices[p] for p in parts if "step" not in p]
    return np.hstack(cols), scal, vec


def make(kind, scal, vec, k):
    tf = [("scalars", StandardScaler(), scal)] + [(f"pca{i}", make_pipeline(StandardScaler(), PCA(k, random_state=0)), v) for i, v in enumerate(vec)]
    head = LogisticRegression(C=.05, max_iter=3000, class_weight="balanced") if kind == "logistic" else HistGradientBoostingClassifier(max_depth=3, learning_rate=.05, max_iter=150, min_samples_leaf=15, l2_regularization=2.0, class_weight="balanced", random_state=1)
    return make_pipeline(ColumnTransformer(tf), head)


def set_weights(d, how):
    """'equal': each label set carries the same total weight per class, so the 170 easy Bamori polygons cannot outvote the reference."""
    if how == "none":
        return np.ones(len(d))
    w = np.zeros(len(d))
    for (_, y), g in d[d.y >= 0].groupby(["set", "y"]):
        w[g.index] = 1 / len(g) if how == "equal" else 1 / np.sqrt(len(g))
    return w / w[d.y.values >= 0].mean()


def oof(X, d, kind, scal, vec, k, sw):
    y, g = d.y.values, d.block.values
    use = np.flatnonzero(y >= 0)
    S = np.full((REPEATS, len(d)), np.nan)
    for rep in range(REPEATS):
        for a, b in StratifiedGroupKFold(FOLDS, shuffle=True, random_state=rep).split(use, y[use], g[use]):
            tr, te = use[a], use[b]
            m = make(kind, scal, vec, k)
            m.fit(X[tr], y[tr], **{m.steps[-1][0] + "__sample_weight": sw[tr]})
            S[rep, te] = m.predict_proba(X[te])[:, 1]
    return S


def curve(s, y, w):
    """Precision at the first score where weighted recall reaches each target."""
    o = np.argsort(-s)
    tp, fp = np.cumsum((w * y)[o]), np.cumsum((w * (1 - y))[o])
    r, p = tp / tp[-1], tp / np.maximum(tp + fp, 1e-9)
    return {f"P@R{int(t * 100)}": round(float(p[np.searchsorted(r, t)]), 3) for t in RECALLS}


def evaluate(d, S):
    k = (d.set == "reference").values
    y, w = d.y.values[k], ref_w(d)[k]
    rows = {}
    rows["auc"] = round(float(np.mean([roc_auc_score(y, s[k], sample_weight=w) for s in S])), 3)
    bg, fl = (d.stratum.values[k] == "background"), (d.stratum.values[k] == "flagged")
    rows["auc_bg"] = round(float(np.mean([roc_auc_score(y[bg], s[k][bg]) for s in S])), 3)
    rows["auc_fl"] = round(float(np.mean([roc_auc_score(y[fl], s[k][fl]) for s in S])), 3)
    q = [curve(s[k], y, w) for s in S]
    for c in q[0]:
        rows[c] = round(float(np.mean([a[c] for a in q])), 3)
        rows[c + "_sd"] = round(float(np.std([a[c] for a in q])), 3)
    fp = (d.set == "bamori_fp").values
    tp = (d.set == "bamori_tp").values & (d.y.values == 1)
    rows["bamori_auc"] = round(float(np.mean([roc_auc_score(np.r_[np.ones(tp.sum()), np.zeros(fp.sum())], np.r_[s[tp], s[fp]]) for s in S])), 3)
    return rows


def main():
    d, A = load()
    W = wide(d)
    B = blocks(regional(A, d), regional(W, d))
    res = []
    grid = [(("step",), None), (("step", "local step"), None), (("local step",), None), (("step", "local step", "change"), 8), (("step", "local step", "local change"), 8),
            (("step", "local step", "change", "local change"), 8), (("step", "local step", "before", "after"), 8), (("step", "local step", "change", "before", "after"), 8), (("step", "local step", "change", "before", "after"), 16)]
    for parts, k in grid:
        X, scal, vec = design(B, parts)
        for kind in ("logistic", "hgb"):
            for how in ("none", "sqrt", "equal"):
                row = dict(parts="+".join(parts), k=k, model=kind, weights=how, **evaluate(d, oof(X, d, kind, scal, vec, k, set_weights(d, how))))
                res.append(row)
                print(json.dumps(row), flush=True)
    t = pd.DataFrame(res).sort_values("auc", ascending=False)
    t.to_csv(REPORT / "cc_local_grid.csv", index=False)
    pd.set_option("display.width", 300, "display.max_columns", 30)
    print(t[[c for c in t if not c.endswith("_sd")]].head(25).to_string())


if __name__ == "__main__":
    main()
