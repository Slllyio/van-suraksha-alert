"""Change/no-change classifier on AlphaEarth 2017-2025 at Guna points. Spatially blocked, repeated CV; thresholds come only from inner folds of the training blocks.
Scores the owner's blind reference with the same area weights as the rule, so the numbers compare directly. Usage: e76_cc_train.py"""
import json
import sys
import warnings

sys.path.insert(0, "E:/FIRE/forest_loss_monitor/scripts")

import numpy as np
import pandas as pd
from sklearn.ensemble import ExtraTreesClassifier, HistGradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import StratifiedGroupKFold
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from common import *
from e23_guna_labels import A_H, wpr

warnings.filterwarnings("ignore")
GT = ROOT / "ground_truth"
REPORT = OUT / "interim" / "report"
YS = list(range(2017, 2026))
BLOCK_M = 5000
REPEATS, FOLDS = 10, 5
TARGETS = (.90, .70)
SETS_SHOWN = ("felling", "recall_kit", "recent_new", "bamori_tp", "bamori_fp")


def load():
    d = pd.read_csv(GT / "guna_cc_labels.csv", keep_default_na=False, na_values=[""])
    e = pd.DataFrame([json.loads(l) for l in open(WORK / "cc_emb.jsonl")]).drop_duplicates("cid").set_index("cid").reindex(d.cid)
    A = np.stack([e[[f"y{y}_{i:02d}" for i in range(64)]].values for y in YS], axis=1).astype("float64")
    ok = ~np.isnan(A).any(axis=(1, 2))
    print("points", len(d), "with all years", int(ok.sum()), flush=True)
    d = d[ok].reset_index(drop=True)
    A = A[ok]
    A /= np.linalg.norm(A, axis=2, keepdims=True)
    d["block"] = (d.x // BLOCK_M).astype(int).astype(str) + "_" + (d.y_m // BLOCK_M).astype(int).astype(str)
    return d, A


def regional(A, d):
    """Remove the year-wide shift (rain, sensors), measured on random forest points only, so no label is involved."""
    m = A[(d.set == "random").values].mean(axis=0)
    return A - (m - m.mean(axis=0))


def step_feats(A):
    """Best single break in each series: no event date is needed, here or on a map."""
    n, T, _ = A.shape
    best = np.full(n, -np.inf)
    out = {k: np.zeros(n) for k in ("step", "t", "brk", "noise", "cos", "jump", "persist")}
    pre_b, post_b = np.zeros((n, 64)), np.zeros((n, 64))
    for b in range(1, T):
        pre, post = A[:, :b].mean(axis=1), A[:, b:].mean(axis=1)
        sse = ((A[:, :b] - pre[:, None]) ** 2).sum(axis=(1, 2)) + ((A[:, b:] - post[:, None]) ** 2).sum(axis=(1, 2))
        noise = np.sqrt(sse / max(T - 2, 1))
        step = np.linalg.norm(post - pre, axis=1)
        t = step / (noise + .01) * np.sqrt(b * (T - b) / T)
        u = t > best
        best[u] = t[u]
        out["step"][u], out["t"][u], out["brk"][u], out["noise"][u] = step[u], t[u], b, noise[u]
        out["cos"][u] = ((pre * post).sum(axis=1) / (np.linalg.norm(pre, axis=1) * np.linalg.norm(post, axis=1)))[u]
        out["jump"][u] = np.linalg.norm(A[:, b] - A[:, b - 1], axis=1)[u]
        out["persist"][u] = np.linalg.norm(A[:, -1] - pre, axis=1)[u]
        pre_b[u], post_b[u] = pre[u], post[u]
    out["pp1"] = np.linalg.norm(A[:, 5:8].mean(axis=1) - A[:, :3].mean(axis=1), axis=1)
    out["pp2"] = np.linalg.norm(A[:, 6:9].mean(axis=1) - A[:, :3].mean(axis=1), axis=1)
    for j in range(1, T):
        out[f"j{YS[j]}"] = np.linalg.norm(A[:, j] - A[:, j - 1], axis=1)
    return pd.DataFrame(out), pre_b, post_b


def views(A):
    s, pre, post = step_feats(A)
    fixed = A[:, 5:8].mean(axis=1) - A[:, :3].mean(axis=1)
    return {"step only": s.values,
            "step + change vector": np.c_[s.values, post - pre],
            "step + before + after": np.c_[s.values, pre, post],
            "fixed windows": np.c_[np.linalg.norm(fixed, axis=1), fixed, A[:, :3].mean(axis=1), A[:, 5:8].mean(axis=1)]}


MODELS = {"logistic": lambda: make_pipeline(StandardScaler(), LogisticRegression(C=.05, max_iter=3000, class_weight="balanced")),
          "extra trees": lambda: ExtraTreesClassifier(300, min_samples_leaf=3, max_features="sqrt", class_weight="balanced", n_jobs=-1, random_state=1),
          "gradient boosting": lambda: HistGradientBoostingClassifier(max_depth=3, learning_rate=.05, max_iter=200, min_samples_leaf=10, l2_regularization=2.0, class_weight="balanced", random_state=1)}


def ref_w(d):
    n = d[d.set == "reference"].stratum.value_counts()
    return np.where(d.set == "reference", d.stratum.map(lambda s: A_H.get(s, 0) / n.get(s, 1)), 0.)


def thr_for(s, y, w, tg):
    """Highest threshold that still reaches the recall target on these scores."""
    o = np.argsort(-s)
    r = np.cumsum((w * y)[o]) / max((w * y).sum(), 1e-9)
    return s[o][min(int(np.searchsorted(r, tg)), len(s) - 1)]


def cv(X, d, train_mask, model, rep):
    """Out-of-fold score plus flags per recall target. Evaluated points are never trained on, nor is anything in their blocks."""
    y, w, g = d.y.values, ref_w(d), d.block.values
    use = np.flatnonzero(y >= 0)
    s = np.full(len(d), np.nan)
    flags = {t: np.zeros(len(d), bool) for t in TARGETS}
    for a, b in StratifiedGroupKFold(FOLDS, shuffle=True, random_state=rep).split(use, y[use], g[use]):
        tr, te = use[a], use[b]
        tr = tr[train_mask[tr]]
        s[te] = model().fit(X[tr], y[tr]).predict_proba(X[te])[:, 1]
        inner = np.full(len(tr), np.nan)
        for c, e in StratifiedGroupKFold(3, shuffle=True, random_state=rep).split(tr, y[tr], g[tr]):
            inner[e] = model().fit(X[tr[c]], y[tr[c]]).predict_proba(X[tr[e]])[:, 1]
        ri = d.set.values[tr] == "reference"
        for t in TARGETS:
            flags[t][te] = s[te] >= thr_for(inner[ri], y[tr][ri], w[tr][ri], t)
    return s, flags


def score(d, f):
    y = d.y.values
    k = (d.set == "reference").values
    p, r = wpr(y[k], f[k].astype(int), ref_w(d)[k])
    bg = k & (d.stratum == "background").values & (y == 1)
    fl = k & (d.stratum == "flagged").values & (y == 1)
    o = dict(precision=p, recall=r, flagged=int(f[k].sum()), real=int((f[k] & (y[k] == 1)).sum()), of_49=int(f[fl].sum()), of_6=int(f[bg].sum()), random_rate=f[(d.set == "random").values].mean())
    for st in SETS_SHOWN:
        q = (d.set == st).values
        o[st] = f"{int(f[q & (y == 1)].sum())}/{int((q & (y == 1)).sum())}+{int(f[q & (y == 0)].sum())}/{int((q & (y == 0)).sum())}"
    return o


def main():
    d, A = load()
    print(d.groupby(["set", "y"]).size().unstack(fill_value=0).to_string())
    print("blocks", d.block.nunique())
    corrected = regional(A, d)
    masks = {"everything": np.ones(len(d), bool),
             "no random": (d.set != "random").values,
             "no Bamori false alarms": (d.set != "bamori_fp").values,
             "no Bamori at all": ~d.set.isin(["bamori_tp", "bamori_fp"]).values,
             "earlier mix": ~d.set.isin(["bamori_fp", "random"]).values}
    rows = []

    def run(tag, X, model_name, mask):
        out = [cv(X, d, mask, MODELS[model_name], r) for r in range(REPEATS)]
        for t in TARGETS:
            sc = [score(d, o[1][t]) for o in out]
            row = dict(tag, model=model_name, target=t, **{a: round(float(np.nanmean([q[a] for q in sc])), 3) for a in ("precision", "recall", "flagged", "real", "of_49", "of_6", "random_rate")})
            row["p_sd"], row["r_sd"] = round(float(np.nanstd([q["precision"] for q in sc])), 3), round(float(np.std([q["recall"] for q in sc])), 3)
            row.update({st: sc[0][st] for st in SETS_SHOWN})
            rows.append(row)
            print(json.dumps(row), flush=True)
    V = views(corrected)
    for vn, X in V.items():
        for mn in MODELS:
            run(dict(view=vn, train="everything", shift="removed"), X, mn, masks["everything"])
    for sn, m in masks.items():
        if sn != "everything":
            run(dict(view="step + change vector", train=sn, shift="removed"), V["step + change vector"], "extra trees", m)
    run(dict(view="step + change vector", train="everything", shift="kept"), views(A)["step + change vector"], "extra trees", masks["everything"])
    t = pd.DataFrame(rows)
    t.to_csv(REPORT / "cc_model_grid.csv", index=False)
    pd.set_option("display.width", 300, "display.max_columns", 30)
    print(t.drop(columns=["p_sd", "r_sd"]).to_string())


if __name__ == "__main__":
    main()
