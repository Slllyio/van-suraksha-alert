"""Stage B: LandTrendr on the stored annual stacks. Exports raw per-pixel attributes of the greatest disturbance
with detection year in 2016-2025, so thresholds and the MMU can be tuned locally without recomputing anything.
Usage: 03_export_landtrendr.py cal|all [--version v3]"""
import sys

import ee
import pandas as pd

from common import *

LT_PARAMS = dict(maxSegments=4, spikeThreshold=0.9, vertexCountOvershoot=3, preventOneYearRecovery=True,
                 recoveryThreshold=0.25, pvalThreshold=0.1, bestModelProportion=0.75, minObservationsNeeded=6)
COARSE_M = 960       # anomaly surface grid; served from the mean pyramids of the stack assets
ANOM_RADIUS_PX = 16  # ~15 km smoothing radius
MISSING = -30000     # NDVI x 10000 no-observation flag inside the fixed-length array
BANDS = ["yod", "end", "dur", "mag", "pre_nbr", "pre_ndvi", "post_ndvi", "rec_ndvi", "last_ndvi", "base_ndvi",
         "burned", "hansen_year", "treecover", "dw_crops", "dw_trees"]


def local_anomaly(stack, band):
    """Regional inter-annual anomaly of `band` per year: monsoon/phenology swing shared by all forest within ~15 km."""
    coarse = ee.Projection(WKT).atScale(COARSE_M)
    smooth = [stack.select(f"{band}_{y}").rename("v").reproject(coarse).focal_mean(ANOM_RADIUS_PX, "circle", "pixels")
              .reproject(coarse) for y in YEARS]
    med = ee.ImageCollection(smooth).median()
    return [s.subtract(med).resample("bilinear") for s in smooth]


def annual_series(stack):
    """Returns the NBR collection for LandTrendr and the same-year NDVI as one fixed-length 14-element array image."""
    nbr_off, ndvi_off = local_anomaly(stack, "NBR"), local_anomaly(stack, "NDVI")
    seg, ndvi = [], []
    for i, y in enumerate(YEARS):
        n = stack.select(f"NBR_{y}").subtract(nbr_off[i])
        seg.append(n.multiply(-1).rename("seg").toInt16().set("system:time_start", ee.Date.fromYMD(y, 7, 1).millis()))
        ndvi.append(stack.select(f"NDVI_{y}").subtract(ndvi_off[i]).rename(f"n{y}").unmask(MISSING))
    return ee.ImageCollection(seg), ee.Image.cat(ndvi).toFloat().toArray()


def burned_by_year():
    """MCD64A1 burned in the 12 months before each year's leaf-on composite (Nov Y-1 .. Oct Y)."""
    c = ee.ImageCollection("MODIS/061/MCD64A1").select("BurnDate")
    return ee.Image.cat([c.filterDate(f"{y - 1}-11-01", f"{y}-11-01").max().gt(0).unmask(0).toByte() for y in REPORT_YEARS])


