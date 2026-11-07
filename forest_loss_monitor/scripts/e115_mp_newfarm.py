"""New farmland inside recorded forest for any MP division, at 30 m, nearest to Guna first.
Per division: (1) 500 random forest pixels give each year's embedding mean and sd, so every year is z-matched to 2022 before the crop classifier of e105 (fitted on the owner's 2022 Bamori polygons)
is applied; (2) the old-field model of e114 (Landsat 2014-16 + 2017 embedding) says whether the pixel was already farmland around 2015; (3) new farmland = not crop in any of 2017-19, crop in
at least 2 of 2023-25, old-field probability below the model threshold, patches of 0.5 ha or more. Tables per range and beat. Usage: e115_mp_newfarm.py fetch <Division|next> | tables <Division>"""
import io
import json
import sys
import time

sys.path.insert(0, "E:/FIRE/forest_loss_monitor/scripts")
ARGS = sys.argv[1:]
sys.argv = sys.argv[:1]

import ee
import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio
from rasterio.transform import from_origin
from scipy.ndimage import label
from shapely.geometry import box

from common import *
from e33_map10m import init_retry
from e75_cc_fetch import COL
from e105_cc_cropmask import M as CROP_M, retry
from e114_oldfield import M as OLD_M, oldfield_image

YS = list(range(2017, 2026))
RES, CHUNK, MIN_PX = 30, 256, 6          # 6 px of 30 m = 0.54 ha
MPD = WORK / "mp_newfarm"
OUTD = OUT / "mp_newfarm"


def divisions():
    """All divisions, nearest to Guna first."""
    b = gpd.read_parquet(WORK / "beats_albers.parquet")
    d = b.dissolve("Division")
    g = d.loc["Guna"].geometry
    return (d.geometry.distance(g) + d.geometry.centroid.distance(g.centroid) * 1e-3).sort_values().index.tolist()[1:]


def year_stats(beats):
    """Mean and sd of the 64 bands per year over random forest pixels of the division."""
    rng = np.random.default_rng(7)
    geom = beats.geometry.union_all()
    x0, y0, x1, y1 = geom.bounds
    P = gpd.points_from_xy(rng.uniform(x0, x1, 40000), rng.uniform(y0, y1, 40000))
    P = P[geom.contains(P)][:500]
    proj = ee.Projection(WKT)
    fc = ee.FeatureCollection([ee.Feature(ee.Geometry.Point([p.x, p.y], proj), dict(i=k)) for k, p in enumerate(P)])
    ims = [ee.ImageCollection(COL).filterDate(f"{y}-01-01", f"{y + 1}-01-01").mosaic().rename([f"y{y}_{i:02d}" for i in range(64)]) for y in YS]
    rows = [f["properties"] for f in retry(lambda: ee.Image.cat(ims).sampleRegions(fc, scale=RES, tileScale=4).getInfo())["features"]]
    e = pd.DataFrame(rows).dropna()
    A = np.stack([e[[f"y{y}_{i:02d}" for i in range(64)]].values for y in YS], axis=1)
    return A.mean(axis=0), A.std(axis=0), len(e)


def crop_image(mu, sd):
    m = json.load(open(CROP_M))
    w, b0 = np.array(m["coef"]), m["intercept"]
    k22 = YS.index(2022)
    out = []
    for k, y in enumerate(YS):
        a = sd[k22] / np.maximum(sd[k], 1e-6)
        coef, b = w * a, b0 + w @ (mu[k22] - mu[k] * a)
        z = ee.ImageCollection(COL).filterDate(f"{y}-01-01", f"{y + 1}-01-01").mosaic().select(m["bands"]).multiply(ee.Image.constant(coef.tolist())).reduce(ee.Reducer.sum()).add(float(b))
        out.append(ee.Image(1).divide(ee.Image(1).add(z.multiply(-1).exp())).rename(f"c{y}"))
    return ee.Image.cat(out)


def grid_of(b):
    x0, y0, x1, y1 = b.total_bounds
    x0, y1 = np.floor(x0 / 30) * 30, np.ceil(y1 / 30) * 30
    return dict(x0=float(x0), y1=float(y1), nx=int(np.ceil((x1 - x0) / RES)), ny=int(np.ceil((y1 - y0) / RES)))


def fetch(div):
    init_retry()
    beats = gpd.read_parquet(WORK / "beats_albers.parquet")
    b = beats[beats.Division == div]
    d = MPD / div
    d.mkdir(parents=True, exist_ok=True)
    if not (d / "year_stats.json").exists():
        mu, sd, n = year_stats(b)
        json.dump(dict(mu=mu.tolist(), sd=sd.tolist(), n=n), open(d / "year_stats.json", "w"))
        print(div, "year stats from", n, "pixels; largest shift vs 2022 in sd units:", {y: round(float(np.abs((mu[k] - mu[YS.index(2022)]) / sd[YS.index(2022)]).max()), 2) for k, y in enumerate(YS)}, flush=True)
    st = json.load(open(d / "year_stats.json"))
    img = ee.Image.cat([crop_image(np.array(st["mu"]), np.array(st["sd"])), oldfield_image().rename("old")]).multiply(200).round().toUint8().reproject(ee.Projection(WKT).atScale(RES))
    g = grid_of(b)
    json.dump(g, open(d / "grid.json", "w"))
    poly = b.union_all()
    jobs = [(i, j) for i in range(0, g["ny"], CHUNK) for j in range(0, g["nx"], CHUNK)
            if box(g["x0"] + j * RES, g["y1"] - (i + CHUNK) * RES, g["x0"] + (j + CHUNK) * RES, g["y1"] - i * RES).intersects(poly) and not (d / f"{i}_{j}.npy").exists()]
    print(div, "forest ha", round(b.area.sum() / 1e4), "chunks", len(jobs), flush=True)
    t0 = time.time()
    for n, (i, j) in enumerate(jobs):
        h, w = min(CHUNK, g["ny"] - i), min(CHUNK, g["nx"] - j)
        raw = retry(lambda: ee.data.computePixels(dict(expression=img, fileFormat="NPY", grid=dict(dimensions=dict(width=w, height=h), crsWkt=WKT,
                                                     affineTransform=dict(scaleX=RES, shearX=0, translateX=g["x0"] + j * RES, shearY=0, scaleY=-RES, translateY=g["y1"] - i * RES)))))
        a = np.load(io.BytesIO(raw))
        np.save(d / f"{i}_{j}.npy", np.stack([a[f"c{y}"] for y in YS] + [a["old"]]).astype("uint8"))
        if n % 10 == 0:
            print(div, n + 1, "of", len(jobs), round(time.time() - t0), "s", flush=True)
    print(div, "DONE", flush=True)


