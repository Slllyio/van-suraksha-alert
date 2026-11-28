"""Year x class x recovery tables at state/district/division/range/beat level, then charts and maps.
Every pixel is 0.09 ha on the equal-area grid. Usage: 06_stats_maps.py"""
import json

import geopandas as gpd
import matplotlib
import numpy as np
import pandas as pd
import rasterio

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from common import *
from zones import zone as zone_of

REPORT_YEARS = list(range(2018, 2026))   # first detectable year from AlphaEarth (2017 baseline) to the latest

CLS = {1: "clearing", 2: "degradation", 3: "small_lowconf"}
REC = {1: "recovered", 2: "persistent", 3: "unknown"}
T, M = OUT / "tables", OUT / "maps"
T.mkdir(parents=True, exist_ok=True)
M.mkdir(parents=True, exist_ok=True)


def cause_hint(division):
    """Cheap, name-based: project/FDC divisions are MPRVVN production plantations."""
    n = division.lower()
    return "mprvvn_plantation" if ("proj" in n or "fdc" in n) else "other"


def long_table():
    """One row per (beat, district, year, class, recovery, burned, hansen) with pixel counts."""
    c = np.load(WORK / "classified.npz")
    yod, cls, rec, burned, hans = c["yod"], c["cls"], c["rec"], c["burned"], c["hansen"]
    with rasterio.open(WORK / "zone_beat.tif") as s:
        zb = s.read(1)
    with rasterio.open(WORK / "zone_district.tif") as s:
        zd = s.read(1)
    i = np.nonzero(yod)
    df = pd.DataFrame(dict(zone_id=zb[i], dist_id=zd[i], year=yod[i], cls=cls[i], rec=rec[i], burned=burned[i], hansen=hans[i]))
    g = df.groupby(list(df.columns)).size().rename("px").reset_index()
    g["ha"] = g.px * PX_HA
    forest_px = np.bincount(zb[zb > 0], minlength=int(zb.max()) + 1)
    pairs = pd.DataFrame(dict(zone_id=zb[zb > 0], dist_id=zd[zb > 0])).value_counts().rename("px").reset_index()
    return g, forest_px, pairs


def pivot(g, keys, area, label):
    """ha per year x class x recovery, plus totals and share of the recorded forest area."""
    g = g.assign(col=g.cls.map(CLS) + "_" + g.rec.map(REC))
    long = g.groupby(keys + ["year", "col"]).ha.sum().reset_index()
    wide = long.pivot_table(index=keys + ["year"], columns="col", values="ha", fill_value=0).reset_index()
    for c in [f"{a}_{b}" for a in CLS.values() for b in REC.values()]:
        wide[c] = wide.get(c, 0.0)
    wide["small_lowconf_ha"] = wide[[f"small_lowconf_{b}" for b in REC.values()]].sum(axis=1)
    wide["total_ha"] = wide[[f"{a}_{b}" for a in ("clearing", "degradation") for b in REC.values()]].sum(axis=1)  # small patches apart
    wide["clearing_ha"] = wide[[f"clearing_{b}" for b in REC.values()]].sum(axis=1)
    wide["degradation_ha"] = wide[[f"degradation_{b}" for b in REC.values()]].sum(axis=1)
    wide = wide.round(2)
    wide.to_csv(T / f"loss_by_{label}_year_class.csv", index=False)
    tot = wide.groupby(keys)[["total_ha", "clearing_ha", "degradation_ha", "clearing_persistent", "small_lowconf_ha"]].sum().reset_index()
    if area is not None:
        tot = tot.merge(area, on=keys, how="right").fillna(0)
        tot["loss_pct_of_forest"] = (100 * tot.total_ha / tot.forest_ha).round(3)
    tot.sort_values("total_ha", ascending=False).round(2).to_csv(T / f"loss_by_{label}_total.csv", index=False)
    return wide, tot


