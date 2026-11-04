"""Independent water mask on the state grid: JRC Global Surface Water maximum extent (1984-2021), widened by 1 pixel for shorelines.
Chosen as a fixed physical rule, not tuned on the labels. Output: work/water.npy"""
import io
import json
import time
from concurrent.futures import ThreadPoolExecutor

import ee
import numpy as np
import pandas as pd
from scipy import ndimage

from common import *

CHUNK = 3000


def tile(img, s):
    for attempt in range(6):
        try:
            raw = ee.data.computePixels(dict(expression=img, fileFormat="NPY", grid=dict(
                dimensions=dict(width=int(s.w), height=int(s.h)), crsWkt=WKT,
                affineTransform=dict(scaleX=RES, shearX=0, translateX=s.x0, shearY=0, scaleY=-RES, translateY=s.y1))))
            return s, np.load(io.BytesIO(raw))["w"]
        except Exception:
            if attempt == 5:
                raise
            time.sleep(2 ** attempt)


def main():
    init()
    g = json.load(open(WORK / "grid.json"))
    t = pd.read_csv(WORK / "tiles.csv", keep_default_na=False)
    img = ee.Image("JRC/GSW1_4/GlobalSurfaceWater").select("max_extent").unmask(0).rename("w").toByte()
    out = np.zeros((g["height"], g["width"]), bool)
    with ThreadPoolExecutor(6) as ex:
        for s, a in ex.map(lambda s: tile(img, s), t.itertuples()):
            out[s.row:s.row + s.h, s.col:s.col + s.w] = a > 0
    out = ndimage.binary_dilation(out, structure=np.ones((3, 3), bool))
    np.save(WORK / "water.npy", out)
    print("water ha", round(out.sum() * PX_HA))


if __name__ == "__main__":
    main()
