"""Does knowing how a pixel of this kind normally behaves help? From 2,000 unlabelled Guna forest pixels: how unusual is this point's change among pixels that looked like it in 2017-19 (nearest neighbours),
how far it ends from where a ridge model expected, and Mahalanobis distance of the change vector under the pool's covariance. Also tests the pool as extra negatives. Usage: e81_cc_conditional.py"""
import json
import sys
import warnings

sys.path.insert(0, "E:/FIRE/forest_loss_monitor/scripts")

import numpy as np
import pandas as pd
from sklearn.covariance import LedoitWolf
from sklearn.linear_model import Ridge
from sklearn.metrics import roc_auc_score
from sklearn.neighbors import NearestNeighbors

from common import *
from e76_cc_train import REPORT, YS, load, ref_w, step_feats
from e77_cc_local import BOX, WIDE, design, evaluate, oof, set_weights, wide

warnings.filterwarnings("ignore")
K = 100
Z = ("step", "t", "jump", "persist", "pp2")


def pool(half):
    e = pd.DataFrame([json.loads(l) for l in open(WORK / f"cc_pool_{half}.jsonl")]).drop_duplicates("cid").set_index("cid").sort_index()
    return e, np.stack([e[[f"y{y}_{i:02d}" for i in range(64)]].values for y in YS], axis=1).astype("float64")


def cond(A, L, Pa, Pl):
    """Each point against pool pixels with a similar 2017-19 state. A point never counts as its own neighbour because labelled points are not in the pool."""
    sa, _, post_a = step_feats(A)
    sl, _, _ = step_feats(L)
    spa, _, _ = step_feats(Pa)
    spl, _, _ = step_feats(Pl)
    st, stp = A[:, :3].mean(axis=1), Pa[:, :3].mean(axis=1)
    idx = NearestNeighbors(n_neighbors=K).fit(stp).kneighbors(st, return_distance=False)
    out = {}
    for nm, s, sp in (("box", sa, spa), ("local", sl, spl)):
        for c in Z:
            v = sp[c].values[idx]
            med = np.median(v, axis=1)
            out[f"z_{nm}_{c}"] = (s[c].values - med) / (1.4826 * np.median(np.abs(v - med[:, None]), axis=1) + 1e-3)
            out[f"pct_{nm}_{c}"] = (v < s[c].values[:, None]).mean(axis=1)
    end, endp = A[:, 6:9].mean(axis=1), Pa[:, 6:9].mean(axis=1)
    r = Ridge(1.0).fit(stp, endp)
    res = end - r.predict(st)
    out["ridge_resid"] = np.linalg.norm(res, axis=1)
    lc = L[:, 6:9].mean(axis=1) - L[:, :3].mean(axis=1)
    lcp = Pl[:, 6:9].mean(axis=1) - Pl[:, :3].mean(axis=1)
    cov = LedoitWolf().fit(lcp)
    out["mahal_local"] = np.sqrt(cov.mahalanobis(lc))
    cov2 = LedoitWolf().fit(endp - stp)
    out["mahal_box"] = np.sqrt(cov2.mahalanobis(end - st))
    return pd.DataFrame(out), sa, sl


def main():
    d, A = load()
    W = wide(d)
    e25, Pa = pool(25)
    e250, Pw = pool(250)
    common = e25.index.intersection(e250.index)
    Pa, Pw = Pa[e25.index.get_indexer(common)], Pw[e250.index.get_indexer(common)]
    keep = ~(np.isnan(Pa).any(axis=(1, 2)) | np.isnan(Pw).any(axis=(1, 2)))
    Pa, Pw = Pa[keep], Pw[keep]
    print("pool", len(Pa))
    Pa /= np.linalg.norm(Pa, axis=2, keepdims=True)
    shift_a, shift_w = Pa.mean(axis=0), Pw.mean(axis=0)
    fix = lambda X, m: X - (m - m.mean(axis=0))
    A1, W1, Pa1, Pw1 = fix(A, shift_a), fix(W, shift_w), fix(Pa, shift_a), fix(Pw, shift_w)
    ring = lambda a, w: a - (w * WIDE - a * BOX) / (WIDE - BOX)
    L, Pl = ring(A1, W1), ring(Pa1, Pw1)
    C, sa, sl = cond(A1, L, Pa1, Pl)
    k = (d.set == "reference").values
    y, w = d.y.values[k], ref_w(d)[k]
    bg, fl = d.stratum.values[k] == "background", d.stratum.values[k] == "flagged"
    u = []
    for c in list(C.columns) + ["pre_only"]:
        v = C[c].values[k] if c != "pre_only" else sa.pp2.values[k]
        u.append(dict(feature=c if c != "pre_only" else "plain pp2", auc=round(roc_auc_score(y, v, sample_weight=w), 3), auc_bg=round(roc_auc_score(y[bg], v[bg]), 3), auc_fl=round(roc_auc_score(y[fl], v[fl]), 3)))
    print(pd.DataFrame(u).sort_values("auc", ascending=False).head(14).to_string())
    B = dict(step=sa.values, local=sl.values, cond=C.values)
    B["local step"], B["cond step"] = B.pop("local"), B.pop("cond")
    res = []
    for parts in (("step", "local step"), ("cond step",), ("step", "local step", "cond step")):
        X, scal, vec = design(B, parts)
        for kind in ("logistic", "hgb"):
            row = dict(parts="+".join(parts), model=kind, **evaluate(d, oof(X, d, kind, scal, vec, None, set_weights(d, "none"))))
            res.append(row)
            print(json.dumps(row), flush=True)
    pd.DataFrame(res).to_csv(REPORT / "cc_conditional.csv", index=False)
    pd.DataFrame(u).to_csv(REPORT / "cc_conditional_features.csv", index=False)


if __name__ == "__main__":
    main()
