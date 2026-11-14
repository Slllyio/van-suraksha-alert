"""Score the Bamori feature map with the saved embedding model, keep recorded forest of the range, and turn flagged pixels into patches of at least 0.5 ha.
Two settings: stage 1 (90% area-weighted recall on the reference) and strict (70%), thresholds from e84 on held-out scores. Writes a GeoTIFF, patch GeoJSON and a beat table.
Then draws the blind check sample: strict patches, stage-1-only patches and unflagged forest points, mixed under random codes. Usage: e98_cc_mapscore.py score | sample"""
import json
import sys

sys.path.insert(0, "E:/FIRE/forest_loss_monitor/scripts")

import geopandas as gpd
import joblib
import numpy as np
import pandas as pd
import rasterio
from rasterio.features import shapes
from rasterio.transform import from_origin
from scipy.ndimage import label
from shapely.geometry import shape

from common import *
from e97_cc_map import D, MODEL, NAMES

OUTD = OUT / "guna_bamori_map"
MIN_PX = 50                      # 0.5 ha at 10 m
SETTINGS = {"stage1": .9, "strict": .7}
SEED = 20261110


def mosaic():
    g = json.load(open(D / "grid.json"))
    F = np.full((len(NAMES), g["ny"], g["nx"]), np.nan, "float32")
    for f in D.glob("*.npy"):
        i, j = map(int, f.stem.split("_"))
        a = np.load(f)
        F[:, i:i + a.shape[1], j:j + a.shape[2]] = a
    return F, g


