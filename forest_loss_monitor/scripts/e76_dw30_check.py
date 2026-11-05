"""Does taking Dynamic World and NDVI window means at 30 m instead of 10 m change the result? Approximates 30 m by averaging the 3 x 3 pixels around each pixel's position in the stored 5 x 5 box. Usage: e76_dw30_check.py"""
import numpy as np
import pandas as pd

from common import *
from e48_tests import by_point, load
from e49_ts import guna_ref, score_ref, series_feats
from e69_rule_sweep import trig

DW = ["ea_t", "ea_s", "ea_c", "eb_t", "eb_s", "eb_c", "la_t", "la_c", "la_b", "la_u", "la_s", "lb_t", "lb_c", "lb_b", "lb_u", "lb_s", "mon0", "mon24", "nea", "nla", "neb", "nlb", "water"]


def coarse(p):
    """Three 30 m blocks across the 5 x 5 box, pixel order row by row."""
    q = p.copy()
    n = p.groupby("pid").cumcount().values
    if (p.groupby("pid").size() != 25).any():
        keep = p.groupby("pid").pid.transform("size").values == 25
        q, n = q[keep].reset_index(drop=True), n[keep]
    block = (n // 5 // 2).astype(int) * 3 + (n % 5 // 2).astype(int)
    g = pd.DataFrame({"pid": q.pid.values, "b": block})
    for c in DW:
        g[c] = q[c].values
    q[DW] = g.groupby(["pid", "b"])[DW].transform("mean").values
    return q


def main():
    p = load()
    r = guna_ref(set(p.pid))
    p = p[p.pid.isin(r.pid)].reset_index(drop=True)
    q = coarse(p)
    print("rows", len(p), len(q))
    rows = []
    for nm, d in (("10 m", p), ("30 m (approx.)", q)):
        sf = series_feats(d)
        roll = pd.Series(False, index=d.index)
        m = pd.Series(trig(d, "woody", .06, .05, True, False, roll), index=d.index)
        rows.append(score_ref(r, by_point(d, m, 1), f"{nm}: wide net"))
        rows.append(score_ref(r, by_point(d, m & (sf.drop_n >= .1) & (sf.drop_r >= .2), 13), f"{nm}: NDVI .10, NBR .20, 13 px"))
        rows.append(score_ref(r, by_point(d, m & (sf.drop_n >= .2) & (sf.drop_r >= .15), 5), f"{nm}: strict, 5 px"))
    print(pd.DataFrame(rows).to_string())


if __name__ == "__main__":
    main()
