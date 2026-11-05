"""Blind yearly image strips for labelling the kind of change. Per point: Sentinel-2 false colour (NIR, red, green) for Oct-Nov of each year 2017-2025, then Jan-Feb of 2018, 2022 and 2025; 600 m window, yellow box = the 50 m scored area.
Under each frame: NDVI of the box / NDVI of the rest of the window. Rows carry a random code only; the key stays unopened until labels are saved.
Points: every reference point stage 1 flags, the two missed losses, 30 ignored reference points, rejected and confirmed felling candidates, and the new flags. Usage: e93_cc_strips.py select | fetch [threads] | sheets"""
import sys
import time
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, "E:/FIRE/forest_loss_monitor/scripts")

import ee
import numpy as np
import pandas as pd
from PIL import Image, ImageDraw

from common import *
from e32_enetra10m import S2
from e33_map10m import init_retry

GT = ROOT / "ground_truth"
KEY = GT / "cc_strips_key_DO_NOT_OPEN_BEFORE_LABELLING.csv"
CH = WORK / "cc_strips"
SH = OUT / "cc_strip_sheets"
HALF, SCALE, PER = 300, 2, 6
FRAMES = [(f"ON {y}", y, (10, 11)) for y in range(2017, 2026)] + [(f"JF {y}", y, (1, 2)) for y in (2018, 2022, 2025)]
LO, HI = np.array([300, 100, 100]), np.array([4500, 2200, 1900])
SEED = 20261109


def select():
    d = pd.read_csv(GT / "guna_cc_labels.csv", keep_default_na=False, na_values=[""])
    f = pd.read_csv(OUT / "interim" / "report" / "cc_four_points_logistic.csv")
    s1 = dict(zip(f.cid, f.iloc[:, 7]))                 # stage-1 flag column
    rng = np.random.default_rng(SEED)
    ref = d[d.set == "reference"]
    flagged = ref[ref.cid.map(s1).fillna(False).astype(bool)]
    missed = ref[(ref.y == 1) & ~ref.cid.isin(flagged.cid)]
    ignored = ref[(ref.y == 0) & ~ref.cid.isin(flagged.cid)].sample(30, random_state=SEED)
    cand = d[d.set.isin(["felling", "recall_kit", "recent_new"]) & (d.y == 0)]
    fell = d[(d.set == "felling") & (d.y == 1)].sample(20, random_state=SEED)
    new = d[d.set == "new_flag"]
    t = pd.concat([flagged, missed, ignored, cand, fell, new], ignore_index=True)
    t["code"] = rng.permutation(len(t)) + 1
    t.sort_values("code")[["code", "cid", "set", "id", "y", "stratum", "x", "y_m"]].to_csv(KEY, index=False)
    print(len(t), "points:", len(flagged), "reference flags,", len(missed), "missed,", len(ignored), "ignored,", len(cand), "rejected candidates,", len(fell), "fellings,", len(new), "new flags")


def clean(i):
    q = i.select("SCL")
    return i.updateMask(q.eq(1).Or(q.eq(3)).Or(q.eq(8)).Or(q.eq(9)).Or(q.eq(10)).Not()).select(["B8", "B4", "B3"]).toFloat()


def chip(s):
    f = CH / f"{s.code}.npy"
    if f.exists():
        return 0
    roi = ee.Geometry.Rectangle([s.x - HALF, s.y_m - HALF, s.x + HALF, s.y_m + HALF], ee.Projection(WKT), False)
    r4 = roi.transform("EPSG:4326", 10)
    bands = []
    for k, (_, y, m) in enumerate(FRAMES):
        c = ee.ImageCollection(S2).filterBounds(r4).filter(ee.Filter.calendarRange(y, y, "year")).filter(ee.Filter.calendarRange(m[0], m[1], "month")).filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", 60)).map(clean)
        bands.append(c.median().rename([f"p{k}_n", f"p{k}_r", f"p{k}_g"]))
    img = ee.Image.cat(bands).unmask(0).toInt16().reproject(ee.Projection(WKT).atScale(10))
    wait, msg = 30, ""
    for _ in range(10):
        try:
            a = img.sampleRectangle(region=roi, defaultValue=0).getInfo()["properties"]
            np.save(f, np.stack([np.dstack([a[f"p{k}_{b}"] for b in "nrg"]) for k in range(len(FRAMES))]).astype("int16"))
            return 1
        except Exception as e:
            msg = str(e)[:120]
            time.sleep(wait if "Too Many" in msg else 5)
            wait = min(wait * 2, 300)
    print("failed", s.code, msg, flush=True)
    return 0


def fetch(th):
    init_retry()
    CH.mkdir(parents=True, exist_ok=True)
    n = 0
    with ThreadPoolExecutor(th) as ex:
        for i, ok in enumerate(ex.map(chip, pd.read_csv(KEY).itertuples())):
            n += ok
            if i % 10 == 0:
                print(i, n, flush=True)
    print("FINISHED")


def sheets():
    SH.mkdir(parents=True, exist_ok=True)
    codes = sorted(int(f.stem) for f in CH.glob("*.npy"))
    a0 = np.load(CH / f"{codes[0]}.npy")
    P = a0.shape[1] * SCALE
    gap, left, top = 4, 34, 14
    W, H = left + len(FRAMES) * (P + gap), P + 14
    for k in range(0, len(codes), PER):
        sub = codes[k:k + PER]
        can = Image.new("RGB", (W, top + len(sub) * H), "white")
        dr = ImageDraw.Draw(can)
        for q, (nm, _, _) in enumerate(FRAMES):
            dr.text((left + q * (P + gap) + 30, 1), nm, fill="black")
        for j, code in enumerate(sub):
            a = np.load(CH / f"{code}.npy").astype(float)
            y0 = top + j * H
            dr.text((2, y0 + P // 2 - 5), str(code), fill="black")
            c = a.shape[1] // 2
            box = np.zeros(a.shape[1:3], bool)
            box[c - 2:c + 3, c - 2:c + 3] = True
            for q in range(len(FRAMES)):
                v = np.clip((a[q] - LO) / (HI - LO), 0, 1) * 255
                im = Image.fromarray(v.astype("uint8")).resize((P, P), Image.NEAREST)
                ImageDraw.Draw(im).rectangle([(c - 2) * SCALE - 2, (c - 2) * SCALE - 2, (c + 3) * SCALE + 1, (c + 3) * SCALE + 1], outline="yellow")
                x0 = left + q * (P + gap)
                can.paste(im, (x0, y0))
                n, r = a[q, :, :, 0], a[q, :, :, 1]
                ok = (n + r) > 0
                nd = np.where(ok, (n - r) / np.maximum(n + r, 1), np.nan)
                txt = "no data" if not ok[box].any() else f"{np.nanmean(nd[box]):.2f} / {np.nanmean(nd[~box & ok]):.2f}"
                dr.text((x0 + 26, y0 + P), txt, fill="black")
        can.save(SH / f"sheet_{k // PER:02d}.png")
    print("sheets", int(np.ceil(len(codes) / PER)), "points", len(codes))


if __name__ == "__main__":
    dict(select=select, fetch=lambda: fetch(int(sys.argv[2]) if len(sys.argv) > 2 else 2), sheets=sheets)[sys.argv[1]]()
