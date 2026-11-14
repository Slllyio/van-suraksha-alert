"""New farmland per Guna range and beat from the yearly 5-class maps of e111, with active crop and fallow counted apart.
New farmland: not crop or fallow in each of 2017-19, crop or fallow in at least 2 of 2023-25, patches of 0.5 ha or more.
Each pixel is then split by how often it is active crop in 2023-25: 2-3 years (active crop), 1 year (crop once), 0 years (fallow only).
Every figure is given before the 2015 survey mask and after it (BLANK, UNDER STOCK, PLANTATION in 2015 only). Usage: e112_newcrop5.py [Range]"""
import json
import sys

sys.path.insert(0, "E:/FIRE/forest_loss_monitor/scripts")
ARGS = sys.argv[1:]
sys.argv = sys.argv[:1]

import numpy as np
import pandas as pd
import pyproj
import rasterio
from rasterio.features import rasterize
from rasterio.transform import from_origin
from scipy.ndimage import label

from common import *
from e110_newcrop_map import MIN_PX, survey, zone10

C5 = WORK / "class5"
OUTD = OUT / "guna_newcrop5"
NEW_2015 = (4, 5, 6)
KIND = {2: "active_crop", 3: "active_crop", 1: "crop_once", 0: "fallow_only"}


def load(rng):
    d = C5 / rng
    g = json.load(open(d / "grid.json"))
    K = np.full((9, g["ny"], g["nx"]), 255, "uint8")
    for f in d.glob("*.npy"):
        i, j = map(int, f.stem.split("_"))
        a = np.load(f)
        K[:, i:i + a.shape[1], j:j + a.shape[2]] = a
    return g, K


def main():
    OUTD.mkdir(parents=True, exist_ok=True)
    sv = survey()
    lk = pd.read_csv(OUT / "beat_lookup.csv")
    lk = lk[lk.Division == "Guna"].set_index("zone_id")
    rows, patches = [], []
    for rng in sorted(p.name for p in C5.iterdir() if (p / "grid.json").exists()):
        if ARGS and rng != ARGS[0]:
            continue
        g, K = load(rng)
        tr = from_origin(g["x0"], g["y1"], 10, 10)
        s15 = rasterize([(geom, c) for geom, c in zip(sv.geometry, sv.cls)], out_shape=K.shape[1:], transform=tr, fill=0, dtype="uint8")
        z = zone10(g)
        ok = (K[0] < 255) & np.isin(z, lk[lk.Range == rng].index.values)
        farm, crop = K <= 1, K == 0
        new = ok & ~farm[:3].any(axis=0) & (farm[6:].sum(axis=0) >= 2)
        lab, _ = label(new, structure=np.ones((3, 3)))
        n = np.bincount(lab.ravel())
        new = (n[lab] >= MIN_PX) & (lab > 0)
        ncrop = crop[6:].sum(axis=0)
        stay = np.flip(np.cumprod(np.flip(farm, axis=0), axis=0), axis=0).astype(bool)        # farmed from this year to 2025 without a gap
        first = np.where(stay.any(axis=0), 2017 + np.argmax(stay, axis=0), 2025)
        i = np.nonzero(new)
        masked = np.isin(s15[i], NEW_2015)
        rows.append(pd.DataFrame(dict(Range=rng, zone_id=z[i], kind=pd.Series(ncrop[i]).map(KIND).values, masked=masked, year=first[i])).value_counts().rename("px").reset_index())
        p = pd.DataFrame(dict(lab=lab[i], r=i[0], c=i[1], zone_id=z[i], crop=ncrop[i] >= 2, m=masked, year=first[i])).groupby("lab").agg(
            ha=("r", "size"), r=("r", "mean"), c=("c", "mean"), zone_id=("zone_id", lambda s: s.mode().iloc[0]), active_crop_share=("crop", "mean"), new_since_2015_share=("m", "mean"), first_year=("year", "median"))
        p["ha"] *= .01
        p["x"], p["y_m"] = g["x0"] + (p.c + .5) * 10, g["y1"] - (p.r + .5) * 10
        patches.append(p.assign(Range=rng).drop(columns=["r", "c"]))
        with rasterio.open(OUTD / f"newfarm_{rng}.tif", "w", driver="GTiff", width=g["nx"], height=g["ny"], count=3, dtype="uint8", crs=PROJ4, transform=tr, compress="deflate", nodata=0) as o:
            o.write(np.where(new, first - 2000, 0).astype("uint8"), 1)
            o.write(np.where(new, ncrop + 1, 0).astype("uint8"), 2)
            o.write(np.where(new, s15, 0).astype("uint8"), 3)
            o.descriptions = ("first_farm_year_minus_2000", "active_crop_years_2023_25_plus_1", "survey_2015_class")
        print(rng, "new farmland ha", round(new.sum() * .01), flush=True)
    d = pd.concat(rows, ignore_index=True)
    d["ha"] = d.px * .01
    d["Beat"] = d.zone_id.map(lk.Beat)

    def wide(keys):
        a = d.pivot_table(index=keys, columns="kind", values="ha", aggfunc="sum", fill_value=0).add_prefix("all_")
        b = d[d.masked].pivot_table(index=keys, columns="kind", values="ha", aggfunc="sum", fill_value=0).add_prefix("new2015_")
        t = a.join(b).fillna(0)
        t.insert(0, "all_total", a.sum(axis=1))
        t["new2015_total"] = b.sum(axis=1).reindex(t.index).fillna(0)
        return t

    by_range = wide("Range")
    by_range.loc["Guna"] = by_range.sum()
    by_beat = wide(["Range", "Beat"]).sort_values("new2015_total", ascending=False)
    by_year = wide("year")
    P = pd.concat(patches, ignore_index=True)
    P["Beat"] = P.zone_id.map(lk.Beat)
    P["lon"], P["lat"] = pyproj.Transformer.from_crs(PROJ4, 4326, always_xy=True).transform(P.x.values, P.y_m.values)
    P = P.sort_values("ha", ascending=False)[["Range", "Beat", "ha", "lat", "lon", "first_year", "active_crop_share", "new_since_2015_share"]]
    for nm, t in (("by_range", by_range), ("by_beat", by_beat), ("by_first_year", by_year)):
        t.round(1).to_csv(OUTD / f"guna_newfarm_{nm}.csv")
    P.round(5).to_csv(OUTD / "guna_newfarm_patches_ranked.csv", index=False)
    pd.set_option("display.width", 260, "display.max_columns", 30)
    print(by_range.round(0).to_string())
    print(by_year.round(0).to_string())
    print(P.head(10).round(4).to_string())


if __name__ == "__main__":
    main()
