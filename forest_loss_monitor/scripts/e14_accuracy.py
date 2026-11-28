"""Stratified accuracy and area (Olofsson 2014) from visual labels of the validation sample.
Reference loss = L or D. T (visible then recovered) is also loss in the sensitivity run. Points are design-weighted by stratum.
Reads outputs/validation/labels_filled.csv if present (the reader's corrections), else prelabels.csv. Usage: e14_accuracy.py [--selftest]"""
import json
import os
import sys

import numpy as np
import pandas as pd

from common import OUT, WORK

D = OUT / os.environ.get("FLM_VAL", "validation")
MAIN = ["clearing", "partial"]
B = 2000


def weights(df, area):
    n = df.stratum.map(df.stratum.value_counts())
    return df.stratum.map(area) / n


def metrics(y, m, w):
    tp, fp, fn = (w * y * m).sum(), (w * (1 - y) * m).sum(), (w * y * (1 - m)).sum()
    p = tp / (tp + fp) if tp + fp else np.nan
    r = tp / (tp + fn) if tp + fn else np.nan
    return p, r, (2 * p * r / (p + r) if p + r else np.nan)


def boot(df, area, ycol, mcol, seed=1):
    """95% range by resampling inside each stratum. A subgroup uses only its own points, with the full-design weights."""
    rng = np.random.default_rng(seed)
    y, m, st = df[ycol].values, df[mcol].values, df.stratum.values
    idx = {s: np.flatnonzero(st == s) for s in pd.unique(st)}
    w0 = df._w.values
    out = []
    for _ in range(B):
        take = np.concatenate([rng.choice(i, len(i)) for i in idx.values()])
        out.append(metrics(y[take], m[take], w0[take]))
    a = np.array(out)
    with np.errstate(all="ignore"):
        lo, hi = np.nanpercentile(a, 2.5, axis=0), np.nanpercentile(a, 97.5, axis=0)
    return lo, hi


def table(df, area, groups, ycol="real"):
    rows = []
    for gname, sub in groups:
        for label, mcol in (("AlphaEarth map", "m_map"), ("CCDC", "m_ccdc"), ("Hansen", "m_hansen")):
            s = sub.dropna(subset=[mcol])
            if not len(s) or not s[ycol].sum():
                rows.append(dict(group=gname, method=label, n=len(s), ref_loss_n=int(s[ycol].sum())))
                continue
            p, r, f = metrics(s[ycol].values, s[mcol].values, s._w.values)
            lo, hi = boot(s, area, ycol, mcol)
            rows.append(dict(group=gname, method=label, n=len(s), ref_loss_n=int(s[ycol].sum()), precision=p, p_lo=lo[0], p_hi=hi[0],
                             recall=r, r_lo=lo[1], r_hi=hi[1], f1=f, f1_lo=lo[2], f1_hi=hi[2]))
    return pd.DataFrame(rows).round(3)


def area_estimate(df, area, ycol):
    """Stratified estimator of true loss area and its standard error."""
    tot, var = 0.0, 0.0
    for s, a in area.items():
        y = df.loc[df.stratum == s, ycol].astype(float)
        tot += a * y.mean()
        var += a ** 2 * y.var(ddof=1) / len(y)
    return tot, 1.96 * np.sqrt(var)


def selftest():
    area = {"clearing": 100.0, "stable_tree": 900.0}
    d = pd.DataFrame(dict(stratum=["clearing"] * 10 + ["stable_tree"] * 10, real=[1] * 8 + [0] * 2 + [1] + [0] * 9))
    t, ci = area_estimate(d, area, "real")
    assert abs(t - (100 * .8 + 900 * .1)) < 1e-9 and ci > 0
    d["_w"] = weights(d, area)
    d["m"] = (d.stratum == "clearing").astype(int)
    p, r, f = metrics(d.real.values, d.m.values, d._w.values)
    assert abs(p - .8) < 1e-9 and abs(r - 80 / 170) < 1e-9
    print("selftest ok")


def main():
    area = json.load(open(D / "strata_area_ha.json"))
    k = pd.read_csv(D / "validation_key_DO_NOT_OPEN_BEFORE_LABELLING.csv")
    f = D / "labels_filled.csv" if (D / "labels_filled.csv").exists() else D / "prelabels.csv"
    lab = pd.read_csv(f)
    lab = lab.rename(columns={"label_change": "label"})[["sample_id", "label"]]
    print("labels from", f.name)
    a = pd.read_csv(D / "attributes.csv")
    df = k.merge(lab, on="sample_id").merge(a, on="sample_id", how="left")
    c = D / "ccdc.csv"
    df = df.merge(pd.read_csv(c), on="sample_id", how="left") if c.exists() else df.assign(ccdc_loss=np.nan, n_breaks=np.nan)
    df["real"] = df.label.isin(list("LD")).astype(int)
    df["real_t"] = df.label.isin(list("LDT")).astype(int)
    df["_w"] = weights(df, area)
    df["m_map"] = df.stratum.isin(MAIN).astype(int)
    if (WORK / "water.npy").exists() and "--water" in sys.argv:
        w = np.load(WORK / "water.npy", mmap_mode="r")
        df["water"] = np.asarray(w[df.row.values, df.col.values])
        df["m_map"] = (df.stratum.isin(MAIN) & ~df.water).astype(int)   # same points, same labels; only the map changes
        print("mapped points falling in the water mask", int((df.stratum.isin(MAIN) & df.water).sum()))
    df["m_map_small"] = df.stratum.isin(MAIN + ["small"]).astype(int)
    df["m_hansen"] = df.hansen_year.between(18, 25).astype(int)
    # a point with no CCDC result stays missing; a successful run with no break counts as "no loss"
    df["m_ccdc"] = np.where(df.ran == 1, df.ccdc_loss, np.nan) if "ran" in df else np.nan
    df.to_csv(D / "validation_joined.csv", index=False)
    print(pd.crosstab(df.stratum, df.label).to_string())

    groups = [("ALL", df)]
    for col in ("forest_zone", "canopy_class", "slope_class", "aspect_class"):
        groups += [(f"{col}={v}", g) for v, g in df.groupby(col, observed=True)]
    t = table(df, area, groups)
    t.to_csv(D / "accuracy_by_stratum.csv", index=False)
    print(t[t.group == "ALL"].to_string(index=False))
    print(t[t.method == "AlphaEarth map"][["group", "n", "ref_loss_n", "precision", "p_lo", "p_hi", "recall", "r_lo", "r_hi", "f1"]].to_string(index=False))
    t2 = table(df, area, [("ALL incl. recovered as loss", df)], "real_t")
    print(t2.to_string(index=False))

    mapped = sum(area[s] for s in MAIN)
    rows = []
    for nm, y in (("loss = L or D", "real"), ("loss = L, D or T", "real_t")):
        tot, ci = area_estimate(df, area, y)
        rows.append(dict(reference=nm, mapped_ha=round(mapped), adjusted_ha=round(tot), ci95_ha=round(ci), low=round(tot - ci), high=round(tot + ci)))
    res = pd.DataFrame(rows)
    res.to_csv(D / "area_estimate.csv", index=False)
    print(res.to_string(index=False))
    for s in area:
        g = df[df.stratum == s]
        print(s, "n", len(g), "share real %.2f" % g.real.mean(), "area ha", round(area[s]), "implied loss ha", round(area[s] * g.real.mean()))
    cl = df[df.stratum == "clearing"]
    print("clearing stratum labelled L: %.2f, L or D %.2f" % ((cl.label == "L").mean(), cl.real.mean()))


if __name__ == "__main__":
    selftest() if "--selftest" in sys.argv else main()
