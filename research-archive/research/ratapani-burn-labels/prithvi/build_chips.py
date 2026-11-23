"""Cut 224 x 224 before/after chips with weak labels from the burn-scar detector.

For each pair of consecutive clear images (a, b) in a season (b between 1 Jan and 20 Jun, gap <= 20 days):
  label 1  = pixel clear in both, and the detector's scar appeared in (a, b]
  label 0  = eligible cover, clear in both, no new scar in (a, b] (old scars count as 0: the model learns change)
  label -1 = ignored (cloud in either image, cropland/water/built-up, outside the AOI, or near a validation point)
Writes <outdir>/x_<season>.npy (N, 6, 2, 224, 224) int16, y_<season>.npy (N, 224, 224) int8, meta_<season>.csv.
Usage: python build_chips.py <obsroot> <burndir> <worldcover.npy> <key.csv> <outdir> [pos_per_season] [neg_per_season]
"""
import os, sys, csv
import numpy as np
from scipy.ndimage import binary_dilation
from common import fetch, detect, season_files, load_image, CHIP, ROWS, COLS


def tiles(h, w, step=CHIP):
    rs = sorted(set(list(range(0, h - CHIP + 1, step)) + [h - CHIP]))
    cs = sorted(set(list(range(0, w - CHIP + 1, step)) + [w - CHIP]))
    return [(r, c) for r in rs for c in cs]


def main(obsroot, burndir, wc, keycsv, outdir, npos=150, nneg=150, seed=0):
    rng = np.random.default_rng(seed)
    os.makedirs(outdir, exist_ok=True)
    H, W = fetch.INSIDE.shape
    elig = np.zeros((H, W), bool)
    elig[fetch.INSIDE] = np.isin(np.load(wc), detect.LANDCOVER_OK)
    key = list(csv.DictReader(open(keycsv)))
    for y in range(2017, 2027):
        if os.path.exists(os.path.join(outdir, f"y_{y}.npy")):
            continue
        b = np.load(os.path.join(burndir, f"burn_{y}.npz"))
        end = np.full((H, W), -999, np.int16)
        end[fetch.INSIDE] = b["end"]
        hold = np.zeros((H, W), bool)  # keep the judged validation points out of training
        for r in key:
            if int(r["year"]) == y:
                hold[int(r["row"]), int(r["col"])] = True
        hold = binary_dilation(hold, iterations=3)
        files = season_files(os.path.join(obsroot, str(y)))
        dates = list(files)
        doy = [(d - __import__("datetime").date(y, 1, 1)).days for d in dates]
        pairs = [(k - 1, k) for k in range(1, len(dates)) if 0 <= doy[k] <= 171 and doy[k] - doy[k - 1] <= 20]
        valid = {}
        for k in sorted({i for p in pairs for i in p}):
            valid[k] = load_image(files[dates[k]])[1]
        cands = []
        for a, bb in pairs:
            lab = np.full((H, W), -1, np.int8)
            v = valid[a] & valid[bb] & elig & ~hold
            lab[v] = 0
            lab[v & (end > doy[a]) & (end <= doy[bb])] = 1
            for r, c in tiles(H, W):
                t = lab[r:r + CHIP, c:c + CHIP]
                nl, npx = int((t >= 0).sum()), int((t == 1).sum())
                if nl >= 0.3 * CHIP * CHIP:
                    cands.append((a, bb, r, c, nl, npx))
        pos = [x for x in cands if x[5] >= 50]
        neg = [x for x in cands if x[5] == 0 and x[4] >= 0.5 * CHIP * CHIP]
        pick = [pos[i] for i in rng.permutation(len(pos))[:npos]] + [neg[i] for i in rng.permutation(len(neg))[:nneg]]
        need = sorted({i for p in pick for i in p[:2]})
        imgs = {k: load_image(files[dates[k]]) for k in need}
        X = np.zeros((len(pick), 6, 2, CHIP, CHIP), np.int16)
        Y = np.full((len(pick), CHIP, CHIP), -1, np.int8)
        meta = []
        for n, (a, bb, r, c, nl, npx) in enumerate(pick):
            X[n, :, 0] = imgs[a][0][:, r:r + CHIP, c:c + CHIP]
            X[n, :, 1] = imgs[bb][0][:, r:r + CHIP, c:c + CHIP]
            v = (imgs[a][1] & imgs[bb][1] & elig & ~hold)[r:r + CHIP, c:c + CHIP]
            e = end[r:r + CHIP, c:c + CHIP]
            Y[n][v] = 0
            Y[n][v & (e > doy[a]) & (e <= doy[bb])] = 1
            meta.append(dict(season=y, pre=dates[a].isoformat(), post=dates[bb].isoformat(), row=r, col=c,
                             labelled=nl, burned=npx))
        np.save(os.path.join(outdir, f"x_{y}.npy"), X)
        with open(os.path.join(outdir, f"meta_{y}.csv"), "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(meta[0])); w.writeheader(); w.writerows(meta)
        np.save(os.path.join(outdir, f"y_{y}.npy"), Y)  # written last: marks the season done
        print(y, "pairs", len(pairs), "candidates pos", len(pos), "neg", len(neg), "chips", len(pick), flush=True)


if __name__ == "__main__":
    a = sys.argv
    main(a[1], a[2], a[3], a[4], a[5], *(int(v) for v in a[6:8]))
