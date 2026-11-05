"""Phenology check of division-based zones from cached point data, and the sal-belt method comparison on the same points. All on my round 1 and 2 labels; thresholds tuned on training beats, 5-fold by beat, 3 repeats. Usage: e80_zone_sal.py zones | sal"""
import sys
import warnings

import numpy as np
import pandas as pd
from sklearn.model_selection import StratifiedGroupKFold

from common import *
from e48_tests import YS, load
from e49_ts import series_feats
from e63_cascade import labels
from e69_rule_sweep import boot, pr, trig
from zones import zone as zone_of

warnings.filterwarnings("ignore")
REPORT = OUT / "interim" / "report"


def zones():
    """Oct-Nov vs Apr-May NDVI drop 2017-19, and Jan-Mar vs Oct-Nov, on points that were wooded before and show no flagged loss."""
    p = load()
    L = labels().set_index("pid")
    k = []
    for base, sub in ((100000, "validation"), (200000, "validation2")):
        q = pd.read_csv(OUT / sub / "validation_key_DO_NOT_OPEN_BEFORE_LABELLING.csv").merge(pd.read_csv(OUT / sub / "prelabels.csv"), on="sample_id")
        k.append(q.assign(pid=q.sample_id + base)[["pid", "Division", "label"]])
    r = pd.read_csv(ROOT / "ground_truth" / "s2f_random300.csv")
    lk = pd.read_csv(OUT / "beat_lookup.csv").set_index("zone_id")
    k.append(pd.DataFrame(dict(pid=r.pid, Division=r.zone_id.map(lk.Division), label="N")))
    K = pd.concat(k).set_index("pid")
    g = p.groupby("pid")[[f"ln{y}" for y in (2017, 2018, 2019)] + [f"d{y}" for y in (2017, 2018, 2019)] + [f"r{y}" for y in (2017, 2018, 2019)] + ["ea_t", "ea_s"]].mean()
    x = K.join(g, how="inner")
    x = x[(x.ea_t >= .3) & x.label.isin(["N"])]
    x["leaf_on"], x["dry"], x["rabi"] = x[[f"ln{y}" for y in (2017, 2018, 2019)]].mean(axis=1), x[[f"d{y}" for y in (2017, 2018, 2019)]].mean(axis=1), x[[f"r{y}" for y in (2017, 2018, 2019)]].mean(axis=1)
    x["amp"] = x.leaf_on - x.dry
    x["zone"] = x.Division.map(zone_of)
    print("forest points", len(x))
    print(x.groupby("zone").agg(n=("amp", "size"), amp=("amp", "median"), q25=("amp", lambda s: s.quantile(.25)), q75=("amp", lambda s: s.quantile(.75)), dry_ndvi=("dry", "median"), trees=("ea_t", "median")).round(3).to_string())
    d = x.groupby(["Division", "zone"]).agg(n=("amp", "size"), amp=("amp", "median"), dry_ndvi=("dry", "median")).reset_index().sort_values("amp")
    fa = pd.read_csv(OUT / "coverage_divisions.csv").set_index("Division").forest_ha
    d["forest_ha"] = d.Division.map(fa).round()
    d.to_csv(REPORT / "phenology_by_division.csv", index=False)
    print(d[d.n >= 5].to_string(index=False))
    print(pd.read_csv(OUT / "coverage_divisions.csv").assign(zone=lambda q: q.Division.map(zone_of)).groupby("zone").forest_ha.sum().round().to_string())


def lt_flag(d, m, dr):
    return ((d.mag >= m) & d.yod.between(2018, 2025) & (d.pre_ndvi >= 3500) & ((d.pre_ndvi - d.post_ndvi) >= dr)).values


