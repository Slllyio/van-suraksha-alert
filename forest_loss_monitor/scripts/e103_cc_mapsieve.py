"""The sieve for the Bamori map: the same time-series fall check used at the labelled points (e49.series_feats), computed for every 10 m pixel on Earth Engine.
Per pixel, yearly Oct-Nov Sentinel-2 NDVI and NBR 2017-2025 (SCL cloud mask); the best downward break in NDVI with at least 2 seasons on each side; NDVI and NBR fall across that break.
Same grid and chunks as e97. Usage: e103_cc_mapsieve.py fetch | apply"""
import io
import json
import sys
import time

sys.path.insert(0, "E:/FIRE/forest_loss_monitor/scripts")

import ee
import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio
from scipy import ndimage
from scipy.ndimage import label
from shapely.geometry import box

from common import *
from e32_enetra10m import S2
from e33_map10m import init_retry
from e97_cc_map import CHUNK, D, grid

DS = WORK / "cc_map_bamori_sieve"
YS = list(range(2017, 2026))
FALL, MIN_PX = .15, (2, 5)
FALLS = (.15, .12)


def series(aoi):
    def f(i):
        s = i.select("SCL")
        bad = s.eq(1).Or(s.eq(3)).Or(s.eq(8)).Or(s.eq(9)).Or(s.eq(10))
        return ee.Image.cat(i.normalizedDifference(["B8", "B4"]).rename("n"), i.normalizedDifference(["B8", "B12"]).rename("r")).updateMask(bad.Not())
    return [ee.ImageCollection(S2).filterBounds(aoi).filterDate(f"{y}-10-01", f"{y}-12-01").map(f).median() for y in YS]


def falls(aoi):
    s = series(aoi)
    n = [x.select("n") for x in s]
    r = [x.select("r") for x in s]
    T = len(YS)
    cands = []
    for k in range(2, T - 1):
        pre, post = ee.ImageCollection(n[:k]).mean(), ee.ImageCollection(n[k:]).mean()
        sse = ee.ImageCollection([n[j].subtract(pre if j < k else post).pow(2) for j in range(T)]).sum()
        rpre, rpost = ee.ImageCollection(r[:k]).mean(), ee.ImageCollection(r[k:]).mean()
        c = ee.Image.cat(sse.multiply(-1).rename("q"), pre.subtract(post).rename("dn"), rpre.subtract(rpost).rename("dr"), ee.Image.constant(YS[k]).toFloat().rename("yr"))
        cands.append(c.updateMask(pre.gt(post)))
    best = ee.ImageCollection(cands).qualityMosaic("q")
    return best.select(["dn", "dr", "yr"]).unmask(-9).toFloat().reproject(ee.Projection(WKT).atScale(10))


def fetch():
    init_retry()
    DS.mkdir(parents=True, exist_ok=True)
    r, x0, y1, nx, ny = grid()
    poly = r.union_all()
    jobs = [(i, j) for i in range(0, ny, CHUNK) for j in range(0, nx, CHUNK)
            if box(x0 + j * 10, y1 - (i + CHUNK) * 10, x0 + (j + CHUNK) * 10, y1 - i * 10).intersects(poly) and not (DS / f"{i}_{j}.npy").exists()]
    print("chunks to fetch", len(jobs), flush=True)
    t0 = time.time()
    for k, (i, j) in enumerate(jobs):
        h, w = min(CHUNK, ny - i), min(CHUNK, nx - j)
        aoi = ee.Geometry.Rectangle([x0 + j * 10, y1 - (i + h) * 10, x0 + (j + w) * 10, y1 - i * 10], ee.Projection(WKT), False).transform("EPSG:4326", 10)
        img = falls(aoi)
        wait = 30
        for _ in range(8):
            try:
                raw = ee.data.computePixels(dict(expression=img, fileFormat="NPY", grid=dict(dimensions=dict(width=w, height=h), crsWkt=WKT,
                                                 affineTransform=dict(scaleX=10, shearX=0, translateX=x0 + j * 10, shearY=0, scaleY=-10, translateY=y1 - i * 10))))
                a = np.load(io.BytesIO(raw))
                np.save(DS / f"{i}_{j}.npy", np.stack([a[c] for c in ("dn", "dr", "yr")]).astype("float32"))
                break
            except Exception as e:
                print("retry", i, j, str(e)[:120], flush=True)
                time.sleep(wait)
                wait = min(wait * 2, 600)
        print(k + 1, "of", len(jobs), round(time.time() - t0), "s", flush=True)
    print("FINISHED")


def apply():
    """Net (stage 1 or strict) AND enough sieve pixels in the 5 x 5 box, then patches of 0.5 ha or more."""
    from e98_cc_mapscore import MIN_PX as PATCH, OUTD, forest_mask
    g = json.load(open(D / "grid.json"))
    S = np.full((3, g["ny"], g["nx"]), np.nan, "float32")
    for f in DS.glob("*.npy"):
        i, j = map(int, f.stem.split("_"))
        a = np.load(f)
        S[:, i:i + a.shape[1], j:j + a.shape[2]] = a
    S[S == -9] = np.nan
    cls, ok = np.load(WORK / "cc_map_bamori_cls.npy"), np.load(WORK / "cc_map_bamori_ok.npy")
    _, zone = forest_mask(g)
    lk = pd.read_csv(OUT / "beat_lookup.csv").set_index("zone_id").Beat
    rows, keep = [], {}
    for fall in FALLS:
      with np.errstate(invalid="ignore"):
          ts = (S[0] >= FALL) & (S[1] >= fall)
      cnt = np.rint(ndimage.uniform_filter(ts.astype("float32"), 5, mode="constant") * 25)
      for net_name, net in (("stage 1", cls >= 1), ("strict", cls == 2)):
        for mp in MIN_PX:
            f = net & ts & (cnt >= mp)
            lab, _ = label(f, structure=np.ones((3, 3)))
            size = np.bincount(lab.ravel())
            k = np.isin(lab, np.flatnonzero(size >= PATCH)) & (lab > 0)
            keep[(fall, net_name, mp)] = k
            rows.append(dict(net=net_name, sieve=f"NDVI fall >= {FALL}, NBR fall >= {fall}, on {mp} px", forest_ha=round(ok.sum() * .01), net_ha=round(net[ok].sum() * .01), after_sieve_ha=round(k.sum() * .01),
                             patches=int((size[1:] >= PATCH).sum()), share_of_forest_pct=round(100 * k.sum() / ok.sum(), 2)))
    t = pd.DataFrame(rows)
    print(t.to_string())
    t.to_csv(OUTD / "bamori_area_sieved.csv", index=False)
    final = keep[(.15, "strict", 5)]
    with np.errstate(invalid="ignore"):
        ts = (S[0] >= FALL) & (S[1] >= FALL)
    yr = np.where(final, S[2], np.nan)
    print("by sieve break year:", pd.Series(yr[final]).value_counts().sort_index().mul(.01).round(1).to_dict())
    b = pd.DataFrame(dict(beat=lk.reindex(zone[ok]).values, f=final[ok])).groupby("beat").agg(forest_ha=("f", "size"), loss_ha=("f", "sum")) * .01
    b["loss_pct"] = (100 * b.loss_ha / b.forest_ha).round(2)
    b.round(1).sort_values("loss_ha", ascending=False).to_csv(OUTD / "bamori_by_beat_sieved.csv")
    print(b.round(1).sort_values("loss_ha", ascending=False).head(10).to_string())
    np.save(WORK / "cc_map_bamori_final.npy", final)


if __name__ == "__main__":
    dict(fetch=fetch, apply=apply)[sys.argv[1]]()
