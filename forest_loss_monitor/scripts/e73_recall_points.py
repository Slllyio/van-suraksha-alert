"""Recall operating points chosen on training beats and scored on held-out beats, what each filter stage costs in real losses, and how label source alone moves precision on the same Guna points.
Offline. Usage: e73_recall_points.py"""
import warnings
from itertools import product

import numpy as np
import pandas as pd
from sklearn.model_selection import StratifiedGroupKFold

from common import *
from e48_tests import GT, load, s2f_flags
from e49_ts import rolling, series_feats
from e63_cascade import labels
from e69_rule_sweep import FALLS, ND, NPIX, TD, boot, pr, trig

warnings.filterwarnings("ignore")
REPORT = OUT / "interim" / "report"
TARGETS = (.55, .65, .75)


def main():
    p = load()
    L = labels().set_index("pid")
    L = L[L.set.isin(["blind_reference", "round1", "round2"]) & L.index.isin(set(p.pid))]
    p = p[p.pid.isin(L.index)].reset_index(drop=True)
    sf = series_feats(p)
    roll = rolling(p, .12, .08) & (p.water < 5)
    pi = pd.Series(np.arange(len(L)), index=L.index)[p.pid].values
    dn, dr = sf.drop_n.values, sf.drop_r.values
    cfg, flags = [], []
    for t in product(("trees", "woody"), TD, ND, (True, False), (False, True)):
        m = trig(p, *t, roll)
        for fn, fr in product(FALLS, FALLS):
            k = m & (dn >= fn if fn else True) & (dr >= fr if fr else True)
            c = np.bincount(pi, weights=k, minlength=len(L))
            for n in NPIX:
                cfg.append(t + (fn, fr, n))
                flags.append(c >= n)
    F = np.array(flags, dtype=bool)
    C = pd.DataFrame(cfg, columns=["forest", "tree_drop", "ndvi_drop", "recent", "rolling", "ndvi_fall", "nbr_fall", "npix"])
    y, w = L.y.values.astype(float), L.eval_w.values.astype(float)
    g, z = L.group.values, L.zone.values
    guna, state = (L.set == "blind_reference").values, L.set.isin(["round1", "round2"]).values
    strat = np.where(guna, 0, 1) * 2 + y
    sets = [("Guna", guna), ("Statewide", state)] + [(zn, state & (z == zn)) for zn in sorted(set(z[state]))]
    out, picks = [], []
    for tname, tmask in (("Guna", guna), ("Statewide", state)):
        for tg in TARGETS:
            oof = np.zeros((3, len(L)), bool)
            for rep in range(3):
                for tr, te in StratifiedGroupKFold(5, shuffle=True, random_state=rep).split(F.T[:, :1], strat, g):
                    mk = np.intersect1d(tr, np.flatnonzero(tmask))
                    fw = F[:, mk] * w[mk]
                    tp = (fw * y[mk]).sum(axis=1)
                    pp, rr = tp / np.maximum(fw.sum(axis=1), 1e-9), tp / (w[mk] * y[mk]).sum()
                    v = np.where(rr >= tg, pp, -1)
                    i = int(np.argmax(v))
                    picks.append(dict(chosen_on=tname, target=tg, **C.iloc[i].to_dict()))
                    oof[rep, te] = F[i, te]
            for sn, mk in sets:
                a, b = pr(oof[:, mk], y[mk], w[mk])
                r = boot(y[mk], w[mk], oof.mean(axis=0)[mk] >= .5, g[mk])
                out.append(dict(chosen_on=tname, target=tg, points=sn, precision=round(float(a.mean()), 3), p_range=r[0], recall=round(float(b.mean()), 3), r_range=r[1]))
    t = pd.DataFrame(out)
    t.to_csv(REPORT / "recall_points_heldout.csv", index=False)
    print(t.to_string())
    k = pd.DataFrame(picks)
    print(k.groupby(["chosen_on", "target"]).agg(lambda s: s.value_counts().index[0]).to_string())
    # stage costs under the switched net
    m = trig(p, "woody", .06, .05, True, False, roll)
    allnet = trig(p, "woody", .06, .05, True, True, roll) | s2f_flags(p, .1, .15, .3, 2)
    def cnt(mask, n=1):
        return np.bincount(pi, weights=mask, minlength=len(L)) >= n
    stage = [("net + rolling + scrub-to-farm", cnt(allnet)), ("net, no rolling", cnt(m)), ("+ NDVI fall >= .20", cnt(m & (dn >= .2))), ("net + NBR fall >= .15 only", cnt(m & (dr >= .15))), ("net + 5 px only", cnt(m, 5)), ("+ NDVI .20 and NBR .15", cnt(m & (dn >= .2) & (dr >= .15))), ("+ both falls + 2 px", cnt(m & (dn >= .2) & (dr >= .15), 2)), ("+ both falls + 5 px", cnt(m & (dn >= .2) & (dr >= .15), 5))]
    rows = []
    for nm, f in stage:
        for sn, mk in sets[:2]:
            a, b = pr(f[None, mk], y[mk], w[mk])
            rows.append(dict(stage=nm, points=sn, precision=round(float(a[0]), 3), recall=round(float(b[0]), 3), flagged=int(f[mk].sum()), real=int((f[mk] * y[mk]).sum()), background_real=int((f[mk] & (L.stratum.values[mk] == "background") & (y[mk] == 1)).sum())))
    s = pd.DataFrame(rows)
    s.to_csv(REPORT / "filter_stage_costs.csv", index=False)
    print(s.to_string())
    # same Guna points scored with my labels and the owner's labels
    a = pd.read_csv(GT / "agreement" / "labels.csv")
    print(a.columns.tolist(), pd.crosstab(a.label, a.mine).to_string())
    gl = pd.read_csv(GT / "guna_labels.csv")
    keycols = [c for c in ("gid", "pid", "x", "y") if c in a.columns]
    print("agreement key cols", keycols)
    if "gid" in a:
        a["pid"] = a.gid + 500000
        bf = cnt(trig(p, "trees", .12, .08, True, False, roll))
        fl = pd.Series(bf, index=L.index)
        q = a[a.pid.isin(fl.index)].assign(f=lambda d: fl.reindex(d.pid).values)
        print("rule on the agreement points: flagged", int(q.f.sum()), "owner real among them", int((q.f & (q.label == 1)).sum()), "my real among them", int((q.f & (q.mine == 1)).sum()), "| real by owner", int(q.label.sum()), "caught", int((q.f & (q.label == 1)).sum()), "| real by me", int(q.mine.sum()), "caught", int((q.f & (q.mine == 1)).sum()))


if __name__ == "__main__":
    main()
