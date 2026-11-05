"""What a patch-size filter does to the embedding change score. Per-pixel best-break statistic computed on Earth Engine in a 300 m window around each point, as on a map.
A point counts as flagged if a connected patch of pixels above the threshold, at least the minimum area, touches its 50 m box. Thresholds come from training blocks; 5 km blocks as before.
Usage: e85_cc_area.py check | fetch | test"""
import json
import sys
import time

sys.path.insert(0, "E:/FIRE/forest_loss_monitor/scripts")

import ee
import numpy as np
import pandas as pd
from scipy.ndimage import label
from sklearn.model_selection import StratifiedGroupKFold

from common import *
from e23_guna_labels import wpr
from e33_map10m import init_retry
from e75_cc_fetch import COL, ORDER
from e76_cc_train import FOLDS, GT, REPORT, YS, load, ref_w, thr_for
from e79_cc_fusion import boot

F = WORK / "cc_window_t.jsonl"
HALF, BOX_HALF, BATCH = 150, 25, 20
AREAS_HA = (0, .1, .25, .5, 1.0)
PX_HA = .01
TARGETS = (.9, .8, .7, .6, .5)
REPEATS = 10


def t_image(shift):
    """Same statistic as step_feats, on Earth Engine: largest t over the 8 possible breaks."""
    T = len(YS)
    ims = [ee.ImageCollection(COL).filterDate(f"{y}-01-01", f"{y + 1}-01-01").mosaic().toFloat().subtract(ee.Image.constant(shift[i].tolist())) for i, y in enumerate(YS)]
    ts = []
    for b in range(1, T):
        pre = ee.ImageCollection(ims[:b]).mean()
        post = ee.ImageCollection(ims[b:]).mean()
        step = post.subtract(pre).pow(2).reduce(ee.Reducer.sum()).sqrt()
        sse = ee.ImageCollection([ims[j].subtract(pre if j < b else post).pow(2).reduce(ee.Reducer.sum()) for j in range(T)]).sum()
        noise = sse.divide(T - 2).sqrt()
        ts.append(step.divide(noise.add(.01)).multiply((b * (T - b) / T) ** .5))
    return ee.ImageCollection(ts).max().rename("t")


def call(part, im):
    p = ee.Projection(WKT)
    fc = ee.FeatureCollection([ee.Feature(ee.Geometry.Rectangle([x - HALF, y - HALF, x + HALF, y + HALF], p, False), dict(cid=int(i))) for x, y, i in zip(part.x, part.y_m, part.cid)])
    full = im.addBands(ee.Image.pixelCoordinates(p).rename(["px", "py"]))
    return [f["properties"] for f in full.reduceRegions(fc, ee.Reducer.toList(), crs=WKT, scale=10, tileScale=8).getInfo()["features"]]


def shift_of():
    d, A = load()
    m = A[(d.set == "random").values].mean(axis=0)
    return d, A, m - m.mean(axis=0)


def check():
    """Server statistic must match the one computed locally from the pixel table."""
    init_retry()
    d, A, shift = shift_of()
    part = d[d.set == "reference"].head(4)
    r = call(part, t_image(shift))
    from e76_cc_train import step_feats
    px = {}
    for l in open(WORK / "cc_emb_px.jsonl"):
        q = json.loads(l)
        if q["cid"] in set(part.cid):
            px[q["cid"]] = q
    for row in r:
        q = px[row["cid"]]
        X = np.array([[q[f"y{y}_{b:02d}"] for b in range(64)] for y in YS], "float64").transpose(2, 0, 1)
        X = X / np.linalg.norm(X, axis=2, keepdims=True) - shift
        s = d[d.cid == row["cid"]].iloc[0]
        c = (np.abs(np.array(row["px"]) - s.x) <= BOX_HALF) & (np.abs(np.array(row["py"]) - s.y_m) <= BOX_HALF)
        print(row["cid"], "window pixels", len(row["t"]), "server box max", round(np.array(row["t"])[c].max(), 2), "local box max", round(step_feats(X)[0].t.max(), 2), "server median", round(np.median(np.array(row["t"])[c]), 2), "local median", round(step_feats(X)[0].t.median(), 2))


