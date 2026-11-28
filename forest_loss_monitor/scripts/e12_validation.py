"""Independent validation sample and the layers reported with it.
Primary strata come from the map: clearing, partial, small patch, stable next to loss, stable tree cover, stable low tree cover
(mostly farmland, scrub and open ground inside recorded forest). Attributes per point: forest zone, canopy density (Meta/WRI 1 m
height to cover at 30 m), slope and aspect (Copernicus GLO-30), Hansen and CCDC verdicts.
Usage: e12_validation.py sample | attrs | ccdc | chips"""
import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor

import ee
import numpy as np
import pandas as pd
import rasterio
from pyproj import Transformer
from scipy import ndimage

from chips import make_chips
from common import *
from common import _landsat, _sentinel2
from zones import zone as zone_of

SEED = 20261104
# high_score_unmapped holds pixels with a high model score that the rules rejected: where missed loss is most likely
ALLOC = {"clearing": 80, "partial": 80, "small": 40, "stable_near_loss": 70, "high_score_unmapped": 110, "stable_tree": 80, "stable_low_tree": 50}
D = OUT / os.environ.get("FLM_VAL", "validation")
VERSION = os.environ.get("FLM_VERSION", "v3")
HIGH_Z, HIGH_DROP = -0.5, 0.05
CCDC_DROP = -0.20    # same size of NBR fall as the map rule; set before seeing any results of this round
KEY = D / "validation_key_DO_NOT_OPEN_BEFORE_LABELLING.csv"
LOW_TREE = 0.30
CANOPY = "projects/meta-forest-monitoring-okw37/assets/CanopyHeight"


def sample():
    D.mkdir(parents=True, exist_ok=True)
    c = np.load(WORK / "classified.npz")
    yod, cls = c["yod"], c["cls"]
    g = json.load(open(WORK / "grid.json"))
    with rasterio.open(WORK / "zone_beat.tif") as s:
        zone = s.read(1)
    t = pd.read_csv(WORK / "tiles.csv", keep_default_na=False)
    tree17 = np.zeros(zone.shape, "int16")
    for s in t.itertuples():
        with rasterio.open(WORK / f"emb_{VERSION}" / f"{s.tile}.tif") as src:
            i = list(src.descriptions).index("tree2017") + 1
            tree17[s.row:s.row + s.h, s.col:s.col + s.w] = src.read(i)
    near = ndimage.binary_dilation(cls > 0, iterations=3) & (cls == 0) & (zone > 0)
    sc = np.load(WORK / "score_state.npz")
    st = np.zeros(zone.shape, "uint8")
    st[(zone > 0) & (tree17 >= LOW_TREE * 1e4)] = 6
    st[(zone > 0) & (tree17 < LOW_TREE * 1e4)] = 7
    st[(zone > 0) & (sc["score"] >= HIGH_Z * 1000) & (sc["drop"] >= HIGH_DROP * 1e4)] = 5
    st[near] = 4
    st[cls == 3] = 3
    st[cls == 2] = 2
    st[cls == 1] = 1
    names = dict(zip(range(1, 8), ALLOC))
    rng = np.random.default_rng(SEED)
    rows, area = [], {}
    for k, n in names.items():
        ii = np.flatnonzero(st.ravel() == k)
        area[n] = float(len(ii) * PX_HA)
        for p in rng.choice(ii, min(ALLOC[n], len(ii)), replace=False):
            r, col = np.unravel_index(p, zone.shape)
            rows.append(dict(stratum=n, row=int(r), col=int(col), x=g["x0"] + (col + .5) * RES, y=g["y1"] - (r + .5) * RES,
                             map_year=int(yod[r, col]) if cls[r, col] else 0, zone_id=int(zone[r, col])))
    df = pd.DataFrame(rows).sample(frac=1, random_state=SEED).reset_index(drop=True)
    df.insert(0, "sample_id", np.arange(1, len(df) + 1))
    lon, lat = Transformer.from_crs(PROJ4, "EPSG:4326", always_xy=True).transform(df.x.values, df.y.values)
    df["lon"], df["lat"] = np.round(lon, 6), np.round(lat, 6)
    b = pd.read_csv(OUT / "beat_lookup.csv").set_index("zone_id")
    for col in ("Division", "Range", "Beat"):
        df[col] = df.zone_id.map(b[col])
    df["forest_zone"] = df.Division.map(zone_of)
    x = np.load(WORK / "aux_state.npz")
    df["hansen_year"] = x["hansen_year"][df.row, df.col] + 0
    df["treecover2000"] = x["treecover"][df.row, df.col] + 0
    df.to_csv(KEY, index=False)
    json.dump(area, open(D / "strata_area_ha.json", "w"), indent=1)
    print(df.stratum.value_counts().to_dict(), area)
    print(pd.crosstab(df.stratum, df.forest_zone).to_string())


def _points(df):
    p = ee.Projection(WKT)
    return ee.FeatureCollection([ee.Feature(ee.Geometry.Point([x, y], p), dict(sample_id=int(i))) for x, y, i in zip(df.x, df.y, df.sample_id)])


