"""AlphaEarth route, step 4: fit the change model and export per-year scores.
Model: logistic on E(t)-E(t-1), E(t+1)-E(t-1) and the two distances. In the final year E(t+1) is E(t).
A second linear model maps one year's embedding to Dynamic World tree probability, for clearing vs partial and recovery.
Scoring is local (e7_score.py); the export path here was replaced because batch export took about 2 days.
Usage: e4_model_export.py fit"""
import json
import sys

import ee
import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression, RidgeCV
from sklearn.model_selection import cross_val_predict, KFold
from sklearn.preprocessing import StandardScaler

from common import *
from e1_export_scores import embedding
from e3_train_eval import A_BANDS, D, labelled_points

MODEL = ROOT / "scripts" / "model_loss.json"
TREE = ROOT / "scripts" / "model_tree.json"


def fit_loss():
    """Final model on all labels. Design and hold-out test live in e10_tile_holdout.py."""
    from e10_tile_holdout import fit
    d = labelled_points()
    m = d.merge(pd.read_parquet(D / "features.parquet"), on="sample_id").dropna()
    M = fit(m)
    json.dump(M, open(MODEL, "w"))
    print("fitted on", M["n"], "positives", M["positives"])


def fit_tree(n_points=4000):
    """Embedding -> Dynamic World tree probability, leaf-on window of the same year, random forest pixels."""
    if TREE.exists():
        return
    init()
    fc = ee.FeatureCollection(DIVISIONS_ASSET)
    rows = []
    for y in (2018, 2021, 2024):
        dw = ee.ImageCollection("GOOGLE/DYNAMICWORLD/V1").select("trees").filterDate(f"{y}-09-15", f"{y}-12-01").mean().rename("dw")
        pts = dw.addBands(embedding(y)).sample(fc.geometry(), scale=300, numPixels=n_points // 3, seed=y, tileScale=8, dropNulls=True)
        rows += [q["properties"] for q in pts.getInfo()["features"]]
    t = pd.DataFrame(rows)
    X, y = t[A_BANDS].values, t.dw.values
    r = RidgeCV(alphas=np.logspace(-4, 1, 12))
    pred = cross_val_predict(r, X, y, cv=KFold(5, shuffle=True, random_state=0))
    r.fit(X, y)
    print("tree model n", len(y), "cv r2 %.3f mae %.3f" % (1 - ((y - pred) ** 2).sum() / ((y - y.mean()) ** 2).sum(), np.abs(y - pred).mean()))
    json.dump(dict(intercept=float(r.intercept_), coef=r.coef_.tolist()), open(TREE, "w"))


if __name__ == "__main__":
    fit_loss()
    fit_tree()
