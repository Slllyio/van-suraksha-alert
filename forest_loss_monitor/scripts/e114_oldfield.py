"""Old-field model for MP: was a pixel already farmland around 2014-16? Follows the compare thread's recipe (Landsat 8 2014-16 rabi, kharif and dry-season NDVI plus the 2017 AlphaEarth
embedding), but as a logistic model so it can be applied on Earth Engine for every division. Trained on the forest department's 2015 Guna survey: CULTIVATION, PATTA, ENCROACHMENT = old field (1),
BLANK, UNDER STOCK = never farmed (0), all 8 ranges, 2 km spatial blocks for the check. Usage: e114_oldfield.py sample | fit"""
import json
import sys
import time

sys.path.insert(0, "E:/FIRE/forest_loss_monitor/scripts")

import ee
import geopandas as gpd
import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import GroupKFold

from common import *
from e33_map10m import init_retry
from e75_cc_fetch import COL
from e105_cc_cropmask import retry

STOCK = ROOT / "ground_truth" / "shared" / "forest-stock-2015" / "guna_stock_2015.gpkg"
S = WORK / "oldfield_samples.csv"
M = WORK / "oldfield_model.json"
OLD = {"CULTIVATION", "PATTA", "ENCROACHMENT"}
NEW = {"BLANK", "UNDER STOCK"}
YS = (2014, 2015, 2016)
E = [f"A{i:02d}" for i in range(64)]
LS = [f"{k}{y}" for y in YS for k in ("rabi", "kharif", "dry")]
N_PER = 3000


def landsat_ndvi(a, b, reducer):
    col = ee.ImageCollection("LANDSAT/LC08/C02/T1_L2").filterDate(a, b)

    def f(i):
        q = i.select("QA_PIXEL")
        m = q.bitwiseAnd(1 << 3).eq(0).And(q.bitwiseAnd(1 << 4).eq(0))
        o = i.select(["SR_B4", "SR_B5"]).multiply(2.75e-5).add(-0.2)
        return o.normalizedDifference(["SR_B5", "SR_B4"]).updateMask(m)
    return col.map(f).reduce(reducer)


def features():
    """2017 embedding plus the nine Landsat NDVI bands, at the native scale of each."""
    e17 = ee.ImageCollection(COL).filterDate("2017-01-01", "2018-01-01").mosaic().select(E)
    bands = []
    for y in YS:
        bands += [landsat_ndvi(f"{y}-01-01", f"{y}-03-31", ee.Reducer.max()).rename(f"rabi{y}"),
                  landsat_ndvi(f"{y}-09-15", f"{y}-11-30", ee.Reducer.max()).rename(f"kharif{y}"),
                  landsat_ndvi(f"{y}-04-15", f"{y}-06-10", ee.Reducer.min()).rename(f"dry{y}")]
    return ee.Image.cat([e17] + bands)


def derived(d):
    for y in YS:
        d[f"rk{y}"] = d[f"rabi{y}"] - d[f"kharif{y}"]
    d["rabimax"] = d[[f"rabi{y}" for y in YS]].max(axis=1)
    d["rkmax"] = d[[f"rk{y}" for y in YS]].max(axis=1)
    d["rabimed"] = d[[f"rabi{y}" for y in YS]].median(axis=1)
    return d


DER = ["rk2014", "rk2015", "rk2016", "rabimax", "rkmax", "rabimed"]


def sample():
    init_retry()
    g = gpd.read_file(STOCK)
    g["T"] = g.Type.str.upper().str.strip().replace({"ENCROCHMENT": "ENCROACHMENT", "ENCROCHMENT OLD": "ENCROACHMENT", "CULTIVATION NEW": "CULTIVATION", "CULTIVATION OLD": "CULTIVATION",
                                                     "CULTIVATON": "CULTIVATION", "PATTA OLD": "PATTA", "PTTA": "PATTA", "UNDERSTOCK": "UNDER STOCK", "STOCK": "UNDER STOCK"})
    g = g[g["T"].isin(OLD | NEW) & g.geometry.notna()].to_crs(PROJ4)
    rng = np.random.default_rng(1)
    pts = []
    for old, grp in ((1, OLD), (0, NEW)):
        geom = g[g["T"].isin(grp)].geometry.union_all().buffer(-20)
        x0, y0, x1, y1 = geom.bounds
        got = 0
        while got < N_PER:
            P = gpd.points_from_xy(rng.uniform(x0, x1, 20000), rng.uniform(y0, y1, 20000))
            for p in P[geom.contains(P)][:N_PER - got]:
                pts.append(dict(old=old, x=p.x, y_m=p.y))
                got += 1
    q = pd.DataFrame(pts)
    q["ptid"] = range(len(q))
    img = features()
    proj = ee.Projection(WKT)
    rows = []
    for i in range(0, len(q), 500):
        ch = q.iloc[i:i + 500]
        fc = ee.FeatureCollection([ee.Feature(ee.Geometry.Point([x, y], proj), dict(ptid=int(t))) for x, y, t in zip(ch.x, ch.y_m, ch.ptid)])
        rows += [f["properties"] for f in retry(lambda: img.sampleRegions(fc, scale=30, tileScale=4).getInfo())["features"]]
        print(len(rows), "of", len(q), flush=True)
    pd.DataFrame(rows).merge(q, on="ptid").to_csv(S, index=False)


def fit():
    d = derived(pd.read_csv(S).dropna(subset=E))
    d["blk"] = (np.floor(d.x / 2000) * 1000 + np.floor(d.y_m / 2000)).astype(int)
    for nm, cols in (("Landsat + derived", LS + DER), ("2017 embedding", E), ("embedding + Landsat", E + LS + DER)):
        X = d[cols].fillna(-1).values
        pr = np.zeros(len(d))
        for tr, te in GroupKFold(5).split(X, d.old, d.blk):
            pr[te] = LogisticRegression(C=1.0, max_iter=5000).fit(X[tr], d.old.values[tr]).predict_proba(X[te])[:, 1]
        thr = np.quantile(pr[d.old == 0], .90)
        print(f"{nm:22s} AUC {roc_auc_score(d.old, pr):.3f} | keeping 90% of never-farmed: threshold {thr:.2f} removes {(pr[d.old == 1] > thr).mean():.0%} of old fields", flush=True)
    cols = E + LS + DER
    m = LogisticRegression(C=1.0, max_iter=5000).fit(d[cols].fillna(-1).values, d.old)
    json.dump(dict(bands=cols, coef=m.coef_[0].tolist(), intercept=float(m.intercept_[0]), threshold=float(thr)), open(M, "w"))
    print("saved", M)


def oldfield_image():
    """Probability of being an old field, on Earth Engine (derived bands built server-side)."""
    m = json.load(open(M))
    im = features()
    rk = [im.select(f"rabi{y}").subtract(im.select(f"kharif{y}")).rename(f"rk{y}") for y in YS]
    rabi = im.select([f"rabi{y}" for y in YS])
    im = ee.Image.cat([im] + rk + [rabi.reduce(ee.Reducer.max()).rename("rabimax"), ee.Image.cat(rk).reduce(ee.Reducer.max()).rename("rkmax"), rabi.reduce(ee.Reducer.median()).rename("rabimed")])
    z = im.select(m["bands"]).unmask(-1).multiply(ee.Image.constant(m["coef"])).reduce(ee.Reducer.sum()).add(m["intercept"])
    return ee.Image(1).divide(ee.Image(1).add(z.multiply(-1).exp()))


if __name__ == "__main__":

    dict(sample=sample, fit=fit)[sys.argv[1]]()
