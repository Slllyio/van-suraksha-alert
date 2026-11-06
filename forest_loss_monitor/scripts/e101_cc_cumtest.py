"""Does accumulated 2017-2025 change, read as patches, find loss that the yearly-break model misses? From the 300 m windows of e100.
Per point and per signal (start-to-end distance 2017-18 vs 2024-25, 2017-19 vs 2023-25, straight-line trend, Dynamic World tree fall; and the yearly break for comparison): the largest patch
touching the 50 m box at thresholds set as percentiles of random forest land (no labels), so 'a 1 ha patch of accumulated change' is tested directly.
Then held-out comparison on 5 km blocks: yearly-break model, accumulated-change features, both. Usage: e101_cc_cumtest.py"""
import json
import sys
import warnings

sys.path.insert(0, "E:/FIRE/forest_loss_monitor/scripts")
sys.argv = [sys.argv[0], "logistic", "10"]

import numpy as np
import pandas as pd
from scipy.ndimage import label
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import StratifiedGroupKFold

import e91_cc_four as m
from e76_cc_train import REPORT, WORK, load, ref_w, thr_for, wpr
from e77_cc_local import wide
from e83_cc_pxmodel import px_features
from e85_cc_area import BOX_HALF, F as TWIN

warnings.filterwarnings("ignore")
REPEATS = 10
SIG = ("e2", "e3", "tr", "dw")
PCT = (80, 90, 95)
AREAS = (.25, .5, 1.0, 2.0)


def grids(d):
    """cid -> dict of 30 x 30 arrays (signals of e100 plus the yearly break t of e85) and the box mask."""
    pos = {c: i for i, c in enumerate(d.cid)}
    G = {}
    for path, bands in ((WORK / "cc_cumwin.jsonl", SIG), (TWIN, ("t",))):
        for l in open(path):
            r = json.loads(l)
            i = pos.get(r["cid"])
            if i is None:
                continue
            x, y = np.array(r["px"]), np.array(r["py"])
            col, row = ((x - x.min()) / 10).round().astype(int), ((y.max() - y) / 10).round().astype(int)
            e = G.setdefault(i, {})
            for b in bands:
                g = np.full((row.max() + 1, col.max() + 1), np.nan)
                v = np.array(r[b], float)
                g[row, col] = np.where(v == -9, np.nan, v)
                e[b] = g
            c = np.zeros(g.shape, bool)
            cr, cc, n = int((y.max() - d.y_m[i]) / 10), int((d.x[i] - x.min()) / 10), BOX_HALF // 10
            c[max(cr - n, 0):cr + n + 1, max(cc - n, 0):cc + n + 1] = True
            e["box_" + ("t" if b == "t" else "c")] = c
    return G


def patch_ha(g, c, th):
    lab, _ = label(np.nan_to_num(g, nan=-9) >= th, structure=np.ones((3, 3)))
    ids = np.unique(lab[c])
    ids = ids[ids > 0]
    return 0. if not len(ids) else float(np.bincount(lab.ravel())[ids].max()) * .01


