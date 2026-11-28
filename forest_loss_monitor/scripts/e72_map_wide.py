"""New map input per 9 km chunk, stored for every pixel so nets, filters, operating points and patch minimums are applied afterwards with no re-fetch.
Yearly Oct-Nov NDVI, NBR, BSI 2017-25 at 10 m in 4 tiles (SCL cloud masking; the cloud-probability join overran memory). Dynamic World and NDVI window means at 30 m in one request (10 m took over 7 minutes a tile).
Values int8 x 100, -128 = missing. Writes to map10m_stats, never the old map10m. Unfinished chunks first, then the finished ones. Usage: e72_map_wide.py state [threads] | test"""
import io
import sys
import time
from concurrent.futures import ThreadPoolExecutor

import ee
import numpy as np
import pandas as pd

from common import *
from e32_enetra10m import A_EARLY, A_LATE, B_EARLY, B_LATE, S2, dw_mean, ndvi_mean
from e33_map10m import init_retry, jobs, keep_awake

W = WORK / "map10m_stats"
YS = list(range(2017, 2026))
TILE = 450


def leaf(y, a):
    def f(i):
        q = i.select("SCL")
        bad = q.eq(1).Or(q.eq(3)).Or(q.eq(8)).Or(q.eq(9)).Or(q.eq(10))
        bsi = i.expression("((b('B11')+b('B4'))-(b('B8')+b('B2')))/((b('B11')+b('B4'))+(b('B8')+b('B2')))")
        return ee.Image.cat(i.normalizedDifference(["B8", "B4"]), i.normalizedDifference(["B8", "B12"]), bsi).rename(["n", "r", "b"]).toFloat().updateMask(bad.Not())
    return ee.ImageCollection(S2).filterBounds(a).filterDate(f"{y}-10-01", f"{y}-12-01").map(f).median().rename([f"ln{y}", f"lr{y}", f"lb{y}"])


def yearly(a):
    return ee.Image.cat([leaf(y, a) for y in YS]).multiply(100).round().unmask(-128).toInt8()


def inputs(a):
    ea, la, eb, lb = dw_mean(a, *A_EARLY), dw_mean(a, *A_LATE), dw_mean(a, *B_EARLY), dw_mean(a, *B_LATE)
    im = ee.Image.cat(ea.select(["trees", "shrub_and_scrub", "crops"], ["ea_t", "ea_s", "ea_c"]), eb.select(["trees", "shrub_and_scrub", "crops"], ["eb_t", "eb_s", "eb_c"]),
                      la.select(["trees", "shrub_and_scrub", "crops", "bare", "built"], ["la_t", "la_s", "la_c", "la_b", "la_u"]), lb.select(["trees", "shrub_and_scrub", "crops", "bare", "built"], ["lb_t", "lb_s", "lb_c", "lb_b", "lb_u"]),
                      dw_mean(a, A_EARLY[0], A_EARLY[1], (8, 10)).select(["trees"], ["mon0"]), dw_mean(a, 2024, 2024, (8, 10)).select(["trees"], ["mon24"]),
                      ndvi_mean(a, *A_EARLY).rename("nea"), ndvi_mean(a, *A_LATE).rename("nla"), ndvi_mean(a, *B_EARLY).rename("neb"), ndvi_mean(a, *B_LATE).rename("nlb"))
    water = ee.Image("JRC/GSW1_4/GlobalSurfaceWater").select("occurrence").unmask(0).gte(5).rename("water").toInt8()
    return im.multiply(100).round().unmask(-128).toInt8().addBands(water)


def request(fn, x0, y1, h, w, res):
    roi = ee.Geometry.Rectangle([x0, y1 - h * res, x0 + w * res, y1], ee.Projection(WKT), False).transform("EPSG:4326", 10)
    wait = 30
    for _ in range(40):
        try:
            raw = ee.data.computePixels(dict(expression=fn(roi), fileFormat="NPY", grid=dict(dimensions=dict(width=w, height=h), crsWkt=WKT, affineTransform=dict(scaleX=res, shearX=0, translateX=x0, shearY=0, scaleY=-res, translateY=y1))))
            return np.load(io.BytesIO(raw))
        except Exception as e:
            if "Too Many Requests" not in str(e):
                raise
            time.sleep(wait + np.random.uniform(0, 30))
            wait = min(wait * 2, 900)
    raise RuntimeError("refused too long")


