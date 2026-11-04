"""Dense time series at points, 2015-2025: Landsat 8/9 C2 + Sentinel-2 SR, cloud and shadow masked, NBR/NDVI/NDMI/SWIR1.
CCDC keeps its raw segments so loss rules can be tuned locally without another GEE run. LandTrendr at points uses the stored stacks.
Usage: e18_timeseries.py fit | ccdc <points.csv> <out.jsonl> | lt <points.csv> <out.csv>     (points: sample_id, x, y, tile)
Resumable: finished sample_ids are skipped."""
import importlib
import json
import sys
from concurrent.futures import ThreadPoolExecutor

import ee
import numpy as np
import pandas as pd

from common import *
from common import _landsat, _sentinel2

D = OUT / "timeseries"
FIT = D / "s2_fit.json"
START, END = 2015, 2025
GROUP = 12              # points per CCDC request, spatially close
BANDS = ["NBR", "NDVI", "NDMI", "SWIR1"]


def landsat_bands(i):
    x = ee.Image.cat(i.normalizedDifference(["nir", "swir2"]).rename("NBR"), i.normalizedDifference(["nir", "red"]).rename("NDVI"),
                     i.normalizedDifference(["nir", "swir1"]).rename("NDMI"), i.select("swir1").rename("SWIR1"))
    return x.toFloat().copyProperties(i, ["system:time_start"])


def s2_bands(F):
    def f(i):
        x = ee.Image(landsat_bands(i))
        out = [x.select(b).multiply(F[b][0]).add(F[b][1]) for b in BANDS]
        return ee.Image.cat(out).rename(BANDS).toFloat().copyProperties(i, ["system:time_start"])
    return f


def series(roi, F):
    w = ("01-01", "12-31")
    c = ee.ImageCollection([])
    for y in range(START, END + 1):
        c = c.merge(_landsat("LANDSAT/LC08/C02/T1_L2", y, w, roi, False).map(landsat_bands))
        if y >= 2021:
            c = c.merge(_landsat("LANDSAT/LC09/C02/T1_L2", y, w, roi, False).map(landsat_bands))
        if y >= 2016:
            c = c.merge(_sentinel2(y, w, roi).map(s2_bands(F)))
    return c.sort("system:time_start")


def rma(x, y):
    r = y - x
    k = np.abs(r - np.median(r)) < 3 * 1.48 * np.median(np.abs(r - np.median(r)))
    x, y = x[k], y[k]
    b = y.std() / x.std()
    return float(b), float(y.mean() - b * x.mean()), float(np.corrcoef(x, y)[0, 1])


def fit():
    """S2 -> Landsat for all four bands, same method as fit_s2_to_landsat.py; NBR and NDVI should reproduce the values in common.py."""
    D.mkdir(parents=True, exist_ok=True)
    init()
    div = ee.FeatureCollection(DIVISIONS_ASSET)
    ident = {b: (1.0, 0.0) for b in BANDS}
    rows = []
    for name in ["Guna", "Lamta_Proj_N_Balaghat", "South_Betul", "Singrauli"]:
        roi = div.filter(ee.Filter.eq("Division", name)).geometry()
        pts = ee.FeatureCollection.randomPoints(roi, 200, 31)
        imgs = []
        for y in (2019, 2021, 2023, 2025):
            w = WINDOW
            L = _landsat("LANDSAT/LC08/C02/T1_L2", y, w, roi, False).map(landsat_bands).median().rename([f"L{b}_{y}" for b in BANDS])
            S = _sentinel2(y, w, roi).map(s2_bands(ident)).median().rename([f"S{b}_{y}" for b in BANDS])
            imgs += [L, S]
        d = ee.Image.cat(imgs).reduceRegions(pts, ee.Reducer.first(), scale=30, tileScale=4).getInfo()
        rows.append(pd.DataFrame([f["properties"] for f in d["features"]]))
        print(name, flush=True)
    t = pd.concat(rows).apply(pd.to_numeric, errors="coerce")
    F = {}
    for b in BANDS:
        x = np.concatenate([t[f"S{b}_{y}"] for y in (2019, 2021, 2023, 2025)])
        y_ = np.concatenate([t[f"L{b}_{y}"] for y in (2019, 2021, 2023, 2025)])
        k = np.isfinite(x) & np.isfinite(y_)
        s, c, r = rma(x[k], y_[k])
        F[b] = [s, c]
        print(b, "slope %.4f intercept %.4f r %.3f" % (s, c, r))
    json.dump(F, open(FIT, "w"))


