"""Dynamic World seasonal means at points, per year 2017-2025: monsoon Aug-Oct (fallback Oct-Nov, then the neighbouring year) and
rabi Jan-Mar, plus JRC occurrence. Long table for the hard gates in e22. Resumable. Usage: e21_dw_points.py points.csv out.csv"""
import sys
from concurrent.futures import ThreadPoolExecutor

import ee
import pandas as pd

from common import *

CLASSES = ["water", "trees", "grass", "shrub_and_scrub", "crops", "built", "bare"]
YEARS9 = list(range(2017, 2026))
MIN_IMAGES = 3
GROUP = 25
D = OUT / "timeseries"


def season(col, start, end):
    return col.filterDate(start, end).select(CLASSES)


def monsoon(col, y):
    """Aug-Oct mean; pixels with under MIN_IMAGES clear images fall back to Oct-Nov, then to the same season of the next year."""
    a = season(col, f"{y}-08-01", f"{y}-11-01")
    b = season(col, f"{y}-10-01", f"{y}-12-01")
    c = season(col, f"{min(y + 1, 2025)}-08-01", f"{min(y + 1, 2025)}-11-01")
    def with_count(ic):
        return ic.mean().updateMask(ic.select("trees").count().gte(MIN_IMAGES))
    return ee.ImageCollection([with_count(c), with_count(b), with_count(a)]).mosaic()


def stack():
    col = ee.ImageCollection("GOOGLE/DYNAMICWORLD/V1")
    bands = [ee.Image("JRC/GSW1_4/GlobalSurfaceWater").select("occurrence").unmask(0).rename("gsw_occ")]
    for y in YEARS9:
        bands.append(monsoon(col, y).rename([f"m{y}_{c}" for c in CLASSES]))
        bands.append(season(col, f"{y}-01-01", f"{y}-04-01").mean().rename([f"r{y}_{c}" for c in CLASSES]))
    return ee.Image.cat(bands).toFloat()


def run(part, img):
    p = ee.Projection(WKT)
    pts = ee.FeatureCollection([ee.Feature(ee.Geometry.Point([x, y], p), dict(sample_id=int(i))) for x, y, i in zip(part.x, part.y, part.sample_id)])
    for attempt in range(4):
        try:
            return [f["properties"] for f in img.reduceRegions(pts, ee.Reducer.first(), crs=WKT, scale=RES, tileScale=8).getInfo()["features"]]
        except Exception as e:
            msg = str(e)[:150]
    print("failed", list(part.sample_id)[:3], msg, flush=True)
    return []


def main():
    init()
    df = pd.read_csv(sys.argv[1])
    out = D / sys.argv[2]
    done = pd.read_csv(out) if out.exists() else pd.DataFrame(columns=["sample_id"])
    df = df[~df.sample_id.isin(done.sample_id)].assign(ry=lambda d: (d.y // 45000).astype(int), rx=lambda d: (d.x // 45000).astype(int)).sort_values(["ry", "rx"])
    img = stack()
    parts = [df.iloc[i:i + GROUP] for i in range(0, len(df), GROUP)]
    rows = []
    with ThreadPoolExecutor(5) as ex:
        for r in ex.map(lambda p: run(p, img), parts):
            rows += r
            pd.concat([done, pd.DataFrame(rows)], ignore_index=True).to_csv(out, index=False)
            print(len(rows), flush=True)
    print("done", len(rows))


if __name__ == "__main__":
    main()
