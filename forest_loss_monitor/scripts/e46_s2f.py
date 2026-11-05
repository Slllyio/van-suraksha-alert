"""Scrub-to-farm clean test. sample: 300 random points in covered recorded forest. feats: crop-cycle and DW inputs at every labelled point.
chips: blind S2 sheets for the 300 (pre and post, rabi and leaf-on; the same for every point, rule verdict never shown).
Usage: e46_s2f.py sample | feats | chips | sheets"""
import io
import sys
import time
from concurrent.futures import ThreadPoolExecutor

import ee
import numpy as np
import pandas as pd
import rasterio
from PIL import Image, ImageDraw

from common import *
from e32_enetra10m import A_EARLY, A_LATE, S2, dw_mean
from e33_map10m import D as MAP_D, init_retry
from e39_conversion import ndvi

GT = ROOT / "ground_truth"
RAND = GT / "s2f_random300.csv"
F = GT / "s2f_points.csv"
CH = WORK / "s2f_chips"
SH = OUT / "s2f_sheets"
YS = list(range(2017, 2026))
RAND_BASE = 600000
PX, M = 120, 1200                     # 1.2 km at 10 m
VIEW = [("rabi 2018-19", (2018, 2019), (1, 3)), ("rabi 2023-24", (2023, 2024), (1, 3)), ("Oct-Nov 2018-19", (2018, 2019), (10, 11)), ("Oct-Nov 2023-24", (2023, 2024), (10, 11))]


