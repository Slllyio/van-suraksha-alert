"""Do Sentinel-1 and dry-season Sentinel-2 see the losses that Oct-Nov greenness misses? Per series: best single break (fall, and change of either sign), year-wide shift removed on random points.
Reports each feature's AUC on the reference, where the 6 background losses rank, and the second stage with and without the new signals (same 5 km blocks, nested thresholds). Usage: e89_cc_second.py"""
import json
import sys
import warnings

sys.path.insert(0, "E:/FIRE/forest_loss_monitor/scripts")

import numpy as np
import pandas as pd
from sklearn.metrics import roc_auc_score

from e49_ts import series_feats
from e63_cascade import feats, triggers
from e76_cc_train import REPORT, WORK, load, ref_w
from e77_cc_local import design, wide
from e79_cc_fusion import cv_view, flags_at, line, px_table
from e83_cc_pxmodel import px_features

warnings.filterwarnings("ignore")
REPEATS = 10
YS = list(range(2017, 2026))
SERIES = ("dry_vv", "dry_vh", "leaf_vv", "leaf_vh", "jf_n", "jf_r", "jf_m", "mm_n", "mm_r", "mm_m")


def breaks(v):
    """v: points x years. Best break with at least 2 seasons each side: t and size of the fall, and t of a change of either sign."""
    T = v.shape[1]
    out = {k: np.full(len(v), np.nan) for k in ("t_fall", "fall", "t_any")}
    best_f, best_a = np.full(len(v), -np.inf), np.full(len(v), -np.inf)
    with np.errstate(all="ignore"):
        for b in range(2, T - 1):
            pre, post = np.nanmean(v[:, :b], axis=1), np.nanmean(v[:, b:], axis=1)
            sse = np.nansum((v[:, :b] - pre[:, None]) ** 2, axis=1) + np.nansum((v[:, b:] - post[:, None]) ** 2, axis=1)
            n = np.isfinite(v).sum(axis=1)
            sd = np.sqrt(sse / np.maximum(n - 2, 1))
            t = (pre - post) / (sd + 1e-3 + .02 * np.nanstd(v)) * np.sqrt(b * (T - b) / T)
            u = np.isfinite(t) & (t > best_f)
            best_f[u], out["t_fall"][u], out["fall"][u] = t[u], t[u], (pre - post)[u]
            u = np.isfinite(t) & (np.abs(t) > best_a)
            best_a[u], out["t_any"][u] = np.abs(t[u]), np.abs(t[u])
    return out


def new_feats(d):
    e = pd.DataFrame([json.loads(l) for l in open(WORK / "cc_s1dry.jsonl")]).drop_duplicates("cid").set_index("cid").reindex(d.cid).replace(-99, np.nan)
    rnd = (d.set == "random").values
    S = {s: e[[f"{s}{y}" for y in YS]].values.astype(float) for s in SERIES}
    S["dry_ratio"], S["leaf_ratio"] = S["dry_vh"] - S["dry_vv"], S["leaf_vh"] - S["leaf_vv"]
    cols = {}
    for s, v in S.items():
        m = np.nanmedian(v[rnd], axis=0)
        v = v - (m - np.nanmean(m))
        for k, x in breaks(v).items():
            cols[f"{s}:{k}"] = x
    print("points with radar", int(np.isfinite(S["dry_vh"]).all(axis=1).sum()), "with dry-season S2 in all years", int(np.isfinite(S["mm_r"]).all(axis=1).sum()), "of", len(d))
    return pd.DataFrame(cols)


def main():
    d, A = load()
    N = new_feats(d)
    y, w = d.y.values, ref_w(d)
    k = (d.set == "reference").values
    bg, fl = k & (d.stratum == "background").values, k & (d.stratum == "flagged").values
    rows = []
    for c in N:
        v = N[c].fillna(N[c].median()).values
        rows.append(dict(feature=c, auc=round(roc_auc_score(y[k], v[k], sample_weight=w[k]), 3), auc_background=round(roc_auc_score(y[bg], v[bg]), 3), auc_flagged=round(roc_auc_score(y[fl], v[fl]), 3)))
    u = pd.DataFrame(rows).sort_values("auc_background", ascending=False)
    u.to_csv(REPORT / "cc_second_features.csv", index=False)
    print(u.head(16).to_string())
    top = u.feature.head(6).tolist()
    q = d.index[bg & (y == 1)]
    neg = bg & (y == 0)
    print(pd.DataFrame({"id": d.id[q], **{c: [round(100 * (N[c][neg] < N[c][i]).mean()) for i in q] for c in top}}).to_string())
    scal = px_features(d, A, wide(d))[0]
    X, sc, ve = design({"step": scal}, ("step",))
    emb = [cv_view(X, d, y, sc, ve, r) for r in range(REPEATS)]
    s1 = [flags_at(a, b, y, w, k, .9) for a, b in emb]
    p = px_table(d)
    sf = series_feats(p)
    Fx = feats(p, sf, triggers(p, sf)).reindex(d.cid).values
    views = {"time series": Fx, "radar + dry season": N.values, "time series + radar + dry season": np.c_[Fx, N.values], "radar only": N[[c for c in N if c.startswith(("dry_v", "leaf_v", "dry_ratio", "leaf_ratio"))]].values}
    res = [line("stage 1: embeddings at 0.9", d, np.mean(s1, axis=0) >= .5, y, w, k)]
    for nm, V in views.items():
        m = [cv_view(V, d, y, list(range(V.shape[1])), [], r) for r in range(REPEATS)]
        both = [((a + c) / 2, [(g[0], g[1], (g[2] + h[2]) / 2) for g, h in zip(b, f)]) for (a, b), (c, f) in zip(emb, m)]
        for tg in (.85, .8, .7, .6):
            res.append(line(f"stage 2 with {nm}, target {tg}", d, np.mean([flags_at(a, b, y, w, k, tg, g) for (a, b), g in zip(both, s1)], axis=0) >= .5, y, w, k))
    r = pd.DataFrame(res)
    r.to_csv(REPORT / "cc_second_stage.csv", index=False)
    pd.set_option("display.width", 320, "display.max_columns", 30, "display.max_colwidth", 70)
    print(r.to_string())


if __name__ == "__main__":
    main()
