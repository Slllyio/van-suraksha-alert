"""10 m map from the extended e_Netra rule, fetched directly in chunks, resumable per chunk. S2 SR only, so 2017-18 share one processing level.
Bands: cls 1 clearing to crop/bare/built, 2 tree-to-shrub or thinning, 3 shrub-to-crop; yr = year of largest leaf-on NBR fall, minus 2000.
Water is masked. Usage: e33_map10m.py timing | divisions | state [threads]"""
import ctypes
import io
import sys
import time
from concurrent.futures import ThreadPoolExecutor

import ee
import numpy as np
import pandas as pd
import rasterio

from common import *
from e32_enetra10m import A_LATE, B_EARLY, B_LATE, S2, dw_mean, rule_bands

CHUNK = 900         # 10 m pixels; 9 km
D = WORK / "map10m"
YRS = list(range(2018, 2026))
ANNUAL = list(range(2016, 2026))
PROB_MAX = 40
TEST_DIVS = ["Guna", "Harda", "East_Mandla", "Lamta_Proj_N_Balaghat"]


def leaf_nbr(y, aoi):
    s2 = ee.ImageCollection(S2).filterBounds(aoi).filterDate(f"{y}-10-01", f"{y}-12-01")
    prob = ee.ImageCollection("COPERNICUS/S2_CLOUD_PROBABILITY").filterBounds(aoi).filterDate(f"{y}-10-01", f"{y}-12-01")
    j = ee.ImageCollection(ee.Join.saveFirst("p").apply(s2, prob, ee.Filter.equals(leftField="system:index", rightField="system:index")))
    return j.map(lambda i: ee.Image(i).normalizedDifference(["B8", "B12"]).rename("n").toFloat().updateMask(ee.Image(ee.Image(i).get("p")).select("probability").lt(PROB_MAX))).median().rename("n")


def product(aoi):
    f, ea, la, lb = rule_bands(aoi)
    nw = f.select("water").Not()
    a = f.select("e_recent")
    b = f.select("late").And(a.Not())
    conv = lambda l: l.select(["crops", "bare", "built"]).reduce(ee.Reducer.max()).gte(l.select(["trees", "shrub_and_scrub"]).reduce(ee.Reducer.max()))
    clear = a.And(conv(la)).Or(b.And(conv(lb)))
    s2c = f.select("s2c_a").Or(f.select("s2c_b")).And(a.Or(b).Not())
    cls = ee.Image(0).where(a.Or(b), 2).where(clear, 1).where(s2c, 3).updateMask(nw).unmask(0).rename("cls").toByte()
    hit = cls.gt(0)
    nbr = {y: leaf_nbr(y, aoi).unmask(-9).updateMask(hit) for y in ANNUAL}   # computed only where flagged
    drops = []
    for y in YRS:
        pre = ee.ImageCollection([nbr[y - 2], nbr[y - 1]]).map(lambda i: i.updateMask(i.gt(-8))).mean()
        post = ee.ImageCollection([nbr[y], nbr[min(y + 1, 2025)]]).map(lambda i: i.updateMask(i.gt(-8))).mean()
        drops.append(pre.subtract(post).unmask(-9).rename("d"))
    yr = ee.ImageCollection(drops).toBands().toArray().arrayArgmax().arrayGet([0]).add(18).toByte().unmask(0).rename("yr")
    return cls.addBands(yr)


def request(s, r, c, h, w):
    """One chunk from Earth Engine. Waits out concurrency limits instead of giving up; other errors are raised."""
    x0, y1 = s.x0 + c * 10, s.y1 - r * 10
    roi = ee.Geometry.Rectangle([x0, y1 - h * 10, x0 + w * 10, y1], ee.Projection(WKT), False).transform("EPSG:4326", 10)
    wait = 30
    while True:
        try:
            raw = ee.data.computePixels(dict(expression=product(roi), fileFormat="NPY", grid=dict(
                dimensions=dict(width=w, height=h), crsWkt=WKT,
                affineTransform=dict(scaleX=10, shearX=0, translateX=x0, shearY=0, scaleY=-10, translateY=y1))))
            a = np.load(io.BytesIO(raw))
            return a["cls"], a["yr"]
        except Exception as e:
            if "Too Many Requests" not in str(e):
                raise
            time.sleep(wait + np.random.uniform(0, 30))
            wait = min(wait * 2, 900)