def split10(s, r, c, h, w):
    x0, y1 = s.x0 + c * 10, s.y1 - r * 10
    try:
        return request(yearly, x0, y1, h, w, 10)
    except Exception as e:
        if "memory" not in str(e) and "timed out" not in str(e) or h < 100:
            raise
    h2, w2 = h // 2, w // 2
    out = None
    for ro, ho in ((0, h2), (h2, h - h2)):
        for co, wo in ((0, w2), (w2, w - w2)):
            p = split10(s, r + ro, c + co, ho, wo)
            if out is None:
                out = np.zeros((h, w), p.dtype)
            out[ro:ro + ho, co:co + wo] = p
    return out


def fetch(s, r, c, h, w, out):
    if out.exists():
        return 0
    for attempt in range(3):
        try:
            y = None
            for ro in range(0, h, TILE):
                for co in range(0, w, TILE):
                    hh, ww = min(TILE, h - ro), min(TILE, w - co)
                    p = split10(s, r + ro, c + co, hh, ww)
                    if y is None:
                        y = np.zeros((h, w), p.dtype)
                    y[ro:ro + hh, co:co + ww] = p
            x0, y1 = s.x0 + c * 10, s.y1 - r * 10
            d = request(inputs, x0, y1, int(np.ceil(h / 3)), int(np.ceil(w / 3)), 30)
            tmp = out.with_suffix(".tmp.npz")
            np.savez_compressed(tmp, **{f"y_{k}": y[k] for k in y.dtype.names}, **{f"d_{k}": d[k] for k in d.dtype.names})
            tmp.replace(out)
            return 1
        except Exception as e:
            msg = str(e)[:180]
            time.sleep(10 * 2 ** attempt)
    print("failed", out.name, msg, flush=True)
    return 0


def priority_names():
    """Chunks touching the divisions listed in work/priority_divisions.txt go first."""
    f = WORK / "priority_divisions.txt"
    if not f.exists():
        return set()
    import rasterio
    divs = [l.strip() for l in open(f) if l.strip()]
    b = pd.read_csv(OUT / "beat_lookup.csv")
    with rasterio.open(WORK / "zone_beat.tif") as s:
        z = np.isin(s.read(1), b[b.Division.isin(divs)].zone_id.values)
    return {j[5].name for j in jobs() if z[j[0].row + j[1] // 3:j[0].row + (j[1] + 900) // 3, j[0].col + j[2] // 3:j[0].col + (j[2] + 900) // 3].any()}


def guna_distance():
    """Chunk-centre distance (zone grid cells) to the Guna division centroid: the owner's rollout runs outward from Guna."""
    import rasterio
    b = pd.read_csv(OUT / "beat_lookup.csv")
    with rasterio.open(WORK / "zone_beat.tif") as s:
        r, c = np.nonzero(np.isin(s.read(1), b[b.Division == "Guna"].zone_id.values))
    r0, c0 = r.mean(), c.mean()
    return {j[5].name: float(np.hypot(j[0].row + (j[1] + 450) / 3 - r0, j[0].col + (j[2] + 450) / 3 - c0)) for j in jobs()}


def ordered():
    pri, dist = priority_names(), guna_distance()
    js = [(*j[:5], W / j[5].name) for j in jobs()]
    return [j for j in sorted(js, key=lambda j: (j[5].name not in pri, dist[j[5].name])) if not j[5].exists()]


def state(th):
    init_retry()
    W.mkdir(parents=True, exist_ok=True)
    keep_awake()
    js = ordered()
    print("chunks to fetch", len(js), flush=True)
    t0 = time.time()
    n = 0
    with ThreadPoolExecutor(th) as ex:
        for i, ok in enumerate(ex.map(lambda j: fetch(*j), js)):
            n += ok
            if i % 5 == 0:
                print(i, "ok", n, int(time.time() - t0), "s", flush=True)
    print("FINISHED", n)


def test():
    init_retry()
    W.mkdir(parents=True, exist_ok=True)
    j = ordered()[0]
    t0 = time.time()
    print(j[5].name, "done", fetch(*j), round(time.time() - t0), "s", flush=True)
    print("MB", round(j[5].stat().st_size / 1e6, 1))
    a = np.load(j[5])
    print(len(a.files), a["y_ln2020"].shape, a["d_ea_t"].shape, "missing lnNDVI 2020", round(float((a["y_ln2020"] == -128).mean()), 3), "ea_t range", int(a["d_ea_t"].min()), int(a["d_ea_t"].max()))


if __name__ == "__main__":
    test() if sys.argv[1] == "test" else state(int(sys.argv[2]) if len(sys.argv) > 2 else 2)
