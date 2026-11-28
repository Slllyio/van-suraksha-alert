"""Stage A: export the annual leaf-on NBR/NDVI stack per tile to an EE ImageCollection (10000 x index, int16).
Usage: 02_export_composites.py cal|all   -- resumable, skips finished or running tiles."""
import sys

import ee
import pandas as pd

from common import *

init()
COL = ASSET_DIR + "/stack"
for path, typ in ((ASSET_DIR, "Folder"), (COL, "ImageCollection")):
    try:
        ee.data.getAsset(path)
    except ee.EEException:
        ee.data.createAsset({"type": typ}, path)
t = pd.read_csv(WORK / "tiles.csv", keep_default_na=False)
if sys.argv[1] == "cal":
    t = t[t.cal != ""]
fc = ee.FeatureCollection(DIVISIONS_ASSET)
forest = ee.Image(0).byte().paint(fc, 1).paint(fc, 1, 3).selfMask()  # polygon + 3 px outline; exact clip happens locally
done = {a["name"].split("/")[-1] for a in ee.data.listImages(COL).get("images", [])}
active = {x["description"] for x in ee.data.getTaskList() if x["state"] in ("READY", "RUNNING")}
for s in t.itertuples():
    d = f"flm_stack_{s.tile}"
    if s.tile in done or d in active:
        continue
    roi = ee.Geometry.Rectangle([s.x0, s.y1 - s.h * RES, s.x0 + s.w * RES, s.y1], ee.Projection(WKT), False)
    roi_ll = roi.transform("EPSG:4326", 100)
    img = ee.Image.cat([composite(y, roi_ll).rename([f"NBR_{y}", f"NDVI_{y}"]) for y in YEARS])
    img = img.multiply(10000).round().toInt16().updateMask(forest)
    ee.batch.Export.image.toAsset(img, description=d, assetId=f"{COL}/{s.tile}", crs=WKT,
                                  crsTransform=tile_transform(s), dimensions=f"{s.w}x{s.h}", maxPixels=1e10,
                                  pyramidingPolicy={".default": "mean"}).start()
    print("started", s.tile, s.cal, flush=True)
