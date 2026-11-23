"""Blind visual validation of the burn maps.

make:  python validate.py make <obsroot> <burndir> <outdir> <n_burned> <n_unburned> <seed>
       Samples points (burned pixels and unburned eligible pixels, all seasons), and for each
       renders three false-colour chips (SWIR2/NIR/red, 1.6 km wide): last clear image before
       the window, first image after it, and one ~2-4 weeks later. Burned points use their
       detected window; unburned points use a random clear window in Feb-May. Sheets show
       10 points each, shuffled, with no hint of the detector's answer. key.csv holds the truth.
score: python validate.py score <outdir>   (reads judged.csv: point_id,judged_burned[0/1/9=unsure])
"""
import os, sys, glob, csv, datetime as dt
import numpy as np
from PIL import Image, ImageDraw

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fetch

I = fetch.INSIDE
rows_, cols_ = np.where(I)
HALF, SCALE = 40, 2


def obs_index(obsdir):
    files = sorted(glob.glob(os.path.join(obsdir, "*.npz")))
    return [(dt.date.fromisoformat(os.path.basename(f)[:10]), f) for f in files]


def chip(fn, r, c):
    z = np.load(fn)
    out = []
    for k in ("swir2", "nir", "red"):
        f = np.zeros(I.shape, np.float32); f[I] = z[k] / 10000
        out.append(f)
    v = np.zeros(I.shape, bool); v[I] = z["valid"]
    sl = (slice(max(r - HALF, 0), r + HALF), slice(max(c - HALF, 0), c + HALF))
    rgb = np.stack([o[sl] for o in out], -1)
    return rgb, v[sl]


def render(chips):
    allv = np.concatenate([c[0][c[1]] for c in chips if c[1].any()]) if any(c[1].any() for c in chips) else np.zeros((1, 3))
    lo, hi = np.percentile(allv, 2, axis=0), np.percentile(allv, 98, axis=0)
    ims = []
    for rgb, v in chips:
        x = np.clip((rgb - lo) / np.maximum(hi - lo, 1e-3), 0, 1)
        x[~v] = 0
        im = Image.fromarray((x * 255).astype(np.uint8)).resize((x.shape[1] * SCALE, x.shape[0] * SCALE), Image.NEAREST)
        d = ImageDraw.Draw(im)
        cx, cy = HALF * SCALE, HALF * SCALE
        d.ellipse([cx - 9, cy - 9, cx + 9, cy + 9], outline=(0, 255, 255), width=2)
        ims.append(im)
    return ims


