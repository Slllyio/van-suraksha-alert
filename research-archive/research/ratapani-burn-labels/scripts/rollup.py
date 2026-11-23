"""Turn per-season burn maps into 500 m cell labels, a clear-sky calendar and GeoTIFFs.

Outputs in <outdir>:
  burn_windows.csv    season, cell_id, window_start, window_end, burned_ha, burned (>= 0.5 ha)
                      window_start = last clear look before the scar (not burned then),
                      window_end   = first clear look showing the scar. Burn date is in (start, end].
  clear_calendar.csv  season, date, cell_id, clear_frac   (share of the cell's eligible 20 m pixels
                      seen clear that day; lets a model know which cells were checked and unburned)
  cell_season.csv     season, cell_id, burned_ha_total, first_window_start, first_window_end
  burn_<season>.tif   20 m GeoTIFF, EPSG:32643: band 1 window_end day-of-year, band 2 window_start
                      day-of-year (negative = December), band 3 NBR-anomaly drop x1000; -999 = none
Usage: python rollup.py <obsroot> <burndir> <outdir>
"""
import os, sys, glob, datetime as dt
import numpy as np, pandas as pd, geopandas as gpd, rasterio
from rasterio.features import rasterize

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fetch, detect

PX_HA = fetch.RES * fetch.RES / 1e4
MIN_HA = 0.5


def cell_raster():
    g = gpd.read_file("/mnt/project-files/ratapani/grid_500m.geojson").to_crs(fetch.CRS)
    r = rasterize(((geom, int(cid)) for geom, cid in zip(g.geometry, g.cell_id)),
                  out_shape=fetch.INSIDE.shape, transform=fetch.TR, fill=-1, dtype="int32")
    return r[fetch.INSIDE]


def main(obsroot, burndir, outdir):
    os.makedirs(outdir, exist_ok=True)
    cell = cell_raster()
    lc = np.load(fetch.WORLDCOVER)
    elig = np.isin(lc, detect.LANDCOVER_OK) & (cell >= 0)
    n_elig = np.bincount(cell[elig], minlength=cell.max() + 1)
    wins, cal, tot = [], [], []
    for f in sorted(glob.glob(os.path.join(burndir, "burn_*.npz"))):
        y = int(os.path.basename(f)[5:9])
        b = np.load(f)
        d0 = dt.date(y, 1, 1)
        hit = (b["end"] > -999) & (cell >= 0)
        df = pd.DataFrame(dict(cell_id=cell[hit], s=b["start"][hit], e=b["end"][hit]))
        w = df.groupby(["cell_id", "s", "e"]).size().rename("px").reset_index()
        w["burned_ha"] = (w.px * PX_HA).round(2)
        w["window_start"] = [(d0 + dt.timedelta(days=int(v))).isoformat() for v in w.s]
        w["window_end"] = [(d0 + dt.timedelta(days=int(v))).isoformat() for v in w.e]
        w["season"] = y
        wins.append(w[["season", "cell_id", "window_start", "window_end", "burned_ha"]])
        t = w.groupby("cell_id").agg(burned_ha_total=("burned_ha", "sum")).reset_index()
        first = w.sort_values("window_end").groupby("cell_id").first().reset_index()
        t = t.merge(first[["cell_id", "window_start", "window_end"]], on="cell_id")
        t.columns = ["cell_id", "burned_ha_total", "first_window_start", "first_window_end"]
        t["season"] = y
        tot.append(t)
        # clear-sky calendar per cell
        for fn in sorted(glob.glob(os.path.join(obsroot, str(y), "*.npz"))):
            v = np.load(fn)["valid"] & elig
            c = np.bincount(cell[v], minlength=len(n_elig))
            nz = np.where(n_elig > 0)[0]
            frac = c[nz] / n_elig[nz]
            keep = frac > 0
            cal.append(pd.DataFrame(dict(season=y, date=os.path.basename(fn)[:10], sensor=os.path.basename(fn)[11:13],
                                         cell_id=nz[keep], clear_frac=frac[keep].round(3))))
        # GeoTIFF
        arr = np.full((3,) + fetch.INSIDE.shape, -999, np.int16)
        arr[0][fetch.INSIDE] = b["end"]; arr[1][fetch.INSIDE] = b["start"]
        arr[2][fetch.INSIDE] = np.where(b["end"] > -999, (b["mag"] * 1000).astype(np.int16), -999)
        with rasterio.open(os.path.join(outdir, f"burn_{y}.tif"), "w", driver="GTiff", height=arr.shape[1],
                           width=arr.shape[2], count=3, dtype="int16", crs=fetch.CRS, transform=fetch.TR,
                           nodata=-999, compress="deflate") as dst:
            dst.write(arr)
            dst.update_tags(1, name="window_end_doy"); dst.update_tags(2, name="window_start_doy")
            dst.update_tags(3, name="nbr_anomaly_drop_x1000")
    W = pd.concat(wins)
    W["burned"] = (W.burned_ha >= MIN_HA).astype(int)
    W.to_csv(os.path.join(outdir, "burn_windows.csv"), index=False)
    T = pd.concat(tot)[["season", "cell_id", "burned_ha_total", "first_window_start", "first_window_end"]]
    T.to_csv(os.path.join(outdir, "cell_season.csv"), index=False)
    C = pd.concat(cal)
    C.to_csv(os.path.join(outdir, "clear_calendar.csv"), index=False)
    s = T.assign(b=T.burned_ha_total >= MIN_HA).groupby("season").agg(cells_burned=("b", "sum"), ha=("burned_ha_total", "sum"))
    s["km2"] = (s.ha / 100).round(1)
    print(s[["cells_burned", "km2"]].to_string())
    print("windows", len(W), "calendar rows", len(C))


if __name__ == "__main__":
    main(*sys.argv[1:4])