def forest_mask(g):
    """Recorded forest of the Bamori beats, from the 30 m zone raster, repeated to 10 m."""
    lk = pd.read_csv(OUT / "beat_lookup.csv")
    ids = lk[(lk.Division == "Guna") & (lk.Range == "Bamori")].zone_id.values
    with rasterio.open(WORK / "zone_beat.tif") as s:
        tr = s.transform
        c0, r0 = int(round((g["x0"] - tr.c) / tr.a)), int(round((tr.f - g["y1"]) / -tr.e))
        z = s.read(1, window=((r0, r0 + g["ny"] // 3 + 2), (c0, c0 + g["nx"] // 3 + 2)))
    z10 = np.repeat(np.repeat(z, 3, axis=0), 3, axis=1)[:g["ny"], :g["nx"]]
    return np.isin(z10, ids), z10


def score():
    OUTD.mkdir(parents=True, exist_ok=True)
    F, g = mosaic()
    m = joblib.load(MODEL)["scalars"]            # written by e84 on this machine
    forest, zone = forest_mask(g)
    ok = forest & np.isfinite(F).all(axis=0)
    s = np.full(ok.shape, np.nan, "float32")
    s[ok] = m["model"].decision_function(F[:, ok].T)
    tr = from_origin(g["x0"], g["y1"], 10, 10)
    year = (2017 + np.round(F[NAMES.index("brk")])).astype("float32")
    cls = np.zeros(ok.shape, "uint8")
    rows, polys = [], []
    for k, (nm, tg) in enumerate(SETTINGS.items(), start=1):
        flag = ok & (s >= m["thresholds"][tg])
        lab, n = label(flag, structure=np.ones((3, 3)))
        size = np.bincount(lab.ravel())
        keep = np.isin(lab, np.flatnonzero(size >= MIN_PX)) & (lab > 0)
        cls[keep] = k
        rows.append(dict(setting=nm, threshold=round(m["thresholds"][tg], 3), forest_ha=round(ok.sum() * .01), flagged_ha_any_size=round(flag.sum() * .01), flagged_ha_patches_0_5ha=round(keep.sum() * .01),
                         patches=int((size[1:] >= MIN_PX).sum()), share_of_forest_pct=round(100 * keep.sum() / ok.sum(), 2)))
        lab2, _ = label(keep, structure=np.ones((3, 3)))
        for geom, v in shapes(lab2.astype("int32"), mask=lab2 > 0, transform=tr, connectivity=8):
            px = lab2 == int(v)
            polys.append(dict(setting=nm, patch=int(v), ha=round(px.sum() * .01, 2), mean_score=round(float(s[px].mean()), 3), year=int(np.median(year[px])), geometry=shape(geom)))
    t = pd.DataFrame(rows)
    print(t.to_string())
    t.to_csv(OUTD / "bamori_area.csv", index=False)
    P = gpd.GeoDataFrame(polys, crs=PROJ4)
    P.to_file(OUTD / "bamori_flags.geojson", driver="GeoJSON")
    lk = pd.read_csv(OUT / "beat_lookup.csv").set_index("zone_id").Beat
    beat = pd.DataFrame(dict(beat=lk.reindex(zone[ok]).values, s1=cls[ok] >= 1, strict=cls[ok] == 2)).groupby("beat").agg(forest_ha=("s1", "size"), stage1_ha=("s1", "sum"), strict_ha=("strict", "sum"))
    beat = (beat * .01).round(1).assign(strict_pct=lambda q: (100 * q.strict_ha / q.forest_ha).round(2)).sort_values("strict_ha", ascending=False)
    beat.to_csv(OUTD / "bamori_by_beat.csv")
    print(beat.head(10).to_string())
    print(P.groupby(["setting", "year"]).ha.sum().round(1).unstack(0).to_string())
    with rasterio.open(OUTD / "bamori_change.tif", "w", driver="GTiff", width=g["nx"], height=g["ny"], count=2, dtype="float32", crs=PROJ4, transform=tr, compress="deflate", nodata=np.nan) as o:
        o.write(s, 1)
        o.write(np.where(cls > 0, year, np.nan).astype("float32"), 2)
        o.descriptions = ("score", "break_year_where_flagged")
    np.save(WORK / "cc_map_bamori_cls.npy", cls)
    np.save(WORK / "cc_map_bamori_ok.npy", ok)


def sample():
    """Blind check: 40 strict patches, 30 stage-1-only patches, 30 unflagged forest pixels. One point per patch, inside it."""
    g = json.load(open(D / "grid.json"))
    P = gpd.read_file(OUTD / "bamori_flags.geojson")
    rng = np.random.default_rng(SEED)
    strict = P[P.setting == "strict"]
    s1 = P[P.setting == "stage1"]
    s1_only = s1[~s1.geometry.intersects(strict.union_all())]
    a = strict.sample(min(40, len(strict)), random_state=SEED)
    b = s1_only.sample(min(30, len(s1_only)), random_state=SEED)
    cls, ok = np.load(WORK / "cc_map_bamori_cls.npy"), np.load(WORK / "cc_map_bamori_ok.npy")
    rr, cc = np.nonzero(ok & (cls == 0))
    i = rng.choice(len(rr), 30, replace=False)
    pts = [dict(group="strict", ha=r.ha, year=r.year, x=r.geometry.representative_point().x, y_m=r.geometry.representative_point().y) for r in a.itertuples()]
    pts += [dict(group="stage1 only", ha=r.ha, year=r.year, x=r.geometry.representative_point().x, y_m=r.geometry.representative_point().y) for r in b.itertuples()]
    pts += [dict(group="not flagged", ha=np.nan, year=np.nan, x=g["x0"] + (c + .5) * 10, y_m=g["y1"] - (r + .5) * 10) for r, c in zip(rr[i], cc[i])]
    k = pd.DataFrame(pts)
    k["code"] = rng.permutation(len(k)) + 1
    k["cid"] = 900000 + k.code
    k.sort_values("code").to_csv(ROOT / "ground_truth" / "bamori_map_key_DO_NOT_OPEN_BEFORE_LABELLING.csv", index=False)
    print(k.group.value_counts().to_dict(), "strict patches available", len(strict), "stage-1-only", len(s1_only))


if __name__ == "__main__":
    dict(score=score, sample=sample)[sys.argv[1]]()