def zone30(g):
    with rasterio.open(WORK / "zone_beat.tif") as s:
        tr = s.transform
        c0, r0 = int(round((g["x0"] - tr.c) / tr.a)), int(round((tr.f - g["y1"]) / -tr.e))
        return s.read(1, window=((r0, r0 + g["ny"]), (c0, c0 + g["nx"])), boundless=True, fill_value=0)


def tables(div):
    OUTD.mkdir(parents=True, exist_ok=True)
    d = MPD / div
    g = json.load(open(d / "grid.json"))
    m = json.load(open(OLD_M))
    thr = m.get("threshold_mp", m["threshold"])        # 0.2 set from the blind-labelled spots of 4 divisions (e117)
    P = np.zeros((10, g["ny"], g["nx"]), "uint8")
    have = np.zeros((g["ny"], g["nx"]), bool)
    for f in d.glob("*_*.npy"):
        i, j = map(int, f.stem.split("_"))
        a = np.load(f)
        P[:, i:i + a.shape[1], j:j + a.shape[2]] = a
        have[i:i + a.shape[1], j:j + a.shape[2]] = True
    lk = pd.read_csv(OUT / "beat_lookup.csv")
    lk = lk[lk.Division == div].set_index("zone_id")
    z = zone30(g)
    ok = have & np.isin(z, lk.index.values)
    C = P[:9] >= 100
    old = P[9] >= thr * 200
    base = ok & ~C[:3].any(axis=0) & (C[6:].sum(axis=0) >= 2)
    new = base & ~old
    lab, _ = label(new, structure=np.ones((3, 3)))
    n = np.bincount(lab.ravel())
    new = (n[lab] >= MIN_PX) & (lab > 0)
    stay = np.flip(np.cumprod(np.flip(C, axis=0), axis=0), axis=0).astype(bool)
    first = np.where(stay.any(axis=0), 2017 + np.argmax(stay, axis=0), 2025).astype("int16")
    ha = RES * RES / 1e4
    tr = from_origin(g["x0"], g["y1"], RES, RES)
    with rasterio.open(OUTD / f"newfarm_{div}.tif", "w", driver="GTiff", width=g["nx"], height=g["ny"], count=2, dtype="int16", crs=PROJ4, transform=tr, compress="deflate", nodata=0) as o:
        o.write(np.where(new, first, 0), 1)
        o.write(np.where(ok, P[9], 0).astype("int16"), 2)
        o.descriptions = ("first_farm_year", "old_field_prob_x200")
    zz = z[ok]
    t = pd.DataFrame(dict(zone_id=zz, new=new[ok], base=base[ok], old_crop=(C[6:].sum(axis=0) >= 2)[ok] & old[ok], crop_now=(C[6:].sum(axis=0) >= 2)[ok], crop_before=(C[:3].sum(axis=0) >= 2)[ok])).groupby("zone_id").agg(
        forest_ha=("new", "size"), new_farmland_ha=("new", "sum"), new_without_oldfield_filter_ha=("base", "sum"), cropland_2023_25_ha=("crop_now", "sum"), cropland_2017_19_ha=("crop_before", "sum"))
    t = t * ha
    t["Range"], t["Beat"] = lk.Range.reindex(t.index).values, lk.Beat.reindex(t.index).values
    i = np.nonzero(new)
    fy = pd.DataFrame(dict(zone_id=z[i], year=first[i])).value_counts().rename("px").reset_index()
    fy["ha"] = fy.px * ha
    t = t.join(fy.pivot_table(index="zone_id", columns="year", values="ha", aggfunc="sum", fill_value=0).add_prefix("first_")).fillna(0)
    t["new_farmland_pct_of_forest"] = 100 * t.new_farmland_ha / t.forest_ha
    by_beat = t.set_index(["Range", "Beat"]).sort_values("new_farmland_ha", ascending=False)
    by_range = t.groupby("Range").sum(numeric_only=True)
    by_range.loc["ALL"] = by_range.sum()
    by_range["new_farmland_pct_of_forest"] = 100 * by_range.new_farmland_ha / by_range.forest_ha
    by_beat.round(1).to_csv(OUTD / f"{div}_newfarm_by_beat.csv")
    by_range.round(1).to_csv(OUTD / f"{div}_newfarm_by_range.csv")
    pd.set_option("display.width", 250, "display.max_columns", 30)
    print(by_range.round(0).to_string())


if __name__ == "__main__":
    if ARGS[0] == "list":
        print(divisions())
    elif ARGS[0] == "fetch":
        for div in (divisions() if ARGS[1] == "all" else [ARGS[1]]):
            fetch(div)
    else:
        tables(ARGS[1])
