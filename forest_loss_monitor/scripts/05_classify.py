"""Apply thresholds + minimum mapping unit to the LandTrendr attributes and write the state rasters.
Thresholds live in thresholds.json so calibration can change them without touching code.
Usage: 05_classify.py lt_v1 [--tiles-only]  (only tiles downloaded so far are processed)

Classes  (band `class`):  1 clearing (stand-replacing), 2 degradation (partial canopy loss),
                          3 small low-confidence patch (0.5-2.25 ha, reported separately from the totals)
Recovery (band `recovery`): 1 recovered, 2 persistent, 3 unknown (fewer than 3 years of follow-up)
"""
import json
import sys

import numpy as np
import pandas as pd
import rasterio
from rasterio.transform import from_origin
from rasterio.windows import Window
from scipy import ndimage

from common import *

NAMES = ["yod", "end", "dur", "mag", "pre_nbr", "pre_ndvi", "post_ndvi", "rec_ndvi", "last_ndvi", "base_ndvi",
         "burned", "hansen_year", "treecover", "dw_crops", "dw_trees"]
EIGHT = np.ones((3, 3), bool)


def load_state(version):
    """Stack the downloaded tiles onto the state grid."""
    g = json.load(open(WORK / "grid.json"))
    A = {n: np.zeros((g["height"], g["width"]), "int16") for n in NAMES}
    t = pd.read_csv(WORK / "tiles.csv", keep_default_na=False)
    have = np.zeros((g["height"], g["width"]), bool)
    for s in t.itertuples():
        f = WORK / version / f"{s.tile}.tif"
        if not f.exists():
            continue
        with rasterio.open(f) as src:
            for i, n in enumerate(src.descriptions):
                A[n][s.row:s.row + s.h, s.col:s.col + s.w] = src.read(i + 1)
        have[s.row:s.row + s.h, s.col:s.col + s.w] = True
    with rasterio.open(WORK / "zone_beat.tif") as src:
        zone = src.read(1)
    return g, A, zone, have


def patches(mask, yod, min_px):
    """Pixels of `mask` in patches of at least min_px. A patch may span adjacent detection years, because a coupe is
    often split across two years by the annual fit; a pixel stays if any year pair containing its year is big enough."""
    keep = np.zeros(yod.shape, bool)
    for y in REPORT_YEARS:
        m = mask & ((yod == y) | (yod == y + 1))
        if not m.any():
            continue
        lab, n = ndimage.label(m, structure=EIGHT)
        size = np.bincount(lab.ravel(), minlength=n + 1)
        size[0] = 0
        keep |= size[lab] >= min_px
    return keep


def classify(A, zone, th):
    """Returns (yod, cls, rec), 0 = no detection. Calibrated on blind visual labels, see README."""
    yod, mag, pre, post = A["yod"], A["mag"].astype("int32"), A["pre_ndvi"].astype("int32"), A["post_ndvi"].astype("int32")
    drop = pre - post
    valid = (zone > 0) & (yod > 0) & (pre >= th["pre_ndvi_min"] * 1e4) & (A["dw_crops"] < th["crop_max"] * 1e4)
    core_mask = valid & (mag >= th["core_mag"] * 1e4) & (drop >= th["core_ndvi_drop"] * 1e4)
    core = patches(core_mask, yod, th["core_min_px"])
    grow_mask = valid & (mag >= th["grow_mag"] * 1e4) & (drop >= th["grow_ndvi_drop"] * 1e4)
    # grow only a short way: edges of a coupe yes, but a wide search would absorb neighbouring noise
    main = ndimage.binary_dilation(core, structure=EIGHT, iterations=th["grow_px"], mask=grow_mask)
    small_mask = valid & (mag >= th["small_mag"] * 1e4) & (drop >= th["small_ndvi_drop"] * 1e4) & ~main
    small = patches(small_mask, yod, th["small_min_px"])
    clear = main & (mag >= th["clearing_mag"] * 1e4) & (post <= th["clearing_post_ndvi"] * 1e4)
    cls = np.zeros(yod.shape, "uint8")
    cls[main] = 2
    cls[clear] = 1
    cls[small] = 3
    out_yod = np.where(cls > 0, yod, 0).astype("int16")
    # recovery: NDVI 2-3 years after the drop has regained rec_fraction of it
    recovered = (A["rec_ndvi"].astype("int32") - post) >= th["rec_fraction"] * drop
    enough = A["end"] + 3 <= YEARS[-1]
    rec = np.where(cls > 0, np.where(enough, np.where(recovered, 1, 2), 3), 0).astype("uint8")
    return out_yod, cls, rec