def fetch():
    init_retry()
    d, _, shift = shift_of()
    im = t_image(shift)
    seen = {json.loads(l)["cid"] for l in open(F)} if F.exists() else set()
    q = d[~d.cid.isin(seen)].assign(o=lambda z: z.set.map(ORDER.index), ry=lambda z: (z.y_m // 10000).astype(int)).sort_values(["o", "ry", "x"])
    with open(F, "a") as o:
        for i in range(0, len(q), BATCH):
            wait = 30
            for _ in range(8):
                try:
                    for row in call(q.iloc[i:i + BATCH], im):
                        o.write(json.dumps(dict(cid=row["cid"], t=[round(v, 2) for v in row["t"]], px=[round(v) for v in row["px"]], py=[round(v) for v in row["py"]])) + "\n")
                    break
                except Exception as e:
                    print("retry", str(e)[:140], flush=True)
                    time.sleep(wait)
                    wait = min(wait * 2, 600)
            o.flush()
            print(min(i + BATCH, len(q)), "of", len(q), flush=True)
    print("FINISHED")


def grid(row):
    x, y = np.array(row["px"]), np.array(row["py"])
    col, r = ((x - x.min()) / 10).round().astype(int), ((y.max() - y) / 10).round().astype(int)
    g = np.full((r.max() + 1, col.max() + 1), -np.inf)
    g[r, col] = row["t"]
    return g, x.min(), y.max()


def best_threshold(g, centre, min_px, cand):
    """Highest threshold at which a patch of at least min_px touches the box: the point's score under this area rule."""
    for th in cand:
        lab, n = label(g >= th, structure=np.ones((3, 3)))
        if n == 0:
            continue
        ids = np.unique(lab[centre])
        ids = ids[ids > 0]
        if len(ids) and np.bincount(lab.ravel())[ids].max() >= min_px:
            return th
    return -np.inf


def test():
    d, _, _ = shift_of()
    d = d[d.y >= 0].reset_index(drop=True)
    pos = {c: i for i, c in enumerate(d.cid)}
    y, w, k = d.y.values, ref_w(d), (d.set == "reference").values
    cand = np.round(np.arange(9, .2, -.05), 2)
    S = {a: np.full(len(d), -np.inf) for a in AREAS_HA}
    sizes = {}
    for l in open(F):
        r = json.loads(l)
        i = pos.get(r["cid"])
        if i is None:
            continue
        g, x0, y1 = grid(r)
        c = np.zeros(g.shape, bool)
        cr, cc = int((y1 - d.y_m[i]) / 10), int((d.x[i] - x0) / 10)
        n = BOX_HALF // 10
        c[max(cr - n, 0):cr + n + 1, max(cc - n, 0):cc + n + 1] = True
        for a in AREAS_HA:
            S[a][i] = best_threshold(g, c, max(int(round(a / PX_HA)), 1), cand)
    print("points scored", int(np.isfinite(S[0]).sum()), "of", len(d), flush=True)
    rows = []
    g = d.block.values
    rnd = (d.set == "random").values
    for a in AREAS_HA:
        s = S[a]
        for tg in TARGETS:
            fl = np.zeros((REPEATS, len(d)), bool)
            for rep in range(REPEATS):
                for tr, te in StratifiedGroupKFold(FOLDS, shuffle=True, random_state=rep).split(s, y, g):
                    ri = tr[k[tr]]
                    fl[rep, te] = s[te] >= thr_for(s[ri], y[ri], w[ri], tg)
            f = fl.mean(axis=0) >= .5
            p, r = wpr(y[k], f[k].astype(int), w[k])
            ci = boot(d, f)
            th = thr_for(s[k], y[k], w[k], tg)
            rows.append(dict(min_patch_ha=a, target=tg, precision=round(p, 3), p_ci=ci[0], recall=round(r, 3), r_ci=ci[1], threshold_all_data=th, flagged=int(f[k].sum()), real=int((f[k] & (y[k] == 1)).sum()), of_49=int(f[(d.stratum == "flagged").values & (y == 1)].sum()), of_6=int(f[(d.stratum == "background").values & (y == 1)].sum()), random_flag_pct=round(100 * f[rnd].mean(), 1),
                             bamori_tp=f"{int(f[(d.set == 'bamori_tp').values & (y == 1)].sum())}/170", bamori_fp=f"{int(f[(d.set == 'bamori_fp').values].sum())}/112"))
            print(json.dumps(rows[-1]), flush=True)
    t = pd.DataFrame(rows)
    t.to_csv(REPORT / "cc_area_filter.csv", index=False)
    pd.set_option("display.width", 300, "display.max_columns", 30)
    print(t.to_string())


if __name__ == "__main__":
    dict(check=check, fetch=fetch, test=test)[sys.argv[1]]()
