"""Render validation sheets TimeSync-style: three false-colour chips plus the pixel's NBR series.

Sentinel-2 chips are put on the Landsat scale so a sensor switch doesn't look like a change.
The NBR panel shows the pixel (dots: orange = Sentinel-2, white = Landsat) and the mean of the
surrounding ~1.5 km (grey line), Dec to Jun, with the chip dates as faint ticks. Nothing on the
sheet shows the detector's answer.
Usage: python rerender.py <obsroot> <valdir>    (reads valdir/key.csv, writes valdir/ts_sheet_XX.png)
"""
import os, sys, csv, glob, datetime as dt
import numpy as np
from PIL import Image, ImageDraw

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fetch, detect
from validate import HALF, SCALE

I = fetch.INSIDE
SCL = dict(swir2=detect.S2_TO_LS["swir2"], nir=detect.S2_TO_LS["nir"], red=0.93)


def chip(fn, r, c):
    z = np.load(fn)
    s2 = fn.endswith("_s2.npz")
    out = []
    for k in ("swir2", "nir", "red"):
        f = np.zeros(I.shape, np.float32); f[I] = z[k] / 10000 * (SCL[k] if s2 else 1)
        out.append(f)
    v = np.zeros(I.shape, bool); v[I] = z["valid"]
    sl = (slice(max(r - HALF, 0), r + HALF), slice(max(c - HALF, 0), c + HALF))
    return np.stack([o[sl] for o in out], -1), v[sl]


def render_chips(chips):
    allv = np.concatenate([c[0][c[1]] for c in chips if c[1].any()])
    lo, hi = np.percentile(allv, 2, axis=0), np.percentile(allv, 98, axis=0)
    ims = []
    for rgb, v in chips:
        x = np.clip((rgb - lo) / np.maximum(hi - lo, 1e-3), 0, 1); x[~v] = 0
        im = Image.fromarray((x * 255).astype(np.uint8)).resize((x.shape[1] * SCALE, x.shape[0] * SCALE), Image.NEAREST)
        d = ImageDraw.Draw(im); cx = HALF * SCALE
        d.ellipse([cx - 9, cx - 9, cx + 9, cx + 9], outline=(0, 255, 255), width=2)
        ims.append(im)
    return ims


def spark(year, dates, sensors, px, loc, marks, w, h):
    im = Image.new("RGB", (w, h), (15, 15, 15)); d = ImageDraw.Draw(im)
    x = lambda dd: int((dd - dt.date(year - 1, 12, 1)).days / 202 * (w - 10)) + 5
    yv = lambda v: int(h - 5 - (v + 0.4) / 1.0 * (h - 10))
    for v in (-0.2, 0.0, 0.2, 0.4):
        d.line([(0, yv(v)), (w, yv(v))], fill=(50, 50, 50))
        d.text((2, yv(v) - 10), f"{v:+.1f}", fill=(90, 90, 90))
    for m in range(1, 7):
        d.text((x(dt.date(year, m, 1)), h - 14), "JFMAMJ"[m - 1], fill=(110, 110, 110))
    for mk in marks:
        d.line([(x(mk), 0), (x(mk), 8)], fill=(0, 200, 200))
    pts = [(x(dd), yv(l)) for dd, l in zip(dates, loc) if not np.isnan(l)]
    if len(pts) > 1:
        d.line(pts, fill=(130, 130, 130), width=1)
    for dd, v, s in zip(dates, px, sensors):
        if not np.isnan(v):
            cx, cy = x(dd), yv(np.clip(v, -0.4, 0.6))
            d.ellipse([cx - 3, cy - 3, cx + 3, cy + 3], fill=(255, 150, 0) if s == "s2" else (240, 240, 240))
    return im


def main(obsroot, valdir):
    key = list(csv.DictReader(open(os.path.join(valdir, "key.csv"))))
    by_year = {}
    for r in key:
        by_year.setdefault(int(r["year"]), []).append(r)
    panels = {}
    for y, rows in sorted(by_year.items()):
        obsdir = os.path.join(obsroot, str(y))
        dates, nbr, nir, mirbi = detect.load(obsdir)
        files = {dt.date.fromisoformat(os.path.basename(f)[:10]): f for f in sorted(glob.glob(os.path.join(obsdir, "*.npz")))}
        sensors = ["s2" if files[dd].endswith("_s2.npz") else "ls" for dd in dates]
        loc = np.full((len(dates), len(rows)), np.nan)
        pix = np.array([int(r["pixel"]) for r in rows])
        for t in range(len(dates)):
            ok = ~np.isnan(nbr[t])
            if ok.sum() > 100:
                loc[t] = detect.local_mean(np.nan_to_num(nbr[t]), ok, detect.P["win"])[pix]
        for n, r in enumerate(rows):
            i, rr, cc = int(r["pixel"]), int(r["row"]), int(r["col"])
            use = [r["pre"], r["post"], r["late"]]
            fl = [glob.glob(os.path.join(obsdir, f"{u}_*.npz")) for u in use]
            fl = [sorted(f, key=lambda p: -int(np.load(p)["valid"][i]))[0] for f in fl]
            ims = render_chips([chip(f, rr, cc) for f in fl])
            sp = spark(y, dates, sensors, nbr[:, i], loc[:, n], [dt.date.fromisoformat(u) for u in use],
                       ims[0].width * 2, ims[0].height)
            panels[int(r["point_id"])] = (ims + [sp], use)
    ids = sorted(panels)
    for s in range(0, len(ids), 10):
        chunk = ids[s:s + 10]
        w = panels[chunk[0]][0][0].width
        canvas = Image.new("RGB", (w * 5 + 60, (w + 18) * len(chunk)), (30, 30, 30))
        d = ImageDraw.Draw(canvas)
        for rr, p in enumerate(chunk):
            ims, use = panels[p]; y0 = rr * (w + 18)
            d.text((4, y0 + w // 2), f"#{p}", fill=(255, 255, 255))
            for cc, im in enumerate(ims):
                canvas.paste(im, (60 + cc * w, y0 + 14))
                if cc < 3:
                    d.text((60 + cc * w + 4, y0), use[cc], fill=(200, 200, 200))
        canvas.save(os.path.join(valdir, f"ts_sheet_{s // 10:02d}.png"))
    print("rendered", len(ids))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
