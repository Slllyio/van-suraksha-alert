"""Interim tables from finished chunks only, no GEE calls. Rates use the forest already covered as the denominator.
Compares the mapped rate with the point-based rule estimate, both state-wide and on the points inside the covered area. Usage: e42_interim.py"""
import json

import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio

from common import *
from zones import zone as zone_of

D = WORK / "map10m"
I = OUT / "interim"
CLS = {1: "clearing", 2: "tree_to_shrub", 3: "shrub_to_crop"}
PA = 0.01
RULE_BANDS = ["e_recent", "late", "s2c_a", "s2c_b"]


def main():
    I.mkdir(parents=True, exist_ok=True)
    t = pd.read_csv(WORK / "tiles.csv", keep_default_na=False).set_index("tile")
    with rasterio.open(WORK / "zone_beat.tif") as s:
        zb = s.read(1)
    with rasterio.open(WORK / "zone_district.tif") as s:
        zd = s.read(1)
    done = np.zeros(zb.shape, bool)
    fr = []
    files = sorted(D.glob("*.npz"))
    for f in files:
        tile, r, c = f.stem.split("_")
        r, c = int(r), int(c)
        s = t.loc[tile]
        a = np.load(f)
        h, w = a["cls"].shape
        done[s.row + r // 3:s.row + (r + h) // 3, s.col + c // 3:s.col + (c + w) // 3] = True
        rr, cc = np.arange(h) // 3 + s.row + r // 3, np.arange(w) // 3 + s.col + c // 3
        zz = zb[np.ix_(rr, cc)]
        i = np.nonzero((a["cls"] > 0) & (zz > 0))
        if len(i[0]):
            fr.append(pd.DataFrame(dict(zone_id=zz[i], dist_id=zd[np.ix_(rr, cc)][i], cls=a["cls"][i], year=a["yr"][i].astype(int) + 2000)).value_counts().rename("px").reset_index())
    d = pd.concat(fr).groupby(["zone_id", "dist_id", "cls", "year"], as_index=False).px.sum()
    d["ha"] = d.px * PA
    d["c"] = d.cls.map(CLS)
    b = gpd.read_parquet(WORK / "beats_albers.parquet")[["zone_id", "Division", "Range", "Beat"]]
    dist = gpd.read_parquet(WORK / "districts_albers.parquet")[["dist_id", "dtname"]]
    d = d.merge(b, on="zone_id", how="left").merge(dist, on="dist_id", how="left")
    d["forest_zone"] = d.Division.map(zone_of)
    d["state"] = "covered area"
    n = int(b.zone_id.max()) + 1
    all_b, cov_b = np.bincount(zb.ravel(), minlength=n) * PX_HA, np.bincount(zb[done], minlength=n) * PX_HA
    z = b.assign(forest_ha=all_b[b.zone_id], covered_ha=cov_b[b.zone_id], forest_zone=b.Division.map(zone_of), state="covered area")
    m = zb > 0
    dd = np.bincount(zd[m], minlength=len(dist) + 2) * PX_HA
    dc = np.bincount(zd[m & done], minlength=len(dist) + 2) * PX_HA
    areas = {"district": dist.assign(forest_ha=dd[dist.dist_id], covered_ha=dc[dist.dist_id])[["dtname", "forest_ha", "covered_ha"]]}
    out = {}
    for label, keys in (("state", ["state"]), ("forest_zone", ["forest_zone"]), ("district", ["dtname"]), ("division", ["Division"]), ("range", ["Division", "Range"])):
        w = d.pivot_table(index=keys + ["year"], columns="c", values="ha", aggfunc="sum", fill_value=0).reset_index()
        for c in CLS.values():
            w[c] = w.get(c, 0.0)
        w["total"] = w[list(CLS.values())].sum(axis=1)
        tot = w.groupby(keys)[list(CLS.values()) + ["total"]].sum().reset_index()
        ar = areas[label] if label in areas else z.groupby(keys, as_index=False)[["forest_ha", "covered_ha"]].sum()
        tot = ar.merge(tot, on=keys, how="left").fillna(0)
        tot["coverage_pct"] = (100 * tot.covered_ha / tot.forest_ha.replace(0, np.nan)).round(1)
        tot["partly_covered"] = tot.coverage_pct < 99.5
        tot["rate_pct_of_covered"] = (100 * tot.total / tot.covered_ha.replace(0, np.nan)).round(3)
        tot["rate_excl_shrub_to_crop"] = (100 * (tot.clearing + tot.tree_to_shrub) / tot.covered_ha.replace(0, np.nan)).round(3)
        tot = tot[tot.covered_ha > 0].sort_values("total", ascending=False).round(2)
        tot.to_csv(I / f"interim_by_{label}_total.csv", index=False)
        w.round(2).to_csv(I / f"interim_by_{label}_year_class.csv", index=False)
        out[label] = (w, tot)
    # point comparison: same rule, sampled at round-2 random points in a 50 m box
    k = pd.read_csv(OUT / "validation2" / "validation_key_DO_NOT_OPEN_BEFORE_LABELLING.csv").assign(pid=lambda x: x.sample_id + 200000)
    p = pd.read_csv(GT_POINTS).merge(k, on="pid")
    area = json.load(open(OUT / "validation2" / "strata_area_ha.json"))
    p["_w"] = p.stratum.map(area) / p.stratum.map(p.stratum.value_counts())
    p["f"] = (p[RULE_BANDS].fillna(0).max(axis=1) > 0) & (p.water.fillna(0) == 0)
    p["cov"] = done[p.row, p.col]
    state_rate = 100 * (p.f * p._w).sum() / p._w.sum()
    q = p[p["cov"]]
    cov_rate = 100 * (q.f * q._w).sum() / q._w.sum()
    total_cov, sta = out["state"][1].iloc[0], out["state"][0]
    res = dict(chunks=len(files), covered_ha=round(float(total_cov.covered_ha)), forest_ha=round(float(all_b[1:].sum())), coverage_pct=round(100 * float(total_cov.covered_ha) / float(all_b[1:].sum()), 1),
               mapped_ha=round(float(total_cov.total)), mapped_rate_pct=round(float(total_cov.rate_pct_of_covered), 3),
               point_state_ha=round(float((p.f * p._w).sum())), point_state_rate_pct=round(float(state_rate), 3),
               point_covered_rate_pct=round(float(cov_rate), 3), points_in_covered=int(len(q)), flagged_points_in_covered=int(q.f.sum()))
    json.dump(res, open(I / "interim_headline.json", "w"), indent=1)
    print(res)
    print(sta.round(0).to_string(index=False))
    print(total_cov[list(CLS.values()) + ["total", "rate_pct_of_covered", "rate_excl_shrub_to_crop"]].to_dict())
    print(out["forest_zone"][1].drop(columns=["forest_ha"]).to_string(index=False))
    for lab in ("division", "district"):
        print(out[lab][1].head(8)[[out[lab][1].columns[0], "covered_ha", "coverage_pct", "total", "rate_pct_of_covered"]].to_string(index=False))
    big = out["division"][1][out["division"][1].coverage_pct >= 50].sort_values("rate_pct_of_covered", ascending=False)
    print(big[["Division", "coverage_pct", "total", "rate_pct_of_covered"]].to_string(index=False))


GT_POINTS = ROOT / "ground_truth" / "enetra10m_points.csv"

if __name__ == "__main__":
    main()
