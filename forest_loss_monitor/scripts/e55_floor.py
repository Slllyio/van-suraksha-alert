"""Each recall lever with the filter, thresholds chosen for the most recall at training precision >= 0.66, scored on the other half of the beats. Usage: e55_floor.py"""
import json

import pandas as pd

from common import *
from e23_guna_labels import wpr
from e32_enetra10m import FOREST_MIN, NDVI_DROP, TREE_DROP, WOODY_MIN
from e48_tests import by_point, load, rule, s2f_flags, split
from e49_ts import FG, REPORT, guna_ref, rolling, score_ref, series_feats, ts_pass

FLOOR = .66


def main():
    p = load()
    r = guna_ref(set(p.pid))
    p = p[p.pid.isin(r.pid)].reset_index(drop=True)
    fl = rule(p)[0]
    sf = series_feats(p)
    nda, ndb, nw = p.nea - p.nla, p.neb - p.nlb, p.water < 5
    td = (((p.ea_t >= FOREST_MIN) & (p.ea_t - p.la_t >= .08) & (nda >= NDVI_DROP)) | ((p.eb_t >= FOREST_MIN) & (p.eb_t - p.lb_t >= .08) & (ndb >= NDVI_DROP))) & nw
    forest = (p.ea_t >= FOREST_MIN) | (p.eb_t >= FOREST_MIN)
    roll = rolling(p, TREE_DROP, NDVI_DROP) & nw
    nbr = forest & (sf.drop_r >= .15) & nw
    s2 = s2f_flags(p, .1, .15, .3, 2)
    lv = {"rule": fl, "tree drop 0.08": fl | td, "rolling": fl | roll, "NBR trigger": fl | nbr, "rule + scrub-to-farm": fl | s2, "rolling + scrub-to-farm": fl | roll | s2, "rolling + NBR + tree 0.08 + scrub-to-farm": fl | roll | nbr | td | s2}
    a = split(r.beat)
    rows = []
    for name, m in lv.items():
        h, pk = pd.Series(False, index=r.pid), []
        for tr, te in ((r[r.beat.isin(a)], r[~r.beat.isin(a)]), (r[~r.beat.isin(a)], r[r.beat.isin(a)])):
            best = None
            for g in FG:
                ok = m & ts_pass(sf, g)
                for mp in (1, 3, 5, 9, 13):
                    f = by_point(p, ok, mp).reindex(tr.pid).fillna(False).astype(int).values
                    if f.sum():
                        pr, re = wpr(tr.label.values, f, tr._w.values)
                        if pr >= FLOOR and (best is None or re > best[0]):
                            best = (re, g, mp)
            if best:
                pk.append(best[1:])
                h[te.pid] = by_point(p, m & ts_pass(sf, best[1]), best[2]).reindex(te.pid).fillna(False).values
        d = score_ref(r, h, name + " at training precision >= 0.66, held out")
        d["picks"] = str(pk)
        rows.append(d)
        print(d, flush=True)
    pd.DataFrame(rows).to_csv(REPORT / "recall_levers_precision_floor.csv", index=False)


if __name__ == "__main__":
    main()