def fetch_split(s, r, c, h, w):
    """Whole chunk; if it runs out of memory or time, four quarters merged (twice at most, through recursion)."""
    try:
        return request(s, r, c, h, w)
    except Exception as e:
        if not ("memory" in str(e) or "timed out" in str(e)) or h < 200:
            raise
    h2, w2 = h // 2, w // 2
    cls, yr = np.zeros((h, w), "uint8"), np.zeros((h, w), "uint8")
    for ro, ho in ((0, h2), (h2, h - h2)):
        for co, wo in ((0, w2), (w2, w - w2)):
            a, b = fetch_split(s, r + ro, c + co, ho, wo)
            cls[ro:ro + ho, co:co + wo], yr[ro:ro + ho, co:co + wo] = a, b
    return cls, yr


def fetch(s, r, c, h, w, out):
    if out.exists():
        return 0
    for attempt in range(3):
        try:
            cls, yr = fetch_split(s, r, c, h, w)
            tmp = out.with_suffix(".tmp.npz")
            np.savez_compressed(tmp, cls=cls, yr=yr)
            tmp.replace(out)
            return 1
        except Exception as e:
            msg = str(e)[:180]
            time.sleep(10 * 2 ** attempt)
    print("failed", out.name, msg, flush=True)
    return 0


def jobs(tiles=None, divs=None):
    t = pd.read_csv(WORK / "tiles.csv", keep_default_na=False)
    if tiles:
        t = t[t.tile.isin(tiles)]
    with rasterio.open(WORK / "zone_beat.tif") as src:
        z = src.read(1)
    if divs:
        b = pd.read_csv(OUT / "beat_lookup.csv")
        z = np.isin(z, b[b.Division.isin(divs)].zone_id.values) * z
    out = []
    for s in t.itertuples():
        zz = z[s.row:s.row + s.h, s.col:s.col + s.w] > 0
        for r in range(0, s.h * 3, CHUNK):
            for c in range(0, s.w * 3, CHUNK):
                if zz[r // 3:(r + CHUNK) // 3, c // 3:(c + CHUNK) // 3].any():
                    out.append((s, r, c, min(CHUNK, s.h * 3 - r), min(CHUNK, s.w * 3 - c), D / f"{s.tile}_{r:05d}_{c:05d}.npz"))
    return out


def keep_awake():
    """Windows will not sleep while this process runs (needs no change to system settings)."""
    ctypes.windll.kernel32.SetThreadExecutionState(0x80000000 | 0x00000001)


def run(js, threads):
    D.mkdir(parents=True, exist_ok=True)
    keep_awake()
    js = [j for j in js if not j[-1].exists()]
    print("chunks to fetch", len(js), flush=True)
    t0 = time.time()
    n = 0
    with ThreadPoolExecutor(threads) as ex:
        for i, ok in enumerate(ex.map(lambda j: fetch(*j), js)):
            n += ok
            if i % 5 == 0:
                print(i, "ok", n, int(time.time() - t0), "s", flush=True)
    print("FINISHED", n, "chunks", int(time.time() - t0), "s")


def init_retry():
    wait = 60
    while True:
        try:
            return init()
        except Exception as e:
            print("init waiting", str(e)[:90], flush=True)
            time.sleep(wait)
            wait = min(wait * 2, 900)


if __name__ == "__main__":
    init_retry()
    th = int(sys.argv[2]) if len(sys.argv) > 2 else 3
    if sys.argv[1] == "timing":
        js = [j for j in jobs(tiles=["r02c03"]) if j[1] >= 2700][:12]
        run(js, 6)
    elif sys.argv[1] == "divisions":
        run(jobs(divs=TEST_DIVS), th)
    else:
        run(jobs(), th)
