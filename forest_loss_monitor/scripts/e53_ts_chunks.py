"""Time-series attributes for mapped pixels: yearly Oct-Nov NDVI and NBR fetched only at flagged pixels, break fitted locally, saved beside each chunk.
Nothing in the chunks changes. ts = fitted-break fall >= 0.15 in both NDVI and NBR, as tested on the Guna points. Finished chunks and new ones go through the same sweep,
which repeats until the state run ends, so it covers backfill and new chunks alike. Usage: e53_ts_chunks.py once [threads] | sweep [threads] | test"""
import sys
import time
from concurrent.futures import ThreadPoolExecutor

import ee
import numpy as np
import pandas as pd

from common import *
from e33_map10m import D, init_retry
from e47_px import YS, leaf
from e49_ts import series_feats

OUTD = WORK / "map10m_ts"
BATCH = 1500
FALL = .15
PAUSE = 600


def fetch_part(x, y, ids):
    p = ee.Projection(WKT)
    fc = ee.FeatureCollection([ee.Feature(ee.Geometry.Point([float(a), float(b)], p), dict(i=int(c))) for a, b, c in zip(x, y, ids)])
    a = fc.geometry().bounds(100, "EPSG:4326")
    img = ee.Image.cat([leaf(yy, a) for yy in YS]).select(["(ln|lr).*"]).toFloat()
    wait = 30
    while True:
        try:
            return [f["properties"] for f in img.reduceRegions(fc, ee.Reducer.first(), crs=WKT, scale=10, tileScale=8).getInfo()["features"]]
        except Exception as e:
            msg = str(e)
            if "Too Many" in msg:
                time.sleep(wait)
                wait = min(wait * 2, 600)
            elif len(ids) > 50:
                m = len(ids) // 2
                return fetch_part(x[:m], y[:m], ids[:m]) + fetch_part(x[m:], y[m:], ids[m:])
            else:
                raise


def one(f, t):
    out = OUTD / f.name
    if out.exists():
        return 0
    tile, r, c = f.stem.split("_")
    s = t.loc[tile]
    a = np.load(f)
    rr, cc = np.nonzero(a["cls"] > 0)
    if not len(rr):
        np.savez_compressed(out, r=rr.astype("int16"), c=cc.astype("int16"))
        return 1
    x, y = s.x0 + (int(c) + cc + .5) * 10, s.y1 - (int(r) + rr + .5) * 10
    ids = np.arange(len(rr))
    rows = []
    for k in range(0, len(ids), BATCH):
        rows += fetch_part(x[k:k + BATCH], y[k:k + BATCH], ids[k:k + BATCH])
    d = pd.DataFrame(rows).set_index("i").reindex(ids)
    for col in [f"{b}{yy}" for b in ("ln", "lr") for yy in YS]:
        if col not in d:
            d[col] = np.nan
    sf = series_feats(d.reset_index(drop=True))
    tmp = out.with_suffix(".tmp.npz")
    np.savez_compressed(tmp, r=rr.astype("int16"), c=cc.astype("int16"), ndvi_fall=sf.drop_n.values.astype("float32"), nbr_fall=sf.drop_r.values.astype("float32"),
                        persist=sf.persist.values.astype("int8"), break_year=sf.break_year.values.astype("int16"), back=sf.back.values)
    tmp.replace(out)
    return 1


def safe(f, t):
    try:
        return one(f, t)
    except Exception as e:
        print("failed", f.name, str(e)[:150], flush=True)
        return 0


def sweep(th, repeat):
    init_retry()
    OUTD.mkdir(parents=True, exist_ok=True)
    t = pd.read_csv(WORK / "tiles.csv", keep_default_na=False).set_index("tile")
    t0 = time.time()
    while True:
        todo = [f for f in sorted(D.glob("*.npz")) if not (OUTD / f.name).exists()]
        print("chunks to process", len(todo), int(time.time() - t0), "s", flush=True)
        with ThreadPoolExecutor(th) as ex:
            for i, ok in enumerate(ex.map(lambda f: safe(f, t), todo)):
                if i % 10 == 0:
                    print(i, "of", len(todo), int(time.time() - t0), "s", flush=True)
        if not repeat:
            break
        time.sleep(PAUSE)
    print("FINISHED")


def test():
    init_retry()
    OUTD.mkdir(parents=True, exist_ok=True)
    t = pd.read_csv(WORK / "tiles.csv", keep_default_na=False).set_index("tile")
    fs = sorted(D.glob("*.npz"), key=lambda f: -int((np.load(f)["cls"] > 0).sum()))
    f = fs[len(fs) // 20]
    t0 = time.time()
    print(f.name, "flagged", int((np.load(f)["cls"] > 0).sum()), "done", safe(f, t), round(time.time() - t0), "s")
    a = np.load(OUTD / f.name)
    keep = (a["ndvi_fall"] >= FALL) & (a["nbr_fall"] >= FALL)
    print("kept share", round(float(keep.mean()), 3), "missing", round(float(np.isnan(a["ndvi_fall"]).mean()), 3), "median falls", round(float(np.nanmedian(a["ndvi_fall"])), 3), round(float(np.nanmedian(a["nbr_fall"])), 3))


if __name__ == "__main__":
    m = sys.argv[1]
    th = int(sys.argv[2]) if len(sys.argv) > 2 else 2
    test() if m == "test" else sweep(th, m == "sweep")
