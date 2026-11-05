"""Embedding model vs time-series model vs both, and a two-stage cascade: stage 1 catches at least the target recall, stage 2 removes false alarms. Same 5 km blocks, nested thresholds, same area weights as the rule.
Includes a shuffled-label control and the fate of each of the 6 background losses. Usage: e79_cc_fusion.py [repeats]"""
import json
import sys
import warnings

sys.path.insert(0, "E:/FIRE/forest_loss_monitor/scripts")

import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.decomposition import PCA
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import StratifiedGroupKFold
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from e76_cc_train import FOLDS, GT, REPORT, WORK, load, ref_w, regional, thr_for, wpr
from e77_cc_local import blocks, curve, design, wide

from e48_tests import F as PX_OLD, rule
from e49_ts import series_feats, ts_pass
from e63_cascade import NETS, feats, triggers
from e78_cc_px import F as PX_NEW, PID0

warnings.filterwarnings("ignore")
REPEATS = int(sys.argv[1]) if len(sys.argv) > 1 else 10
TARGETS = (.9, .8, .7, .5)
SEED = 20261106


def px_table(d):
    """Pixel table keyed by cid: earlier points through their old ids, new points through cid + PID0."""
    g = pd.read_csv(GT / "guna_labels.csv").assign(pid=lambda q: q.gid + 500000)
    src = {"reference": "blind_reference", "felling": "felling_alert_verdict", "bamori_tp": "bamori_validated"}
    old = {}
    for s, o in src.items():
        q = g[g.source == o].set_index("id").pid
        for c, i in d[d.set == s][["cid", "id"]].values:
            if i in q.index:
                old[int(q[i])] = int(c)
    rows = []
    for path, mapping in ((PX_OLD, old), (PX_NEW, None)):
        for l in open(path):
            r = json.loads(l)
            pid = r.pop("pid")
            cid = mapping.get(pid) if mapping is not None else pid - PID0
            n = max(len(v) for v in r.values())
            if cid is None or n == 0 or any(len(v) != n for v in r.values()):
                continue
            t = pd.DataFrame(r)
            t.insert(0, "pid", cid)
            rows.append(t)
    return pd.concat(rows, ignore_index=True).replace(-9, np.nan)


def fit_scores(X, y, sw, Xt, scal, vec):
    tf = [("s", make_pipeline(SimpleImputer(strategy="median"), StandardScaler()), scal)] + [(f"v{i}", make_pipeline(StandardScaler(), PCA(8, random_state=0)), v) for i, v in enumerate(vec)]
    m = make_pipeline(ColumnTransformer(tf), LogisticRegression(C=.05, max_iter=3000, class_weight="balanced"))
    m.fit(X, y)
    return m.decision_function(Xt)


def cv_view(X, d, y, scal, vec, rep):
    """Out-of-fold logit, plus the logit of inner folds of each training split, needed for nested thresholds."""
    g = d.block.values
    use = np.flatnonzero(y >= 0)
    s = np.full(len(d), np.nan)
    folds = []
    for a, b in StratifiedGroupKFold(FOLDS, shuffle=True, random_state=rep).split(use, y[use], g[use]):
        tr, te = use[a], use[b]
        s[te] = fit_scores(X[tr], y[tr], None, X[te], scal, vec)
        inner = np.full(len(tr), np.nan)
        for c, e in StratifiedGroupKFold(3, shuffle=True, random_state=rep).split(tr, y[tr], g[tr]):
            inner[e] = fit_scores(X[tr[c]], y[tr[c]], None, X[tr[e]], scal, vec)
        folds.append((tr, te, inner))
    return s, folds


def flags_at(s, folds, y, w, is_ref, tg, gate=None):
    """Threshold from inner scores of the training blocks only. With a gate, recall is counted after the gate."""
    f = np.zeros(len(y), bool)
    for tr, te, inner in folds:
        ri = is_ref[tr]
        sc = inner[ri] if gate is None else np.where(gate[tr][ri], inner[ri], -1e9)
        f[te] = s[te] >= thr_for(sc, y[tr][ri], w[tr][ri], tg)
    return f if gate is None else f & gate


def boot(d, f, n=500):
    """Whole beats resampled."""
    k = d[d.set == "reference"].index.values
    w, y, b = ref_w(d)[k], d.y.values[k], d.beat.values[k]
    rng = np.random.default_rng(SEED)
    idx = {x: np.flatnonzero(b == x) for x in np.unique(b)}
    P, R = [], []
    for _ in range(n):
        i = np.concatenate([idx[x] for x in rng.choice(list(idx), len(idx))])
        p, r = wpr(y[i], f[k][i].astype(int), w[i])
        if np.isfinite(p):
            P.append(p)
        R.append(r)
    return [round(float(np.quantile(P, q)), 2) for q in (.025, .975)], [round(float(np.quantile(R, q)), 2) for q in (.025, .975)]


def line(name, d, f, y, w, k):
    p, r = wpr(y[k], f[k].astype(int), w[k])
    ci = boot(d, f)
    fl, rn = (d.stratum == "flagged").values & (y == 1), (d.set == "random").values
    o = dict(method=name, precision=round(p, 3), p_ci=ci[0], recall=round(r, 3), r_ci=ci[1], flagged=int(f[k].sum()), real=int((f[k] & (y[k] == 1)).sum()), of_49=int(f[fl].sum()), of_6=int(f[(d.stratum == "background").values & (y == 1)].sum()), random_flag_pct=round(100 * f[rn].mean(), 1))
    for st in ("felling", "recall_kit", "recent_new", "bamori_tp", "bamori_fp"):
        q = (d.set == st).values
        o[st] = f"{int(f[q & (y == 1)].sum())}/{int((q & (y == 1)).sum())}+{int(f[q & (y == 0)].sum())}/{int((q & (y == 0)).sum())}"
    print(json.dumps(o), flush=True)
    return o


