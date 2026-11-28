"""The agreed filter with a minimum number of passing pixels in the 50 m box, on Guna and round 2. Usage: e59_minpx.py"""
import json

import pandas as pd

from common import *
from e14_accuracy import boot, metrics
from e48_tests import by_point, load, rule
from e49_ts import guna_ref, score_ref, series_feats, ts_pass


def main():
    p = load()
    r = guna_ref(set(p.pid))
    q = p[p.pid.isin(r.pid)].reset_index(drop=True)
    ok = rule(q)[0] & ts_pass(series_feats(q), (.15, .15, 0, 9))
    rows = [score_ref(r, by_point(q, ok, n), f"min {n} px") for n in (1, 2, 3, 5, 9, 13)]
    print(pd.DataFrame(rows).to_string())
    k = pd.read_csv(OUT / "validation2" / "validation_key_DO_NOT_OPEN_BEFORE_LABELLING.csv").merge(pd.read_csv(OUT / "validation2" / "prelabels.csv"), on="sample_id").assign(pid=lambda d: d.sample_id + 200000)
    area = json.load(open(OUT / "validation2" / "strata_area_ha.json"))
    k["real"] = k.label.isin(list("LD")).astype(int)
    k["_w"] = k.stratum.map(area) / k.stratum.map(k.stratum.value_counts())
    q = p[p.pid.isin(k.pid)].reset_index(drop=True)
    ok = rule(q)[0] & ts_pass(series_feats(q), (.15, .15, 0, 9))
    for n in (1, 2, 3, 5, 9, 13):
        k["m"] = by_point(q, ok, n).reindex(k.pid).fillna(False).astype(int).values
        pr, re, _ = metrics(k.real.values, k.m.values, k._w.values)
        lo, hi = boot(k, area, "real", "m")
        print("round 2 min", n, "flagged", int(k.m.sum()), "true", int((k.m & k.real).sum()), "P", round(pr, 3), [round(lo[0], 3), round(hi[0], 3)], "R", round(re, 3), [round(lo[1], 3), round(hi[1], 3)], "ha", round(float((k.m * k._w).sum())))


if __name__ == "__main__":
    main()