def main():
    d, A = load()
    n = len(d)
    G = grids(d)
    have = np.array([i in G and all(s in G[i] for s in SIG + ("t",)) for i in range(n)])
    print("points with windows", int(have.sum()), "of", n, flush=True)
    rnd = (d.set == "random").values & have
    y = np.where(d.y.values == 1, 1, 0)
    w, k = ref_w(d), (d.set == "reference").values & have
    bg, fl = k & (d.stratum == "background").values, k & (d.stratum == "flagged").values
    cols, rows = {}, []
    for s in SIG + ("t",):
        boxk = "box_t" if s == "t" else "box_c"
        allv = np.concatenate([G[i][s][np.isfinite(G[i][s])] for i in np.flatnonzero(rnd)])
        cols[f"{s}_boxmax"] = np.array([np.nanmax(G[i][s][G[i][boxk]]) if have[i] else np.nan for i in range(n)])
        cols[f"{s}_boxmed"] = np.array([np.nanmedian(G[i][s][G[i][boxk]]) if have[i] else np.nan for i in range(n)])
        for p in PCT:
            th = np.percentile(allv, p)
            a = np.array([patch_ha(G[i][s], G[i][boxk], th) if have[i] else np.nan for i in range(n)])
            cols[f"{s}_patch{p}"] = a
            for ar in AREAS:
                f = a >= ar
                pr, re = wpr(y[k], f[k].astype(int), w[k])
                rows.append(dict(signal=s, pixel_bar=f"top {100 - p}% of random land", min_patch_ha=ar, precision=round(pr, 3), recall=round(re, 3), flagged=int(f[k].sum()), real=int((f[k] & (y[k] == 1)).sum()),
                                 background_losses=f"{int(f[bg & (y == 1)].sum())}/6", random_flag_pct=round(100 * f[rnd].mean(), 1)))
    C = pd.DataFrame(cols)
    t = pd.DataFrame(rows)
    t.to_csv(REPORT / "cc_cum_patch_rules.csv", index=False)
    pd.set_option("display.width", 260, "display.max_columns", 30, "display.max_rows", 200)
    names = dict(e2="start-to-end 2017-18 vs 2024-25", e3="start-to-end 2017-19 vs 2023-25", tr="straight-line trend", dw="tree-cover fall (Dynamic World)", t="yearly break (current)")
    print(t.assign(signal=t.signal.map(names))[t.min_patch_ha.isin([.5, 1.0])].to_string())
    u = []
    for c in C:
        v = C[c].fillna(C[c].median()).values
        u.append(dict(feature=c, auc_area=round(roc_auc_score(y[k], v[k], sample_weight=w[k]), 3), auc_background=round(roc_auc_score(y[bg], v[bg]), 3), auc_flagged=round(roc_auc_score(y[fl], v[fl]), 3)))
    u = pd.DataFrame(u).sort_values("auc_area", ascending=False)
    u.to_csv(REPORT / "cc_cum_features.csv", index=False)
    print(u.to_string())
    q = d.index[bg & (y == 1)].tolist() + d.index[k & (y == 1) & (d.id.isin(["REF_0258"]))].tolist()
    neg = bg & (y == 0)
    show = ["t_boxmax", "e2_boxmax", "e3_boxmax", "tr_boxmax", "e3_patch90", "tr_patch90", "t_patch90"]
    print("percentile among background non-loss points:")
    print(pd.DataFrame({"id": d.id[q], **{c: [round(100 * (C[c][neg] < C[c][i]).mean()) for i in q] for c in show}}).to_string())
    # held-out comparison
    scal = px_features(d, A, wide(d))[0]
    cum = C[[c for c in C if not c.startswith("t_")]].values
    kcls = m.classes(d)
    g = d.block.values
    tm = (d.y.values >= 0) & have
    kk = (d.set == "reference").values
    runs = {"yearly-break model (current)": scal, "accumulated-change features only": cum, "both": np.hstack([scal, cum])}
    S, gates = {a: [] for a in runs}, []
    for rep in range(REPEATS):
        folds = list(StratifiedGroupKFold(m.FOLDS, shuffle=True, random_state=rep).split(np.zeros(n), kcls, g))
        for a, X in runs.items():
            S[a].append(m.run_cv(X, list(range(X.shape[1])), [], y, tm, folds, kcls, g, rep))
        s, fo = S["yearly-break model (current)"][-1]
        gate, gi = np.zeros(n, bool), []
        for tr, te, inner in fo:
            ri = tr[kk[tr] & np.isfinite(inner[tr])]
            th = thr_for(inner[ri], y[ri], w[ri], .9)
            gate[te] = s[te] >= th
            gi.append(inner >= th)
        gates.append((gate, gi))
        print("repeat", rep, flush=True)
    res = []
    beat = d.beat.values[kk]
    wk = ref_w(d)
    for a in runs:
        # as a detector on its own: recall targets on the whole reference
        for tg in (.9, .7, .5):
            fl_ = []
            for s, fo in S[a]:
                f = np.zeros(n, bool)
                for tr, te, inner in fo:
                    ri = tr[kk[tr] & np.isfinite(inner[tr])]
                    f[te] = s[te] >= thr_for(inner[ri], y[ri], wk[ri], tg)
                fl_.append(f)
            f = np.mean(fl_, axis=0) >= .5
            tp, fp = int((f[kk] & (y[kk] == 1)).sum()), int((f[kk] & (y[kk] == 0)).sum())
            pw, rw = wpr(y[kk], f[kk].astype(int), wk[kk])
            pc, rc, ppc = m.boot(beat, y[kk], wk[kk], f[kk])
            res.append(dict(model=a, recall_target=tg, losses=f"{tp}/55", false_alarms=fp, point_precision=round(tp / max(tp + fp, 1), 3), area_precision=round(pw, 3), area_p_range=pc, area_recall=round(rw, 3), area_r_range=rc,
                            background_losses=f"{int((f & kk & (d.stratum == 'background').values & (y == 1)).sum())}/6", random_flag_pct=round(100 * f[(d.set == 'random').values].mean(), 1)))
            print(json.dumps(res[-1]), flush=True)
        res[-1]["auc_area"] = round(float(np.mean([roc_auc_score(y[kk], s[kk], sample_weight=wk[kk]) for s, _ in S[a]])), 3)
    r = pd.DataFrame(res)
    r.to_csv(REPORT / "cc_cum_models.csv", index=False)
    print(r.to_string())


if __name__ == "__main__":
    main()
