"""Blind stratified sample for the Guna loss-area estimate (owner's methodology v1, 6 Nov).
Strata: map flag (default view, or the new-cropland map) / net fired only (max-recall view) / quiet, x old field in 2017-19 (DW crops dominant) or not,
x distance to 2017-19 farmland (< 200 m, 200-500 m, > 500 m; farmland from DW over whole chunks, inside and outside beats).
draw: writes outputs/final/guna_sample/sample_frame.csv (strata areas) and sample_points.csv (shuffled order, stratum hidden from the label sheets).
Usage: e102_guna_sample.py draw"""
import sys

import numpy as np
import pandas as pd
import rasterio
from rasterio.warp import Resampling, reproject
from scipy import ndimage

from common import *
from e33_map10m import jobs
from e72_map_wide import W
from e97_guna_eval import GD, grid, rd

SD = OUT / "final" / "guna_sample"
NC = OUT / "guna_newcrop"
N_TOTAL = 300
SHARE = {"map flag": .40, "net fired only": .25, "quiet": .35}
MIN_PER = 4
SEED = 20261107


def farmland(tr, shp):
    """2017-19 farmland (DW crops >= trees and shrub) over every chunk pixel, on the Guna 10 m grid."""
    g = np.zeros(shp, bool)
    for s, r, c, h, w, p in jobs():
        f = W / p.name
        if not f.exists():
            continue
        x0, y1 = s.x0 + c * 10, s.y1 - r * 10
        col, row = map(int, ~tr * (x0, y1))
        if row >= shp[0] or col >= shp[1] or row + h <= 0 or col + w <= 0:
            continue
        with np.load(f) as z:
            ec, et, es = (z[k].astype("float32") for k in ("d_ea_c", "d_ea_t", "d_ea_s"))
        fm = (ec >= np.maximum(et, es)) & (ec != -128)
        fm = np.repeat(np.repeat(fm, 3, 0), 3, 1)[:h, :w]
        rs, cs = max(0, -row), max(0, -col)
        re_, ce = min(h, shp[0] - row), min(w, shp[1] - col)
        g[row + rs:row + re_, col + cs:col + ce] |= fm[rs:re_, cs:ce]
    return g


def newcrop(tr, shp):
    out = np.zeros(shp, "int16")
    for f in sorted(NC.glob("newcrop_*.tif")):
        with rasterio.open(f) as s:
            tmp = np.zeros(shp, "int16")
            reproject(s.read(1), tmp, src_transform=s.transform, src_crs=s.crs, dst_transform=tr, dst_crs=PROJ4, resampling=Resampling.nearest)
            np.maximum(out, tmp, out=out)
    return out > 0


def draw():
    SD.mkdir(parents=True, exist_ok=True)
    tr, shp = grid()
    beat = np.load(GD / "guna_beat.npy")
    gm = beat > 0
    a, mx, stock = rd("guna_default"), rd("guna_max_recall"), rd("guna_stock_2017_19")
    flag = (a == 1) | (a == 2) | newcrop(tr, shp)          # our tree loss or the new-cropland map; our scrub-to-farm layer is retired (22% precision)
    net = ~flag & ((mx == 1) | (mx == 2))
    fm = farmland(tr, shp)
    dist = ndimage.distance_transform_edt(~fm) * 10
    lvl = np.where(flag, 0, np.where(net, 1, 2))
    old = (stock == 1).astype(int)
    db = np.digitize(dist, [200, 500])
    code = (lvl * 6 + old * 3 + db).astype("int16")
    code[~gm] = -1
    names = {l * 6 + o * 3 + d: (ln, on, dn) for l, ln in enumerate(SHARE) for o, on in enumerate(("not old field", "old field 2017-19")) for d, dn in enumerate(("< 200 m", "200-500 m", "> 500 m"))}
    cnt = np.bincount(code[gm].ravel(), minlength=18)
    fr = pd.DataFrame([dict(stratum=k, level=v[0], old_field=v[1], dist_farmland=v[2], ha=cnt[k] * .01) for k, v in names.items()])
    # allocation: level share split across its strata by area, at least MIN_PER where the stratum exists
    fr["n"] = 0
    for ln, sh in SHARE.items():
        q = fr[(fr.level == ln) & (fr.ha > 0)]
        n = np.maximum(MIN_PER, np.round(N_TOTAL * sh * q.ha / q.ha.sum())).astype(int)
        fr.loc[q.index, "n"] = n
    rng = np.random.default_rng(SEED)
    pts = []
    for q in fr[fr.n > 0].itertuples():
        rr, cc = np.nonzero(code == q.stratum)
        k = rng.choice(len(rr), size=min(q.n, len(rr)), replace=False)
        for i in k:
            x, y = tr * (cc[i] + .5, rr[i] + .5)
            pts.append(dict(stratum=q.stratum, x=x, y=y, row=int(rr[i]), col=int(cc[i]), zone_id=int(beat[rr[i], cc[i]])))
    p = pd.DataFrame(pts).sample(frac=1, random_state=SEED).reset_index(drop=True)
    p.insert(0, "sid", np.arange(len(p)))
    fr.to_csv(SD / "sample_frame.csv", index=False)
    p.to_csv(SD / "sample_points.csv", index=False)
    print(fr.to_string())
    print("points", len(p))


if __name__ == "__main__":
    {"draw": draw}[sys.argv[1]]()
