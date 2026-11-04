"""Download tile assets to local GeoTIFFs (chunked, 8 threads, resumable). Usage: 04_download.py lt_v1"""
import io
import sys
from concurrent.futures import ThreadPoolExecutor

import ee
import numpy as np
import pandas as pd
import rasterio
from rasterio.transform import from_origin

from common import *

CHUNK = 1000
init()
name = sys.argv[1]
col = f"{ASSET_DIR}/{name}"
d = WORK / name
d.mkdir(parents=True, exist_ok=True)
t = pd.read_csv(WORK / "tiles.csv", keep_default_na=False).set_index("tile")
ids = [a["name"] for a in ee.data.listImages(col).get("images", [])]


def fetch(asset, tile):
    out = d / f"{tile}.tif"
    if out.exists():
        return
    s = t.loc[tile]
    bands = [b["id"] for b in ee.data.getAsset(asset)["bands"]]
    arr = np.zeros((len(bands), int(s.h), int(s.w)), "int16")
    for r in range(0, int(s.h), CHUNK):
        for c in range(0, int(s.w), CHUNK):
            h, w = min(CHUNK, int(s.h) - r), min(CHUNK, int(s.w) - c)
            for attempt in range(5):
                try:
                    raw = ee.data.getPixels(dict(assetId=asset, fileFormat="NPY", grid=dict(
                        dimensions=dict(width=w, height=h), crsWkt=WKT,
                        affineTransform=dict(scaleX=RES, shearX=0, translateX=s.x0 + c * RES,
                                             shearY=0, scaleY=-RES, translateY=s.y1 - r * RES))))
                    break
                except Exception:
                    if attempt == 4:
                        raise
            a = np.load(io.BytesIO(raw))
            for i, b in enumerate(bands):
                arr[i, r:r + h, c:c + w] = a[b]
    with rasterio.open(out, "w", driver="GTiff", width=int(s.w), height=int(s.h), count=len(bands), dtype="int16",
                       crs=PROJ4, transform=from_origin(s.x0, s.y1, RES, RES), compress="deflate", predictor=2,
                       tiled=True) as o:
        o.write(arr)
        o.descriptions = tuple(bands)
    print("ok", tile, flush=True)


with ThreadPoolExecutor(8) as ex:
    list(ex.map(lambda a: fetch(a, a.split("/")[-1]), ids))
print("done", len(ids))