def main():
    b = gpd.read_parquet(WORK / "beats_albers.parquet")
    dist = gpd.read_parquet(WORK / "districts_albers.parquet")
    g, forest_px, pairs = long_table()
    lk = b[["zone_id", "Division", "Range", "Beat"]]
    g = g.merge(lk, on="zone_id", how="left").merge(dist[["dist_id", "dtname"]], on="dist_id", how="left")
    g["dtname"] = g.dtname.fillna("outside_district_layer")
    z = pd.DataFrame(dict(zone_id=np.arange(len(forest_px)), forest_ha=forest_px * PX_HA)).merge(lk, on="zone_id")
    p = pairs.merge(dist[["dist_id", "dtname"]], on="dist_id", how="left")
    p["forest_ha"] = p.px * PX_HA
    p["dtname"] = p.dtname.fillna("outside_district_layer")

    g["state"] = "Madhya Pradesh"
    state, _ = pivot(g, ["state"], None, "state")
    state.to_csv(T / "loss_by_state_year_class.csv", index=False)
    _, dt = pivot(g, ["dtname"], p.groupby("dtname", as_index=False).forest_ha.sum(), "district")
    _, dv = pivot(g, ["Division"], z.groupby("Division", as_index=False).forest_ha.sum(), "division")
    _, rg = pivot(g, ["Division", "Range"], z.groupby(["Division", "Range"], as_index=False).forest_ha.sum(), "range")
    _, bt = pivot(g, ["Division", "Range", "Beat", "zone_id"], z[["Division", "Range", "Beat", "zone_id", "forest_ha"]], "beat")

    g["forest_zone"] = g.Division.map(zone_of)
    zz = z.assign(forest_zone=z.Division.map(zone_of)).groupby("forest_zone", as_index=False).forest_ha.sum()
    pivot(g, ["forest_zone"], zz, "forest_zone")

    # Cause hints and comparison with Hansen; hints are attributes, not attributions
    g["plantation_div"] = g.Division.map(cause_hint)
    g = g[g.cls != 3]
    hints = g.groupby(["year"]).apply(lambda x: pd.Series(dict(
        total_ha=x.ha.sum(), burned_ha=x.ha[x.burned == 1].sum(), plantation_division_ha=x.ha[x.plantation_div != "other"].sum(),
        hansen_overlap_ha=x.ha[x.hansen == 1].sum()))).round(1).reset_index()
    hints.to_csv(T / "cause_hints_by_year.csv", index=False)

    charts(state, hints)
    maps(dist, dt, b, dv)
    return state, dt, dv, bt


def charts(state, hints):
    fig, ax = plt.subplots(figsize=(9, 4.6))
    cols = [("clearing_persistent", "#7f1d1d", "Clearing, persistent"), ("clearing_recovered", "#dc2626", "Clearing, recovered"),
            ("clearing_unknown", "#fca5a5", "Clearing, recovery unknown"), ("degradation_persistent", "#92400e", "Degradation, persistent"),
            ("degradation_recovered", "#d97706", "Degradation, recovered"), ("degradation_unknown", "#fcd34d", "Degradation, recovery unknown")]
    bottom = np.zeros(len(state))
    for c, col, lab in cols:
        ax.bar(state.year, state[c], bottom=bottom, color=col, label=lab, edgecolor="white", linewidth=0.5)
        bottom += state[c].values
    ax.set_xticks(state.year)
    ax.set_ylabel("Hectares")
    ax.set_title("Madhya Pradesh recorded forest: loss mapped per year, 2018-2025 (not area-corrected)")
    ax.yaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda v, _: f"{v:,.0f}"))
    ax.spines[["top", "right"]].set_visible(False)
    ax.legend(frameon=False, fontsize=8, loc="upper left", bbox_to_anchor=(1.0, 1.0))
    fig.tight_layout()
    fig.savefig(M / "state_loss_by_year.png", dpi=170)
    plt.close(fig)


