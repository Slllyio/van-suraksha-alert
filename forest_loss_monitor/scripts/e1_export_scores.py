"""AlphaEarth route, step 1: per-year embedding change score (1 - dot product of consecutive years) per tile.
Used to draw candidate samples and as one classifier feature. Usage: e1_export_scores.py cal|all"""
import sys
from datetime import datetime, timezone

import ee
import pandas as pd

from common import *

EMB = "GOOGLE/SATELLITE_EMBEDDING/V1/ANNUAL"


def embedding(year):
    return ee.ImageCollection(EMB).filterDate(f"{year}-01-01", f"{year + 1}-01-01").mosaic()


def embedding_years():
    pt = ee.Geometry.Point(78.5, 23.5)
    ms = ee.ImageCollection(EMB).filterBounds(pt).aggregate_array("system:time_start").getInfo()
    return sorted({datetime.fromtimestamp(m / 1000, timezone.utc).year for m in ms})


def change_score(y):
    return ee.Image(1).subtract(embedding(y - 1).multiply(embedding(y)).reduce("sum")).rename(f"c{y}")


if __name__ == "__main__":
    init()
    ys = embedding_years()
    print("embedding years", ys)
    COL = ASSET_DIR + "/emb_score"
    try:
        ee.data.getAsset(COL)
    except ee.EEException:
        ee.data.createAsset({"type": "ImageCollection"}, COL)
    fc = ee.FeatureCollection(DIVISIONS_ASSET)
    forest = ee.Image(0).byte().paint(fc, 1).paint(fc, 1, 3).selfMask()
    t = pd.read_csv(WORK / "tiles.csv", keep_default_na=False)
    if sys.argv[1] == "cal":
        t = t[t.cal != ""]
    done = {a["name"].split("/")[-1] for a in ee.data.listImages(COL).get("images", [])}
    active = {x["description"] for x in ee.data.getTaskList() if x["state"] in ("READY", "RUNNING")}
    img = ee.Image.cat([change_score(y) for y in ys[1:]]).multiply(10000).round().toInt16().updateMask(forest)
    for s in t.itertuples():
        d = f"flm_emb_{s.tile}"
        if s.tile in done or d in active:
            continue
        ee.batch.Export.image.toAsset(img, description=d, assetId=f"{COL}/{s.tile}", crs=WKT, crsTransform=tile_transform(s),
                                      dimensions=f"{s.w}x{s.h}", maxPixels=1e10, pyramidingPolicy={".default": "sample"}).start()
        print("started", s.tile, flush=True)
