"""Scrub-to-farm class, tight setting (agreed with the owner): open before (DW trees < 0.30, trees + shrub >= 0.10 in 2017-19), no rabi crop cycle in 2017-19, a cycle in at least 2 consecutive
later rabi seasons, not water. Cycle = Jan-Mar NDVI >= 0.30 and at least 0.15 above Apr-May. Earth Engine returns only the flag and first cycle year; the 50 m majority (>= 13 of 25 pixels) is applied locally.
Saved beside each chunk, chunks unchanged. The sweep covers finished and new chunks. Usage: e62_s2f_chunks.py test | once [threads] | sweep [threads]"""
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor

import ee
import numpy as np
import pandas as pd
import rasterio
from scipy import ndimage

from common import *
from e32_enetra10m import A_EARLY, FOREST_MIN, dw_mean
from e33_map10m import D, init_retry
from e39_conversion import ndvi

OUTD = WORK / "map10m_s2f"
FLOOR, AMP, RABI, MIN_MAJ = .1, .15, .3, 13
YS = list(range(2017, 2026))
LATER = list(range(2020, 2026))
TILE = 300
PAUSE = 600
with rasterio.open(WORK / "zone_beat.tif") as _s:
    ZB = _s.read(1)


def product(aoi):
    cyc = {y: ndvi(aoi, y, 1, 3).rename("r").subtract(ndvi(aoi, y, 4, 5).rename("r")).gte(AMP).And(ndvi(aoi, y, 1, 3).gte(RABI)).unmask(0) for y in YS}
    none_early = cyc[2017].Or(cyc[2018]).Or(cyc[2019]).Not()
    pair = ee.Image(0)
    for a, b in zip(LATER[:-1], LATER[1:]):
        pair = pair.Or(cyc[a].And(cyc[b]))
    e = dw_mean(aoi, *A_EARLY)
    was_open = e.select("trees").lt(FOREST_MIN).And(e.select("trees").add(e.select("shrub_and_scrub")).gte(FLOOR)).unmask(0)
    nw = ee.Image("JRC/GSW1_4/GlobalSurfaceWater").select("occurrence").unmask(0).lt(5)
    f = was_open.And(none_early).And(pair).And(nw).rename("f").toByte()
    first = ee.Image(0)
    for y in reversed(LATER):
        first = first.where(cyc[y], y - 2000)
    return f.addBands(first.updateMask(f).unmask(0).rename("y").toByte()).reproject(ee.Projection(WKT).atScale(10))


def part(x0, y1, h, w):
    roi = ee.Geometry.Rectangle([x0, y1 - h * 10, x0 + w * 10, y1], ee.Projection(WKT), False)
    img = product(roi.transform("EPSG:4326", 10))
    wait = 30
    while True:
        try:
            a = img.sampleRectangle(region=roi, defaultValue=0).getInfo()["properties"]
            return np.array(a["f"], "uint8"), np.array(a["y"], "uint8")
        except Exception as e:
            if "Too Many" not in str(e):
                raise
            time.sleep(wait)
            wait = min(wait * 2, 600)


def one(f, t):
    out = OUTD / f.name
    if out.exists():
        return 0
    tile, r, c = f.stem.split("_")
    s = t.loc[tile]
    z0 = np.load(f)
    h, w = z0["cls"].shape if "cls" in z0.files else z0["y_ln2020"].shape
    fl, yr = np.zeros((h, w), "uint8"), np.zeros((h, w), "uint8")
    z = ZB[np.ix_(np.arange(h) // 3 + s.row + int(r) // 3, np.arange(w) // 3 + s.col + int(c) // 3)]
    for ro in range(0, h, TILE):
        for co in range(0, w, TILE):
            hh, ww = min(TILE, h - ro), min(TILE, w - co)
            if not z[ro:ro + hh, co:co + ww].any():
                continue
            a, b = part(s.x0 + (int(c) + co) * 10, s.y1 - (int(r) + ro) * 10, hh, ww)
            a, b = a[:hh, :ww], b[:hh, :ww]
            fl[ro:ro + a.shape[0], co:co + a.shape[1]], yr[ro:ro + a.shape[0], co:co + a.shape[1]] = a, b
    n = ndimage.uniform_filter(fl.astype("float32"), 5, mode="constant") * 25
    tmp = out.with_suffix(".tmp.npz")
    np.savez_compressed(tmp, f=fl, y=yr, maj=(np.rint(n) >= MIN_MAJ) & (fl > 0))
    tmp.replace(out)
    return 1


def safe(f, t):
    try:
        return one(f, t)
    except Exception as e:
        print("failed", f.name, str(e)[:150], flush=True)
        return 0


def sweep(th, repeat):
    init_retry()
    OUTD.mkdir(parents=True, exist_ok=True)
    t = pd.read_csv(WORK / "tiles.csv", keep_default_na=False).set_index("tile")
    t0 = time.time()
    while True:
        files = {f.name: f for f in (WORK / "map10m_stats").glob("*.npz")}
        files.update({f.name: f for f in D.glob("*.npz")})
        todo = [files[n] for n in sorted(files) if not (OUTD / n).exists()]
        print("chunks to process", len(todo), int(time.time() - t0), "s", flush=True)
        with ThreadPoolExecutor(th) as ex:
            for i, ok in enumerate(ex.map(lambda f: safe(f, t), todo)):
                if i % 10 == 0:
                    print(i, "of", len(todo), int(time.time() - t0), "s", flush=True)
        if not repeat:
            break
        time.sleep(PAUSE)
    print("FINISHED")


def test():
    init_retry()
    OUTD.mkdir(parents=True, exist_ok=True)
    t = pd.read_csv(WORK / "tiles.csv", keep_default_na=False).set_index("tile")
    g = pd.read_csv(ROOT / "ground_truth" / "guna_labels.csv")
    q = g[g.source == "bamori_validated"].iloc[0]
    s = t[(t.x0 <= q.x) & (t.x0 + t.w * RES > q.x) & (t.y1 >= q.y) & (t.y1 - t.h * RES < q.y)].iloc[0]
    r0, c0 = int((s.y1 - q.y) // 10 // 900 * 900), int((q.x - s.x0) // 10 // 900 * 900)
    f = D / f"{s.name}_{r0:05d}_{c0:05d}.npz"
    t0 = time.time()
    print(f.name, "done", safe(f, t), round(time.time() - t0), "s")
    a = np.load(OUTD / f.name)
    print("flag share", round(float((a["f"] > 0).mean()), 4), "majority share", round(float(a["maj"].mean()), 4), "years", np.unique(a["y"][a["maj"]], return_counts=True))


if __name__ == "__main__":
    m = sys.argv[1]
    th = int(sys.argv[2]) if len(sys.argv) > 2 else 2
    test() if m == "test" else sweep(th, m == "sweep")
