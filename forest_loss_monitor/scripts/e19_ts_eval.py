"""Does time series beat or improve AlphaEarth? Thresholds tuned on validation round 1 only; all reported accuracy is round 2.
Loss = CCDC break in 2018-2025 with leaf-on (20 Oct) predicted NBR drop >= T, segment mean drop >= T, and >= 1 year of post-break data.
A recovering post-segment is flagged as felling or regrowth. Usage: e19_ts_eval.py [--selftest]"""
import json
import sys

import numpy as np
import pandas as pd

from common import OUT, WORK
from e14_accuracy import boot, metrics, weights

D = OUT / "timeseries"
MAIN = ["clearing", "partial"]
W = 2 * np.pi
LEAF = 0.8                     # 20 October as a fraction of the year
TS = [0.03, 0.05, 0.07, 0.10, 0.12, 0.15, 0.20, 0.25, 0.30]
LT_MAGS = [1000, 1500, 2000, 2500, 3000, 4000]


def predict(c, t):
    return c[0] + c[1] * t + c[2] * np.cos(W * t) + c[3] * np.sin(W * t) + c[4] * np.cos(2 * W * t) + c[5] * np.sin(2 * W * t) \
        + c[6] * np.cos(3 * W * t) + c[7] * np.sin(3 * W * t)


def year_mean(c, t):
    return np.mean([predict(c, t + d) for d in np.arange(0, 1, 1 / 24)])


def breaks(p):
    """All candidate loss breaks at a point, each with its size and whether it recovers."""
    out = []
    ts, te, tb, co = p.get("tStart") or [], p.get("tEnd") or [], p.get("tBreak") or [], p.get("NBR_coefs") or []
    for k in range(len(tb) - 1):
        b = tb[k]
        if not b or not 2018 <= b < 2026 or not ts[k + 1]:
            continue
        pre, post = co[k], co[k + 1]
        t0 = np.floor(b - LEAF) + LEAF                 # last 20 Oct before the break
        t1 = np.ceil(b - LEAF) + LEAF                  # first 20 Oct after it
        leaf = predict(pre, t0) - predict(post, t1)
        mean = year_mean(pre, b - 1) - year_mean(post, b)
        dur = te[k + 1] - ts[k + 1]
        later = predict(post, min(t1 + 3, te[k + 1]))
        rec = (later - predict(post, t1)) >= 0.5 * leaf if leaf > 0 else False
        out.append(dict(year=int(np.floor(b)), leaf=float(leaf), mean=float(mean), dur=float(dur), recovers=bool(rec)))
    return out


def ccdc_table():
    rows = []
    for line in open(D / "ccdc_1020.jsonl"):
        p = json.loads(line)
        ok = [x for x in breaks(p) if x["dur"] >= 1]
        best = max(ok, key=lambda x: min(x["leaf"], x["mean"]), default=None)
        rows.append(dict(sample_id=p["sample_id"], ran=int(p.get("tStart") is not None), n_breaks=sum(1 for b in (p.get("tBreak") or []) if b),
                         ts_size=min(best["leaf"], best["mean"]) if best else 0.0, ts_year=best["year"] if best else 0, ts_recovers=best["recovers"] if best else False))
    return pd.DataFrame(rows)


