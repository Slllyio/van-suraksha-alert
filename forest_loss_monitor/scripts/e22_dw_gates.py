"""Dynamic World hard gates on AlphaEarth, per the research-thread spec. Reference and weights as in round 2; gates are not fitted to labels.
Water, was-forest, fallow and real-change are reported separately and in order, overall and by zone.
Loss year per point: map year where mapped, else the year of top model score from emb_v3. Usage: e22_dw_gates.py [--selftest]"""
import json
import sys

import numpy as np
import pandas as pd
import rasterio

from common import *
from e14_accuracy import boot, metrics
from e19_ts_eval import load as load_points
from zones import zone as zone_of

D = OUT / "timeseries"
Y0, Y1 = 2017, 2025
WOODY_MIN, TREES_MIN, FALLOW_MAX, RISE, WATER_MAX, GSW_MAX = 0.40, 0.225, 0.30, 0.15, 0.20, 5.0
CLASSES = ["water", "trees", "grass", "shrub_and_scrub", "crops", "built", "bare"]


def v(r, s, y, c):
    return r.get(f"{s}{y}_{c}", np.nan)


def mean_years(r, s, c, ys):
    a = [v(r, s, y, c) for y in ys]
    return float(np.nanmean(a)) if np.isfinite(a).any() else np.nan


def gates(r, y):
    """Dict of pass flags at one point, for loss year y. r: mapping of band name to value."""
    pre = [yy for yy in (y - 2, y - 1) if Y0 <= yy <= Y1] or [Y0]
    post = [yy for yy in (y + 1, y + 2) if Y0 <= yy <= Y1] or [Y1]
    water = [v(r, s, yy, "water") for s in "mr" for yy in range(Y0, Y1 + 1)]
    g1 = not (np.nanmax(water) >= WATER_MAX if np.isfinite(water).any() else False) and not r.get("gsw_occ", 0) >= GSW_MAX
    m_all = {c: mean_years(r, "m", c, pre) for c in CLASSES}
    woody = m_all["trees"] + m_all["shrub_and_scrub"]
    rabi_crops = mean_years(r, "r", "crops", pre)
    others = [m_all[c] for c in CLASSES if c not in ("trees", "shrub_and_scrub")]
    g2 = bool(woody >= WOODY_MIN and all(woody >= o for o in others if np.isfinite(o)) and m_all["trees"] >= TREES_MIN and m_all["trees"] > rabi_crops)
    g3 = not rabi_crops >= FALLOW_MAX
    both = []
    for yy in post:
        m = {c: v(r, "m", yy, c) for c in CLASSES}
        rb = {c: v(r, "r", yy, c) for c in ("crops", "built", "bare")}
        both.append(any(np.nanmax([m[c], rb[c]]) - np.nanmax([m_all[c], mean_years(r, "r", c, pre)]) >= RISE for c in ("bare", "built", "crops")))
    post_w = np.nanmean([v(r, "m", yy, "trees") + v(r, "m", yy, "shrub_and_scrub") for yy in post])
    post_open = np.nanmean([v(r, "m", yy, "bare") + v(r, "m", yy, "grass") for yy in post])
    pre_open = m_all["bare"] + m_all["grass"]
    g4 = bool(all(both) or (woody - post_w >= RISE and post_open > pre_open))
    return dict(g_water=bool(g1), g_forest=g2, g_fallow=bool(g3), g_change=g4)


def score_year(df):
    """Top-score year per point from the state rasters, for points not mapped."""
    t = pd.read_csv(WORK / "tiles.csv", keep_default_na=False)
    out = np.zeros(len(df), "int32")
    for s in t.itertuples():
        i = np.flatnonzero((df.row >= s.row) & (df.row < s.row + s.h) & (df.col >= s.col) & (df.col < s.col + s.w))
        if not len(i):
            continue
        with rasterio.open(WORK / "emb_v3" / f"{s.tile}.tif") as src:
            names = list(src.descriptions)
            z = src.read([k + 1 for k, n in enumerate(names) if n.startswith("z")])
        yrs = np.array([int(n[1:]) for n in names if n.startswith("z")])
        out[i] = yrs[z[:, df.row.values[i] - s.row, df.col.values[i] - s.col].argmax(0)]
    return out


