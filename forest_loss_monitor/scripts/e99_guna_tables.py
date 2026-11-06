"""Guna division tables from the finished chunks of the state 10 m rule map, no Earth Engine calls. Per range and beat: recorded forest, how much of it is covered, mapped loss before
and after the time-series filter (NDVI and NBR fall >= 0.15 on 2 px in the 5 x 5 box, the setting scored 78% precision / 45% recall on the owner's reference), by year and class.
Usage: e99_guna_tables.py"""
import sys

sys.path.insert(0, "E:/FIRE/forest_loss_monitor/scripts")

import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio

from common import *
from e33_map10m import D
from e53_ts_chunks import OUTD
from e54_recommended import CLS, layers

OUTG = OUT / "guna_tables"
PA = .01


def main():
    OUTG.mkdir(parents=True, exist_ok=True)
    t = pd.read_csv(WORK / "tiles.csv", keep_default_na=False).set_index("tile")
    with rasterio.open(WORK / "zone_beat.tif") as src:
        zb = src.read(1)
    b = gpd.read_parquet(WORK / "beats_albers.parquet")
    g = b[b.Division == "Guna"][["zone_id", "Range", "Beat"]]
    ids = set(g.zone_id)
    done10 = np.zeros(zb.shape, bool)
    donets = np.zeros(zb.shape, bool)
    px = []
    for f in sorted(D.glob("*.npz")):
        tile, r, c = f.stem.split("_")
        r, c = int(r), int(c)
        s = t.loc[tile]
        a = np.load(f)
        h, w = a["cls"].shape
        rr, cc = np.arange(h) // 3 + s.row + r // 3, np.arange(w) // 3 + s.col + c // 3
        zz = zb[np.ix_(rr, cc)]
        if not np.isin(zz, list(ids)).any():
            continue
        done10[s.row + r // 3:s.row + (r + h) // 3, s.col + c // 3:s.col + (c + w) // 3] = True
        hit = (a["cls"] > 0) & np.isin(zz, list(ids))
        has_ts = (OUTD / f.name).exists()
        if has_ts:
            donets[s.row + r // 3:s.row + (r + h) // 3, s.col + c // 3:s.col + (c + w) // 3] = True
            s0 = np.load(OUTD / f.name)
            rec = layers(a, s0)[3] if len(s0["r"]) else np.zeros_like(hit)
        else:
            rec = np.zeros_like(hit)
        i = np.nonzero(hit)
        if len(i[0]):
            px.append(pd.DataFrame(dict(zone_id=zz[i], cls=a["cls"][i], year=a["yr"][i].astype(int) + 2000, rec=rec[i], ts_done=has_ts)).value_counts().rename("px").reset_index())
    n = int(b.zone_id.max()) + 1
    forest = np.bincount(zb.ravel(), minlength=n) * PX_HA
    cov = np.bincount(zb[done10], minlength=n) * PX_HA
    covts = np.bincount(zb[donets], minlength=n) * PX_HA
    g = g.assign(forest_ha=forest[g.zone_id], covered_ha=cov[g.zone_id], filter_covered_ha=covts[g.zone_id])
    d = pd.concat(px).groupby(["zone_id", "cls", "year", "rec", "ts_done"], as_index=False).px.sum().merge(g[["zone_id", "Range", "Beat"]], on="zone_id")
    d["ha"], d["c"] = d.px * PA, d.cls.map(CLS)
    d.to_csv(OUTG / "guna_pixels_by_beat_year_class.csv", index=False)

    def table(keys):
        a = g.groupby(keys)[["forest_ha", "covered_ha", "filter_covered_ha"]].sum()
        u = d.groupby(keys).ha.sum().rename("mapped_ha")
        uf = d[d.ts_done].groupby(keys).ha.sum().rename("mapped_ha_where_filtered")
        rc = d[d.rec].groupby(keys).ha.sum().rename("recommended_ha")
        o = a.join(u).join(uf).join(rc).fillna(0)
        o["covered_pct"] = (100 * o.covered_ha / o.forest_ha).round(1)
        o["recommended_pct_of_covered_forest"] = (100 * o.recommended_ha / o.filter_covered_ha.where(o.filter_covered_ha > 0)).round(2)
        return o.round(1)

    rng, beat = table(["Range"]), table(["Range", "Beat"])
    tot = table([]) if False else pd.DataFrame([rng.sum(numeric_only=True)], index=["Guna"])
    tot["covered_pct"] = (100 * tot.covered_ha / tot.forest_ha).round(1)
    tot["recommended_pct_of_covered_forest"] = (100 * tot.recommended_ha / tot.filter_covered_ha).round(2)
    yr = d[d.rec].pivot_table(index="year", columns="c", values="ha", aggfunc="sum", fill_value=0).round(1)
    yr_r = d[d.rec].pivot_table(index="Range", columns="year", values="ha", aggfunc="sum", fill_value=0).round(1)
    cl_r = d[d.rec].pivot_table(index="Range", columns="c", values="ha", aggfunc="sum", fill_value=0).round(1)
    for nm, x in (("guna_total", tot), ("guna_by_range", rng), ("guna_by_beat", beat), ("guna_recommended_by_year_class", yr), ("guna_recommended_by_range_year", yr_r), ("guna_recommended_by_range_class", cl_r)):
        x.to_csv(OUTG / f"{nm}.csv")
    pd.set_option("display.width", 260, "display.max_columns", 30)
    print(tot.to_string())
    print(rng.to_string())
    print(yr.to_string())
    print(yr_r.to_string())
    print(cl_r.to_string())
    print(beat.sort_values("recommended_ha", ascending=False).head(20).to_string())
    print("beats", len(beat), "with any coverage", int((beat.covered_ha > 0).sum()), "fully covered", int((beat.covered_pct >= 99).sum()))


if __name__ == "__main__":
    main()
