"""Comparison layers on the state grid, resumable per tile: Hansen loss year and canopy 2000, MCD64A1 burned per loss year.
Light bands, so requests are faster than the embeddings. Usage: e9_fetch_aux.py (then the assembled file is work/aux_state.npz)."""
import io
import json
import time
from concurrent.futures import ThreadPoolExecutor

import ee
import numpy as np
import pandas as pd
import rasterio

from common import *

YEARS8 = list(range(2018, 2026))
CHUNK = 1500
D = WORK / "aux"


def image():
    h = ee.Image(HANSEN)
    c = ee.ImageCollection("MODIS/061/MCD64A1").select("BurnDate")
    burn = [c.filterDate(f"{y - 1}-11-01", f"{y}-11-01").max().gt(0).unmask(0).toByte().rename(f"b{y}") for y in YEARS8]
    return ee.Image.cat([h.select("lossyear").rename("hansen_year").toByte(), h.select("treecover2000").rename("treecover").toByte()] + burn)


def fetch_tile(img, s, names):
    out = D / f"{s.tile}.npy"
    if out.exists():
        return
    arr = np.zeros((len(names), int(s.h), int(s.w)), "uint8")
    for r in range(0, int(s.h), CHUNK):
        for c in range(0, int(s.w), CHUNK):
            h, w = min(CHUNK, int(s.h) - r), min(CHUNK, int(s.w) - c)
            for attempt in range(6):
                try:
                    raw = ee.data.computePixels(dict(expression=img, fileFormat="NPY", grid=dict(
                        dimensions=dict(width=w, height=h), crsWkt=WKT,
                        affineTransform=dict(scaleX=RES, shearX=0, translateX=s.x0 + c * RES, shearY=0, scaleY=-RES, translateY=s.y1 - r * RES))))
                    break
                except Exception:
                    if attempt == 5:
                        raise
                    time.sleep(2 ** attempt)
            a = np.load(io.BytesIO(raw))
            for i, n in enumerate(names):
                arr[i, r:r + h, c:c + w] = a[n]
    np.save(out, arr)
    print("ok", s.tile, flush=True)


def main():
    init()
    D.mkdir(exist_ok=True)
    t = pd.read_csv(WORK / "tiles.csv", keep_default_na=False)
    img = image()
    names = ["hansen_year", "treecover"] + [f"b{y}" for y in YEARS8]
    with ThreadPoolExecutor(6) as ex:
        list(ex.map(lambda s: fetch_tile(img, s, names), t.itertuples()))
    g = json.load(open(WORK / "grid.json"))
    H, W = g["height"], g["width"]
    hy, tc, burned = np.zeros((H, W), "uint8"), np.zeros((H, W), "uint8"), np.zeros((len(YEARS8), H, W), "uint8")
    for s in t.itertuples():
        a = np.load(D / f"{s.tile}.npy")
        hy[s.row:s.row + s.h, s.col:s.col + s.w] = a[0]
        tc[s.row:s.row + s.h, s.col:s.col + s.w] = a[1]
        burned[:, s.row:s.row + s.h, s.col:s.col + s.w] = a[2:]
    np.savez_compressed(WORK / "aux_state.npz", hansen_year=hy, treecover=tc, burned=burned)
    print("aux_state written")


if __name__ == "__main__":
    main()
