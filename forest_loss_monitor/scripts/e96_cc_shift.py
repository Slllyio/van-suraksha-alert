"""Does a land-type-dependent year correction remove the 2021 false alarms? The first model removed one year-wide shift for all of Guna. Here each pixel's series is corrected by the yearly shift of the
K unlabelled pool pixels (of 2,000) most like it in 2017-19, so tree cover, scrub and cropland each get their own correction. Labels are not used for the correction.
Compares embeddings-only models built on both corrections: same held-out 5 km blocks, stage 1 at 90% area-weighted recall, then fixed shares of caught losses. Usage: e96_cc_shift.py"""
import json
import sys
import warnings

sys.path.insert(0, "E:/FIRE/forest_loss_monitor/scripts")
sys.argv = [sys.argv[0], "logistic", "10"]

import numpy as np
import pandas as pd
from sklearn.model_selection import StratifiedGroupKFold
from sklearn.neighbors import NearestNeighbors

import e91_cc_four as m
from e76_cc_train import GT, REPORT, WORK, YS, load, ref_w, step_feats, thr_for, wpr
from e77_cc_local import wide
from e81_cc_conditional import pool

warnings.filterwarnings("ignore")
REPEATS, K, TOP = 10, 100, 3
KEEP = (1.0, .95, .9, .8)


def summarise(X, ring):
    """Same 22 numbers per point as e83.px_features."""
    L = X - ring[None]
    s, _, _ = step_feats(X)
    ls, _, _ = step_feats(L)
    o = np.argsort(-s.t.values)[:TOP]
    q = lambda v: [np.median(v), np.quantile(v, .75), np.quantile(v, .9), v.max()]
    return q(s.t.values) + q(ls.t.values) + q(s.step.values) + q(ls.step.values) + [(s.t.values > 3).mean(), (s.t.values > 4).mean(), (s.t.values > 5).mean(), (ls.t.values > 3).mean(), np.median(s.brk.values[o]), s.noise.values[o].mean()]


def build(d, A, W):
    _, Pa = pool(25)
    _, Pw = pool(250)
    ok = ~(np.isnan(Pa).any(axis=(1, 2)) | np.isnan(Pw).any(axis=(1, 2)))
    Pa, Pw = Pa[ok], Pw[ok]
    Pa /= np.linalg.norm(Pa, axis=2, keepdims=True)
    anom_a, anom_w = Pa - Pa.mean(axis=1, keepdims=True), Pw - Pw.mean(axis=1, keepdims=True)
    nn_a, nn_w = NearestNeighbors(n_neighbors=K).fit(Pa[:, :3].mean(axis=1)), NearestNeighbors(n_neighbors=K).fit(Pw[:, :3].mean(axis=1))
    g_a, g_w = anom_a.mean(axis=0), anom_w.mean(axis=0)            # one shift for everything, as before but from the pool
    pos = {c: i for i, c in enumerate(d.cid)}
    out = {k: np.full((len(d), 22), np.nan) for k in ("one shift", "shift by land type")}
    wshift = np.median(anom_w[nn_w.kneighbors(W[:, :3].mean(axis=1), return_distance=False)], axis=1)
    for l in open(WORK / "cc_emb_px.jsonl"):
        r = json.loads(l)
        i = pos.get(r.pop("cid"))
        if i is None:
            continue
        X = np.array([[r[f"y{y}_{b:02d}"] for b in range(64)] for y in YS], "float64").transpose(2, 0, 1)
        X /= np.linalg.norm(X, axis=2, keepdims=True)
        out["one shift"][i] = summarise(X - g_a, W[i] - g_w)
        sh = np.median(anom_a[nn_a.kneighbors(X[:, :3].mean(axis=1), return_distance=False)], axis=1)
        out["shift by land type"][i] = summarise(X - sh, W[i] - wshift[i])
    return out


def main():
    d, A = load()
    n = len(d)
    F = build(d, A, wide(d))
    lab = pd.read_csv(GT / "cc_strips_labelled.csv", keep_default_na=False).set_index("cid").label
    mine = d.cid.map(lab).fillna("").values
    new = (d.set == "new_flag").values
    kcls = m.classes(d)
    ybin = np.isin(kcls, [1, 2]).astype(int)
    tm = d.y.values >= 0
    w, g, k = ref_w(d), d.block.values, (d.set == "reference").values
    y, beat, rows = ybin, d.beat.values[k], []
    cols = list(range(22))
    for name, X in F.items():
        S, gates = [], []
        for rep in range(REPEATS):
            folds = list(StratifiedGroupKFold(m.FOLDS, shuffle=True, random_state=rep).split(np.zeros(n), kcls, g))
            s, fo = m.run_cv(X, cols, [], ybin, tm, folds, kcls, g, rep)
            gate, gate_in = np.zeros(n, bool), []
            for tr, te, inner in fo:
                ri = tr[k[tr] & np.isfinite(inner[tr])]
                th = thr_for(inner[ri], ybin[ri], w[ri], m.S1_TARGET)
                gate[te] = s[te] >= th
                gate_in.append(inner >= th)
            S.append((s, fo))
            gates.append((gate, gate_in))
        for keep in KEEP:
            fl = []
            for (s, fo), (gate, gate_in) in zip(S, gates):
                f = np.zeros(n, bool)
                for (tr, te, inner), gi in zip(fo, gate_in):
                    ri = tr[k[tr] & (y[tr] == 1) & gi[tr] & np.isfinite(inner[tr])]
                    f[te] = gate[te] & (s[te] >= (np.quantile(inner[ri], 1 - keep, method="lower") if len(ri) else -np.inf))
                fl.append(f)
            f = np.mean(fl, axis=0) >= .5
            fk = f[k]
            tp, fp = int((fk & (y[k] == 1)).sum()), int((fk & (y[k] == 0)).sum())
            pw, rw = wpr(y[k], fk.astype(int), w[k])
            pc, rc, ppc = m.boot(beat, y[k], w[k], fk)
            bg = k & (d.stratum == "background").values
            fa = f & k & (y == 0)
            rows.append(dict(correction=name, keep_target=keep, losses=f"{tp}/55", false_alarms=fp, false_alarms_2021=int((fa & (np.round(X[:, 20]) == 4)).sum()), background_false=int((f & bg & (y == 0)).sum()), background_losses=f"{int((f & bg & (y == 1)).sum())}/6",
                             point_precision=round(tp / max(tp + fp, 1), 3), point_p_range=ppc, area_precision=round(pw, 3), area_p_range=pc, area_recall=round(rw, 3), area_r_range=rc, random_flag_pct=round(100 * f[(d.set == "random").values].mean(), 1),
                             new_no_change_flagged=f"{int(f[new & (mine == 'N')].sum())}/46", new_clearing_flagged=f"{int(f[new & (mine == 'C')].sum())}/6", new_thinning_flagged=f"{int(f[new & (mine == 'T')].sum())}/5"))
            print(json.dumps(rows[-1]), flush=True)
        brk = 2017 + np.round(X[:, 20]).astype(int)
        print(name, "break years, all reference:", pd.Series(brk[k]).value_counts().sort_index().to_dict(), "| random land:", pd.Series(brk[(d.set == 'random').values]).value_counts().sort_index().to_dict(), flush=True)
    t = pd.DataFrame(rows)
    t.to_csv(REPORT / "cc_shift.csv", index=False)
    pd.set_option("display.width", 330, "display.max_columns", 40)
    print(t.to_string())


if __name__ == "__main__":
    main()
