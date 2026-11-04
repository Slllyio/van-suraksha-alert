"""Regional year anomaly per score and tree band: drought or wet years shift whole landscapes and would read as loss.
offset[band, year] = smoothed local median of that year - median of those across years, on a ~9 km grid of forest pixels."""
import json

import cv2
import numpy as np
import pandas as pd
import rasterio
from scipy.ndimage import gaussian_filter

from common import *

CELL = 300            # 9 km grid
SIGMA = 1.5           # cells, ~13 km smoothing


def _medians(version):
    g = json.load(open(WORK / "grid.json"))
    ny, nx = g["height"] // CELL + 1, g["width"] // CELL + 1
    t = pd.read_csv(WORK / "tiles.csv", keep_default_na=False)
    with rasterio.open(WORK / "zone_beat.tif") as s:
        full = s.read(1)
    first = rasterio.open(WORK / f"emb_{version}" / f"{t.tile[0]}.tif")
    names = list(first.descriptions)
    first.close()
    M = np.full((len(names), ny, nx), np.nan, "float32")
    for s in t.itertuples():
        with rasterio.open(WORK / f"emb_{version}" / f"{s.tile}.tif") as src:
            a = src.read()
        z = full[s.row:s.row + s.h, s.col:s.col + s.w] > 0
        for r0 in range(0, int(s.h), CELL):
            for c0 in range(0, int(s.w), CELL):
                m = z[r0:r0 + CELL, c0:c0 + CELL]
                if m.sum() < 300:
                    continue
                cy, cx = (s.row + r0) // CELL, (s.col + c0) // CELL
                M[:, cy, cx] = np.median(a[:, r0:r0 + CELL, c0:c0 + CELL][:, m], axis=1)
    return names, M


def build(version):
    names, M = _medians(version)
    valid = np.isfinite(M[0])
    smooth = np.zeros_like(M)
    w = gaussian_filter(valid.astype("float32"), SIGMA)
    for i in range(M.shape[0]):
        smooth[i] = gaussian_filter(np.where(valid, M[i], 0), SIGMA) / np.maximum(w, 1e-3)
    off = np.zeros_like(M)
    for pre in ("z", "tree"):
        idx = [i for i, n in enumerate(names) if n.startswith(pre)]
        off[idx] = smooth[idx] - np.median(smooth[idx], axis=0)
    np.savez(WORK / f"anomaly_{version}.npz", off=off, names=np.array(names))
    print("anomaly grid", off.shape, "state mean offset per band",
          {n: int(off[i][w > .1].mean()) for i, n in enumerate(names)})
    return off, names


def load(version):
    x = np.load(WORK / f"anomaly_{version}.npz")
    return x["off"], [str(n) for n in x["names"]]


def tile_offset(off, s):
    """Bilinear offset per band on one tile's pixels."""
    r0, r1 = s.row / CELL, (s.row + s.h) / CELL
    c0, c1 = s.col / CELL, (s.col + s.w) / CELL
    out = np.zeros((off.shape[0], int(s.h), int(s.w)), "int16")
    rr = np.linspace(r0, r1, int(s.h), dtype="float32")
    cc = np.linspace(c0, c1, int(s.w), dtype="float32")
    my, mx = np.meshgrid(rr - .5, cc - .5, indexing="ij")
    for i in range(off.shape[0]):
        out[i] = np.clip(cv2.remap(off[i].astype("float32"), mx, my, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE), -32000, 32000)
    return out


if __name__ == "__main__":
    import sys
    build(sys.argv[1])