def attrs():
    """Canopy density and terrain per point; density = share of 1 m pixels at or above 3 m inside the 30 m pixel."""
    init()
    df = pd.read_csv(KEY)
    canopy = ee.ImageCollection(CANOPY).mosaic().gte(3).rename("canopy")
    dem = ee.ImageCollection("COPERNICUS/DEM/GLO30").select("DEM").mosaic().setDefaultProjection(ee.Projection("EPSG:4326").atScale(30))
    terrain = ee.Terrain.products(dem).select(["slope", "aspect"])
    rows = []

    def run(part):
        pts = _points(part)
        boxes = pts.map(lambda f: f.setGeometry(ee.Geometry(f.geometry()).buffer(15).bounds()))
        a = canopy.reduceRegions(boxes, ee.Reducer.mean(), scale=1, tileScale=4).getInfo()["features"]
        b = terrain.reduceRegions(pts, ee.Reducer.first(), scale=30, tileScale=4).getInfo()["features"]
        ca = {f["properties"]["sample_id"]: f["properties"].get("mean") for f in a}
        return [dict(sample_id=f["properties"]["sample_id"], canopy_cover=ca.get(f["properties"]["sample_id"]),
                     slope=f["properties"].get("slope"), aspect=f["properties"].get("aspect")) for f in b]
    parts = [df.iloc[i:i + 40] for i in range(0, len(df), 40)]
    with ThreadPoolExecutor(4) as ex:
        for r in ex.map(run, parts):
            rows += r
    a = pd.DataFrame(rows)
    a["canopy_class"] = pd.cut(a.canopy_cover, [-.01, .1, .4, .7, 1.01], labels=["scrub_lt10", "open_10_40", "moderate_40_70", "very_dense_ge70"])
    a["slope_class"] = pd.cut(a.slope, [-1, 5, 15, 30, 90], labels=["flat_lt5", "gentle_5_15", "moderate_15_30", "steep_gt30"])
    a["aspect_class"] = np.array(["N", "NE", "E", "SE", "S", "SW", "W", "NW", "N"])[((a.aspect.fillna(0) + 22.5) // 45).astype(int)]
    a.to_csv(D / "attributes.csv", index=False)
    print(a.canopy_class.value_counts().to_dict(), a.slope_class.value_counts().to_dict())


def ccdc_series(roi):
    keep = lambda i: i.select(["red", "nir", "swir2"]).toFloat().copyProperties(i, ["system:time_start"])
    c = ee.ImageCollection([])
    for y in range(2016, 2026):
        w = ("01-01", "12-31")
        c = c.merge(_landsat("LANDSAT/LC08/C02/T1_L2", y, w, roi, False).map(keep)).merge(_sentinel2(y, w, roi).map(keep))
        if y >= 2021:
            c = c.merge(_landsat("LANDSAT/LC09/C02/T1_L2", y, w, roi, False).map(keep))
        if y <= 2016:
            c = c.merge(_landsat("LANDSAT/LE07/C02/T1_L2", y, w, roi, True).map(keep))
    return c.map(lambda i: i.addBands(i.normalizedDifference(["nir", "swir2"]).rename("NBR").toFloat()).select(["red", "nir", "swir2", "NBR"]))


def ccdc():
    """CCDC on all Landsat and Sentinel-2 observations at the validation points; loss = NBR-falling break in 2018-2025."""
    init()
    df = pd.read_csv(KEY)
    rows = []

    def run(part):
        pts = _points(part)
        col = ccdc_series(pts.geometry().bounds(1, ee.Projection(WKT)))
        res = ee.Algorithms.TemporalSegmentation.Ccdc(collection=col, breakpointBands=["nir", "swir2", "NBR"], minObservations=6,
                                                      chiSquareProbability=0.99, minNumOfYearsScaler=1.33, dateFormat=1, maxIterations=25000, **{"lambda": 20})
        img = res.select(["tBreak", "NBR_magnitude"])
        out = img.reduceRegions(pts, ee.Reducer.first(), scale=30, tileScale=8).getInfo()["features"]
        return [dict(sample_id=f["properties"]["sample_id"], tBreak=f["properties"].get("tBreak"), mag=f["properties"].get("NBR_magnitude")) for f in out]
    parts = [df.iloc[i:i + 10] for i in range(0, len(df), 10)]
    with ThreadPoolExecutor(4) as ex:
        for r in ex.map(lambda p: _safe(run, p), parts):
            rows += r
    out = []
    for r in rows:
        t, m = r["tBreak"] or [], r["mag"] or []
        loss = [(a, b) for a, b in zip(t, m) if a and b is not None and 2018 <= a < 2026 and b < CCDC_DROP]
        out.append(dict(sample_id=r["sample_id"], ran=int(r["tBreak"] is not None), n_breaks=sum(1 for a in t if a), ccdc_loss=int(bool(loss)),
                        ccdc_year=int(min(loss, key=lambda x: x[1])[0]) if loss else 0, ccdc_mag=min((b for _, b in loss), default=0)))
    pd.DataFrame(out).to_csv(D / "ccdc.csv", index=False)
    print("ccdc points", len(out), "with loss break", sum(o["ccdc_loss"] for o in out))


def _safe(fn, p):
    try:
        return fn(p)
    except Exception as e:
        print("ccdc part failed", str(e)[:150], flush=True)
        return [dict(sample_id=int(i), tBreak=None, mag=None) for i in p.sample_id]


if __name__ == "__main__":
    cmd = sys.argv[1]
    if cmd == "chips":
        make_chips(pd.read_csv(KEY).assign(map_year=-1), D / "chips")
    else:
        {"sample": sample, "attrs": attrs, "ccdc": ccdc}[cmd]()
