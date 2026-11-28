"""Local scoring: model scores z<year> (x1000) and tree<year> (x10000) per tile from the downloaded embeddings.
Output work/emb_<version>/<tile>.tif on the tile grid. Skips tiles with missing years. Usage: e7_score.py <version> [tile1,tile2]"""
import json
import sys

import numpy as np
import pandas as pd
import rasterio
from rasterio.transform import from_origin

from common import *
from e6_fetch_embeddings import EMB_DIR

FIRST, LAST = 2018, 2025


def score_tile(s, z, M, T, out):
    mask = z > 0
    E = {y: np.load(EMB_DIR / f"{s.tile}_{y}.npz")["vals"].astype("float32") / 127 for y in range(FIRST - 1, LAST + 1)}
    wc, wn, wt = np.array(M["change_c"], "float32"), np.array(M["change_n"], "float32"), np.array(T["coef"], "float32")
    bands, names = [], []
    for y in range(FIRST, LAST + 1):
        p, c, n = E[y - 1], E[y], E[min(y + 1, LAST)]
        v = (c - p) @ wc + (n - p) @ wn + M["dist_pc"] * (1 - (p * c).sum(1)) + M["dist_pn"] * (1 - (p * n).sum(1)) + M["intercept"]
        bands.append(np.clip(v * 1000, -32000, 32000))
        names.append(f"z{y}")
    for y in range(FIRST - 1, LAST + 1):
        bands.append(np.clip((E[y] @ wt + T["intercept"]) * 10000, -32000, 32000))
        names.append(f"tree{y}")
    arr = np.zeros((len(bands),) + z.shape, "int16")
    for i, b in enumerate(bands):
        arr[i][mask] = b.round().astype("int16")
    with rasterio.open(out, "w", driver="GTiff", width=int(s.w), height=int(s.h), count=len(names), dtype="int16", crs=PROJ4,
                       transform=from_origin(s.x0, s.y1, RES, RES), compress="deflate", predictor=2, tiled=True) as o:
        o.write(arr)
        o.descriptions = tuple(names)


def main():
    version = sys.argv[1]
    d = WORK / f"emb_{version}"
    d.mkdir(exist_ok=True, parents=True)
    M, T = json.load(open(ROOT / "scripts" / "model_loss.json")), json.load(open(ROOT / "scripts" / "model_tree.json"))
    t = pd.read_csv(WORK / "tiles.csv", keep_default_na=False)
    if len(sys.argv) > 2:
        t = t[t.tile.isin(sys.argv[2].split(","))]
    with rasterio.open(WORK / "zone_beat.tif") as src:
        full = src.read(1)
    n = 0
    for s in t.sort_values("forest_px").itertuples():
        out = d / f"{s.tile}.tif"
        if out.exists() or not all((EMB_DIR / f"{s.tile}_{y}.npz").exists() for y in range(FIRST - 1, LAST + 1)):
            continue
        score_tile(s, full[s.row:s.row + s.h, s.col:s.col + s.w], M, T, out)
        n += 1
        print("scored", s.tile, flush=True)
    print("scored now", n, "total", len(list(d.glob("*.tif"))), "of", len(t))


if __name__ == "__main__":
    main()
