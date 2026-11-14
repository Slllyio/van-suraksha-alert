"""'Already cropland before 2018' mask from the owner's 2022 Bamori land-cover polygons (c crops, c2 crop fallow, b bare, f forest, df dense forest).
A logistic model on the 2022 AlphaEarth embedding learns cropland (c, c2) against the rest, checked on whole held-out polygons; it is then applied to the mean 2017-18 embedding.
Usage: e105_cc_cropmask.py sample | fit | points | map | test"""
import io
import json
import sys
import time

sys.path.insert(0, "E:/FIRE/forest_loss_monitor/scripts")

import ee
import geopandas as gpd
import numpy as np
import pandas as pd
from shapely.geometry import box
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import GroupKFold

from common import *
from e33_map10m import init_retry
from e75_cc_fetch import COL
from e97_cc_map import CHUNK, D, grid

POLY = "E:/e_Netra/data/aoi/training_bamorifinal_2022.shp"
S = WORK / "cropmask_samples.csv"
M = WORK / "cropmask_model.json"
P = WORK / "cropmask_points.csv"
DM = WORK / "cc_map_bamori_crop"
CROP = {"c", "c2"}
PER_POLY = 40
GT = ROOT / "ground_truth"


def emb(y0, y1):
    return ee.ImageCollection([ee.ImageCollection(COL).filterDate(f"{y}-01-01", f"{y + 1}-01-01").mosaic() for y in range(y0, y1 + 1)]).mean().toFloat()


def retry(f):
    wait = 30
    for _ in range(10):
        try:
            return f()
        except Exception as e:
            print("retry", str(e)[:100], flush=True)
            time.sleep(wait)
            wait = min(wait * 2, 600)
    raise RuntimeError("gave up")


def sample():
    init_retry()
    g = gpd.read_file(POLY).reset_index().rename(columns={"index": "pid"})
    im = emb(2022, 2022)
    rows = []
    for i in range(0, len(g), 15):
        part = g.iloc[i:i + 15]
        fc = ee.FeatureCollection([ee.Feature(ee.Geometry(r.geometry.__geo_interface__), dict(pid=int(r.pid), cls=r["class"])) for _, r in part.iterrows()])
        pts = fc.map(lambda f: im.sample(f.geometry(), scale=10, numPixels=PER_POLY, seed=1, geometries=False).map(lambda p: p.set(dict(pid=f.get("pid"), cls=f.get("cls"))))).flatten()
        out = retry(lambda: pts.getInfo()["features"])
        rows += [x["properties"] for x in out]
        print(min(i + 15, len(g)), "of", len(g), "polygons,", len(rows), "pixels", flush=True)
    pd.DataFrame(rows).to_csv(S, index=False)


def fit():
    d = pd.read_csv(S).dropna()
    B = [c for c in d.columns if c.startswith("A")]
    X, y, g = d[B].values, d.cls.isin(CROP).astype(int).values, d.pid.values
    s = np.zeros(len(d))
    for tr, te in GroupKFold(5).split(X, y, g):
        s[te] = LogisticRegression(C=1.0, max_iter=3000).fit(X[tr], y[tr]).predict_proba(X[te])[:, 1]
    print("pixels", len(d), "polygons", d.pid.nunique(), "held-out polygon AUC", round(roc_auc_score(y, s), 3))
    pp = d.assign(s=s).groupby("pid").agg(cls=("cls", "first"), s=("s", "mean"))
    print("held-out mean crop probability by class:", pp.groupby("cls").s.median().round(2).to_dict())
    print("polygons called cropland at 0.5:", pp.assign(c=pp.s >= .5).groupby("cls").c.agg(["sum", "size"]).to_dict("index"))
    m = LogisticRegression(C=1.0, max_iter=3000).fit(X, y)
    json.dump(dict(bands=B, coef=m.coef_[0].tolist(), intercept=float(m.intercept_[0])), open(M, "w"))


def crop_image(y0, y1):
    m = json.load(open(M))
    z = emb(y0, y1).select(m["bands"]).multiply(ee.Image.constant(m["coef"])).reduce(ee.Reducer.sum()).add(m["intercept"])
    return ee.Image(1).divide(ee.Image(1).add(z.multiply(-1).exp()))


