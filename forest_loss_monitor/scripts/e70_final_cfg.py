"""Fixed candidates from the sweep: held-out precision and recall by whole beats on Guna and statewide points, with ranges. Fall and pixel settings are fixed, so nothing is tuned here. Usage: e70_final_cfg.py"""
import numpy as np
import pandas as pd

from common import *
from e48_tests import load
from e49_ts import rolling, series_feats
from e63_cascade import labels
from e69_rule_sweep import boot, pr, trig

CANDS = {"current: rule, falls .15/.15, 2 px": ("trees", .12, .08, True, False, .15, .15, 2),
         "wide A": ("woody", .06, .05, True, True, .2, .15, 2),
         "wide A, 3 px": ("woody", .06, .05, True, True, .2, .15, 3),
         "wide A, 5 px": ("woody", .06, .05, True, True, .2, .15, 5),
         "wide no rolling": ("woody", .06, .05, True, False, .2, .15, 2),
         "wide no rolling, 5 px": ("woody", .06, .05, True, False, .2, .15, 5),
         "trees .30, drop .08, rolling": ("trees", .08, .05, True, True, .2, .15, 2),
         "trees .30, drop .06, no rolling": ("trees", .06, .05, True, False, .2, .15, 2),
         "woody, drop .08, no rolling": ("woody", .08, .05, True, False, .2, .15, 2),
         "woody, drop .12, nd .08": ("woody", .12, .08, True, False, .2, .15, 2)}


def main():
    p = load()
    L = labels().set_index("pid")
    L = L[L.set.isin(["blind_reference", "round1", "round2"]) & L.index.isin(set(p.pid))]
    p = p[p.pid.isin(L.index)].reset_index(drop=True)
    sf = series_feats(p)
    roll = rolling(p, .12, .08) & (p.water < 5)
    pos = pd.Series(np.arange(len(L)), index=L.index)
    pi = pos[p.pid].values
    y, w = L.y.values.astype(float), L.eval_w.values.astype(float)
    g, z = L.group.values, L.zone.values
    guna, state = (L.set == "blind_reference").values, L.set.isin(["round1", "round2"]).values
    sets = [("Guna", guna), ("Statewide", state)] + [(zn[:5], state & (z == zn)) for zn in sorted(set(z[state]))]
    rows = []
    for nm, c in CANDS.items():
        m = trig(p, *c[:5], roll) & (sf.drop_n.values >= c[5]) & (sf.drop_r.values >= c[6])
        f = np.bincount(pi, weights=m, minlength=len(L)) >= c[7]
        row = dict(config=nm)
        for sn, mk in sets:
            a, b = pr(f[None, mk], y[mk], w[mk])
            r = boot(y[mk], w[mk], f[mk], g[mk])
            row[sn] = f"{a[0]*100:.0f}/{b[0]*100:.0f} P{r[0]} R{r[1]} f{int(f[mk].sum())}t{int((f[mk]*y[mk]).sum())}"
        cand = (L.set == "round2").values
        row["round2_ha"] = round(float((f[cand] * w[cand]).sum()))
        rows.append(row)
    t = pd.DataFrame(rows)
    pd.set_option("display.width", 300)
    print(t.to_string())
    t.to_csv(OUT / "interim" / "report" / "rule_final_candidates.csv", index=False)


if __name__ == "__main__":
    main()