def main():
    d, A = load()
    B = blocks(regional(A, d), regional(wide(d), d))
    p = px_table(d)
    print("points with pixel table", p.pid.nunique(), "of", len(d), flush=True)
    sf = series_feats(p)
    t = triggers(p, sf)
    Fx = feats(p, sf, t).reindex(d.cid)
    net = t[NETS["+ scrub tight"]].any(axis=1).groupby(p.pid).any().reindex(d.cid).fillna(False).values
    base = (t["rule"] & ts_pass(sf, (.15, .15, 0, 9))).groupby(p.pid).sum().reindex(d.cid).fillna(0).ge(2).values
    y = d.y.values
    w = ref_w(d)
    is_ref = (d.set == "reference").values
    Xe, se, ve = design(B, ("step", "local step", "local change"))
    Xt = Fx.values
    st = list(range(Xt.shape[1]))
    res = [line("rule: filter + 2 px (no training)", d, base, y, w, is_ref), line("rule net, no filter (no training)", d, net, y, w, is_ref)]
    runs = []
    for rep in range(REPEATS):
        se_s, fo_e = cv_view(Xe, d, y, se, ve, rep)
        st_s, fo_t = cv_view(Xt, d, y, st, [], rep)
        runs.append((se_s, fo_e, st_s, fo_t))
        print("repeat", rep, flush=True)
    both = []
    for se_s, fo_e, st_s, fo_t in runs:
        fus = (se_s + st_s) / 2
        fo = [(a[0], a[1], (a[2] + b[2]) / 2) for a, b in zip(fo_e, fo_t)]
        both.append((fus, fo))

    def maj(fs):
        return np.mean(fs, axis=0) >= .5

    for tg in TARGETS:
        res.append(line(f"embeddings, recall target {tg}", d, maj([flags_at(r[0], r[1], y, w, is_ref, tg) for r in runs]), y, w, is_ref))
        res.append(line(f"time series, recall target {tg}", d, maj([flags_at(r[2], r[3], y, w, is_ref, tg) for r in runs]), y, w, is_ref))
        res.append(line(f"embeddings + time series, recall target {tg}", d, maj([flags_at(a, b, y, w, is_ref, tg) for a, b in both]), y, w, is_ref))
        res.append(line(f"rule net then embeddings + time series, target {tg}", d, maj([flags_at(a, b, y, w, is_ref, tg, net) for a, b in both]), y, w, is_ref))
    # Stage 1 for recall: anything the rule net or the embeddings catch; stage 2 keeps what the fused score believes
    for tg1 in (.9, .8):
        s1s = [net | flags_at(r[0], r[1], y, w, is_ref, tg1) for r in runs]
        res.append(line(f"stage 1 only: rule net OR embeddings at {tg1}", d, maj(s1s), y, w, is_ref))
        for tg2 in (.8, .7, .6, .5):
            res.append(line(f"stage 1 at {tg1}, then stage 2 at {tg2}", d, maj([flags_at(a, b, y, w, is_ref, tg2, s) for (a, b), s in zip(both, s1s)]), y, w, is_ref))
    rng = np.random.default_rng(SEED)
    shuf = []
    for rep in range(min(REPEATS, 5)):
        yy = y.copy()
        u = y >= 0
        yy[u] = rng.permutation(y[u])
        a, fa = cv_view(Xe, d, yy, se, ve, rep)
        shuf.append(wpr(y[is_ref], flags_at(a, fa, yy, w, is_ref, .5)[is_ref].astype(int), w[is_ref]))
    res.append(dict(method="shuffled labels, embeddings, target 0.5", precision=round(float(np.nanmean([a for a, _ in shuf])), 3), recall=round(float(np.mean([b for _, b in shuf])), 3)))
    print(json.dumps(res[-1]), flush=True)
    mean_e, mean_f = np.nanmean([r[0] for r in runs], axis=0), np.nanmean([a for a, _ in both], axis=0)
    q = d[(d.stratum == "background") & (d.y == 1)].index
    rnd = (d.set == "random").values
    print(pd.DataFrame(dict(id=d.id[q], beat=d.beat[q], in_rule_net=net[q], pct_of_random_below_embeddings=[round(100 * (mean_e[rnd] < mean_e[i]).mean()) for i in q], pct_of_random_below_fused=[round(100 * (mean_f[rnd] < mean_f[i]).mean()) for i in q])).to_string())
    k = is_ref
    for nm, s in (("embeddings", mean_e), ("time series", np.nanmean([r[2] for r in runs], axis=0)), ("both", mean_f)):
        print(nm, "averaged score, curve", curve(s[k], y[k], w[k]), flush=True)
    r = pd.DataFrame(res)
    r.to_csv(REPORT / "cc_fusion.csv", index=False)
    d.assign(emb_logit=mean_e, fused_logit=mean_f, rule_net=net, rule_filter=base).drop(columns=["x", "y_m"]).to_csv(REPORT / "cc_points_scored.csv", index=False)
    pd.set_option("display.width", 300, "display.max_columns", 30, "display.max_colwidth", 60)
    print(r.to_string())


if __name__ == "__main__":
    main()
