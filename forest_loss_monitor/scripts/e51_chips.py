"""Blind S2 chips for the random forest points, via sampleRectangle (gets through Restricted Mode far better than computePixels). No rule output is used or shown.
Panels: top rabi 2018-19 | rabi 2023-24, bottom Oct-Nov 2018-19 | Oct-Nov 2023-24. False colour NIR-red-green; yellow box = the 50 m scored area.
Usage: e51_chips.py fetch [threads] | sheets"""
import sys
import time
from concurrent.futures import ThreadPoolExecutor

import ee
import numpy as np
import pandas as pd
from PIL import Image, ImageDraw

from common import *
from e33_map10m import init_retry
from e46_s2f import RAND, RAND_BASE, S2, SH, VIEW

CH = WORK / "s2f_chips2"
HALF = 400
LO, HI = np.array([300, 100, 100]), np.array([4500, 2200, 1900])
SCALE = 2


def clean(i):
    q = i.select("SCL")
    return i.updateMask(q.eq(1).Or(q.eq(3)).Or(q.eq(8)).Or(q.eq(9)).Or(q.eq(10)).Not()).select(["B8", "B4", "B3"]).toFloat()


def chip(s):
    f = CH / f"{s.pid}.npy"
    if f.exists():
        return 0
    roi = ee.Geometry.Rectangle([s.x - HALF, s.y - HALF, s.x + HALF, s.y + HALF], ee.Projection(WKT), False)
    r4 = roi.transform("EPSG:4326", 10)
    bands = []
    for k, (_, yy, m) in enumerate(VIEW):
        c = ee.ImageCollection(S2).filterBounds(r4).filter(ee.Filter.calendarRange(yy[0], yy[1], "year")).filter(ee.Filter.calendarRange(m[0], m[1], "month")).filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", 60)).map(clean)
        bands.append(c.median().rename([f"p{k}_n", f"p{k}_r", f"p{k}_g"]))
    img = ee.Image.cat(bands).unmask(0).toInt16().reproject(ee.Projection(WKT).atScale(10))
    wait = 30
    for _ in range(10):
        try:
            a = img.sampleRectangle(region=roi, defaultValue=0).getInfo()["properties"]
            np.save(f, np.stack([np.dstack([a[f"p{k}_{b}"] for b in "nrg"]) for k in range(4)]).astype("int16"))
            return 1
        except Exception as e:
            msg = str(e)[:120]
            time.sleep(wait if "Too Many" in msg else 5)
            wait = min(wait * 2, 300)
    print("failed", s.pid, msg, flush=True)
    return 0


def fetch(th):
    init_retry()
    CH.mkdir(parents=True, exist_ok=True)
    n = 0
    with ThreadPoolExecutor(th) as ex:
        for i, ok in enumerate(ex.map(chip, pd.read_csv(RAND).itertuples())):
            n += ok
            if i % 20 == 0:
                print(i, n, flush=True)
    print("FINISHED")


def sheets(per=20, cols=5):
    SH.mkdir(parents=True, exist_ok=True)
    t = pd.read_csv(RAND).sort_values("pid")
    P = 81 * SCALE
    S, gap = 2 * P + 2, 14
    for k in range(0, len(t), per):
        sub = t.iloc[k:k + per]
        rows = int(np.ceil(len(sub) / cols))
        can = Image.new("RGB", (cols * (S + gap), rows * (S + gap + 12)), "white")
        dr = ImageDraw.Draw(can)
        for j, s in enumerate(sub.itertuples()):
            f = CH / f"{s.pid}.npy"
            if not f.exists():
                continue
            a = np.load(f)
            x0, y0 = (j % cols) * (S + gap), (j // cols) * (S + gap + 12)
            dr.text((x0 + 2, y0), str(s.pid - RAND_BASE), fill="black")
            for q, (dx, dy) in enumerate(((0, 0), (P + 2, 0), (0, P + 2), (P + 2, P + 2))):
                v = np.clip((a[q] - LO) / (HI - LO), 0, 1) * 255
                im = Image.fromarray(v.astype("uint8")).resize((P, P), Image.NEAREST)
                c = P // 2
                ImageDraw.Draw(im).rectangle([c - 5 * SCALE // 2 - 2, c - 5 * SCALE // 2 - 2, c + 5 * SCALE // 2 + 2, c + 5 * SCALE // 2 + 2], outline="yellow")
                can.paste(im, (x0 + dx, y0 + 12 + dy))
        can.save(SH / f"sheet_{k // per:02d}.png")
    print("sheets", len(t) // per)


if __name__ == "__main__":
    fetch(int(sys.argv[2]) if len(sys.argv) > 2 else 3) if sys.argv[1] == "fetch" else sheets()
