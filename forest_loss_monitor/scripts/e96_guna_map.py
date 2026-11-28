"""Guna division map from stored data, no GEE: 10 m rasters over the division for three views (class code 1 clearing, 2 tree-to-shrub, 3 scrub-to-farm, 9 flooded/masked; 0 none),
loss year, and context layers (2017-19 crop-dominant and bare/very low Oct-Nov NDVI), plus patches. Rates use full beat area. Usage: e96_guna_map.py"""
import json

import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio
from rasterio.features import shapes
from rasterio.transform import from_origin
from scipy import ndimage
from shapely.geometry import shape

from common import *
from e33_map10m import jobs
from e72_map_wide import W
from e79_views import STRUCT, inputs, net, net90, scrub, view
from e84_patches import FLOOD_SHARE, flooded_px
from e87_interim_v2 import pixel_series
from e91_final import MIN_PX, VIEWS
from e98_dw_year import OUTD as DWY, loss_year

GD = WORK / "guna"
DIV = "Guna"


def main():
    GD.mkdir(exist_ok=True)
    b = pd.read_csv(OUT / "beat_lookup.csv")
    ids = b[b.Division == DIV].zone_id.values
    with rasterio.open(WORK / "zone_beat.tif") as src:
        zb = src.read(1)
    g = json.load(open(WORK / "grid.json"))
    gm = np.isin(zb, ids)
    rows, cols = np.nonzero(gm)
    r0, r1, c0, c1 = rows.min(), rows.max() + 1, cols.min(), cols.max() + 1
    H, Wd = (r1 - r0) * 3, (c1 - c0) * 3
    X0, Y1 = g["x0"] + c0 * RES, g["y1"] - r0 * RES
    out = {v: np.zeros((H, Wd), "uint8") for v in VIEWS}
    year = np.zeros((H, Wd), "int16")      # DW year (trees < 0.30 after >= 0.30); falls back to the attributes below where DW gives none
    ybrk = np.zeros((H, Wd), "int16")      # fitted break - 1
    ycrop = np.zeros((H, Wd), "int16")     # first winter-crop year (scrub-to-farm)
    stock = np.zeros((H, Wd), "uint8")      # 1 crop-dominant 2017-19, 2 bare or built-like (Oct-Nov NDVI < 0.2 in 2017-19)
    have = np.zeros((H, Wd), bool)
    t = pd.read_csv(WORK / "tiles.csv", keep_default_na=False).set_index("tile")
    js = [j for j in jobs() if gm[j[0].row + j[1] // 3:j[0].row + (j[1] + 900) // 3, j[0].col + j[2] // 3:j[0].col + (j[2] + 900) // 3].any()]
    missing = missing_dw = 0
    for j in js:
        f = W / j[5].name
        if not f.exists():
            missing += 1
            continue
        s, r, c = j[0], j[1], j[2]
        a = np.load(f)
        h, w = a["y_ln2020"].shape
        zz = zb[np.ix_(np.arange(h) // 3 + s.row + r // 3, np.arange(w) // 3 + s.col + c // 3)]
        inside = np.isin(zz, ids)
        d = inputs(a)
        sc0 = scrub(f.name, None)
        sc = (sc0 if sc0 is not None else np.zeros((h, w), bool)) & inside
        tree = net(d) & inside
        wide = tree | sc
        n90 = (net90(a, d, wide) & inside) | sc
        ps = pixel_series(a, n90)
        conv = np.nanmax(np.stack([d["la_c"], d["la_b"], d["la_u"]]), 0) >= np.nanmax(np.stack([d["la_t"], d["la_s"]]), 0)
        fl = flooded_px(a)
        sy = np.load(WORK / "map10m_s2f" / f.name)["y"].astype("int16") + 2000 if sc0 is not None else np.zeros((h, w), "int16")
        dwf = DWY / f.name
        dy = np.repeat(np.repeat(loss_year(np.load(dwf)["t"]), 3, 0), 3, 1)[:h, :w] if dwf.exists() else np.zeros((h, w), "int16")
        missing_dw += not dwf.exists()
        # window in the Guna grid
        gr, gc = (s.row * 3 + r) - r0 * 3, (s.col * 3 + c) - c0 * 3
        rs, cs = max(0, -gr), max(0, -gc)
        re_, ce = min(h, H - gr), min(w, Wd - gc)
        if re_ <= rs or ce <= cs:
            continue
        sl_g = (slice(gr + rs, gr + re_), slice(gc + cs, gc + ce))
        sl_c = (slice(rs, re_), slice(cs, ce))
        have[sl_g] |= inside[sl_c]
        early_n = np.nanmean(np.stack([np.where(a[f"y_ln{y}"] == -128, np.nan, a[f"y_ln{y}"] / 100) for y in (2017, 2018, 2019)]), 0)
        st = np.where(inside & (d["ea_c"] >= np.maximum(d["ea_t"], d["ea_s"])), 1, np.where(inside & (early_n < .2) & (d["water"] == 0), 2, 0)).astype("uint8")
        stock[sl_g] = np.maximum(stock[sl_g], st[sl_c])
        for vn, (kind, fn, fr, npx) in VIEWS.items():
            cand = wide if kind == "wide" else n90
            ok = view(cand, ps["nf"], ps["rf"], fn, fr, npx, 0) | sc
            ok = view(ok, ps["nf"], ps["rf"], 0, 0, 1, MIN_PX)
            code = np.where(ok & sc & ~tree, 3, np.where(ok & conv, 1, np.where(ok, 2, 0))).astype("uint8")
            lab, k = ndimage.label(ok, structure=STRUCT)
            if k:
                share = ndimage.mean(fl, lab, np.arange(1, k + 1))
                fl_patch = np.r_[False, share >= FLOOD_SHARE][lab]
                code[fl_patch] = 9
            out[vn][sl_g] = np.maximum(out[vn][sl_g], code[sl_c])
            if vn == "default":
                yb = np.where(np.isfinite(ps["brk"]) & (ps["brk"] > 0), ps["brk"] - 1, 0).astype("int16")
                yr = np.where(dy > 0, dy, np.where(code == 3, sy, yb)).astype("int16")
                hit = code[sl_c] > 0
                year[sl_g] = np.where(hit, yr[sl_c], year[sl_g])
                ybrk[sl_g] = np.where(hit, yb[sl_c], ybrk[sl_g])
                ycrop[sl_g] = np.where(hit & (code[sl_c] == 3), sy[sl_c], ycrop[sl_g])
    prof = dict(driver="GTiff", height=H, width=Wd, count=1, crs=PROJ4, transform=from_origin(X0, Y1, 10, 10), compress="deflate")
    for vn, arr in out.items():
        with rasterio.open(GD / f"guna_{vn}.tif", "w", dtype="uint8", **prof) as dst:
            dst.write(arr, 1)
    for nm, arr, dt in (("guna_year", year, "int16"), ("guna_year_break", ybrk, "int16"), ("guna_year_crop", ycrop, "int16"), ("guna_stock_2017_19", stock, "uint8"), ("guna_covered", have.astype("uint8"), "uint8")):
        with rasterio.open(GD / f"{nm}.tif", "w", dtype=dt, **prof) as dst:
            dst.write(arr, 1)
    beat = np.repeat(np.repeat(zb[r0:r1, c0:c1], 3, 0), 3, 1)
    np.save(GD / "guna_beat.npy", np.where(np.isin(beat, ids), beat, 0).astype("int32"))
    print("Guna chunks", len(js), "missing", missing, "no DW year", missing_dw, "covered share of Guna forest", round(float(have.sum() / max(np.isin(beat, ids).sum(), 1)), 3))
    for vn, arr in out.items():
        print(vn, {k: round(float((arr == k).sum()) * .01, 1) for k in (1, 2, 3, 9)})


if __name__ == "__main__":
    main()