def load():
    parts = []
    for rnd, sub, base in ((1, "validation", 100000), (2, "validation2", 200000)):
        k = pd.read_csv(OUT / sub / "validation_key_DO_NOT_OPEN_BEFORE_LABELLING.csv")
        k = k.merge(pd.read_csv(OUT / sub / "prelabels.csv"), on="sample_id")
        area = json.load(open(OUT / sub / "strata_area_ha.json"))
        k["_w"] = weights(k, area)
        k["round"] = rnd
        k["sample_id"] = k.sample_id + base
        parts.append(k)
    df = pd.concat(parts, ignore_index=True)
    w = np.load(WORK / "water.npy", mmap_mode="r")
    df["water"] = np.asarray(w[df.row.values, df.col.values])
    df["real"] = df.label.isin(list("LD")).astype(int)
    df["ae"] = (df.stratum.isin(MAIN) & ~df.water).astype(int)
    df["cand"] = (df.stratum.isin(MAIN + ["small", "high_score_unmapped", "stable_near_loss"]) & ~df.water).astype(int)
    df = df.merge(ccdc_table(), on="sample_id", how="left")
    lt = pd.read_csv(D / "lt_1020.csv")[["sample_id", "yod", "mag", "pre_ndvi", "post_ndvi"]]
    df = df.merge(lt, on="sample_id", how="left")
    df["lt_ok"] = df.mag.notna()
    df["deciduous"] = df.forest_zone.isin(["mixed_dry_deciduous", "teak_belt"]) if "forest_zone" in df else False
    return df


def lt_flag(d, mag):
    return ((d.mag >= mag) & (d.yod.between(2018, 2025)) & (d.pre_ndvi >= 3500) & ((d.pre_ndvi - d.post_ndvi) >= 1500)).astype(int)


def tune(r1):
    """F1 on round 1 only, for each rule."""
    y, w = r1.real.values, r1._w.values
    res = {}
    best = (-1, None)
    for t in TS:
        f = metrics(y, (r1.ts_size >= t).astype(int).values, w)[2]
        best = max(best, (f if f == f else -1, t))
    res["ccdc_only"] = best[1]
    best = (-1, None)
    for t in TS:
        f = metrics(y, (r1.ae & (r1.ts_size >= t)).astype(int).values, w)[2]
        best = max(best, (f if f == f else -1, t))
    res["ae_and_ccdc"] = best[1]
    best = (-1, None)
    for t in TS:
        f = metrics(y, (r1.cand & (r1.ts_size >= t)).astype(int).values, w)[2]
        best = max(best, (f if f == f else -1, t))
    res["candidates_and_ccdc"] = best[1]
    d = r1[r1.lt_ok]
    best = (-1, None)
    for m in LT_MAGS:
        f = metrics(d.real.values, (d.ae & lt_flag(d, m)).astype(int).values, d._w.values)[2]
        best = max(best, (f if f == f else -1, m))
    res["ae_and_lt"] = best[1]
    best = (-1, None)
    for m in LT_MAGS:
        f = metrics(d.real.values, lt_flag(d, m).values, d._w.values)[2]
        best = max(best, (f if f == f else -1, m))
    res["lt_only"] = best[1]
    return res


def add_rules(d, th):
    d = d.copy()
    d["m_ae"] = d.ae
    d["m_ccdc"] = (d.ts_size >= th["ccdc_only"]).astype(int)
    d["m_ae_ccdc"] = (d.ae & (d.ts_size >= th["ae_and_ccdc"])).astype(int)
    d["m_cand_ccdc"] = (d.cand & (d.ts_size >= th["candidates_and_ccdc"])).astype(int)
    d["m_lt"] = lt_flag(d, th["lt_only"]).where(d.lt_ok)
    d["m_ae_lt"] = (d.ae.astype(bool) & (lt_flag(d, th["ae_and_lt"]) == 1)).astype(int).where(d.lt_ok)
    d["m_hansen"] = d.hansen_year.between(18, 25).astype(int)
    return d


RULES = dict(m_ae="AlphaEarth map", m_ae_ccdc="AlphaEarth + CCDC confirm", m_cand_ccdc="AlphaEarth wider candidates + CCDC", m_ccdc="CCDC alone",
             m_lt="LandTrendr alone", m_ae_lt="AlphaEarth + LandTrendr confirm", m_hansen="Hansen")


