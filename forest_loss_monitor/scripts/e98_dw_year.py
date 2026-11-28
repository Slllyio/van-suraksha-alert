"""Dynamic World loss-year sidecar: annual mean DW trees 2017-2025 at 30 m per chunk (values x 100, 255 = missing), saved to work/map10m_dwy.
Loss year = first year trees fall below 0.30 after an earlier year at or above it (threshold chosen on the owner's 51 fellings, the same points it is scored on).
Usage: e98_dw_year.py guna | state [threads]"""
import io
import sys
import time
from concurrent.futures import ThreadPoolExecutor

import ee
import numpy as np

from common import *
from e32_enetra10m import DW
from e33_map10m import init_retry, jobs, keep_awake
from e72_map_wide import guna_distance, priority_names

OUTD = WORK / "map10m_dwy"
YS = list(range(2017, 2026))
TH = .30


def product(x0, y1):
    roi = ee.Geometry.Rectangle([x0, y1 - 9000, x0 + 9000, y1], ee.Projection(WKT), False).transform("EPSG:4326", 10)
    bands = [ee.ImageCollection(DW).filterBounds(roi).filterDate(f"{y}-01-01", f"{y + 1}-01-01").select("trees").mean().rename(f"t{y}") for y in YS]
    return ee.Image.cat(bands).multiply(100).round().unmask(255).toUint8()


def fetch(j):
    s, r, c, h, w, p = j
    out = OUTD / p.name
    if out.exists():
        return 0
    x0, y1 = s.x0 + c * 10, s.y1 - r * 10
    wait = 30
    for _ in range(30):
        try:
            raw = ee.data.computePixels(dict(expression=product(x0, y1), fileFormat="NPY", grid=dict(dimensions=dict(width=-(-w // 3), height=-(-h // 3)), crsWkt=WKT, affineTransform=dict(scaleX=30, shearX=0, translateX=x0, shearY=0, scaleY=-30, translateY=y1))))
            a = np.load(io.BytesIO(raw))
            tmp = out.with_suffix(".tmp.npz")
            np.savez_compressed(tmp, t=np.stack([a[f"t{y}"] for y in YS]).astype("uint8"))
            tmp.replace(out)
            return 1
        except Exception as e:
            msg = str(e)
            if "Too Many" in msg:
                time.sleep(wait)
                wait = min(wait * 2, 600)
            else:
                print("failed", p.name, msg[:150], flush=True)
                return 0
    return 0


def loss_year(t):
    """t: (9, h, w) uint8 x100 with 255 missing. Returns int16 year or 0."""
    v = np.where(t == 255, np.nan, t / 100.0)
    seen = np.zeros(v.shape[1:], bool)
    yr = np.zeros(v.shape[1:], "int16")
    with np.errstate(invalid="ignore"):
        for i, y in enumerate(YS):
            hit = seen & (v[i] < TH) & (yr == 0)
            yr[hit] = y
            seen |= v[i] >= TH
    return yr


def main():
    init_retry()
    OUTD.mkdir(parents=True, exist_ok=True)
    keep_awake()
    mode = sys.argv[1]
    js = jobs()
    if mode == "guna":
        pri = priority_names()
        js = [j for j in js if j[5].name in pri]
    else:
        dist = guna_distance()                 # owner's rollout order: outward from Guna
        js = sorted(js, key=lambda j: dist[j[5].name])
    js = [j for j in js if not (OUTD / j[5].name).exists()]
    print("chunks", len(js), flush=True)
    with ThreadPoolExecutor(int(sys.argv[2]) if len(sys.argv) > 2 else 1) as ex:
        for i, ok in enumerate(ex.map(fetch, js)):
            if i % 10 == 0:
                print(i, "of", len(js), flush=True)
    print("FINISHED")


if __name__ == "__main__":
    main()