def selftest():
    th = json.load(open(ROOT / "scripts" / "thresholds.json"))
    shape = (40, 40)
    A = {n: np.zeros(shape, "int16") for n in NAMES}
    A["end"][:] = 2020
    A["pre_ndvi"][:] = 7000
    A["post_ndvi"][:] = 6800
    A["rec_ndvi"][:] = 6800
    zone = np.ones(shape, "uint16")
    # a 6 x 6 coupe, a 3 x 3 small strong patch, one lone pixel, a coupe on farmland
    def put(r, c, h, w, year, mag, post):
        A["yod"][r:r + h, c:c + w] = year
        A["mag"][r:r + h, c:c + w] = mag
        A["post_ndvi"][r:r + h, c:c + w] = post
    put(2, 2, 6, 6, 2020, 4000, 3000)
    put(20, 2, 3, 3, 2021, 3500, 4000)
    put(30, 30, 1, 1, 2020, 5000, 3000)
    put(20, 20, 6, 6, 2020, 4000, 3000)
    A["dw_crops"][20:26, 20:26] = 3000
    A["rec_ndvi"][2:8, 2:8] = 3000
    yod, cls, rec = classify(A, zone, th)
    assert (cls[2:8, 2:8] == 1).all() and yod[3, 3] == 2020
    assert (cls[20:23, 2:5] == 3).all()
    assert cls[30, 30] == 0, "lone pixel must drop"
    assert (cls[20:26, 20:26] == 0).all(), "baseline farmland must drop"
    assert rec[3, 3] == 2, "no NDVI return = persistent"
    A["rec_ndvi"][2:8, 2:8] = 6500
    assert classify(A, zone, th)[2][3, 3] == 1, "NDVI back = recovered"
    A["yod"][2:8, 2:8] = 2024
    A["end"][2:8, 2:8] = 2024
    assert classify(A, zone, th)[2][3, 3] == 3, "under 3 years of follow-up = unknown"
    print("selftest ok")


def write_cog(path, arr, g, nodata=0, palette=None, resampling="nearest"):
    """Cloud Optimized GeoTIFF through GDAL's COG driver."""
    prof = dict(driver="COG", width=g["width"], height=g["height"], count=1, dtype=arr.dtype.name, crs=PROJ4,
                transform=from_origin(g["x0"], g["y1"], RES, RES), nodata=nodata, compress="DEFLATE", predictor=2,
                blocksize=512, overview_resampling=resampling, BIGTIFF="YES", num_threads="ALL_CPUS")
    with rasterio.open(path, "w", **prof) as o:
        o.write(arr, 1)


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        selftest()
        sys.exit()
    version = sys.argv[1]
    th = json.load(open(ROOT / "scripts" / "thresholds.json"))
    g, A, zone, have = load_state(version)
    yod, cls, rec = classify(A, zone, th)
    r = OUT / "rasters"
    r.mkdir(exist_ok=True, parents=True)
    write_cog(r / "mp_loss_year.tif", yod, g)
    write_cog(r / "mp_loss_class.tif", cls, g)
    write_cog(r / "mp_loss_recovery.tif", rec, g)
    write_cog(r / "mp_loss_magnitude_nbr_x10000.tif", np.where(yod > 0, A["mag"], 0).astype("int16"), g)
    hansen = (A["hansen_year"] >= 16) & (A["hansen_year"] <= 25) & (zone > 0)   # Hansen loss 2016-2025, any canopy
    print("Hansen 2016-2025 inside forest, all canopy ha", hansen.sum() * PX_HA,
          "; canopy>=10 ha", (hansen & (A["treecover"] >= 10)).sum() * PX_HA,
          "; also detected here ha", (hansen & (yod > 0)).sum() * PX_HA)
    np.savez_compressed(WORK / "classified.npz", yod=yod, cls=cls, rec=rec, burned=(A["burned"] > 0) & (yod > 0),
                        hansen=hansen & (yod > 0))
    print("detected ha", (yod > 0).sum() * PX_HA, {int(y): round((yod == y).sum() * PX_HA) for y in REPORT_YEARS})
