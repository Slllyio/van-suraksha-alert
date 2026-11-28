"""AlphaEarth route, step 3: embedding features at all labelled points, held-out accuracy, comparison with the LandTrendr rule.
Target: real loss (L or D) vs everything else, for the labelled pixel in the labelled year.
Held-out test = leave-one-tile-out, so a model never sees the landscape it is scored on; repeated k-fold also shown."""
import importlib
import json
import sys

import ee
import numpy as np
import pandas as pd
import rasterio
from sklearn.ensemble import RandomForestClassifier as RF
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, precision_recall_curve
from sklearn.model_selection import LeaveOneGroupOut, StratifiedKFold
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from common import *
from e1_export_scores import embedding

D = OUT / "calibration_emb"
A_BANDS = [f"A{i:02d}" for i in range(64)]
FIRST, LAST = 2018, 2025


def labelled_points():
    a = pd.read_csv(OUT / "calibration" / "calib_labels.csv")[["sample_id", "tile", "area", "x", "y", "map_year", "label"]]
    b = pd.read_csv(D / "calib_labels.csv")[["sample_id", "tile", "area", "x", "y", "map_year", "label"]]
    parts = [a, b]
    extra = OUT / "calibration_extra" / "calib_labels.csv"
    if extra.exists():
        parts.append(pd.read_csv(extra)[["sample_id", "tile", "area", "x", "y", "map_year", "label"]])
    d = pd.concat(parts, ignore_index=True)
    return d[d.map_year.between(FIRST, LAST)].reset_index(drop=True)


def ensure_features():
    return fetch_features(labelled_points())


def fetch_features(d):
    f = D / "features.parquet"
    old = pd.read_parquet(f) if f.exists() else pd.DataFrame(columns=["sample_id"])
    d = d[~d.sample_id.isin(old.sample_id)]
    if d.empty:
        return old
    init()
    proj = ee.Projection(WKT)
    rows = []
    for yr, g in d.groupby("map_year"):
        pts = ee.FeatureCollection([ee.Feature(ee.Geometry.Point([x, y], proj), dict(sample_id=int(i)))
                                    for x, y, i in zip(g.x, g.y, g.sample_id)])
        yr = int(yr)
        e0 = embedding(yr - 1).rename([f"p_{b}" for b in A_BANDS])
        e1 = embedding(yr).rename([f"c_{b}" for b in A_BANDS])
        e2 = embedding(min(yr + 1, LAST)).rename([f"n_{b}" for b in A_BANDS])
        out = ee.Image.cat(e0, e1, e2).reduceRegions(pts, ee.Reducer.first(), scale=30, tileScale=4).getInfo()
        rows += [q["properties"] for q in out["features"]]
        print(yr, len(g), flush=True)
    x = pd.concat([old, pd.DataFrame(rows)], ignore_index=True)
    x.to_parquet(f)
    return x


def design(m, use_next=True):
    p, c, n = (m[[f"{k}_{b}" for b in A_BANDS]].values for k in "pcn")
    dist = 1 - (p * c).sum(1, keepdims=True)
    dist_pn = 1 - (p * n).sum(1, keepdims=True)
    base = [p, c, c - p, dist]
    if use_next:   # the following year separates lasting loss from a one-year dip; final year has none
        base += [n - p, dist_pn]
    return np.hstack(base)


def rf():
    return RF(500, min_samples_leaf=2, max_features="sqrt", class_weight="balanced", random_state=0, n_jobs=-1)


def logit():
    return make_pipeline(StandardScaler(), LogisticRegression(C=0.05, max_iter=3000, class_weight="balanced"))


def cv_scores(make, X, y, splits):
    p = np.zeros(len(y))
    for tr, te in splits:
        p[te] = make().fit(X[tr], y[tr]).predict_proba(X[te])[:, 1]
    return p


def summary(y, p, name):
    P, R, T = precision_recall_curve(y, p)
    f1 = 2 * P * R / (P + R + 1e-9)
    i = int(np.argmax(f1))
    at = lambda r: P[R >= r].max()
    print(f"{name:34s} AP {average_precision_score(y, p):.3f}  best F1 {f1[i]:.2f} (P {P[i]:.2f} R {R[i]:.2f})  P@R.5 {at(.5):.2f}  P@R.65 {at(.65):.2f}  P@R.8 {at(.8):.2f}")


def rule_hits(d):
    """LandTrendr rule at the same pixels: detected within one year of the labelled year (needs lt_v3)."""
    clf = importlib.import_module("05_classify")
    th = json.load(open(ROOT / "scripts" / "thresholds.json"))
    t = pd.read_csv(WORK / "tiles.csv", keep_default_na=False).set_index("tile")
    with rasterio.open(WORK / "zone_beat.tif") as s:
        full = s.read(1)
    hit = np.zeros(len(d), bool)
    for tile, g in d.groupby("tile"):
        s = t.loc[tile]
        with rasterio.open(WORK / "lt_v3" / f"{tile}.tif") as src:
            A = {n: src.read(i + 1) for i, n in enumerate(src.descriptions)}
        yod, cls, _ = clf.classify(A, full[s.row:s.row + s.h, s.col:s.col + s.w], th)
        r = ((s.y1 - g.y) / RES).astype(int).values
        c = ((g.x - s.x0) / RES).astype(int).values
        hit[g.index] = (cls[r, c] > 0) & (cls[r, c] < 3) & (np.abs(yod[r, c] - g.map_year.values) <= 1)
    return hit


def main():
    d = labelled_points()
    m = d.merge(fetch_features(d), on="sample_id").dropna().reset_index(drop=True)
    y = m.label.isin(list("LD")).astype(int).values
    print("points", len(m), "real", int(y.sum()), m.label.value_counts().to_dict(), m.groupby("area").label.apply(lambda s: s.isin(list("LD")).sum()).to_dict())
    groups = m.tile.values
    X = design(m)
    X_cur = design(m, use_next=False)
    loto = list(LeaveOneGroupOut().split(X, y, groups))
    kf = list(StratifiedKFold(5, shuffle=True, random_state=1).split(X, y))
    out = {}
    for label, mk, XX in (("RF t-1,t,diff,dist,+next", rf, X), ("RF t-1,t,diff,dist", rf, X_cur), ("Logistic t-1,t,diff,dist,+next", logit, X)):
        for nm, sp in (("leave-tile-out", loto), ("5-fold", kf)):
            p = cv_scores(mk, XX, y, sp)
            summary(y, p, f"{label} | {nm}")
            out[(label, nm)] = p
    dist = 1 - (m[[f"p_{b}" for b in A_BANDS]].values * m[[f"c_{b}" for b in A_BANDS]].values).sum(1)
    summary(y, dist, "distance score only (no training)")
    if (WORK / "lt_v3").exists() and "--no-rule" not in sys.argv:
        hit = rule_hits(m)
        tp = (hit & (y == 1)).sum()
        print(f"LandTrendr rule on same points: detected {hit.sum()}, precision {tp / max(hit.sum(), 1):.2f}, recall {tp / y.sum():.2f}")
    pd.DataFrame({"sample_id": m.sample_id, "tile": m.tile, "label": m.label, "p_loto": out[("RF t-1,t,diff,dist,+next", "leave-tile-out")]}).to_csv(D / "heldout_scores.csv", index=False)


if __name__ == "__main__":
    main()
