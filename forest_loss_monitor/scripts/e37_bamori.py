"""Bamori polygons against the 10 m map using the whole polygon, by class, and with the rule's inputs at the polygons."""
import geopandas as gpd
import numpy as np
import pandas as pd
from rasterio.features import rasterize
from rasterio.transform import from_origin

from common import *
from e33_map10m import CHUNK, D

g = gpd.read_file("E:/e_Netra/outputs/bamori_alphaearth_v2/FINAL_LABELS/bamori_validated_change_2017_2024.geojson").to_crs(PROJ4)
t = pd.read_csv(WORK / "tiles.csv", keep_default_na=False)
rows = []
for p in g.itertuples():
    x0, y0, x1, y1 = p.geometry.bounds
    x0, y1 = np.floor(x0 / 10) * 10, np.ceil(y1 / 10) * 10
    w, h = int(np.ceil((x1 - x0) / 10)) + 1, int(np.ceil((y1 - y0) / 10)) + 1
    m = rasterize([(p.geometry, 1)], out_shape=(h, w), transform=from_origin(x0, y1, 10, 10), fill=0, dtype="uint8").astype(bool)
    if not m.any():
        continue
    rr, cc = np.nonzero(m)
    X, Y = x0 + (cc + .5) * 10, y1 - (rr + .5) * 10
    v = np.zeros(len(X), "uint8")
    seen = 0
    for s in t.itertuples():
        k = (X >= s.x0) & (X < s.x0 + s.w * RES) & (Y <= s.y1) & (Y > s.y1 - s.h * RES)
        if not k.any():
            continue
        col, row = ((X[k] - s.x0) / 10).astype(int), ((s.y1 - Y[k]) / 10).astype(int)
        idx = np.flatnonzero(k)
        for (r0, c0) in set(zip(row // CHUNK, col // CHUNK)):
            f = D / f"{s.tile}_{r0 * CHUNK:05d}_{c0 * CHUNK:05d}.npz"
            if not f.exists():
                continue
            a = np.load(f)["cls"]
            q = (row // CHUNK == r0) & (col // CHUNK == c0)
            v[idx[q]] = a[row[q] % CHUNK, col[q] % CHUNK]
            seen += int(q.sum())
    rows.append(dict(id=p.poly_id, cls=p.change_type, ha=p.area_ha, px=len(X), seen=seen, hit=int((v > 0).sum()), hit_clear=int((v == 1).sum()), hit_shrub=int((v == 3).sum())))
d = pd.DataFrame(rows)
d = d[d.seen > .8 * d.px]
d["frac"] = d.hit / d.px
print("polygons inside fetched chunks", len(d), "of", len(g))
print(d.groupby("cls").agg(n=("id", "size"), any_hit=("hit", lambda s: int((s > 0).sum())), ge_25pct=("frac", lambda s: int((s >= .25).sum())), ha=("ha", "sum"), area_cover=("hit", "sum"), px=("px", "sum")).assign(area_cover=lambda x: (100 * x.area_cover / x.px).round(1)).drop(columns="px").round(1).to_string())
