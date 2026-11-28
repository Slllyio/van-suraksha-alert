"""Which 10 m chunks are finished: forest covered per division and district, plus a coverage map. Read-only on the run. Usage: e41_coverage.py"""
import geopandas as gpd
import matplotlib
import numpy as np
import pandas as pd
import rasterio

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from common import *
from e33_map10m import D


def main():
    t = pd.read_csv(WORK / "tiles.csv", keep_default_na=False).set_index("tile")
    with rasterio.open(WORK / "zone_beat.tif") as s:
        zb = s.read(1)
    with rasterio.open(WORK / "zone_district.tif") as s:
        zd = s.read(1)
    done = np.zeros(zb.shape, bool)
    files = sorted(D.glob("*.npz"))
    for f in files:
        tile, r, c = f.stem.split("_")
        r, c = int(r), int(c)
        s = t.loc[tile]
        done[s.row + r // 3:s.row + (r + 900) // 3, s.col + c // 3:s.col + (c + 900) // 3] = True
    b = gpd.read_parquet(WORK / "beats_albers.parquet")
    dist = gpd.read_parquet(WORK / "districts_albers.parquet")
    n = int(b.zone_id.max()) + 1
    fa, fd = np.bincount(zb.ravel(), minlength=n) * PX_HA, np.bincount(zb[done], minlength=n) * PX_HA
    z = pd.DataFrame(dict(zone_id=np.arange(n), forest_ha=fa, done_ha=fd)).merge(b[["zone_id", "Division", "Range"]], on="zone_id")
    dv = z.groupby("Division", as_index=False)[["forest_ha", "done_ha"]].sum()
    dv["pct"] = (100 * dv.done_ha / dv.forest_ha).round(1)
    m = zb > 0
    m2 = np.bincount(zd[m], minlength=len(dist) + 2) * PX_HA
    d2 = np.bincount(zd[m & done], minlength=len(dist) + 2) * PX_HA
    dt = dist[["dist_id", "dtname"]].assign(forest_ha=lambda x: m2[x.dist_id], done_ha=lambda x: d2[x.dist_id])
    dt["pct"] = (100 * dt.done_ha / dt.forest_ha.replace(0, np.nan)).round(1)
    dv.sort_values("pct", ascending=False).round(1).to_csv(OUT / "coverage_divisions.csv", index=False)
    dt.sort_values("pct", ascending=False).round(1).to_csv(OUT / "coverage_districts.csv", index=False)
    print("chunks", len(files), "forest done ha", round(dv.done_ha.sum()), "of", round(dv.forest_ha.sum()), "pct", round(100 * dv.done_ha.sum() / dv.forest_ha.sum(), 1))
    for name, tb, key in (("Divisions", dv, "Division"), ("Districts", dt.dropna(subset=["pct"]), "dtname")):
        full, part, none = tb[tb.pct >= 99.5], tb[(tb.pct > 0) & (tb.pct < 99.5)].sort_values("pct", ascending=False), tb[tb.pct == 0]
        print(name, "full", len(full), "partly", len(part), "none", len(none))
        print(" FULL:", ", ".join(full[key]))
        print(" PART:", ", ".join(f"{a} {p:.0f}%" for a, p in zip(part[key], part.pct)))
        print(" NONE:", ", ".join(none[key]))
    # coarse raster display: 300 m cells; green = recorded forest finished, grey = recorded forest not yet
    k = 10
    h, w = zb.shape[0] // k, zb.shape[1] // k
    fo = m[:h * k, :w * k].reshape(h, k, w, k).any(axis=(1, 3))
    dn = (m & done)[:h * k, :w * k].reshape(h, k, w, k).any(axis=(1, 3))
    import json
    g = json.load(open(WORK / "grid.json"))
    ext = [g["x0"], g["x0"] + w * k * RES, g["y1"] - h * k * RES, g["y1"]]
    img = np.ones((h, w, 3))
    img[fo] = (.82, .82, .82)
    img[dn] = (.13, .55, .30)
    fig, ax = plt.subplots(figsize=(11, 7.5))
    ax.imshow(img, extent=ext, interpolation="nearest")
    b[["Division", "geometry"]].dissolve("Division").boundary.plot(ax=ax, color="#333", linewidth=.3)
    ax.set_title(f"10 m forest loss run: {len(files)} chunks finished, {100 * dv.done_ha.sum() / dv.forest_ha.sum():.0f}% of recorded forest (green done, grey not yet)")
    ax.set_axis_off()
    fig.tight_layout()
    fig.savefig(OUT / "coverage_progress.png", dpi=130)
    print("saved", OUT / "coverage_progress.png")


if __name__ == "__main__":
    main()
