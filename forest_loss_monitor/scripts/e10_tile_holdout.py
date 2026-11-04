"""Honest pixel-rule test: fit on one half of the labelled tiles, score the other half's rasters, apply patch and tree rules,
then compare with labels on the held-out half only. Both directions. Prints precision/recall per rule setting."""
import json

import numpy as np
import pandas as pd
import rasterio
from scipy import ndimage
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler

import anomalies
from common import *
from e3_train_eval import A_BANDS, D, labelled_points
from e6_fetch_embeddings import EMB_DIR
from e8_classify import YEARS8, tree_at

FOLDS = {"A": "r03c09,r02c03,r05c02,r01c04,r04c07".split(","), "B": "r05c07,r01c03,r05c04,r05c05,r02c06".split(",")}
EIGHT = np.ones((3, 3), bool)


def design(m):
    p, c, n = (m[[f"{k}_{b}" for b in A_BANDS]].values for k in "pcn")
    return np.hstack([c - p, n - p, 1 - (p * c).sum(1, keepdims=True), 1 - (p * n).sum(1, keepdims=True)])


def fit(m):
    y = m.label.isin(list("LD")).astype(int).values
    X = design(m)
    sc = StandardScaler().fit(X)
    lr = LogisticRegression(C=0.05, max_iter=3000, class_weight="balanced").fit(sc.transform(X), y)
    w = lr.coef_[0] / sc.scale_
    return dict(intercept=float(lr.intercept_[0] - (lr.coef_[0] * sc.mean_ / sc.scale_).sum()), change_c=w[:64].tolist(),
                change_n=w[64:128].tolist(), dist_pc=float(w[128]), dist_pn=float(w[129]), n=len(y), positives=int(y.sum()))


def scores(tile, zone, M, T):
    """Returns per-year z (x1000) over the tile grid and tree values (x10000)."""
    mask = zone > 0
    E = {y: np.load(EMB_DIR / f"{tile}_{y}.npz")["vals"].astype("float32") / 127 for y in range(2017, 2026)}
    wc, wn, wt = np.array(M["change_c"], "float32"), np.array(M["change_n"], "float32"), np.array(T["coef"], "float32")
    Z, TR = [], []
    for y in YEARS8:
        p, c, n = E[y - 1], E[y], E[min(y + 1, 2025)]
        v = (c - p) @ wc + (n - p) @ wn + M["dist_pc"] * (1 - (p * c).sum(1)) + M["dist_pn"] * (1 - (p * n).sum(1)) + M["intercept"]
        a = np.zeros(zone.shape, "int16")
        a[mask] = np.clip(v * 1000, -32000, 32000)
        Z.append(a)
    for y in range(2017, 2026):
        a = np.zeros(zone.shape, "int16")
        a[mask] = np.clip((E[y] @ wt + T["intercept"]) * 10000, -32000, 32000)
        TR.append(a)
    return np.stack(Z), np.stack(TR)


def patch_keep(mask, yod, min_px):
    keep = np.zeros(yod.shape, bool)
    for y in YEARS8:
        m = mask & ((yod == y) | (yod == y + 1))
        if m.any():
            lab, n = ndimage.label(m, structure=EIGHT)
            size = np.bincount(lab.ravel(), minlength=n + 1)
            size[0] = 0
            keep |= size[lab] >= min_px
    return keep


def main():
    d = labelled_points()
    m = d.merge(pd.read_parquet(D / "features.parquet"), on="sample_id").dropna().reset_index(drop=True)
    T = json.load(open(ROOT / "scripts" / "model_tree.json"))
    t = pd.read_csv(WORK / "tiles.csv", keep_default_na=False).set_index("tile")
    with rasterio.open(WORK / "zone_beat.tif") as s:
        full = s.read(1)
    rows = []
    SET = [(zc, px, dr, pr) for zc in (-1.5, -1, -.5, 0, .5, 1) for px in (25,) for dr in (.05, .1, .15, .2) for pr in (0,)]
    out = {k: [] for k in SET}
    off, off_names = anomalies.load("v2")
    for name, tiles in FOLDS.items():
        M = fit(m[~m.tile.isin(tiles)])
        for tile in tiles:
            g = m[m.tile == tile]
            s = t.loc[tile]
            zone = full[s.row:s.row + s.h, s.col:s.col + s.w]
            Z, TR = scores(tile, zone, M, T)
            o = anomalies.tile_offset(off, s)
            Z = Z - o[[i for i, n in enumerate(off_names) if n.startswith("z")]]
            TR = TR - o[[i for i, n in enumerate(off_names) if n.startswith("tree")]]
            yod = np.array(YEARS8)[Z.argmax(0)]
            top = Z.max(0)
            pre, post = tree_at(TR, yod, (-2, -1)).astype("int32"), tree_at(TR, yod, (1, 2)).astype("int32")
            drop = pre - post
            r = ((s.y1 - g.y) / RES).astype(int).values
            c = ((g.x - s.x0) / RES).astype(int).values
            real = g.label.isin(list("LD")).values
            yr = g.map_year.values
            for (zc, px, dr, pr) in SET:
                k = patch_keep((zone > 0) & (top >= zc * 1000) & (drop >= dr * 1e4) & (pre >= pr * 1e4), yod, px)
                hit = k[r, c] & (np.abs(yod[r, c] - yr) <= 1)
                out[(zc, px, dr, pr)].append((hit.sum(), (hit & real).sum(), real.sum()))
            print(tile, "done", flush=True)
    res = []
    for k, v in out.items():
        a = np.array(v).sum(0)
        res.append(dict(z=k[0], patch=k[1], tree_drop=k[2], pre_tree=k[3], detected=a[0], tp=a[1], prec=a[1] / max(a[0], 1), rec=a[1] / a[2], real=a[2]))
    r = pd.DataFrame(res)
    r["f1"] = 2 * r.prec * r.rec / (r.prec + r.rec + 1e-9)
    r.to_csv(OUT / "calibration" / "rule_search_tile_holdout.csv", index=False)
    print(r.sort_values("f1", ascending=False).head(14).round(2).to_string(index=False))
    print(r[r.rec >= .6].sort_values("prec", ascending=False).head(6).round(2).to_string(index=False))


if __name__ == "__main__":
    main()
