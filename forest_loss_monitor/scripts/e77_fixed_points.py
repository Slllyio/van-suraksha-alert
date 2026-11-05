"""Fixed settings on the 90% net: no fold-by-fold choosing, so these are what a map with one setting would give. Also the label-quality correction for my statewide labels. Usage: e77_fixed_points.py"""
import numpy as np
import pandas as pd

from common import *
from e23_guna_labels import wpr
from e48_tests import by_point
from e49_ts import series_feats
from e63_cascade import labels
from e69_rule_sweep import boot, pr
from e74_net90 import DEC, data, nets, windows

REPORT = OUT / "interim" / "report"
GRID = [(fn, fr, n) for fn in (0, .05, .1, .15, .2) for fr in (0, .05, .1, .15, .2) for n in (1, 3, 5, 9, 13)]
SENS = 14 / 55


def main():
    p, L, pi = data()
    w, sf = windows(p), series_feats(p)
    y, wt, g = L.y.values.astype(float), L.eval_w.values.astype(float), L.group.values
    ref = (L.set == "blind_reference").values
    dec = L.set.isin(["round1", "round2"]).values & L.zone.isin(DEC).values
    rows = []
    for name in ("+ NBR >= .10, BSI rise >= .03", "wide net + scrub"):
        m = nets(p, w, sf)[name]
        for fn, fr, n in GRID:
            k = m & (sf.drop_n.values >= fn if fn else True) & (sf.drop_r.values >= fr if fr else True)
            f = np.bincount(pi, weights=k, minlength=len(L)) >= n
            a, b = pr(f[None, ref], y[ref], wt[ref])
            sa, sb = pr(f[None, dec], y[dec], wt[dec])
            rows.append(dict(net=name, ndvi=fn, nbr=fr, npix=n, guna_p=round(float(a[0]), 3), guna_r=round(float(b[0]), 3), flagged=int(f[ref].sum()), real=int((f[ref] * y[ref]).sum()), bg=int((f[ref] & (L.stratum.values[ref] == "background") & (y[ref] == 1)).sum()), dec_p=round(float(sa[0]), 3), dec_r=round(float(sb[0]), 3)))
    t = pd.DataFrame(rows)
    t.to_csv(REPORT / "net90_fixed_settings.csv", index=False)
    for name, q in t.groupby("net"):
        print(name)
        for tg in (.7, .6, .5, .45, .4):
            s = q[q.guna_r >= tg].sort_values("guna_p", ascending=False).head(2)
            print(" recall >=", tg, s[["ndvi", "nbr", "npix", "guna_p", "guna_r", "flagged", "real", "bg", "dec_p", "dec_r"]].to_string(index=False, header=False))
    print(t[(t.ndvi == .1) & (t.nbr == .2) & (t.npix == 13)].to_string())
    # label quality: my no-loss may hide real loss; 14 of 55 owner losses were called by me, none of 55 owner no-loss
    k = L[L.set.isin(["round1", "round2"])].copy()
    base = pd.DataFrame(dict(pid=p.pid.values, m=nets(p, w, sf)["wide net + scrub"], drop_n=sf.drop_n.values, drop_r=sf.drop_r.values))
    from e48_tests import rule
    r = rule(p)[0].values
    fl = pd.Series(r).groupby(p.pid.values).any().reindex(k.index).fillna(False).values
    strict = pd.Series(r & (sf.drop_n.values >= .15) & (sf.drop_r.values >= .15)).groupby(p.pid.values).sum().reindex(k.index).fillna(0).ge(2).values
    yy, ww = k.y.values.astype(float), k.eval_w.values.astype(float)
    res = []
    for nm, f in (("rule", fl), ("filter + 2 px", strict)):
        for zn, q in [("all", np.ones(len(k), bool))] + [(z, (k.zone == z).values) for z in sorted(set(k.zone))]:
            P, R = pr(f[None, q].astype(float), yy[q], ww[q])
            for lo, hi, tag in ((SENS, SENS, "miss rate 75% (14/55)"), (.45, .45, "miss rate 55%"), (.15, .15, "miss rate 85%")):
                # a flagged point I called no-loss is real with chance c; unflagged no-loss likewise. c comes from Bayes at each stratum weight share.
                prior = (ww[q] * yy[q]).sum() / max(lo, 1e-9) / ww[q].sum()   # true prevalence if I only see a share of it
                prior = min(prior, .9)
                c = prior * (1 - lo) / (prior * (1 - lo) + (1 - prior))
                tp = (ww[q] * f[q] * (yy[q] + (1 - yy[q]) * c)).sum()
                pos = (ww[q] * (yy[q] + (1 - yy[q]) * c)).sum()
                res.append(dict(method=nm, zone=zn, my_precision=round(float(P[0]), 3), my_recall=round(float(R[0]), 3), case=tag, implied_prevalence=round(float(prior), 3), corrected_p_uniform=round(float(tp / max((ww[q] * f[q]).sum(), 1e-9)), 3), corrected_r_uniform=round(float(tp / pos), 3), corrected_p_if_flags_are_where_my_misses_are=round(float(min(1, P[0] / max(lo, 1e-9))), 3)))
    o = pd.DataFrame(res)
    o.to_csv(REPORT / "label_quality_correction.csv", index=False)
    pd.set_option("display.width", 220)
    print(o.to_string())


if __name__ == "__main__":
    main()
