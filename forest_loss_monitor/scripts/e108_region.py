"""The Bamori recipe for any other range, to test whether it transfers. Nothing is retrained: the Guna embedding model, its thresholds, the sieve and the Bamori cropland mask are applied as they are.
Only the year-wide embedding shift is measured locally, on 300 random recorded-forest pixels of the range (no labels).
Steps: shift -> net -> sieve -> crop -> score -> sample -> fetch -> sheets -> estimate.
Usage: e108_region.py <Division> <Range> <step>"""
import io
import json
import sys
import time

sys.path.insert(0, "E:/FIRE/forest_loss_monitor/scripts")
DIV, RNG, STEP = sys.argv[1], sys.argv[2], sys.argv[3]
sys.argv = sys.argv[:1]

import ee
import geopandas as gpd
import joblib
import numpy as np
import pandas as pd
import rasterio
from scipy import ndimage
from scipy.ndimage import label
from shapely.geometry import box

import e93_cc_strips as st
from common import *
from e33_map10m import init_retry
from e75_cc_fetch import COL
from e76_cc_train import YS
from e97_cc_map import CHUNK, MODEL, NAMES, features
from e103_cc_mapsieve import FALL, falls
from e105_cc_cropmask import crop_image

TAG = f"{DIV}_{RNG}".lower().replace(" ", "_")
R = WORK / f"region_{TAG}"
GT = ROOT / "ground_truth"
KEY = GT / f"{TAG}_key_DO_NOT_OPEN_BEFORE_LABELLING.csv"
LAB = GT / f"{TAG}_labels.csv"
OUTD = OUT / f"region_{TAG}"
st.KEY, st.CH, st.SH = KEY, R / "strips", OUTD / "sheets"
SEED, MIN_PX, N_SPOTS = 20261114, 50, 150


def region():
    b = gpd.read_parquet(WORK / "beats_albers.parquet")
    b = b[(b.Division == DIV) & (b.Range == RNG)]
    x0, y0, x1, y1 = b.total_bounds
    x0, y1 = np.floor(x0 / 30) * 30, np.ceil(y1 / 30) * 30
    nx, ny = int(np.ceil((x1 - x0) / 10)), int(np.ceil((y1 - y0) / 10))
    return b, dict(x0=float(x0), y1=float(y1), nx=nx, ny=ny)