def report(d, groups, area):
    rows = []
    for g, s in groups:
        for col, name in RULES.items():
            q = s.dropna(subset=[col])
            if not len(q) or not q.real.sum():
                rows.append(dict(group=g, method=name, n=len(q), ref_loss_n=int(q.real.sum())))
                continue
            p, r, f = metrics(q.real.values, q[col].astype(int).values, q._w.values)
            lo, hi = boot(q.assign(_m=q[col].astype(int)), area, "real", "_m")
            mapped = float((q[col] * q._w).sum())
            rows.append(dict(group=g, method=name, n=len(q), ref_loss_n=int(q.real.sum()), precision=p, p_lo=lo[0], p_hi=hi[0], recall=r, r_lo=lo[1], r_hi=hi[1],
                             f1=f, f1_lo=lo[2], f1_hi=hi[2], area_flagged_ha=mapped))
    return pd.DataFrame(rows).round(3)


def stable_check(d):
    """Does CCDC find loss in the stable strata? Points it flags there, for review."""
    s = d[d.stratum.isin(["stable_tree", "stable_low_tree"])]
    return s, s[s.m_ccdc == 1]


def selftest():
    c0 = [1.3, -.0002, 0, 0, 0, 0, 0, 0]
    post = [.5, -.0001, 0, 0, 0, 0, 0, 0]
    p = dict(tStart=[2015.0, 2020.5], tEnd=[2020.4, 2025.9], tBreak=[2020.45, 0], NBR_coefs=[c0, post])
    b = breaks(p)
    assert len(b) == 1 and b[0]["year"] == 2020 and b[0]["leaf"] > .3 and b[0]["dur"] > 5 and not b[0]["recovers"]
    p2 = dict(tStart=[2015.0, 2020.5], tEnd=[2020.4, 2020.9], tBreak=[2020.45, 0], NBR_coefs=[c0, post])
    assert breaks(p2)[0]["dur"] < 1
    assert breaks(dict(tStart=[2015.0], tEnd=[2025.0], tBreak=[0], NBR_coefs=[c0])) == []
    t = 2020.3
    assert abs(predict([.5, 0, .1, 0, 0, 0, 0, 0], t) - (.5 + .1 * np.cos(W * t))) < 1e-9
    print("selftest ok")


def main():
    from zones import zone as zone_of
    df = load()
    df["forest_zone"] = df.Division.map(zone_of)
    df["deciduous"] = df.forest_zone.isin(["mixed_dry_deciduous", "teak_belt"])
    print("ccdc ran", int(df.ran.fillna(0).sum()), "of", len(df), "lt valid", int(df.lt_ok.sum()))
    r1, r2 = df[df["round"] == 1], df[df["round"] == 2]
    th = tune(r1)
    print("thresholds from round 1:", th)
    json.dump(th, open(D / "thresholds_from_round1.json", "w"))
    r1, r2 = add_rules(r1, th), add_rules(r2, th)
    area = json.load(open(OUT / "validation2" / "strata_area_ha.json"))
    groups = [("ALL", r2), ("deciduous (teak + mixed dry)", r2[r2.deciduous])] + [(z, g) for z, g in r2.groupby("forest_zone")]
    t = report(r2, groups, area)
    t.to_csv(D / "method_comparison_round2.csv", index=False)
    print(t[["group", "method", "n", "ref_loss_n", "precision", "p_lo", "p_hi", "recall", "r_lo", "r_hi", "f1", "area_flagged_ha"]].to_string(index=False))
    t1 = report(r1, [("ALL (round 1, used for tuning)", r1)], json.load(open(OUT / "validation" / "strata_area_ha.json")))
    print(t1[["method", "precision", "recall", "f1"]].to_string(index=False))
    s, f = stable_check(r2)
    print("round-2 stable points", len(s), "flagged by CCDC", len(f), "labels of flagged", f.label.value_counts().to_dict())
    f[["sample_id", "stratum", "lon", "lat", "label", "ts_size", "ts_year", "ts_recovers"]].to_csv(D / "stable_points_flagged_by_ccdc.csv", index=False)
    print("felling/regrowth flags among confirmed AE:", r2[r2.m_ae_ccdc == 1].ts_recovers.value_counts().to_dict())
    print(pd.crosstab(r2.m_ae_ccdc, r2.label).to_string())


if __name__ == "__main__":
    selftest() if "--selftest" in sys.argv else main()
