"""Guna new-cropland map from the yearly cropland probabilities of e109.
1. Year drift: each year's cropland logit is recalibrated against the forest department's 2015 survey, CULTIVATION (crop) against UNDER STOCK (forest), with one slope and offset per year.
2. New crop: recalibrated probability under 0.5 in each of 2017, 2018 and 2019, and 0.5 or more in at least 2 of 2023-25; patches of 0.5 ha or more. First crop year = first year from which it stays cropped.
3. Each patch pixel carries its 2015 survey class, so new encroachment (BLANK, UNDER STOCK, PLANTATION in 2015) is separated from land already cultivated then.
Usage: e110_newcrop_map.py"""
import json
import re
import sys

sys.path.insert(0, "E:/FIRE/forest_loss_monitor/scripts")

import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio
from rasterio.features import rasterize
from rasterio.transform import from_origin
from scipy.ndimage import label
from sklearn.linear_model import LogisticRegression

from common import *

NC = WORK / "newcrop"
OUTD = OUT / "guna_newcrop"
SURVEY = "E:/e_Netra/data/aoi/stock_2015.kml"
YS = list(range(2017, 2026))
CLS = {"CULTIVATION": 1, "PATTA": 2, "ENCROACHMENT": 3, "BLANK": 4, "UNDER STOCK": 5, "PLANTATION": 6}
WAS_FARM = (1, 2, 3)
MIN_PX = 50


def survey():
    g = gpd.read_file(SURVEY).to_crs(PROJ4)
    g["cls"] = g.Name.map(lambda s: next((v for k, v in CLS.items() if k in str(s).upper()), 0))
    print("2015 survey polygons by class:", g.groupby("cls").size().to_dict(), "| unparsed examples:", g[g.cls == 0].Name.head(5).tolist())
    return g[g.cls > 0]


def load_range(rng):
    d = NC / rng
    g = json.load(open(d / "grid.json"))
    P = np.zeros((9, g["ny"], g["nx"]), "uint8")
    have = np.zeros((g["ny"], g["nx"]), bool)
    for f in d.glob("*.npy"):
        i, j = map(int, f.stem.split("_"))
        a = np.load(f)
        P[:, i:i + a.shape[1], j:j + a.shape[2]] = a
        have[i:i + a.shape[1], j:j + a.shape[2]] = True
    return g, P, have


def logit(p):
    q = np.clip(p.astype("float32") / 200, .005, .995)
    return np.log(q / (1 - q))


