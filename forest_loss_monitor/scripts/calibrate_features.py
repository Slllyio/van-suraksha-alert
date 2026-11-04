"""Extra discriminators at the labelled calibration points: patch size, baseline cropland, annual embedding change."""
import ee
import numpy as np
import pandas as pd
import rasterio
from scipy import ndimage

from common import *

EIGHT = np.ones((3, 3), bool)
EMB = "GOOGLE/SATELLITE_EMBEDDING/V1/ANNUAL"


def patch_sizes(d):
    t = pd.read_csv(WORK / "tiles.csv", keep_default_na=False).set_index("tile")
    for mag in (1500, 2000, 3000):
        d[f"patch{mag}"] = 0
    for tile, g in d.groupby("tile"):
        s = t.loc[tile]
        with rasterio.open(WORK / "lt_v2" / f"{tile}.tif") as src:
            names = list(src.descriptions)
            yod, m = src.read(names.index("yod") + 1), src.read(names.index("mag") + 1)
        for mag in (1500, 2000, 3000):
            for yr, gg in g.groupby("map_year"):
                lab, n = ndimage.label((np.abs(yod - yr) <= 1) & (yod > 0) & (m >= mag), structure=EIGHT)
                size = np.bincount(lab.ravel(), minlength=n + 1)
                size[0] = 0
                r = ((s.y1 - gg.y) / RES).astype(int).values
                c = ((gg.x - s.x0) / RES).astype(int).values
                d.loc[gg.index, f"patch{mag}"] = size[lab[r, c]]
    return d


def ee_features(d):
    dw = ee.ImageCollection("GOOGLE/DYNAMICWORLD/V1").select(["crops", "trees", "shrub_and_scrub", "grass", "bare", "built"])
    base = dw.filterDate("2015-09-15", "2015-12-31").merge(dw.filterDate("2016-09-15", "2016-12-31")).mean()
    wc = ee.Image("ESA/WorldCover/v100/2020").rename("wc2020")
    proj = ee.Projection(WKT)
    rows = []
    for yr, g in d.groupby("map_year"):
        pts = ee.FeatureCollection([ee.Feature(ee.Geometry.Point([x, y], proj), dict(sample_id=int(i)))
                                    for x, y, i in zip(g.x, g.y, g.sample_id)])
        y0, y1 = max(int(yr) - 1, 2017), min(int(yr) + 1, 2025)
        e = ee.ImageCollection(EMB).filter(ee.Filter.calendarRange(y0, y0, "year")).mosaic()
        f = ee.ImageCollection(EMB).filter(ee.Filter.calendarRange(y1, y1, "year")).mosaic()
        sim = e.multiply(f).reduce("sum").rename("emb_sim")
        img = ee.Image.cat(base.rename([f"dw_{b}" for b in base.bandNames().getInfo()]), wc, sim)
        out = img.reduceRegions(pts, ee.Reducer.first(), scale=30, tileScale=4).getInfo()
        rows += [f["properties"] for f in out["features"]]
    return pd.DataFrame(rows)


def main():
    d = pd.read_csv(OUT / "calibration" / "calib_labels.csv")
    init()
    d = patch_sizes(d)
    d = d.merge(ee_features(d), on="sample_id", how="left")
    d.to_csv(OUT / "calibration" / "calib_features.csv", index=False)
    print(d.groupby("label")[["patch1500", "patch2000", "patch3000", "dw_crops", "dw_trees", "dw_grass", "dw_shrub_and_scrub", "emb_sim"]].median().round(3).to_string())
    print(pd.crosstab(d.label, d.wc2020).to_string())


if __name__ == "__main__":
    main()