def attributes(stack):
    series, ndvi = annual_series(stack)
    lt = ee.Algorithms.TemporalSegmentation.LandTrendr(timeSeries=series, **LT_PARAMS)
    arr = lt.select("LandTrendr")
    vert = arr.arrayMask(arr.arraySlice(0, 3, 4))          # year, src, fit, isVertex at vertices only
    left, right = vert.arraySlice(1, 0, -1), vert.arraySlice(1, 1)
    y0, y1 = left.arraySlice(0, 0, 1), right.arraySlice(0, 0, 1)
    v0, v1 = left.arraySlice(0, 2, 3), right.arraySlice(0, 2, 3)
    seg = ee.Image.cat(y0.add(1), y1, y1.subtract(y0), v1.subtract(v0), v0.multiply(-1)).toArray(0).toFloat()
    # yod, end, dur, mag (NBR x 10000 drop, + = loss), pre_nbr; keep losses detected in the reporting years
    yod_row = seg.arraySlice(0, 0, 1)
    keep = yod_row.gte(REPORT_YEARS[0]).And(yod_row.lte(REPORT_YEARS[-1])).And(seg.arraySlice(0, 3, 4).gt(0))
    dummy = ee.Image(ee.Array([[0.0]] * 5)).toFloat()
    seg = seg.arrayMask(keep).arrayCat(dummy, 1)           # dummy column: 0 magnitude when no loss segment exists
    best = seg.arraySort(seg.arraySlice(0, 3, 4).multiply(-1)).arraySlice(1, 0, 1).arrayProject([0])               .arrayFlatten([["yod", "end", "dur", "mag", "pre_nbr"]])

    def at(yr):
        """Observed, anomaly-removed NDVI at calendar year `yr`, masked if that year has no observation."""
        v = ndvi.arrayGet(ee.Image(yr).subtract(YEARS[0]).max(0).min(len(YEARS) - 1).toInt())
        return v.updateMask(v.gt(MISSING + 1))

    def mean2(a, b):
        return ee.Image.cat(at(a).rename("a"), at(b).rename("b")).reduce(ee.Reducer.mean())

    has = best.select("yod").gt(0)
    yod, end = best.select("yod"), best.select("end")
    pre = mean2(yod.subtract(2), yod.subtract(1)).updateMask(has).rename("pre_ndvi")
    post = mean2(end, end.add(1)).updateMask(has).rename("post_ndvi")
    rec = mean2(end.add(2), end.add(3)).updateMask(has).rename("rec_ndvi")
    last = mean2(2024, 2025).rename("last_ndvi")
    base = ee.ImageCollection([stack.select(f"NDVI_{y}").rename("n") for y in (2013, 2014, 2015)]).median().rename("base_ndvi")
    burn = burned_by_year().toArray().arrayGet(yod.subtract(REPORT_YEARS[0]).max(0).min(len(REPORT_YEARS) - 1).toInt())         .updateMask(has).rename("burned")
    dw = ee.ImageCollection("GOOGLE/DYNAMICWORLD/V1").select(["crops", "trees"])
    dw_base = dw.filterDate("2015-09-15", "2015-12-31").merge(dw.filterDate("2016-09-15", "2016-12-31")).mean() \
                .multiply(10000).rename(["dw_crops", "dw_trees"])   # land cover before the reporting period
    h = ee.Image(HANSEN)
    out = ee.Image.cat(best, pre, post, rec, last, base, burn, h.select("lossyear").rename("hansen_year"),
                       h.select("treecover2000").rename("treecover"), dw_base.unmask(0))
    fill = out.select(["yod", "end", "dur", "mag", "pre_nbr", "pre_ndvi", "post_ndvi", "rec_ndvi", "burned"]).unmask(0)
    return ee.Image.cat(fill, out.select(["last_ndvi", "base_ndvi", "hansen_year", "treecover", "dw_crops", "dw_trees"])).select(BANDS).toInt16()              .updateMask(stack.select("NBR_2020").mask().Or(stack.select("NBR_2024").mask()))


if __name__ == "__main__":
    init()
    version = sys.argv[sys.argv.index("--version") + 1] if "--version" in sys.argv else "v3"
    COL, STACK = f"{ASSET_DIR}/lt_{version}", ASSET_DIR + "/stack"
    try:
        ee.data.getAsset(COL)
    except ee.EEException:
        ee.data.createAsset({"type": "ImageCollection"}, COL)
    stack = ee.ImageCollection(STACK).mosaic()
    t = pd.read_csv(WORK / "tiles.csv", keep_default_na=False)
    if sys.argv[1] == "cal":
        t = t[t.cal != ""]
    done = {a["name"].split("/")[-1] for a in ee.data.listImages(COL).get("images", [])}
    have = {a["name"].split("/")[-1] for a in ee.data.listImages(STACK).get("images", [])}
    active = {x["description"] for x in ee.data.getTaskList() if x["state"] in ("READY", "RUNNING")}
    for s in t.itertuples():
        d = f"flm_lt_{version}_{s.tile}"
        if s.tile in done or d in active or s.tile not in have:
            continue
        ee.batch.Export.image.toAsset(attributes(stack), description=d, assetId=f"{COL}/{s.tile}", crs=WKT,
                                      crsTransform=tile_transform(s), dimensions=f"{s.w}x{s.h}", maxPixels=1e10,
                                      pyramidingPolicy={".default": "sample"}).start()
        print("started", s.tile, flush=True)