def sample():
    t = pd.read_csv(WORK / "tiles.csv", keep_default_na=False).set_index("tile")
    with rasterio.open(WORK / "zone_beat.tif") as s:
        zb, tr = s.read(1), s.transform
    done = np.zeros(zb.shape, bool)
    for f in MAP_D.glob("*.npz"):
        tile, r, c = f.stem.split("_")
        s = t.loc[tile]
        r, c = int(r), int(c)
        done[s.row + r // 3:s.row + (r + 900) // 3, s.col + c // 3:s.col + (c + 900) // 3] = True
    r, c = np.nonzero(done & (zb > 0))
    i = np.random.default_rng(20261105).choice(len(r), 300, replace=False)
    r, c = r[i], c[i]
    pd.DataFrame(dict(pid=RAND_BASE + np.arange(300), row=r, col=c, zone_id=zb[r, c], x=tr.c + (c + .5) * tr.a, y=tr.f + (r + .5) * tr.e)).to_csv(RAND, index=False)
    print("forest pixels in finished chunks", len(i), "of", len(np.nonzero(done & (zb > 0))[0]))


def all_points():
    g = pd.read_csv(GT / "guna_labels.csv")
    rows = [pd.DataFrame(dict(pid=g.gid + 500000, x=g.x, y=g.y)), pd.read_csv(RAND)[["pid", "x", "y"]]]
    for base, sub in ((100000, "validation"), (200000, "validation2")):
        k = pd.read_csv(OUT / sub / "validation_key_DO_NOT_OPEN_BEFORE_LABELLING.csv")
        rows.append(pd.DataFrame(dict(pid=k.sample_id + base, x=k.x, y=k.y)))
    return pd.concat(rows, ignore_index=True)


def run(part):
    p = ee.Projection(WKT)
    fc = ee.FeatureCollection([ee.Feature(ee.Geometry.Point([x, y], p), dict(pid=int(i))) for x, y, i in zip(part.x, part.y, part.pid)])
    a = fc.geometry().bounds(100, "EPSG:4326")
    bands = []
    for y in YS:
        bands += [ndvi(a, y, 1, 3).rename(f"r{y}"), ndvi(a, y, 4, 5).rename(f"d{y}")]
    e, l = dw_mean(a, *A_EARLY), dw_mean(a, *A_LATE)
    bands += [e.select("trees").rename("trees_e"), e.select("shrub_and_scrub").rename("shrub_e"), e.select("crops").rename("crops_e"), l.select("crops").rename("crops_l"), l.select("trees").rename("trees_l"),
              ee.Image("JRC/GSW1_4/GlobalSurfaceWater").select("occurrence").unmask(0).rename("water")]
    msg, wait = "", 30
    for _ in range(8):
        try:
            return [f["properties"] for f in ee.Image.cat(bands).reduceRegions(fc, ee.Reducer.first(), crs=WKT, scale=10, tileScale=8).getInfo()["features"]]
        except Exception as ex:
            msg = str(ex)[:160]
            if "Too Many" in msg:
                time.sleep(wait)
                wait = min(wait * 2, 600)
    print("failed", msg, flush=True)
    return []


def feats():
    init_retry()
    d = all_points()
    old = pd.read_csv(F) if F.exists() else pd.DataFrame(columns=["pid"])
    d = d[~d.pid.isin(old.pid)].assign(ry=lambda q: (q.y // 45000).astype(int), rx=lambda q: (q.x // 45000).astype(int)).sort_values(["ry", "rx"])
    rows = []
    with ThreadPoolExecutor(4) as ex:
        for r in ex.map(run, [d.iloc[i:i + 15] for i in range(0, len(d), 15)]):
            rows += r
            pd.concat([old, pd.DataFrame(rows)], ignore_index=True).to_csv(F, index=False)
            print(len(rows), flush=True)
    print("FINISHED")


def panel(x, y, years, months):
    half = M / 2
    roi = ee.Geometry.Rectangle([x - half, y - half, x + half, y + half], ee.Projection(WKT), False).transform("EPSG:4326", 10)

    def clean(i):
        s = i.select("SCL")
        return i.updateMask(s.eq(1).Or(s.eq(3)).Or(s.eq(8)).Or(s.eq(9)).Or(s.eq(10)).Not()).select(["B8", "B4", "B3"]).toFloat()
    c = ee.ImageCollection(S2).filterBounds(roi).filter(ee.Filter.calendarRange(years[0], years[1], "year")).filter(ee.Filter.calendarRange(months[0], months[1], "month")).filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", 60)).map(clean)
    img = c.median().visualize(bands=["B8", "B4", "B3"], min=[300, 100, 100], max=[4500, 2200, 1900])
    wait = 30
    while True:
        try:
            raw = ee.data.computePixels(dict(expression=img, fileFormat="NPY", grid=dict(dimensions=dict(width=PX, height=PX), crsWkt=WKT,
                                             affineTransform=dict(scaleX=10, shearX=0, translateX=x - half, shearY=0, scaleY=-10, translateY=y + half))))
            a = np.load(io.BytesIO(raw))
            return np.dstack([a["vis-red"], a["vis-green"], a["vis-blue"]]).astype("uint8")
        except Exception as ex:
            if "Too Many" not in str(ex):
                print("chip failed", str(ex)[:120], flush=True)
                return np.zeros((PX, PX, 3), "uint8")
            time.sleep(wait)
            wait = min(wait * 2, 600)


def chip(s):
    f = CH / f"{s.pid}.npy"
    if not f.exists():
        np.save(f, np.stack([panel(s.x, s.y, y, m) for _, y, m in VIEW]))


def chips():
    init_retry()
    CH.mkdir(parents=True, exist_ok=True)
    t = list(pd.read_csv(RAND).itertuples())
    with ThreadPoolExecutor(4) as ex:
        for i, _ in enumerate(ex.map(chip, t)):
            if i % 20 == 0:
                print(i, flush=True)
    print("FINISHED")


def sheets(per=20, cols=5):
    SH.mkdir(parents=True, exist_ok=True)
    t = pd.read_csv(RAND).sort_values("pid")
    S, gap = 2 * PX + 2, 16
    for k in range(0, len(t), per):
        sub = t.iloc[k:k + per]
        rows = int(np.ceil(len(sub) / cols))
        can = Image.new("RGB", (cols * (S + gap), rows * (S + gap + 12)), "white")
        dr = ImageDraw.Draw(can)
        for j, s in enumerate(sub.itertuples()):
            a = np.load(CH / f"{s.pid}.npy")
            x0, y0 = (j % cols) * (S + gap), (j // cols) * (S + gap + 12)
            dr.text((x0 + 2, y0), str(s.pid - RAND_BASE), fill="black")
            for q, (dx, dy) in enumerate(((0, 0), (PX + 2, 0), (0, PX + 2), (PX + 2, PX + 2))):
                im = Image.fromarray(a[q])
                d2 = ImageDraw.Draw(im)
                d2.rectangle([PX // 2 - 3, PX // 2 - 3, PX // 2 + 3, PX // 2 + 3], outline="yellow")
                can.paste(im, (x0 + dx, y0 + 12 + dy))
        can.save(SH / f"sheet_{k // per:02d}.png")
    print("panels: top rabi 2018-19 | rabi 2023-24; bottom Oct-Nov 2018-19 | Oct-Nov 2023-24; false colour NIR-red-green")


if __name__ == "__main__":
    {"sample": sample, "feats": feats, "chips": chips, "sheets": sheets}[sys.argv[1]]()
