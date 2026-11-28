"""Zone-specific fall thresholds, on my round 1 and 2 labels: tuned on half the beats of a zone, scored on the other half, then swapped. Usage: e66_zone_filter.py"""
import json

import numpy as np
import pandas as pd

from common import *
from e14_accuracy import metrics
from e48_tests import by_point, load, rule, split
from e49_ts import series_feats
from zones import zone as zone_of

GRID = [("both", x) for x in (.05, .08, .1, .12, .15)] + [("ndvi", x) for x in (.05, .08, .1, .15)] + [("nbr", x) for x in (.05, .08, .1, .15)] + [("none", 0)]


def mask(sf, g):
    k, x = g
    if k == "none":
        return pd.Series(True, index=sf.index)
    n, r = sf.drop_n >= x, sf.drop_r >= x
    return n & r if k == "both" else n if k == "ndvi" else r


def main():
    rows = []
    for base, sub in ((100000, "validation"), (200000, "validation2")):
        k = pd.read_csv(OUT / sub / "validation_key_DO_NOT_OPEN_BEFORE_LABELLING.csv").merge(pd.read_csv(OUT / sub / "prelabels.csv"), on="sample_id")
        a = json.load(open(OUT / sub / "strata_area_ha.json"))
        rows.append(k.assign(pid=k.sample_id + base, _w=k.stratum.map(a) / k.stratum.map(k.stratum.value_counts()), real=k.label.isin(list("LD")).astype(int), zone=k.Division.map(zone_of), grp=k.Division + "_" + k.Beat.astype(str), rnd=sub)[["pid", "_w", "real", "zone", "grp", "rnd"]])
    K = pd.concat(rows).set_index("pid", drop=False)
    p = load()
    K = K[K.index.isin(set(p.pid))]
    p = p[p.pid.isin(K.index)].reset_index(drop=True)
    fl = rule(p)[0]
    sf = series_feats(p)

    def flags(g):
        return (by_point(p, fl & mask(sf, g), 1) if g[0] == "none" else by_point(p, fl & mask(sf, g), 2)).reindex(K.index).fillna(False).astype(int)
    tab = {g: flags(g) for g in GRID}
    out = []
    for z, q in K.groupby("zone"):
        q = q.copy()
        a = split(q.grp)
        hold = pd.Series(0, index=q.index)
        picks = []
        for tr, te in ((q[q.grp.isin(a)], q[~q.grp.isin(a)]), (q[~q.grp.isin(a)], q[q.grp.isin(a)])):
            b0 = metrics(tr.real.values, tab[("none", 0)][tr.index].values, tr._w.values)
            best = None
            for g in GRID:
                pr, re, f1 = metrics(tr.real.values, tab[g][tr.index].values, tr._w.values)
                if np.isfinite(f1) and pr >= b0[0] and (best is None or f1 > best[0]):
                    best = (f1, g)
            picks.append(best[1] if best else ("none", 0))
            hold[te.index] = tab[picks[-1]][te.index]
        res = {"unfiltered": tab[("none", 0)], "both >=.15 + 2px": tab[("both", .15)], "held-out zone tuned": hold}
        for n, f in res.items():
            pr, re, _ = metrics(q.real.values, f.reindex(q.index).values, q._w.values)
            out.append(dict(zone=z, method=n, n=len(q), real=int(q.real.sum()), flagged=int(f.reindex(q.index).sum()), true=int((f.reindex(q.index) & q.real).sum()), precision=round(pr, 3), recall=round(re, 3), picks=str(picks) if n.startswith("held") else ""))
        for g in GRID:
            pr, re, _ = metrics(q.real.values, tab[g].reindex(q.index).values, q._w.values)
            out.append(dict(zone=z, method=f"fixed {g[0]} {g[1]}", n=len(q), real=int(q.real.sum()), flagged=int(tab[g].reindex(q.index).sum()), true=int((tab[g].reindex(q.index) & q.real).sum()), precision=round(pr, 3), recall=round(re, 3)))
    t = pd.DataFrame(out)
    print(t[~t.method.str.startswith("fixed")].to_string())
    print(t[t.method.str.startswith("fixed") & t.zone.isin(["sal_belt", "teak_belt", "plantation_mprvvn"])][["zone", "method", "flagged", "true", "precision", "recall"]].to_string())
    t.to_csv(OUT / "interim" / "report" / "zone_filter_test.csv", index=False)


if __name__ == "__main__":
    main()
