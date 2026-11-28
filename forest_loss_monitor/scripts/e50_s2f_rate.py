"""Scrub-to-farm class at the thresholds from the clean test: Guna reference with area weights, flag rate on random forest, flags on my round 1/2 labels.
The rate on random points is what it would add to the map if every flag were counted. Usage: e50_s2f_rate.py"""
import json

import numpy as np
import pandas as pd

from common import *
from e48_tests import GT, by_point, load, rule, s2f_flags
from e49_ts import guna_ref, score_ref

SET = {"A amp .10 min5": (.1, .1, .3, 2, 5), "B amp .15 min13": (.1, .15, .3, 2, 13), "stricter amp .20 min13": (.1, .2, .35, 2, 13), "stricter floor .4 amp .2 min13": (.4, .2, .35, 2, 13), "stricter 3 seasons amp .2 min13": (.1, .2, .35, 3, 13)}


def wilson(k, n, z=1.96):
    if not n:
        return 0, 0
    p = k / n
    d = 1 + z * z / n
    c = p + z * z / (2 * n)
    h = z * np.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return round(100 * (c - h) / d, 1), round(100 * (c + h) / d, 1)


def main():
    p = load()
    have = set(p.pid)
    r = guna_ref(have)
    fl = rule(p)[0]
    base = by_point(p, fl, 1)
    rows, stats = [score_ref(r, base, "rule as mapped")], []
    rnd = sorted(i for i in have if i >= 600000)
    for name, g in SET.items():
        s = by_point(p, s2f_flags(p, *g[:4]), g[4])
        rows.append(score_ref(r, s, name + " alone"))
        rows.append(score_ref(r, base.reindex(s.index).fillna(False) | s, name + " added to rule"))
        k, n = int(s.reindex(rnd).fillna(False).sum()), len(rnd)
        row = dict(setting=name, random_flagged=k, random_n=n, pct=round(100 * k / n, 1), ci=wilson(k, n))
        for base_id, sub in ((100000, "validation"), (200000, "validation2")):
            q = pd.read_csv(OUT / sub / "prelabels.csv").assign(pid=lambda d: d.sample_id + base_id)
            q = q[q.pid.isin(have)]
            row[sub] = q[s.reindex(q.pid).fillna(False).values].label.value_counts().to_dict()
            row[sub + "_n"] = len(q)
        stats.append(row)
    t = pd.DataFrame(rows)
    print(t.to_string())
    print(pd.DataFrame(stats).to_string())
    t.to_csv(OUT / "interim" / "report" / "s2f_guna_weighted.csv", index=False)
    pd.DataFrame(stats).to_csv(OUT / "interim" / "report" / "s2f_random_rates.csv", index=False)
    q = r.assign(s=by_point(p, s2f_flags(p, *SET["B amp .15 min13"][:4]), 13).reindex(r.pid).fillna(False).values, b=base.reindex(r.pid).fillna(False).values)
    print(q[q.s][["pid", "label", "stratum", "beat", "cls", "b"]].to_string())
    print("background real points", q[(q.label == 1)].groupby("stratum").agg(n=("pid", "size"), rule=("b", "sum"), s2f=("s", "sum")).to_string())


if __name__ == "__main__":
    main()