def make(obsroot, burndir, outdir, nb, nu, seed):
    rng = np.random.default_rng(seed)
    lc = np.load(fetch.WORLDCOVER)
    eligible = np.isin(lc, (10, 20, 30))
    pts = []
    strata = dict(burned_px=0, unburned_px=0)
    years = sorted(int(os.path.basename(f)[5:9]) for f in glob.glob(os.path.join(burndir, "burn_*.npz")))
    for y in years:
        b = np.load(os.path.join(burndir, f"burn_{y}.npz"))
        obs = obs_index(os.path.join(obsroot, str(y)))
        burned = np.where(b["end"] > -999)[0]
        unb = np.where((b["end"] == -999) & eligible)[0]
        strata["burned_px"] += int(len(burned)); strata["unburned_px"] += int(len(unb))
        for i in rng.choice(burned, min(nb // len(years), len(burned)), replace=False):
            pts.append((y, i, int(b["start"][i]), int(b["end"][i]), 1))
        for i in rng.choice(unb, nu // len(years), replace=False):
            pts.append((y, i, None, None, 0))
    rng.shuffle(pts)
    os.makedirs(outdir, exist_ok=True)
    key = []
    sheet, n_sheet = [], 0
    for pid, (y, i, s, e, lab) in enumerate(pts):
        obs = obs_index(os.path.join(obsroot, str(y)))
        r, c = rows_[i], cols_[i]
        valid_at = [(d, f) for d, f in obs if np.load(f)["valid"][i]]
        days = [(d - dt.date(y, 1, 1)).days for d, _ in valid_at]
        if lab:
            jb = max(k for k, dd in enumerate(days) if dd <= s)
            ka = days.index(e)
        else:
            cand = [k for k in range(1, len(days)) if 31 <= days[k] <= 150 and days[k] - days[k - 1] <= 20]
            if not cand:
                continue
            ka = int(rng.choice(cand)); jb = ka - 1
        later = [k for k in range(ka + 1, len(days)) if 14 <= days[k] - days[ka] <= 40]
        kl = later[0] if later else min(ka + 1, len(days) - 1)
        use = [valid_at[jb], valid_at[ka], valid_at[kl]]
        ims = render([chip(f, r, c) for _, f in use])
        sheet.append((pid, ims, [d.isoformat() for d, _ in use]))
        key.append(dict(point_id=pid, year=y, pixel=i, row=r, col=c, detected_burned=lab,
                        pre=use[0][0].isoformat(), post=use[1][0].isoformat(), late=use[2][0].isoformat(),
                        landcover=int(lc[i])))
        if len(sheet) == 10 or pid == len(pts) - 1:
            w = sheet[0][1][0].width
            canvas = Image.new("RGB", (w * 3 + 90, (w + 18) * len(sheet)), (30, 30, 30))
            d = ImageDraw.Draw(canvas)
            for rr, (p, ims, ds) in enumerate(sheet):
                y0 = rr * (w + 18)
                d.text((4, y0 + w // 2), f"#{p}", fill=(255, 255, 255))
                for cc, im in enumerate(ims):
                    canvas.paste(im, (90 + cc * w, y0 + 14))
                    d.text((90 + cc * w + 4, y0), ds[cc], fill=(200, 200, 200))
            canvas.save(os.path.join(outdir, f"sheet_{n_sheet:02d}.png"))
            n_sheet += 1
            sheet = []
    with open(os.path.join(outdir, "key.csv"), "w", newline="") as f:
        wr = csv.DictWriter(f, fieldnames=list(key[0])); wr.writeheader(); wr.writerows(key)
    import json
    json.dump(strata, open(os.path.join(outdir, "strata.json"), "w"))
    print("points", len(key), "sheets", n_sheet)


def score(outdir):
    key = {int(r["point_id"]): r for r in csv.DictReader(open(os.path.join(outdir, "key.csv")))}
    judged = {int(r["point_id"]): int(r["judged_burned"]) for r in csv.DictReader(open(os.path.join(outdir, "judged.csv")))}
    tp = fp = fn = tn = uns = 0
    for p, j in judged.items():
        d = int(key[p]["detected_burned"])
        if j == 9:
            uns += 1; continue
        tp += d and j; fp += d and not j; fn += (not d) and j; tn += (not d) and (not j)
    prec = tp / max(tp + fp, 1)
    omit = fn / max(fn + tn, 1)
    # stratified estimate: scale each stratum by its share of eligible pixels
    import json
    area = json.load(open(os.path.join(outdir, "strata.json")))
    burned_true = area["burned_px"] * prec + area["unburned_px"] * omit
    rec = area["burned_px"] * prec / max(burned_true, 1)
    print(f"judged {len(judged)} unsure {uns}  TP {tp} FP {fp} FN {fn} TN {tn}  "
          f"precision {prec:.2f}  omission-rate-in-unburned {omit:.3f}  area-weighted recall {rec:.2f}")
    return dict(tp=tp, fp=fp, fn=fn, tn=tn, unsure=uns, precision=prec, omission_unburned=omit, recall=rec)


if __name__ == "__main__":
    if sys.argv[1] == "make":
        make(sys.argv[2], sys.argv[3], sys.argv[4], int(sys.argv[5]), int(sys.argv[6]), int(sys.argv[7]))
    else:
        score(sys.argv[2])