def groups(df):
    """Spatially close groups, so filterBounds stays small."""
    df = df.assign(ry=(df.y // 45000).astype(int), rx=(df.x // 45000).astype(int)).sort_values(["ry", "rx"])
    return [df.iloc[i:i + GROUP] for i in range(0, len(df), GROUP)]


def ccdc_group(part, F, out_path):
    proj = ee.Projection(WKT)
    pts = ee.FeatureCollection([ee.Feature(ee.Geometry.Point([x, y], proj), dict(sample_id=int(i))) for x, y, i in zip(part.x, part.y, part.sample_id)])
    roi = pts.geometry().transform("EPSG:4326", 1)
    # lambda 20 is for reflectance x 10000; these bands are 0-1, so 20/10000. CCDC fits up to 3 harmonics by itself.
    r = ee.Algorithms.TemporalSegmentation.Ccdc(collection=series(roi, F), breakpointBands=["NBR", "NDMI", "SWIR1"], minObservations=6,
                                                chiSquareProbability=0.99, minNumOfYearsScaler=1.33, dateFormat=1, maxIterations=25000,
                                                **{"lambda": 0.002})
    img = r.select(["tStart", "tEnd", "tBreak", "numObs", "NBR_coefs", "NDVI_coefs", "NBR_rmse", "NBR_magnitude"])
    for attempt in range(3):
        try:
            res = img.reduceRegions(pts, ee.Reducer.first(), crs=WKT, scale=RES, tileScale=8).getInfo()["features"]
            with open(out_path, "a") as o:
                for f in res:
                    o.write(json.dumps(f["properties"]) + "\n")
            print("ok", len(res), flush=True)
            return
        except Exception as e:
            msg = str(e)[:160]
    print("failed", list(part.sample_id)[:3], msg, flush=True)


def ccdc(points, out):
    init()
    F = json.load(open(FIT))
    df = pd.read_csv(points)
    done = set()
    if (D / out).exists():
        done = {json.loads(l)["sample_id"] for l in open(D / out)}
    df = df[~df.sample_id.isin(done)]
    print("to do", len(df), flush=True)
    with ThreadPoolExecutor(5) as ex:
        list(ex.map(lambda p: ccdc_group(p, F, D / out), groups(df)))


def lt(points, out):
    """LandTrendr attributes at points, where a composite stack exists (the composite export was stopped at 36 tiles)."""
    init()
    mod = importlib.import_module("03_export_landtrendr")
    stack = ee.ImageCollection(ASSET_DIR + "/stack").mosaic()
    img = mod.attributes(stack)
    df = pd.read_csv(points)
    rows = []

    def run(part):
        p = ee.Projection(WKT)
        pts = ee.FeatureCollection([ee.Feature(ee.Geometry.Point([x, y], p), dict(sample_id=int(i))) for x, y, i in zip(part.x, part.y, part.sample_id)])
        return [f["properties"] for f in img.reduceRegions(pts, ee.Reducer.first(), crs=WKT, scale=RES, tileScale=8).getInfo()["features"]]
    with ThreadPoolExecutor(5) as ex:
        for r in ex.map(run, groups(df)):
            rows += r
            print(len(rows), flush=True)
    pd.DataFrame(rows).to_csv(D / out, index=False)


if __name__ == "__main__":
    {"fit": lambda: fit(), "ccdc": lambda: ccdc(sys.argv[2], sys.argv[3]), "lt": lambda: lt(sys.argv[2], sys.argv[3])}[sys.argv[1]]()