def sal():
    p = load()
    L = labels().set_index("pid")
    L = L[L.set.isin(["round1", "round2"]) & (L.zone == "sal_belt") & L.index.isin(set(p.pid))]
    p = p[p.pid.isin(L.index)].reset_index(drop=True)
    sf = series_feats(p)
    lt = pd.read_csv(OUT / "timeseries" / "lt_1020.csv").set_index("sample_id").reindex(L.index)
    ok = lt.mag.notna().values
    print("sal points", len(L), "real", int(L.y.sum()), "with LandTrendr", int(ok.sum()), "real among them", int(L.y[ok].sum()))
    y, w, g = L.y.values.astype(float), L.eval_w.values.astype(float), L.group.values
    pi = pd.Series(np.arange(len(L)), index=L.index)[p.pid].values
    k = []
    for base, sub in ((100000, "validation"), (200000, "validation2")):
        q = pd.read_csv(OUT / sub / "validation_key_DO_NOT_OPEN_BEFORE_LABELLING.csv")
        k.append(q.assign(pid=q.sample_id + base).set_index("pid").hansen_year)
    hy = pd.concat(k).reindex(L.index).values
    fam = {}
    fam["LandTrendr"] = {f"mag {m}, drop {d}": lt_flag(lt.assign(), m, d) for m in (500, 1000, 1500, 2000, 2500) for d in (500, 1000, 1500, 2000)}
    n1 = {}
    for fn in (.05, .08, .1, .15, .2, .25, .3):
        for fr in (0, .05, .1, .15, .2, .25, .3):
            for n in (1, 3, 5, 9, 13):
                keep = (sf.drop_n.values >= fn) & (sf.drop_r.values >= fr) & (p.water.values < 5) & (p.ea_t.values + p.ea_s.values >= .3)
                n1[f"NDVI {fn}, NBR {fr}, {n} px"] = np.bincount(pi, weights=keep, minlength=len(L)) >= n
    fam["Yearly NDVI/NBR break differencing"] = n1
    net = trig(p, "woody", .06, .05, True, False, None) if False else None
    roll = pd.Series(False, index=p.index)
    m = trig(p, "woody", .06, .05, True, False, roll)
    fam["Wide net + filter"] = {f"NDVI {fn}, NBR {fr}, {n} px": np.bincount(pi, weights=m & (sf.drop_n.values >= fn) & (sf.drop_r.values >= fr), minlength=len(L)) >= n for fn in (0, .1, .15, .2) for fr in (0, .1, .15, .2) for n in (1, 3, 5)}
    fam["Hansen 2018-25"] = {"as published": (hy >= 18) & (hy <= 25)}
    rows = []
    for nm, opts in fam.items():
        names = list(opts)
        F = np.array([opts[k] for k in names], bool)
        for scope, mk in (("LandTrendr points only", ok), ("all sal points", np.ones(len(L), bool))):
            if nm == "LandTrendr" and scope == "all sal points":
                continue
            idx = np.flatnonzero(mk)
            oof = np.zeros((3, len(L)), bool)
            pk = []
            for rep in range(3):
                for tr, te in StratifiedGroupKFold(5, shuffle=True, random_state=rep).split(idx[:, None], y[idx], g[idx]):
                    tr, te = idx[tr], idx[te]
                    pp, rr = pr(F[:, tr], y[tr], w[tr])
                    i = int(np.argmax(2 * pp * rr / np.maximum(pp + rr, 1e-9)))
                    pk.append(names[i])
                    oof[rep, te] = F[i, te]
            a, b = pr(oof[:, mk], y[mk], w[mk])
            r = boot(y[mk], w[mk], oof.mean(axis=0)[mk] >= .5, g[mk])
            rows.append(dict(method=nm, points=scope, protocol="held out by beat", n=int(mk.sum()), real=int(y[mk].sum()), precision=round(float(a.mean()), 3), p_range=r[0], recall=round(float(b.mean()), 3), r_range=r[1], most_chosen=pd.Series(pk).value_counts().index[0]))
    t = pd.DataFrame(rows)
    pd.set_option("display.width", 220)
    print(t.to_string())
    t.to_csv(REPORT / "sal_method_comparison.csv", index=False)


if __name__ == "__main__":
    {"zones": zones, "sal": sal}[sys.argv[1]]()
