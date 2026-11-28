"""Final tables and maps from the 10 m chunks. Pixels are 0.01 ha on the equal-area grid, clipped to beats through the 30 m zone rasters.
Totals are given with and without shrub-to-crop. Usage: e36_state10m.py"""
import json

import geopandas as gpd
import matplotlib
import numpy as np
import pandas as pd
import rasterio

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from common import *
from e33_map10m import CHUNK, D, jobs
from zones import zone as zone_of

CLS = {1: "clearing", 2: "tree_to_shrub", 3: "shrub_to_crop"}
T, M = OUT / "tables_10m", OUT / "maps_10m"
PA = 0.01
CELL = 100          # 1 km display cell in 10 m pixels


def collect():
    t = pd.read_csv(WORK / "tiles.csv", keep_default_na=False).set_index("tile")
    with rasterio.open(WORK / "zone_beat.tif") as s:
        zb = s.read(1)
    with rasterio.open(WORK / "zone_district.tif") as s:
        zd = s.read(1)
    g = json.load(open(WORK / "grid.json"))
    frames = []
    display = np.zeros((9, g["height"] * 3 // CELL + 2, g["width"] * 3 // CELL + 2), "uint32")
    missing = [j for j in jobs() if not j[-1].exists()]
    for f in sorted(D.glob("*.npz")):
        tile, r, c = f.stem.split("_")
        r, c = int(r), int(c)
        s = t.loc[tile]
        a = np.load(f)
        h, w = a["cls"].shape
        rr = np.arange(h) // 3 + s.row + r // 3
        cc = np.arange(w) // 3 + s.col + c // 3
        zz = zb[np.ix_(rr, cc)]
        i = np.nonzero((a["cls"] > 0) & (zz > 0))
        if not len(i[0]):
            continue
        frames.append(pd.DataFrame(dict(zone_id=zz[i], dist_id=zd[np.ix_(rr, cc)][i], cls=a["cls"][i], year=a["yr"][i].astype(int) + 2000)).value_counts().rename("px").reset_index())
        R = (s.row * 3 + r + i[0]) // CELL
        C = (s.col * 3 + c + i[1]) // CELL
        np.add.at(display, (np.clip(a["yr"][i].astype(int) - 17, 0, 8), R, C), 1)
    d = pd.concat(frames).groupby(["zone_id", "dist_id", "cls", "year"], as_index=False).px.sum()
    d["ha"] = d.px * PA
    return d, zb, zd, display, g, missing


def write_tables(d, zb, zd):
    b = gpd.read_parquet(WORK / "beats_albers.parquet")
    dist = gpd.read_parquet(WORK / "districts_albers.parquet")
    d = d.merge(b[["zone_id", "Division", "Range", "Beat"]], on="zone_id", how="left").merge(dist[["dist_id", "dtname"]], on="dist_id", how="left")
    d["dtname"] = d.dtname.fillna("outside_district_layer")
    d["forest_zone"] = d.Division.map(zone_of)
    d["state"] = "Madhya Pradesh"
    d["c"] = d.cls.map(CLS)
    forest = np.bincount(zb.ravel(), minlength=int(b.zone_id.max()) + 1) * PX_HA
    lk = b[["zone_id", "Division", "Range", "Beat"]].assign(forest_ha=forest[b.zone_id.values], forest_zone=b.Division.map(zone_of), state="Madhya Pradesh")
    p = pd.DataFrame(dict(z=zb.ravel(), d=zd.ravel()))
    p = p[p.z > 0].groupby("d").size().rename("n").reset_index().merge(dist[["dist_id", "dtname"]], left_on="d", right_on="dist_id", how="left")
    p["forest_ha"] = p.n * PX_HA
    areas = {"district": p.groupby("dtname", as_index=False).forest_ha.sum()}
    out = {}
    for label, keys in (("state", ["state"]), ("forest_zone", ["forest_zone"]), ("district", ["dtname"]), ("division", ["Division"]), ("range", ["Division", "Range"]), ("beat", ["Division", "Range", "Beat", "zone_id"])):
        w = d.pivot_table(index=keys + ["year"], columns="c", values="ha", aggfunc="sum", fill_value=0).reset_index()
        for c in CLS.values():
            w[c] = w.get(c, 0.0)
        w["total_with_shrub_to_crop"] = w[list(CLS.values())].sum(axis=1)
        w["total_excl_shrub_to_crop"] = w.clearing + w.tree_to_shrub
        w.round(2).to_csv(T / f"loss_by_{label}_year_class.csv", index=False)
        tot = w.groupby(keys)[list(CLS.values()) + ["total_with_shrub_to_crop", "total_excl_shrub_to_crop"]].sum().reset_index()
        area = areas.get(label, lk.groupby(keys, as_index=False).forest_ha.sum())
        tot = area.merge(tot, on=keys, how="left").fillna(0)
        tot["pct_of_forest"] = (100 * tot.total_with_shrub_to_crop / tot.forest_ha.replace(0, np.nan)).round(3)
        tot.sort_values("total_with_shrub_to_crop", ascending=False).round(2).to_csv(T / f"loss_by_{label}_total.csv", index=False)
        out[label] = (w, tot)
    return out, dist, b


def charts(out, display, g, dist, b):
    w = out["state"][0]
    fig, ax = plt.subplots(figsize=(10, 4.8))
    bot = np.zeros(len(w))
    for c, col, lab in (("clearing", "#7f1d1d", "Clearing"), ("tree_to_shrub", "#d97706", "Tree to shrub or thinning"), ("shrub_to_crop", "#65a30d", "Shrub to crop")):
        ax.bar(w.year, w[c], bottom=bot, color=col, label=lab, edgecolor="white", linewidth=.5)
        bot += w[c].values
    ax.set_xticks(w.year)
    ax.set_ylabel("Hectares")
    ax.set_title("Madhya Pradesh recorded forest: mapped loss by year (year of change is approximate)")
    ax.yaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda v, _: f"{v:,.0f}"))
    ax.spines[["top", "right"]].set_visible(False)
    ax.legend(frameon=False, loc="upper left", bbox_to_anchor=(1.0, 1.0))
    fig.tight_layout()
    fig.savefig(M / "state_loss_by_year.png", dpi=170)
    plt.close(fig)
    for label, gdf, key in (("district", dist, "dtname"), ("division", b[["Division", "geometry"]].dissolve("Division").reset_index(), "Division")):
        m = gdf.merge(out[label][1], on=key, how="left")
        for col, title in (("total_with_shrub_to_crop", "ha"), ("pct_of_forest", "% of recorded forest")):
            fig, ax = plt.subplots(figsize=(10, 7))
            m.plot(column=col, cmap="YlOrRd", legend=True, ax=ax, linewidth=.25, edgecolor="#555", legend_kwds=dict(shrink=.6, label=title), missing_kwds=dict(color="#eee"))
            ax.set_title(f"Mapped forest loss 2018-2025 by {label} ({title})")
            ax.set_axis_off()
            fig.tight_layout()
            fig.savefig(M / f"{label}_{col}.png", dpi=170)
            plt.close(fig)
    ext = [g["x0"], g["x0"] + display.shape[2] * CELL * 10, g["y1"] - display.shape[1] * CELL * 10, g["y1"]]
    outline = b[["Division", "geometry"]].dissolve("Division").boundary
    fig, axes = plt.subplots(2, 4, figsize=(16, 8))
    v = np.percentile(display[display > 0], 99) * PA
    for a, i in zip(axes.ravel(), range(1, 9)):
        outline.plot(ax=a, color="#ccc", linewidth=.15)
        a.imshow(np.where(display[i] > 0, display[i] * PA, np.nan), extent=ext, cmap="inferno_r", vmin=0, vmax=v, interpolation="nearest")
        a.set_title(f"{2017 + i}: {display[i].sum() * PA:,.0f} ha", fontsize=11)
        a.set_axis_off()
    fig.suptitle("Mapped loss per year, ha per 100 ha display cell", fontsize=14)
    fig.tight_layout()
    fig.savefig(M / "loss_small_multiples.png", dpi=170)
    plt.close(fig)


def main():
    T.mkdir(parents=True, exist_ok=True)
    M.mkdir(parents=True, exist_ok=True)
    d, zb, zd, display, g, missing = collect()
    if missing:
        print("WARNING chunks still missing:", len(missing))
    out, dist, b = write_tables(d, zb, zd)
    charts(out, display, g, dist, b)
    for k in ("state", "forest_zone"):
        print(out[k][1].round(1).to_string(index=False))
    print(out["state"][0].round(0).to_string(index=False))
    for k in ("district", "division", "range", "beat"):
        print(out[k][1].sort_values("total_with_shrub_to_crop", ascending=False).head(6).round(1).to_string(index=False))


if __name__ == "__main__":
    main()