def zone10(g):
    with rasterio.open(WORK / "zone_beat.tif") as s:
        tr = s.transform
        c0, r0 = int(round((g["x0"] - tr.c) / tr.a)), int(round((tr.f - g["y1"]) / -tr.e))
        z = s.read(1, window=((r0, r0 + g["ny"] // 3 + 2), (c0, c0 + g["nx"] // 3 + 2)))
    return np.repeat(np.repeat(z, 3, axis=0), 3, axis=1)[:g["ny"], :g["nx"]]


def main():
    OUTD.mkdir(parents=True, exist_ok=True)
    sv = survey()
    lk = pd.read_csv(OUT / "beat_lookup.csv")
    lk = lk[lk.Division == "Guna"].set_index("zone_id")
    ranges = sorted(p.name for p in NC.iterdir() if (p / "grid.json").exists())
    R, cal = {}, {y: ([], []) for y in YS}
    rng0 = np.random.default_rng(1)
    for rng in ranges:
        g, P, have = load_range(rng)
        tr = from_origin(g["x0"], g["y1"], 10, 10)
        s15 = rasterize([(geom, c) for geom, c in zip(sv.geometry, sv.cls)], out_shape=have.shape, transform=tr, fill=0, dtype="uint8")
        z = zone10(g)
        ok = have & np.isin(z, lk[lk.Range == rng].index.values)
        R[rng] = (g, P, ok, s15, z)
        for c, yv in ((1, 1), (5, 0)):
            rr, cc = np.nonzero(ok & (s15 == c))
            if len(rr):
                i = rng0.choice(len(rr), min(20000, len(rr)), replace=False)
                for k, y in enumerate(YS):
                    cal[y][0].append(logit(P[k, rr[i], cc[i]]))
                    cal[y][1].append(np.full(len(i), yv))
        print(rng, "forest ha", round(ok.sum() * .01), "| surveyed share", round(100 * (s15[ok] > 0).mean(), 1), "%", flush=True)
    M = {}
    for y in YS:
        x, t = np.concatenate(cal[y][0]), np.concatenate(cal[y][1])
        m = LogisticRegression(C=10, class_weight="balanced").fit(x[:, None], t)
        M[y] = (float(m.coef_[0, 0]), float(m.intercept_[0]))
        raw = (x >= 0)
        print(y, "raw: cultivation called crop", round(100 * raw[t == 1].mean()), "%, under stock called crop", round(100 * raw[t == 0].mean()), "% | recalibrated:",
              round(100 * (m.predict(x[:, None])[t == 1]).mean()), "% /", round(100 * (m.predict(x[:, None])[t == 0]).mean()), "% | slope", round(M[y][0], 2), "offset", round(M[y][1], 2), flush=True)
    json.dump(M, open(OUTD / "year_recalibration.json", "w"))
    px, tot = [], []
    for rng, (g, P, ok, s15, z) in R.items():
        C = np.stack([(M[y][0] * logit(P[k]) + M[y][1]) >= 0 for k, y in enumerate(YS)])
        base = ok & ~C[0] & ~C[1] & ~C[2]
        loose = base & (C[6:].sum(axis=0) >= 1)
        lab, _ = label(loose, structure=np.ones((3, 3)))
        loose_ha = (np.isin(lab, np.flatnonzero(np.bincount(lab.ravel()) >= MIN_PX)) & (lab > 0)).sum() * .01
        new = base & (C[6:].sum(axis=0) >= 2)
        lab, _ = label(new, structure=np.ones((3, 3)))
        new = np.isin(lab, np.flatnonzero(np.bincount(lab.ravel()) >= MIN_PX)) & (lab > 0)
        stay = np.flip(np.cumprod(np.flip(C, axis=0), axis=0), axis=0).astype(bool)        # cropped from this year to 2025 without a gap
        first = np.where(stay.any(axis=0), 2017 + np.argmax(stay, axis=0), 2025)
        first = np.where(new, first, 0).astype("int16")
        crop25 = ok & (C[6:].sum(axis=0) >= 2)
        tr = from_origin(g["x0"], g["y1"], 10, 10)
        with rasterio.open(OUTD / f"newcrop_{rng}.tif", "w", driver="GTiff", width=g["nx"], height=g["ny"], count=2, dtype="int16", crs=PROJ4, transform=tr, compress="deflate", nodata=0) as o:
            o.write(first, 1)
            o.write(np.where(new, s15, 0).astype("int16"), 2)
            o.descriptions = ("first_crop_year", "survey_2015_class")
        np.save(NC / rng / "new.npy", new)
        i = np.nonzero(new)
        px.append(pd.DataFrame(dict(Range=rng, zone_id=z[i], year=first[i], s15=s15[i])).value_counts().rename("px").reset_index())
        zz = z[ok]
        tot.append(pd.DataFrame(dict(Range=rng, zone_id=zz, crop_now=crop25[ok], crop_2017=(C[0] & C[1] & C[2])[ok], surveyed=s15[ok] > 0, farm_2015=np.isin(s15[ok], WAS_FARM))).groupby(["Range", "zone_id"]).agg(forest_ha=("crop_now", "size"), crop_2017_19_ha=("crop_2017", "sum"), crop_2023_25_ha=("crop_now", "sum"), surveyed_ha=("surveyed", "sum"), farm_2015_ha=("farm_2015", "sum")).reset_index())
        print(rng, "new crop ha: strict (2 of 3 years)", round(new.sum() * .01), "| loose (1 of 3 years)", round(loose_ha), flush=True)
    d = pd.concat(px, ignore_index=True)
    d["ha"] = d.px * .01
    d["Beat"] = d.zone_id.map(lk.Beat)
    inv = {v: k for k, v in CLS.items()}
    d["status_2015"] = d.s15.map(lambda c: inv.get(c, "not surveyed"))
    d["kind"] = np.where(d.s15.isin(WAS_FARM), "already farmed in 2015", np.where(d.s15 == 0, "not surveyed in 2015", "new encroachment since 2015"))
    T = pd.concat(tot, ignore_index=True)
    for c in T.columns[2:]:
        T[c] = T[c] * .01
    T["Beat"] = T.zone_id.map(lk.Beat)
    d.to_csv(OUTD / "newcrop_pixels_by_beat_year_class.csv", index=False)
    by_range = T.groupby("Range")[["forest_ha", "crop_2017_19_ha", "crop_2023_25_ha", "surveyed_ha", "farm_2015_ha"]].sum().join(d.pivot_table(index="Range", columns="kind", values="ha", aggfunc="sum", fill_value=0)).join(d.groupby("Range").ha.sum().rename("new_crop_ha"))
    by_range.loc["Guna"] = by_range.sum()
    by_range["new_crop_pct_of_forest"] = 100 * by_range.new_crop_ha / by_range.forest_ha
    by_beat = T.set_index(["Range", "Beat"])[["forest_ha", "crop_2017_19_ha", "crop_2023_25_ha"]].join(d.pivot_table(index=["Range", "Beat"], columns="kind", values="ha", aggfunc="sum", fill_value=0)).join(d.groupby(["Range", "Beat"]).ha.sum().rename("new_crop_ha")).fillna(0)
    by_beat = by_beat.join(d.pivot_table(index=["Range", "Beat"], columns="year", values="ha", aggfunc="sum", fill_value=0).add_prefix("first_crop_")).fillna(0).sort_values("new_crop_ha", ascending=False)
    by_year = d.pivot_table(index="year", columns="kind", values="ha", aggfunc="sum", fill_value=0)
    by_status = d.groupby("status_2015").ha.sum()
    for nm, t in (("guna_newcrop_by_range", by_range), ("guna_newcrop_by_beat", by_beat), ("guna_newcrop_by_year", by_year), ("guna_newcrop_by_2015_status", by_status)):
        t.round(1).to_csv(OUTD / f"{nm}.csv")
    pd.set_option("display.width", 260, "display.max_columns", 30)
    print(by_range.round(1).to_string())
    print(by_year.round(1).to_string())
    print(by_status.round(1).to_string())
    print(by_beat.round(1).head(15).iloc[:, :8].to_string())


if __name__ == "__main__":
    main()
