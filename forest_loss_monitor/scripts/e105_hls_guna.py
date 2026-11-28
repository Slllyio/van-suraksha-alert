"""HLS L30 seasonal stacks over Guna for the survey-calibrated Prithvi experiment: per year, 3 seasons (rabi Jan-Mar, summer Apr-Jun, post-monsoon Oct-Dec)
x 6 Prithvi bands (B2 blue, B3 green, B4 red, B5 NIR, B6 SWIR1, B7 SWIR2), Fmask cloud/shadow masked, median, reflectance x 10000 int16 (-9999 missing).
30 m on the Guna grid (10 m grid / 3), 256 px tiles, only tiles touching Guna beats. computePixels with an explicit grid (sampleRectangle returns rows flipped).
Writes work/hls_guna/{year}/{r}_{c}.npy (18, 256, 256). 2015 first, then 2017-2025. Stops on quota errors. Usage: e105_hls_guna.py [years]"""
import io
import sys
import time

import ee
import numpy as np

from common import *
from e33_map10m import init_retry, keep_awake
from e97_guna_eval import GD, grid

HD = WORK / "hls_guna"
T = 256
BANDS = ["B2", "B3", "B4", "B5", "B6", "B7"]
SEASONS = ((1, 3), (4, 6), (10, 12))
YEARS = [2015] + list(range(2017, 2026))


def clean(i):
    q = i.select("Fmask").toInt()
    bad = q.bitwiseAnd(2).neq(0).Or(q.bitwiseAnd(4).neq(0)).Or(q.bitwiseAnd(8).neq(0))
    return i.select(BANDS).updateMask(bad.Not())


def stack(roi, y):
    out = []
    for k, (m0, m1) in enumerate(SEASONS):
        end = ee.Date.fromYMD(y, m1, 1).advance(1, "month")
        c = ee.ImageCollection("NASA/HLS/HLSL30/v002").filterBounds(roi).filterDate(ee.Date.fromYMD(y, m0, 1), end).map(clean)
        out.append(c.median().rename([f"s{k}_{b}" for b in BANDS]))
    return ee.Image.cat(out).multiply(10000).round().unmask(-9999).toInt16()


def tiles():
    tr, shp = grid()
    beat = np.load(GD / "guna_beat.npy", mmap_mode="r")
    H, W = shp[0] // 3, shp[1] // 3
    out = []
    for r in range(0, H, T):
        for c in range(0, W, T):
            if np.asarray(beat[r * 3:(r + T) * 3:9, c * 3:(c + T) * 3:9]).any():
                out.append((r, c, tr.c + c * 30, tr.f - r * 30))
    return out


def fetch(y, r, c, x0, y1):
    f = HD / str(y) / f"{r}_{c}.npy"
    if f.exists():
        return 0
    roi = ee.Geometry.Rectangle([x0, y1 - T * 30, x0 + T * 30, y1], ee.Projection(WKT), False).transform("EPSG:4326", 10)
    wait = 30
    for _ in range(30):
        try:
            raw = ee.data.computePixels(dict(expression=stack(roi, y), fileFormat="NPY",
                                             grid=dict(dimensions=dict(width=T, height=T), crsWkt=WKT, affineTransform=dict(scaleX=30, shearX=0, translateX=x0, shearY=0, scaleY=-30, translateY=y1))))
            a = np.load(io.BytesIO(raw))
            arr = np.stack([a[n] for n in a.dtype.names]).astype("int16")
            tmp = f.with_suffix(".tmp.npy")
            np.save(tmp, arr)
            tmp.replace(f)
            return 1
        except Exception as e:
            msg = str(e)
            if "quota" in msg.lower() and "Too Many" not in msg:
                print("quota error, stopping:", msg[:150], flush=True)
                raise SystemExit(2)
            if "Too Many" in msg:          # concurrency refusal: wait 5 minutes and retry (coordinator, 7 Nov)
                print("refused, waiting 5 min", y, r, c, flush=True)
                time.sleep(300)
                continue
            print("retry", y, r, c, msg[:150], flush=True)
            time.sleep(wait)
            wait = min(wait * 2, 600)
    return 0


def main():
    init_retry()
    keep_awake()
    years = [int(v) for v in sys.argv[1].split(",")] if len(sys.argv) > 1 else YEARS
    ts = tiles()
    print("tiles", len(ts), flush=True)
    for y in years:
        (HD / str(y)).mkdir(parents=True, exist_ok=True)
        t0, n = time.time(), 0
        for i, t in enumerate(ts):
            n += fetch(y, *t)
            if i % 20 == 0:
                print(y, i, "of", len(ts), int(time.time() - t0), "s", flush=True)
        print("year done", y, n, flush=True)
    print("FINISHED")


if __name__ == "__main__":
    main()
