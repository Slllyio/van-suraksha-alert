"""The time-series filter at the Guna-chosen thresholds on my round-2 points, area-weighted by the round-2 strata, with the share of flagged pixels it removes. Usage: e52_round2.py"""
import json

import pandas as pd

from common import *
from e14_accuracy import boot, metrics
from e48_tests import by_point, load, rule
from e49_ts import series_feats, ts_pass
from zones import zone as zone_of

G = (.15, .15, 0, 9)


def main():
    p = load()
    k = pd.read_csv(OUT / "validation2" / "validation_key_DO_NOT_OPEN_BEFORE_LABELLING.csv").merge(pd.read_csv(OUT / "validation2" / "prelabels.csv"), on="sample_id").assign(pid=lambda d: d.sample_id + 200000)
    k = k[k.pid.isin(set(p.pid))]
    p = p[p.pid.isin(k.pid)].reset_index(drop=True)
    area = json.load(open(OUT / "validation2" / "strata_area_ha.json"))
    k["real"] = k.label.isin(list("LD")).astype(int)
    k["_w"] = k.stratum.map(area) / k.stratum.map(k.stratum.value_counts())
    k["zone"] = k.Division.map(zone_of)
    fl = rule(p)[0]
    sf = series_feats(p)
    ok = fl & ts_pass(sf, G)
    print("flagged pixels kept", round(float(ok.sum() / fl.sum()), 3), "of", int(fl.sum()))
    k["rule"] = by_point(p, fl, 1).reindex(k.pid).fillna(False).astype(int).values
    k["filt"] = by_point(p, ok, 1).reindex(k.pid).fillna(False).astype(int).values
    rows = []
    for col in ("rule", "filt"):
        for gn, q in [("ALL", k)] + list(k.groupby("zone")):
            pr, re, _ = metrics(q.real.values, q[col].values, q._w.values)
            lo, hi = boot(q, area, "real", col)
            rows.append(dict(method=col, group=gn, n=len(q), real=int(q.real.sum()), flagged=int(q[col].sum()), true=int((q[col] & q.real).sum()), precision=round(pr, 3), p_lo=round(lo[0], 3), p_hi=round(hi[0], 3), recall=round(re, 3), r_lo=round(lo[1], 3), r_hi=round(hi[1], 3), area_ha=round(float((q[col] * q._w).sum()))))
    t = pd.DataFrame(rows)
    print(t.to_string())
    t.to_csv(OUT / "interim" / "report" / "ts_filter_round2.csv", index=False)


if __name__ == "__main__":
    main()
