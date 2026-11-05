"""How much time does each part of a 10 m chunk cost? Same chunk, same grid, three versions, run one after another.
Time is only a stand-in for compute, and Restricted Mode adds queueing, so read differences as rough. Usage: e40_cost_test.py"""
import io
import time

import ee
import numpy as np
import pandas as pd

from common import *
from e32_enetra10m import rule_bands
from e33_map10m import product


def forest_mask():
    """Division polygons plus a 100 m outline, drawn on the export grid (10 px at 10 m)."""
    fc = ee.FeatureCollection(DIVISIONS_ASSET)
    return ee.Image(0).byte().paint(fc, 1).paint(fc, 1, 20).selfMask()


def timed(name, img, s, r, c, n):
    x0, y1 = s.x0 + c * 10, s.y1 - r * 10
    t = time.time()
    for attempt in range(40):
        try:
            raw = ee.data.computePixels(dict(expression=img, fileFormat="NPY", grid=dict(dimensions=dict(width=n, height=n), crsWkt=WKT,
                                        affineTransform=dict(scaleX=10, shearX=0, translateX=x0, shearY=0, scaleY=-10, translateY=y1))))
            print(f"{name:42s} {time.time() - t:6.0f} s, {len(raw) // 1024} kB", flush=True)
            return np.load(io.BytesIO(raw))
        except Exception as e:
            if "Too Many" not in str(e):
                print(name, "error", str(e)[:150], flush=True)
                return None
            t = time.time()      # queueing is not compute: restart the clock
            time.sleep(30)
    print(name, "never got a slot", flush=True)


def main():
    init()
    t = pd.read_csv(WORK / "tiles.csv", keep_default_na=False).set_index("tile")
    s = t.loc["r06c02"]
    s = s.copy()
    s["tile"] = "r06c02"
    r, c, n = 2700, 2700, 450
    x0, y1 = s.x0 + c * 10, s.y1 - r * 10
    roi = ee.Geometry.Rectangle([x0, y1 - n * 10, x0 + n * 10, y1], ee.Projection(WKT), False).transform("EPSG:4326", 10)
    bands = rule_bands(roi)[0]
    rule = bands.select(["e_recent", "late", "s2c_a", "s2c_b", "water"]).toByte()
    m = forest_mask()
    a = None

    full = timed("rule + year, whole chunk (current)", product(roi), s, r, c, n)
    if a is not None and full is not None:
        print("hit share", round(float((a["e_recent"] > 0).mean()), 4), "pixels flagged", int((full["cls"] > 0).sum()))


if __name__ == "__main__":
    main()
