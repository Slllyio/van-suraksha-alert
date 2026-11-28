"""Candidate configs on round-2 points and on the Guna reference, whole-sample scoring with the fixed filter. Usage: e58_cfg_round2.py"""
import json

import pandas as pd

from common import *
from e14_accuracy import boot, metrics
from e32_enetra10m import FOREST_MIN, NDVI_DROP
from e48_tests import by_point, load, rule
from e49_ts import guna_ref, score_ref, series_feats, ts_pass
from zones import zone as zone_of


def cfg(p):
    fl = rule(p)[0]
    sf = series_feats(p)
    nda, ndb, nw = p.nea - p.nla, p.neb - p.nlb, p.water < 5
    td = (((p.ea_t >= FOREST_MIN) & (p.ea_t - p.la_t >= .08) & (nda >= NDVI_DROP)) | ((p.eb_t >= FOREST_MIN) & (p.eb_t - p.lb_t >= .08) & (ndb >= NDVI_DROP))) & nw
    nbr = ts_pass(sf, (0, .15, 0, 9))
    both = ts_pass(sf, (.15, .15, 0, 9))
    return {"rule": fl, "rule + NDVI and NBR falls": fl & both, "rule + NBR fall": fl & nbr, "tree drop .08": fl | td, "tree drop .08 + NBR fall": (fl | td) & nbr, "tree drop .08 + NDVI and NBR falls": (fl | td) & both}


def main():
    p = load()
    r = guna_ref(set(p.pid))
    q = p[p.pid.isin(r.pid)].reset_index(drop=True)
    print(pd.DataFrame([score_ref(r, by_point(q, m, 1), n) for n, m in cfg(q).items()]).to_string())
    k = pd.read_csv(OUT / "validation2" / "validation_key_DO_NOT_OPEN_BEFORE_LABELLING.csv").merge(pd.read_csv(OUT / "validation2" / "prelabels.csv"), on="sample_id").assign(pid=lambda d: d.sample_id + 200000)
    area = json.load(open(OUT / "validation2" / "strata_area_ha.json"))
    k["real"] = k.label.isin(list("LD")).astype(int)
    k["_w"] = k.stratum.map(area) / k.stratum.map(k.stratum.value_counts())
    k["zone"] = k.Division.map(zone_of)
    q = p[p.pid.isin(k.pid)].reset_index(drop=True)
    rows = []
    for n, m in cfg(q).items():
        k["m"] = by_point(q, m, 1).reindex(k.pid).fillna(False).astype(int).values
        for gn, s in [("ALL", k)] + list(k.groupby("zone")):
            pr, re, _ = metrics(s.real.values, s.m.values, s._w.values)
            lo, hi = boot(s, area, "real", "m")
            rows.append(dict(config=n, group=gn, flagged=int(s.m.sum()), true=int((s.m & s.real).sum()), precision=round(pr, 3), p_lo=round(lo[0], 3), p_hi=round(hi[0], 3), recall=round(re, 3), r_lo=round(lo[1], 3), r_hi=round(hi[1], 3), area_ha=round(float((s.m * s._w).sum()))))
    t = pd.DataFrame(rows)
    print(t[t.group == "ALL"].to_string())
    print(t[t.group != "ALL"].to_string())
    t.to_csv(OUT / "interim" / "report" / "config_round2.csv", index=False)


if __name__ == "__main__":
    main()