def selftest():
    r = {f"m{y}_{c}": 0.0 for y in range(Y0, Y1 + 1) for c in CLASSES}
    r.update({f"r{y}_{c}": 0.0 for y in range(Y0, Y1 + 1) for c in CLASSES})
    for y in range(Y0, 2021):
        r[f"m{y}_trees"], r[f"m{y}_shrub_and_scrub"] = .5, .2
    for y in range(2021, Y1 + 1):
        r[f"m{y}_bare"], r[f"m{y}_trees"] = .5, .1
    g = gates(r, 2021)
    assert all(g.values()), g
    w = dict(r, **{"m2019_water": .3})
    assert not gates(w, 2021)["g_water"]
    assert not gates(dict(r, gsw_occ=6), 2021)["g_water"]
    f = {k: (0.0 if "trees" in k or "shrub" in k else val) for k, val in r.items()}
    assert not gates(f, 2021)["g_forest"]
    assert not gates(dict(r, **{f"r{y}_crops": .4 for y in range(Y0, 2021)}), 2021)["g_fallow"]
    stable = {k: val for k, val in r.items()}
    for y in range(2021, Y1 + 1):
        stable[f"m{y}_bare"], stable[f"m{y}_trees"], stable[f"m{y}_shrub_and_scrub"] = 0, .5, .2
    assert not gates(stable, 2021)["g_change"]
    print("selftest ok")


def row(g, name, q, col, area):
    y, m, w = q.real.values, q[col].astype(int).values, q._w.values
    p, r, f = metrics(y, m, w)
    lo, hi = boot(q.assign(_m=m), area, "real", "_m") if y.sum() else ((np.nan,) * 3, (np.nan,) * 3)
    return dict(group=g, rule=name, n=len(q), ref_loss_n=int(y.sum()), precision=round(p, 3), p_lo=round(lo[0], 3), p_hi=round(hi[0], 3),
                recall=round(r, 3), r_lo=round(lo[1], 3), r_hi=round(hi[1], 3), f1=round(f, 3), flagged_ha=round(float((m * w).sum())))


def main():
    df = load_points()
    df["forest_zone"] = df.Division.map(zone_of)
    dw = pd.read_csv(D / "dw_1020.csv")
    df = df.merge(dw, on="sample_id", how="left")
    df["yr"] = np.where(df.map_year > 0, df.map_year, score_year(df))
    df.loc[df.yr == 0, "yr"] = 2021
    G = pd.DataFrame([gates(r, int(r["yr"])) for r in df.to_dict("records")], index=df.index)
    df = pd.concat([df, G], axis=1)
    area = {1: json.load(open(OUT / "validation" / "strata_area_ha.json")), 2: json.load(open(OUT / "validation2" / "strata_area_ha.json"))}
    res = []
    for rnd in (1, 2):
        d = df[df["round"] == rnd].copy()
        d["base"] = d.ae == 1
        steps = [("AlphaEarth map", "base")]
        for name, c in (("+ water only", "g_water"), ("+ was-forest only", "g_forest"), ("+ fallow only", "g_fallow"), ("+ real change only", "g_change")):
            d[c + "_o"] = d.base & d[c]
            steps.append((name, c + "_o"))
        d["seq"] = d.base & d.g_water & d.g_forest & d.g_fallow & d.g_change
        d["seq3"] = d.base & d.g_water & d.g_forest & d.g_fallow
        steps += [("+ water, forest, fallow", "seq3"), ("+ all four gates", "seq")]
        groups = [("ALL", d), ("deciduous (teak + mixed dry)", d[d.forest_zone.isin(["teak_belt", "mixed_dry_deciduous"])])] + [(z, g) for z, g in d.groupby("forest_zone")]
        for g, q in groups:
            for name, c in steps:
                res.append(dict(row(g, name, q, c, area[rnd]), round=rnd))
    t = pd.DataFrame(res)
    t.to_csv(D / "dw_gates_results.csv", index=False)
    print(t[t["round"] == 2].drop(columns=["round", "f1"]).to_string(index=False))
    print(t[(t["round"] == 1) & (t.group == "ALL")][["rule", "precision", "recall", "flagged_ha"]].to_string(index=False))
    r = df[(df["round"] == 2) & (df.ae == 1)]
    print("mapped, by label: pass all gates")
    print(pd.crosstab(r.label, r.g_water & r.g_forest & r.g_fallow & r.g_change).to_string())
    print(pd.crosstab(r.label, r.g_forest).to_string())
    print("missing dw share", float(df.filter(like="m2020_trees").isna().mean().iloc[0]))
    df[["sample_id", "round", "yr", "g_water", "g_forest", "g_fallow", "g_change"]].to_csv(D / "dw_gate_flags.csv", index=False)


if __name__ == "__main__":
    selftest() if "--selftest" in sys.argv else main()
