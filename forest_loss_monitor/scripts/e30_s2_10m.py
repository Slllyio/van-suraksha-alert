"""Sentinel-2 10 m leaf-on (Oct-Nov) annual composites with s2cloudless masking, 2017-2025. Not a state export: a coverage test on one teak
and one mixed dry division, and a signal test against the owner's Guna reference (10 m change at the point vs the 30 m AlphaEarth score).
Usage: e30_s2_10m.py test"""
import ee
import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score, roc_auc_score

from common import *

YEARS9 = list(range(2017, 2026))
GT = ROOT / "ground_truth"
PROB_MAX = 40


def composite10(y, roi):
    """Median NDVI, NBR, BSI at 10 m from clear Oct-Nov scenes; count = clear observations."""
    s2 = ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED" if y >= 2019 else "COPERNICUS/S2_HARMONIZED").filterBounds(roi).filterDate(f"{y}-10-01", f"{y}-12-01")
    prob = ee.ImageCollection("COPERNICUS/S2_CLOUD_PROBABILITY").filterBounds(roi).filterDate(f"{y}-10-01", f"{y}-12-01")
    j = ee.ImageCollection(ee.Join.saveFirst("p").apply(s2, prob, ee.Filter.equals(leftField="system:index", rightField="system:index")))

    def prep(i):
        i = ee.Image(i)
        clear = ee.Image(i.get("p")).select("probability").lt(PROB_MAX)
        ndvi = i.normalizedDifference(["B8", "B4"]).rename("NDVI")
        nbr = i.normalizedDifference(["B8", "B12"]).rename("NBR")
        bsi = i.expression("((S+R)-(N+B))/((S+R)+(N+B))", dict(S=i.select("B11"), R=i.select("B4"), N=i.select("B8"), B=i.select("B2"))).rename("BSI")
        return ee.Image.cat(ndvi, nbr, bsi).toFloat().updateMask(clear)
    c = j.map(prep)
    return c.median().addBands(c.select("NDVI").count().rename("n")).rename([f"NDVI_{y}", f"NBR_{y}", f"BSI_{y}", f"n_{y}"])


def coverage():
    div = ee.FeatureCollection(DIVISIONS_ASSET)
    for name in ["Harda", "Guna"]:
        roi = div.filter(ee.Filter.eq("Division", name)).geometry()
        pts = ee.FeatureCollection.randomPoints(roi, 200, 5)
        rows = {}
        img = ee.Image.cat([composite10(y, roi) for y in YEARS9])
        res = img.reduceRegions(pts, ee.Reducer.first(), scale=10, tileScale=8).getInfo()["features"]
        t = pd.DataFrame([f["properties"] for f in res]).apply(pd.to_numeric, errors="coerce")
        print(name, "clear scenes median per year", {y: float(t[f"n_{y}"].median()) for y in YEARS9}, "pixels with no clear scene", {y: round(float(t[f"NDVI_{y}"].isna().mean()), 3) for y in YEARS9}, flush=True)


def signal():
    ref = pd.read_csv(GT / "guna_scores_v3.csv")
    ref = ref[ref.source == "blind_reference"].reset_index(drop=True)
    p = ee.Projection(WKT)
    img = None
    rows = []

    def run(part):
        pts = ee.FeatureCollection([ee.Feature(ee.Geometry.Point([x, y], p), dict(gid=int(g))) for x, y, g in zip(part.x, part.y, part.gid)])
        roi = pts.geometry().transform("EPSG:4326", 1)
        i = ee.Image.cat([composite10(y, roi).select([0, 1, 2]) for y in YEARS9])
        return [f["properties"] for f in i.reduceRegions(pts, ee.Reducer.first(), crs="EPSG:32643", scale=10, tileScale=8).getInfo()["features"]]
    from concurrent.futures import ThreadPoolExecutor
    ref["ry"], ref["rx"] = (ref.y // 45000).astype(int), (ref.x // 45000).astype(int)
    ref = ref.sort_values(["ry", "rx"])
    parts = [ref.iloc[i:i + 20] for i in range(0, len(ref), 20)]
    with ThreadPoolExecutor(5) as ex:
        for r in ex.map(run, parts):
            rows += r
            print(len(rows), flush=True)
    t = pd.DataFrame(rows).apply(pd.to_numeric, errors="coerce")
    t.to_csv(GT / "s2_10m_reference_points.csv", index=False)
    d = ref.merge(t, on="gid")
    for b, sign in (("NDVI", 1), ("NBR", 1), ("BSI", -1)):
        v = d[[f"{b}_{y}" for y in YEARS9]].values * sign
        best = np.nanmax(np.stack([np.nanmean(v[:, :i], axis=1) - np.nanmean(v[:, i:i + 2], axis=1) for i in range(1, 8)]), axis=0)
        d[f"drop_{b}"] = np.nan_to_num(best)
        print(b, "10 m largest multi-year fall: AUC", round(roc_auc_score(d.label, d[f"drop_{b}"]), 3), "AP", round(average_precision_score(d.label, d[f"drop_{b}"]), 3), flush=True)
    print("30 m AlphaEarth score: AUC", round(roc_auc_score(d.label, d.z), 3), "AP", round(average_precision_score(d.label, d.z), 3), "tree drop AUC", round(roc_auc_score(d.label, d["drop"]), 3), "AP", round(average_precision_score(d.label, d["drop"]), 3), "base", round(d.label.mean(), 3))


if __name__ == "__main__":
    init()
    coverage()
    signal()