def points():
    init_retry()
    from e76_cc_train import load
    d, _ = load()
    k = pd.read_csv(GT / "bamori_map_labelled.csv")
    q = pd.concat([d[["cid", "x", "y_m"]], k[["cid", "x", "y_m"]]], ignore_index=True)
    im = ee.Image.cat(crop_image(2017, 2018).rename("crop_pre"), crop_image(2024, 2025).rename("crop_post"))
    p = ee.Projection(WKT)
    rows = []
    for i in range(0, len(q), 100):
        part = q.iloc[i:i + 100]
        fc = ee.FeatureCollection([ee.Feature(ee.Geometry.Rectangle([x - 25, y - 25, x + 25, y + 25], p, False), dict(cid=int(c))) for x, y, c in zip(part.x, part.y_m, part.cid)])
        rows += [f["properties"] for f in retry(lambda: im.reduceRegions(fc, ee.Reducer.mean(), crs=WKT, scale=10).getInfo()["features"])]
        print(len(rows), "of", len(q), flush=True)
    pd.DataFrame(rows).to_csv(P, index=False)


def mapfetch():
    init_retry()
    DM.mkdir(parents=True, exist_ok=True)
    img = crop_image(2017, 2018).toFloat().reproject(ee.Projection(WKT).atScale(10))
    r, x0, y1, nx, ny = grid()
    poly = r.union_all()
    jobs = [(i, j) for i in range(0, ny, CHUNK) for j in range(0, nx, CHUNK)
            if box(x0 + j * 10, y1 - (i + CHUNK) * 10, x0 + (j + CHUNK) * 10, y1 - i * 10).intersects(poly) and not (DM / f"{i}_{j}.npy").exists()]
    print("chunks", len(jobs), flush=True)
    for n, (i, j) in enumerate(jobs):
        h, w = min(CHUNK, ny - i), min(CHUNK, nx - j)
        raw = retry(lambda: ee.data.computePixels(dict(expression=img, fileFormat="NPY", grid=dict(dimensions=dict(width=w, height=h), crsWkt=WKT,
                                                     affineTransform=dict(scaleX=10, shearX=0, translateX=x0 + j * 10, shearY=0, scaleY=-10, translateY=y1 - i * 10)))))
        a = np.load(io.BytesIO(raw))
        np.save(DM / f"{i}_{j}.npy", a[a.dtype.names[0]].astype("float32"))
        print(n + 1, "of", len(jobs), flush=True)
    print("FINISHED")


def test():
    from e76_cc_train import load, ref_w
    from e23_guna_labels import wpr
    d, _ = load()
    p = pd.read_csv(P).set_index("cid")
    k = pd.read_csv(GT / "bamori_map_labelled.csv").set_index("cid")
    k = k.join(p)
    d = d.join(p, on="cid")
    for th in (.5, .7, .8):
        print(f"\n== mask: drop where 2017-18 crop probability >= {th}")
        f = k[k.group == "final map"]
        keep = f.crop_pre < th
        print("Bamori final-map sample: kept", int(keep.sum()), "of", len(f), "| real loss kept", int((keep & f.label.isin(["C", "T"])).sum()), "of", int(f.label.isin(["C", "T"]).sum()),
              "| fields/villages kept", int((keep & (f.label == "X")).sum()), "of", int((f.label == "X").sum()), "| precision after", round(f[keep].label.isin(["C", "T"]).mean(), 3))
        r = k[k.group == "removed by sieve"]
        print("  removed-by-sieve sample: real loss outside the mask", int(((r.crop_pre < th) & r.label.isin(["C", "T"])).sum()), "of", int(r.label.isin(["C", "T"]).sum()), "| fields outside mask", int(((r.crop_pre < th) & (r.label == "X")).sum()), "of", int((r.label == "X").sum()))
        for st, cl in (("bamori_tp", "forest_to_crop"), ("bamori_tp", "shrub_to_crop"), ("bamori_tp", "bare_to_crop"), ("bamori_fp", None), ("felling", None), ("random", None)):
            q = d[(d.set == st) & ((d.cls == cl) if cl else True) & (d.y != 0 if st in ("bamori_tp", "felling") else True)]
            print(f"  {st} {cl or ''}: kept {int((q.crop_pre < th).sum())} of {len(q)}")
        ref = (d.set == "reference").values
        rq = d[ref]
        print("  reference losses kept", int(((rq.crop_pre < th) & (rq.y == 1)).sum()), "of", int((rq.y == 1).sum()), "| reference non-losses kept", int(((rq.crop_pre < th) & (rq.y == 0)).sum()), "of", int((rq.y == 0).sum()))


if __name__ == "__main__":
    dict(sample=sample, fit=fit, points=points, map=mapfetch, test=test)[sys.argv[1]]()