def forest(g, b):
    with rasterio.open(WORK / "zone_beat.tif") as s:
        tr = s.transform
        c0, r0 = int(round((g["x0"] - tr.c) / tr.a)), int(round((tr.f - g["y1"]) / -tr.e))
        z = s.read(1, window=((r0, r0 + g["ny"] // 3 + 2), (c0, c0 + g["nx"] // 3 + 2)))
    z10 = np.repeat(np.repeat(z, 3, axis=0), 3, axis=1)[:g["ny"], :g["nx"]]
    return np.isin(z10, b.zone_id.values), z10


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


def shift():
    """Mean embedding per year over 300 random forest pixels, at the 50 m box and the 500 m surround."""
    init_retry()
    R.mkdir(parents=True, exist_ok=True)
    b, g = region()
    ok, _ = forest(g, b)
    rr, cc = np.nonzero(ok)
    i = np.random.default_rng(SEED).choice(len(rr), 300, replace=False)
    xs, ys = g["x0"] + (cc[i] + .5) * 10, g["y1"] - (rr[i] + .5) * 10
    p = ee.Projection(WKT)
    im = ee.Image.cat([ee.ImageCollection(COL).filterDate(f"{y}-01-01", f"{y + 1}-01-01").mosaic().rename([f"y{y}_{k:02d}" for k in range(64)]) for y in YS]).toFloat()
    out = {}
    for half, scale in ((25, 10), (250, 30)):
        rows = []
        for k in range(0, 300, 25):
            fc = ee.FeatureCollection([ee.Feature(ee.Geometry.Rectangle([x - half, y - half, x + half, y + half], p, False)) for x, y in zip(xs[k:k + 25], ys[k:k + 25])])
            rows += [f["properties"] for f in retry(lambda: im.reduceRegions(fc, ee.Reducer.mean(), crs=WKT, scale=scale, tileScale=4).getInfo()["features"])]
            print(half, len(rows), flush=True)
        e = pd.DataFrame(rows).dropna()
        A = np.stack([e[[f"y{y}_{k:02d}" for k in range(64)]].values for y in YS], axis=1)
        if half == 25:
            A = A / np.linalg.norm(A, axis=2, keepdims=True)
        m = A.mean(axis=0)
        out[half] = (m - m.mean(axis=0)).tolist()
    json.dump(out, open(R / "shift.json", "w"))
    json.dump(g, open(R / "grid.json", "w"))


def chunks(img_fn, sub, names):
    init_retry()
    d = R / sub
    d.mkdir(parents=True, exist_ok=True)
    b, g = region()
    poly = b.union_all()
    jobs = [(i, j) for i in range(0, g["ny"], CHUNK) for j in range(0, g["nx"], CHUNK)
            if box(g["x0"] + j * 10, g["y1"] - (i + CHUNK) * 10, g["x0"] + (j + CHUNK) * 10, g["y1"] - i * 10).intersects(poly) and not (d / f"{i}_{j}.npy").exists()]
    print(sub, "chunks", len(jobs), flush=True)
    t0 = time.time()
    for n, (i, j) in enumerate(jobs):
        h, w = min(CHUNK, g["ny"] - i), min(CHUNK, g["nx"] - j)
        aoi = ee.Geometry.Rectangle([g["x0"] + j * 10, g["y1"] - (i + h) * 10, g["x0"] + (j + w) * 10, g["y1"] - i * 10], ee.Projection(WKT), False).transform("EPSG:4326", 10)
        img = img_fn(aoi)
        raw = retry(lambda: ee.data.computePixels(dict(expression=img, fileFormat="NPY", grid=dict(dimensions=dict(width=w, height=h), crsWkt=WKT,
                                                     affineTransform=dict(scaleX=10, shearX=0, translateX=g["x0"] + j * 10, shearY=0, scaleY=-10, translateY=g["y1"] - i * 10)))))
        a = np.load(io.BytesIO(raw))
        np.save(d / f"{i}_{j}.npy", np.stack([a[c] for c in (names or a.dtype.names)]).astype("float32"))
        print(sub, n + 1, "of", len(jobs), round(time.time() - t0), "s", flush=True)
    print(sub, "FINISHED", flush=True)


def net():
    s = json.load(open(R / "shift.json"))
    img = features(np.array(s["25"]), np.array(s["250"]))
    chunks(lambda aoi: img, "net", NAMES)


def mosaic(sub, g, nb):
    F = np.full((nb, g["ny"], g["nx"]), np.nan, "float32")
    for f in (R / sub).glob("*.npy"):
        i, j = map(int, f.stem.split("_"))
        a = np.load(f)
        F[:, i:i + a.shape[1], j:j + a.shape[2]] = a
    return F


def score():
    OUTD.mkdir(parents=True, exist_ok=True)
    b, g = region()
    ok0, zone = forest(g, b)
    F = mosaic("net", g, len(NAMES))
    S = mosaic("sieve", g, 3)
    S[S == -9] = np.nan
    C = mosaic("crop", g, 1)[0]
    m = joblib.load(MODEL)["scalars"]            # written by e84 on this machine
    ok = ok0 & np.isfinite(F).all(axis=0)
    s = np.full(ok.shape, np.nan, "float32")
    s[ok] = m["model"].decision_function(F[:, ok].T)
    stage1, strict = ok & (s >= m["thresholds"][.9]), ok & (s >= m["thresholds"][.7])

    def patches(x):
        lab, _ = label(x, structure=np.ones((3, 3)))
        return np.isin(lab, np.flatnonzero(np.bincount(lab.ravel()) >= MIN_PX)) & (lab > 0)

    with np.errstate(invalid="ignore"):
        ts = (S[0] >= FALL) & (S[1] >= FALL)
    cnt = np.rint(ndimage.uniform_filter(ts.astype("float32"), 5, mode="constant") * 25)
    final = patches(patches(strict) & ts & (cnt >= 5))
    rem = patches(patches(strict) & ~final)
    rest = ok & ~final & ~rem
    crop = C >= .5
    net1 = patches(stage1)
    strata = {"1 final map": final, "2 sieve-removed, not cropland before": rem & ~crop, "3 sieve-removed, already cropland": rem & crop,
              "4 unflagged, net fired, not cropland before": rest & net1 & ~crop, "5 unflagged, net fired, already cropland": rest & net1 & crop,
              "6 unflagged, net quiet, not cropland before": rest & ~net1 & ~crop, "7 unflagged, net quiet, already cropland": rest & ~net1 & crop}
    np.savez_compressed(R / "strata.npz", **{k[0]: v for k, v in strata.items()})
    t = pd.DataFrame([dict(stratum=k, area_ha=round(v.sum() * .01)) for k, v in strata.items()])
    print(t.to_string())
    print("recorded forest", round(ok.sum() * .01), "ha | stage-1 net", round(100 * stage1.sum() / ok.sum(), 1), "% | strict net", round(100 * strict.sum() / ok.sum(), 1), "% | final map", round(final.sum() * .01), "ha (",
          round(100 * final.sum() / ok.sum(), 2), "%) | already cropland 2017-18", round(100 * (crop & ok).sum() / ok.sum(), 1), "%")
    lk = pd.read_csv(OUT / "beat_lookup.csv").set_index("zone_id").Beat
    bt = pd.DataFrame(dict(beat=lk.reindex(zone[ok]).values, f=final[ok])).groupby("beat").agg(forest_ha=("f", "size"), map_ha=("f", "sum")) * .01
    bt.round(1).sort_values("map_ha", ascending=False).to_csv(OUTD / "by_beat.csv")
    t.to_csv(OUTD / "strata.csv", index=False)
    json.dump({k: k[0] for k in strata}, open(R / "strata_names.json", "w"))


def strata():
    z = np.load(R / "strata.npz")
    return {k: z[v] for k, v in json.load(open(R / "strata_names.json")).items()}


def sample():
    _, g = region()
    S = strata()
    area = np.array([v.sum() for v in S.values()], float)
    prior = np.array([.78, .33, .05, .09, .07, .04, .05])          # Bamori rates, for allocation only
    w = area * np.sqrt(prior * (1 - prior))
    n = np.maximum(np.round(N_SPOTS * w / w.sum()).astype(int), 8)
    rng = np.random.default_rng(SEED)
    pts = []
    for (nm, m), k in zip(S.items(), n):
        rr, cc = np.nonzero(m)
        if not len(rr):
            continue
        i = rng.choice(len(rr), min(int(k), len(rr)), replace=False)
        pts += [dict(group=nm, x=g["x0"] + (c + .5) * 10, y_m=g["y1"] - (r + .5) * 10) for r, c in zip(rr[i], cc[i])]
    k = pd.DataFrame(pts)
    k["code"] = rng.permutation(len(k)) + 1
    k["cid"] = 930000 + k.code
    k.sort_values("code").to_csv(KEY, index=False)
    print(len(k), k.group.value_counts().sort_index().to_dict())


def estimate():
    S = strata()
    s = pd.read_csv(KEY).merge(pd.read_csv(LAB), on="code")
    s["real"] = s.label.isin(["C", "T"])
    rows = []
    for nm, m in S.items():
        q = s[s.group == nm]
        n, x, a = len(q), int(q.real.sum()), m.sum() * .01
        p = x / n if n else 0
        pv = (x + .5) / (n + 1) if x in (0, n) else p
        rows.append(dict(stratum=nm, area_ha=round(a), spots=n, real=x, share=round(p, 3), est_ha=round(a * p), se=a * np.sqrt(pv * (1 - pv) / max(n, 1))))
    t = pd.DataFrame(rows)
    tot, se = t.est_ha.sum(), np.sqrt((t.se ** 2).sum())
    pd.set_option("display.width", 220)
    print(t.round(1).to_string())
    print(f"total {tot:.0f} ha, 95% range {max(tot - 1.96 * se, 0):.0f} - {tot + 1.96 * se:.0f} ({100 * tot / t.area_ha.sum():.1f}% of recorded forest), spots {int(t.spots.sum())}")
    print("labels by group:", pd.crosstab(s.group, s.label).to_string())
    t.round(1).to_csv(OUTD / "area_estimate.csv", index=False)


if __name__ == "__main__":
    dict(shift=shift, net=net, sieve=lambda: chunks(falls, "sieve", ("dn", "dr", "yr")), crop=lambda: chunks(lambda aoi: crop_image(2017, 2018).toFloat().reproject(ee.Projection(WKT).atScale(10)), "crop", None),
         score=score, sample=sample, fetch=lambda: st.fetch(2), sheets=st.sheets, estimate=estimate)[STEP]()
