"""Pull raw AlphaEarth embeddings directly (parallel chunks) to local int8 files: value x 127, per tile x year.
All later modelling runs locally, so a refit needs no new GEE work. Resumable. Usage: e6_fetch_embeddings.py tile1,tile2|all [threads]"""
import io
import sys
import time
from concurrent.futures import ThreadPoolExecutor

import ee
import numpy as np
import pandas as pd
import rasterio

from common import *
from e1_export_scores import embedding

CHUNK = 340                    # 340 x 340 x 64 x float32 = 29.6 MB, under the 48 MB request limit
BANDS = [f"A{i:02d}" for i in range(64)]
EMB_DIR = WORK / "embeddings"


def fetch_chunk(img, s, r, c, h, w):
    for attempt in range(6):
        try:
            raw = ee.data.computePixels(dict(expression=img, fileFormat="NPY", grid=dict(
                dimensions=dict(width=w, height=h), crsWkt=WKT,
                affineTransform=dict(scaleX=RES, shearX=0, translateX=s.x0 + c * RES, shearY=0, scaleY=-RES, translateY=s.y1 - r * RES))))
            a = np.load(io.BytesIO(raw))
            x = np.stack([a[b] for b in BANDS], axis=-1)
            return np.clip(np.nan_to_num(x) * 127, -127, 127).round().astype("int8")
        except Exception as e:
            if attempt == 5:
                raise
            time.sleep(2 ** attempt)


def fetch_tile(s, year, zone, ex):
    out = EMB_DIR / f"{s.tile}_{year}.npz"
    if out.exists():
        return 0
    img = embedding(year).select(BANDS).toFloat()
    jobs = []
    for r in range(0, int(s.h), CHUNK):
        for c in range(0, int(s.w), CHUNK):
            h, w = min(CHUNK, int(s.h) - r), min(CHUNK, int(s.w) - c)
            if (zone[r:r + h, c:c + w] > 0).any():
                jobs.append((r, c, h, w))
    futs = [ex.submit(fetch_chunk, img, s, *j) for j in jobs]
    mask = zone > 0
    vals = np.zeros((int(mask.sum()), 64), "int8")
    idx = np.cumsum(mask.ravel()).reshape(mask.shape) - 1        # forest pixel order within the tile
    for (r, c, h, w), f in zip(jobs, futs):
        x = f.result()
        m = mask[r:r + h, c:c + w]
        vals[idx[r:r + h, c:c + w][m]] = x[m]
    tmp = out.with_suffix(".tmp.npz")
    np.savez(tmp, vals=vals)                                     # uncompressed: dense signed vectors barely compress
    tmp.replace(out)
    return len(jobs)


def main():
    init()
    EMB_DIR.mkdir(exist_ok=True)
    t = pd.read_csv(WORK / "tiles.csv", keep_default_na=False)
    if sys.argv[1] != "all":
        t = t[t.tile.isin(sys.argv[1].split(","))]
    t = t.sort_values("forest_px", ascending=False)
    threads = int(sys.argv[2]) if len(sys.argv) > 2 else 24
    with rasterio.open(WORK / "zone_beat.tif") as src:
        full = src.read(1)
    t0 = time.time()
    with ThreadPoolExecutor(threads) as ex:
        for s in t.itertuples():
            z = full[s.row:s.row + s.h, s.col:s.col + s.w]
            for y in range(2017, 2026):
                n = fetch_tile(s, y, z, ex)
                print(s.tile, y, n, "chunks", int(time.time() - t0), "s", flush=True)


if __name__ == "__main__":
    main()
