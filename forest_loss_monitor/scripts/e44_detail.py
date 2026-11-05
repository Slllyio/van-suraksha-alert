"""Detailed interim outputs from finished chunks, no GEE: beat table, largest patches with coordinates, charts and maps, an Excel workbook.
Usage: e44_detail.py"""
import json

import geopandas as gpd
import matplotlib
import numpy as np
import pandas as pd
import rasterio
from pyproj import Transformer
from scipy import ndimage

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from common import *
from zones import zone as zone_of

D = WORK / "map10m"
I = OUT / "interim"
CLS = {1: "clearing", 2: "tree_to_shrub", 3: "shrub_to_crop"}
COL = {"clearing": "#7f1d1d", "tree_to_shrub": "#d97706", "shrub_to_crop": "#65a30d"}
PA = 0.01
CELL = 100


def main():
    t = pd.read_csv(WORK / "tiles.csv", keep_default_na=False).set_index("tile")
    g = json.load(open(WORK / "grid.json"))
    with rasterio.open(WORK / "zone_beat.tif") as s:
        zb = s.read(1)
    b = gpd.read_parquet(WORK / "beats_albers.parquet")
    lk = b.set_index("zone_id")[["Division", "Range", "Beat"]]
    done = np.zeros(zb.shape, bool)
    disp = np.zeros((9, g["height"] * 3 // CELL + 2, g["width"] * 3 // CELL + 2), "uint32")
    clsdisp = np.zeros((4,) + disp.shape[1:], "uint32")
    rows, patches = [], []
    tr = Transformer.from_crs(PROJ4, "EPSG:4326", always_xy=True)
    for f in sorted(D.glob("*.npz")):
        tile, r, c = f.stem.split("_")
        r, c = int(r), int(c)
        s = t.loc[tile]
        a = np.load(f)
        h, w = a["cls"].shape
        done[s.row + r // 3:s.row + (r + h) // 3, s.col + c // 3:s.col + (c + w) // 3] = True
        rr, cc = np.arange(h) // 3 + s.row + r // 3, np.arange(w) // 3 + s.col + c // 3
        zz = zb[np.ix_(rr, cc)]
        hit = (a["cls"] > 0) & (zz > 0)
        i = np.nonzero(hit)
        if not len(i[0]):
            continue
        rows.append(pd.DataFrame(dict(zone_id=zz[i], cls=a["cls"][i], year=a["yr"][i].astype(int) + 2000)).value_counts().rename("px").reset_index())
        R, C = (s.row * 3 + r + i[0]) // CELL, (s.col * 3 + c + i[1]) // CELL
        np.add.at(disp, (np.clip(a["yr"][i].astype(int) - 17, 0, 8), R, C), 1)
        np.add.at(clsdisp, (a["cls"][i], R, C), 1)
        lab, n = ndimage.label(hit, structure=np.ones((3, 3), bool))
        if not n:
            continue
        idx = np.arange(1, n + 1)
        size = ndimage.sum_labels(hit, lab, idx)
        for j in idx[size >= 50]:            # at least 0.5 ha within this chunk
            p, q = np.nonzero(lab == j)
            x, y = s.x0 + (c + q.mean() + .5) * 10, s.y1 - (r + p.mean() + .5) * 10
            lon, lat = tr.transform(x, y)
            k = a["cls"][p, q]
            yr = a["yr"][p, q].astype(int) + 2000
            z0 = np.bincount(zz[p, q]).argmax()
            cnt = np.bincount(k, minlength=4)
            patches.append(dict(ha=round(len(p) * PA, 2), year_mode=int(np.bincount(yr).argmax()), main_class=CLS[int(cnt[1:].argmax()) + 1], clearing_ha=round(cnt[1] * PA, 2), tree_to_shrub_ha=round(cnt[2] * PA, 2),
                                shrub_to_crop_ha=round(cnt[3] * PA, 2), lat=round(lat, 6), lon=round(lon, 6), Division=lk.Division.get(z0, ""), Range=lk.Range.get(z0, ""), Beat=lk.Beat.get(z0, "")))
    d = pd.concat(rows).groupby(["zone_id", "cls", "year"], as_index=False).px.sum()
    d["ha"] = d.px * PA
    d["c"] = d.cls.map(CLS)
    d = d.merge(lk.reset_index(), on="zone_id")
    n = int(b.zone_id.max()) + 1
    fa, ca = np.bincount(zb.ravel(), minlength=n) * PX_HA, np.bincount(zb[done], minlength=n) * PX_HA
    bt = d.pivot_table(index=["zone_id", "Division", "Range", "Beat"], columns="c", values="ha", aggfunc="sum", fill_value=0).reset_index()
    for c in CLS.values():
        bt[c] = bt.get(c, 0.0)
    bt["total"] = bt[list(CLS.values())].sum(axis=1)
    bt["beat_forest_ha"] = fa[bt.zone_id]
    bt["covered_ha"] = ca[bt.zone_id]
    bt["coverage_pct"] = (100 * bt.covered_ha / bt.beat_forest_ha.replace(0, np.nan)).round(1)
    bt["rate_pct_of_covered"] = (100 * bt.total / bt.covered_ha.replace(0, np.nan)).round(3)
    yy = d.pivot_table(index="zone_id", columns="year", values="ha", aggfunc="sum", fill_value=0).add_prefix("y")
    bt = bt.merge(yy, on="zone_id").sort_values("total", ascending=False).round(2)
    bt.to_csv(I / "interim_by_beat_total.csv", index=False)
    pt = pd.DataFrame(patches).sort_values("ha", ascending=False)
    pt.to_csv(I / "interim_patches_over_half_ha.csv", index=False)
    print("patches >=0.5 ha", len(pt), "ha", round(pt.ha.sum()), "share of mapped", round(pt.ha.sum() / d.ha.sum(), 3), "size quantiles", pt.ha.quantile([.5, .9, .99]).round(1).to_dict(), "beats with loss", len(bt))
    print(pt.head(12).to_string(index=False))
    print(bt.head(12)[["Division", "Range", "Beat", "total", "clearing", "tree_to_shrub", "shrub_to_crop", "coverage_pct", "rate_pct_of_covered"]].to_string(index=False))
    charts(d, disp, clsdisp, g, b, done, zb)
    book(bt, pt)


def charts(d, disp, clsdisp, g, b, done, zb):
    ext = [g["x0"], g["x0"] + disp.shape[2] * CELL * 10, g["y1"] - disp.shape[1] * CELL * 10, g["y1"]]
    outline = b[["Division", "geometry"]].dissolve("Division").boundary
    k = 10
    h, w = zb.shape[0] // k, zb.shape[1] // k
    cov = (done & (zb > 0))[:h * k, :w * k].reshape(h, k, w, k).any(axis=(1, 3))
    gext = [g["x0"], g["x0"] + w * k * RES, g["y1"] - h * k * RES, g["y1"]]
    y = d.pivot_table(index="year", columns="c", values="ha", aggfunc="sum", fill_value=0).reset_index()
    fig, ax = plt.subplots(figsize=(9, 4.2))
    bot = np.zeros(len(y))
    for c in CLS.values():
        ax.bar(y.year, y[c], bottom=bot, color=COL[c], label=c.replace("_", " "), edgecolor="white", linewidth=.5)
        bot += y[c].values
    ax.set_xticks(y.year)
    ax.set_ylabel("Hectares, finished chunks only")
    ax.spines[["top", "right"]].set_visible(False)
    ax.yaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda v, _: f"{v:,.0f}"))
    ax.legend(frameon=False, loc="upper left", bbox_to_anchor=(1, 1))
    fig.tight_layout()
    fig.savefig(I / "by_year_class.png", dpi=130)
    plt.close(fig)
    base = np.ones((h, w, 3))
    base[cov] = (.88, .88, .88)
    fig, axes = plt.subplots(2, 4, figsize=(15, 7.2))
    v = max(np.percentile(disp[disp > 0], 99) * PA, .1)
    for a, i in zip(axes.ravel(), range(1, 9)):
        a.imshow(base, extent=gext, interpolation="nearest")
        a.imshow(np.where(disp[i] > 0, disp[i] * PA, np.nan), extent=ext, cmap="inferno_r", vmin=0, vmax=v, interpolation="nearest")
        a.set_title(f"{2017 + i}: {disp[i].sum() * PA:,.0f} ha", fontsize=11)
        a.set_axis_off()
    fig.tight_layout()
    fig.savefig(I / "by_year_maps.png", dpi=110)
    plt.close(fig)
    fig, axes = plt.subplots(1, 3, figsize=(15, 4.2))
    for a, (i, c) in zip(axes, CLS.items()):
        a.imshow(base, extent=gext, interpolation="nearest")
        a.imshow(np.where(clsdisp[i] > 0, clsdisp[i] * PA, np.nan), extent=ext, cmap="inferno_r", vmin=0, vmax=v, interpolation="nearest")
        a.set_title(f"{c.replace('_', ' ')}: {clsdisp[i].sum() * PA:,.0f} ha", fontsize=11)
        a.set_axis_off()
    fig.tight_layout()
    fig.savefig(I / "by_class_maps.png", dpi=110)
    plt.close(fig)


def book(bt, pt):
    with pd.ExcelWriter(I / "forest_loss_interim_detailed.xlsx") as x:
        for lab in ("state", "forest_zone", "district", "division", "range"):
            pd.read_csv(I / f"interim_by_{lab}_total.csv").to_excel(x, sheet_name=f"{lab}_total"[:31], index=False)
            pd.read_csv(I / f"interim_by_{lab}_year_class.csv").to_excel(x, sheet_name=f"{lab}_year"[:31], index=False)
        bt.drop(columns="zone_id").to_excel(x, sheet_name="beat_total", index=False)
        pt.to_excel(x, sheet_name="patches_over_half_ha", index=False)
    print("workbook written")


if __name__ == "__main__":
    main()