def choropleth(gdf, col, title, path, cmap="YlOrRd"):
    fig, ax = plt.subplots(figsize=(10, 7))
    gdf.plot(column=col, cmap=cmap, legend=True, ax=ax, linewidth=0.25, edgecolor="#555",
             legend_kwds=dict(shrink=0.6, label=col), missing_kwds=dict(color="#eee"))
    ax.set_title(title)
    ax.set_axis_off()
    fig.tight_layout()
    fig.savefig(path, dpi=170)
    plt.close(fig)


def maps(dist, dt, beats, dv):
    choropleth(dist.merge(dt, on="dtname", how="left"), "total_ha", "Forest loss 2018-2025 by district (ha)", M / "district_loss_map.png")
    div = beats[["Division", "geometry"]].dissolve("Division").reset_index().merge(dv, on="Division", how="left")
    choropleth(div, "total_ha", "Forest loss 2018-2025 by forest division (ha)", M / "division_loss_map.png")
    choropleth(div, "loss_pct_of_forest", "Forest loss 2018-2025 as % of division forest", M / "division_loss_pct_map.png")
    raster_maps(div)


def raster_maps(div, factor=30):
    """Year-of-loss map and per-year small multiples. Each 900 m display cell shows the year with most loss inside it."""
    c = np.load(WORK / "classified.npz")
    yod = c["yod"]
    g = json.load(open(WORK / "grid.json"))
    h, w = yod.shape[0] // factor, yod.shape[1] // factor
    counts = np.stack([np.add.reduce(np.add.reduce((yod[:h * factor, :w * factor] == y).reshape(h, factor, w, factor), 1), 2)
                       for y in REPORT_YEARS])
    ext = [g["x0"], g["x0"] + w * factor * RES, g["y1"] - h * factor * RES, g["y1"]]
    outline = div.boundary
    top = np.where(counts.sum(0) > 0, counts.argmax(0) + REPORT_YEARS[0], np.nan)
    fig, ax = plt.subplots(figsize=(12, 8.5))
    outline.plot(ax=ax, color="#bbb", linewidth=0.3)
    im = ax.imshow(top, extent=ext, cmap="turbo", vmin=REPORT_YEARS[0], vmax=REPORT_YEARS[-1], interpolation="nearest")
    fig.colorbar(im, ax=ax, shrink=0.6, label="Year of largest loss in cell", ticks=REPORT_YEARS)
    ax.set_title("Year of forest loss")
    ax.set_axis_off()
    fig.tight_layout()
    fig.savefig(M / "year_of_loss_map.png", dpi=190)
    plt.close(fig)
    fig, axes = plt.subplots(2, 4, figsize=(16, 8))
    vmax = np.percentile(counts[counts > 0], 99) * PX_HA
    for a, y, k in zip(axes.ravel(), REPORT_YEARS, counts):
        outline.plot(ax=a, color="#ccc", linewidth=0.15)
        a.imshow(np.where(k > 0, k * PX_HA, np.nan), extent=ext, cmap="inferno_r", vmin=0, vmax=vmax, interpolation="nearest")
        a.set_title(f"{y}: {k.sum() * PX_HA:,.0f} ha", fontsize=11)
        a.set_axis_off()
    fig.suptitle("Forest loss per year, ha per 81 ha display cell", fontsize=14)
    fig.tight_layout()
    fig.savefig(M / "loss_small_multiples.png", dpi=170)
    plt.close(fig)


if __name__ == "__main__":
    state, dt, dv, bt = main()
    print(state[["year", "clearing_ha", "degradation_ha", "total_ha"]].to_string(index=False))
    print(dt.sort_values("total_ha", ascending=False).head(10).to_string(index=False))
    print(dv.sort_values("total_ha", ascending=False).head(10).to_string(index=False))
    print(bt.sort_values("total_ha", ascending=False).head(10).to_string(index=False))
