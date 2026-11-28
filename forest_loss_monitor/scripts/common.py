"""Shared grid, composite and LandTrendr definitions for the MP forest-loss pipeline."""
import os
from pathlib import Path

import ee

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "outputs"
WORK = ROOT / "work"          # intermediate rasters (not deliverables)
SHP = ROOT.parent / "data/aoi/MP_Merge Divsion Beat Range/Mp_Beat_Merge.shp"
DISTRICT_URL = ("https://raw.githubusercontent.com/datta07/INDIAN-SHAPEFILES/master/STATES/"
                "MADHYA%20PRADESH/MADHYA%20PRADESH_DISTRICTS.geojson")

GEE_PROJECT = os.environ.get("GEE_PROJECT", "van-suraksha-alert")
ASSET_DIR = f"projects/{GEE_PROJECT}/assets/forest_loss_monitor"
DIVISIONS_ASSET = f"projects/{GEE_PROJECT}/assets/mp_forest_divisions"
HANSEN = "UMD/hansen/global_forest_change_2025_v1_13"

# Equal-area grid: every pixel is exactly 900 m2, so ha = pixels * 0.09 with no latitude correction.
PROJ4 = "+proj=aea +lat_1=22 +lat_2=25 +lat_0=24 +lon_0=78.5 +datum=WGS84 +units=m +no_defs"
WKT = ('PROJCS["MP_Albers",GEOGCS["WGS 84",DATUM["WGS_1984",SPHEROID["WGS 84",6378137,298.257223563]],'
       'PRIMEM["Greenwich",0],UNIT["degree",0.0174532925199433]],PROJECTION["Albers_Conic_Equal_Area"],'
       'PARAMETER["standard_parallel_1",22],PARAMETER["standard_parallel_2",25],'
       'PARAMETER["latitude_of_center",24],PARAMETER["longitude_of_center",78.5],'
       'PARAMETER["false_easting",0],PARAMETER["false_northing",0],UNIT["metre",1]]')
RES = 30
PX_HA = RES * RES / 1e4
TILE_PX = 3000                # 90 km tiles

YEARS = list(range(2013, 2027))   # 2026 is a partial window, used only to anchor the end of the series
REPORT_YEARS = list(range(2016, 2026))
WINDOW = ("09-15", "11-30")       # chosen by composite_window_test.py, see README


def init():
    ee.Initialize(project=GEE_PROJECT)


def _landsat(coll, year, window, roi, etm):
    nir, swir1, swir2, red, green = ("SR_B4", "SR_B5", "SR_B7", "SR_B3", "SR_B2") if etm else \
                                    ("SR_B5", "SR_B6", "SR_B7", "SR_B4", "SR_B3")
    def prep(img):
        qa = img.select("QA_PIXEL")
        bad = qa.bitwiseAnd(0b111110).neq(0)      # dilated cloud, cirrus, cloud, shadow, snow
        sat = img.select("QA_RADSAT").neq(0)
        x = img.select([red, nir, swir1, swir2], ["red", "nir", "swir1", "swir2"]) \
               .multiply(2.75e-5).add(-0.2).updateMask(bad.Not()).updateMask(sat.Not())
        if etm:   # Roy et al. 2016 RMA ETM+ -> OLI
            x = x.multiply(ee.Image([0.9825, 1.0073, 1.0171, 0.9949])) \
                 .add(ee.Image([-0.0022, -0.0021, -0.0030, 0.0029])).rename(x.bandNames())
        return x.copyProperties(img, ["system:time_start"])
    return (ee.ImageCollection(coll).filterBounds(roi)
            .filterDate(f"{year}-{window[0]}", f"{year}-{window[1]}").map(prep))


def _sentinel2(year, window, roi):
    cs = ee.ImageCollection("GOOGLE/CLOUD_SCORE_PLUS/V1/S2_HARMONIZED")
    def prep(img):
        # Claverie et al. 2018 (HLS) MSI -> OLI bandpass adjustment; 20 m bands bilinear to the 30 m grid
        x = img.select(["B4", "B8A", "B11", "B12"], ["red", "nir", "swir1", "swir2"]).divide(10000) \
               .multiply(ee.Image([0.9765, 0.9983, 0.9987, 1.0030])) \
               .add(ee.Image([0.0009, -0.0001, -0.0011, -0.0012])) \
               .rename(["red", "nir", "swir1", "swir2"]).resample("bilinear")
        return x.updateMask(img.select("cs_cdf").gte(0.6)).copyProperties(img, ["system:time_start"])
    return (ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED").filterBounds(roi)
            .filterDate(f"{year}-{window[0]}", f"{year}-{window[1]}")
            .linkCollection(cs, ["cs_cdf"]).map(prep))


# Fitted by fit_s2_to_landsat.py (RMA on 6 divisions, 2017-2025 composite pairs; r = 0.974 / 0.955)
S2_TO_LANDSAT = {"NBR": (0.9660, 0.0554), "NDVI": (0.9543, 0.0484)}


def _indices(img):
    return ee.Image.cat(img.normalizedDifference(["nir", "swir2"]).rename("NBR"),
                        img.normalizedDifference(["nir", "red"]).rename("NDVI")).toFloat()


def _s2_indices(img):
    x = _indices(img)
    return ee.Image.cat(x.select("NBR").multiply(S2_TO_LANDSAT["NBR"][0]).add(S2_TO_LANDSAT["NBR"][1]),
                        x.select("NDVI").multiply(S2_TO_LANDSAT["NDVI"][0]).add(S2_TO_LANDSAT["NDVI"][1])).toFloat()             .copyProperties(img, ["system:time_start"])


def observations(year, roi, window=WINDOW, sensors=("L7", "L8", "L9", "S2")):
    """All harmonised clear NBR/NDVI observations in the leaf-on window of `year`."""
    keep = lambda i: _indices(i).copyProperties(i, ["system:time_start"])
    c = ee.ImageCollection([])
    if "L8" in sensors and year >= 2013:
        c = c.merge(_landsat("LANDSAT/LC08/C02/T1_L2", year, window, roi, False).map(keep))
    if "L9" in sensors and year >= 2021:
        c = c.merge(_landsat("LANDSAT/LC09/C02/T1_L2", year, window, roi, False).map(keep))
    if "L7" in sensors and year <= 2016:   # only while L8 alone is thin; L7 orbit drifts after 2017
        c = c.merge(_landsat("LANDSAT/LE07/C02/T1_L2", year, window, roi, True).map(keep))
    if "S2" in sensors and year >= 2016:
        c = c.merge(_sentinel2(year, window, roi).map(_s2_indices))
    return c


def composite(year, roi, window=WINDOW, sensors=("L7", "L8", "L9", "S2")):
    return observations(year, roi, window, sensors).median()         .set("system:time_start", ee.Date.fromYMD(year, 10, 15).millis()).set("year", year)


def tile_transform(row):
    return [RES, 0, int(row.x0), 0, -RES, int(row.y1)]
