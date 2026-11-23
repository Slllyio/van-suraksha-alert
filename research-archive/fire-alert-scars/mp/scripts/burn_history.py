"""MP 2017-25 burn history on the shared all-MP 500 m grid (ratapani/mp_grid: EPSG:32643, X0 399000, Y1 2996000,
1829 x 1332 cells, cell = row * 1829 + col). Clear scars (status 'scar', 15 Feb-15 Jun, industry filtered, as in
the weekly report) are burned into a 20 m grid; each 500 m cell gets, per season, the share of its area burned, the
share burned on forest ground (ESA WorldCover 2021 tree or shrub), and its forest share.
Out: burn_history/cell_year.parquet (cell, year, burned, burned_forest, forest; shares 0-1, cells with any burn)
     burn_history/forest_ha_by_year.csv. Usage: python burn_history.py"""
import os, sys, json, numpy as np, pandas as pd, geopandas as gpd, shapely, rasterio
from rasterio.features import rasterize
from rasterio.transform import from_origin
from rasterio.vrt import WarpedVRT
from rasterio.enums import Resampling
os.environ.setdefault("CURL_CA_BUNDLE", "/root/.ccr/ca-bundle.crt")
os.environ.setdefault("GDAL_DISABLE_READDIR_ON_OPEN", "EMPTY_DIR")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__))); sys.path.insert(0, "/mnt/project-files/fire-alert-scars/scripts")
import weekly_report as W

G = json.load(open("/mnt/project-files/ratapani/mp_grid/mp_grid.json"))
X0, Y1, NC, S, T, RES = G["X0"], G["Y1"], G["W"], G["S"], G["T"], 20.0
K = int(S / RES)            # 25 x 25 fine pixels per cell
OUT = "/mnt/project-files/fire-alert-scars/mp/burn_history/"
WC = "/vsicurl/https://esa-worldcover.s3.eu-central-1.amazonaws.com/v200/2021/map/ESA_WorldCover_10m_2021_v200_{}_Map.tif"


def forest(x0, y1, n):
    """tree or shrub (WorldCover 10/20) on the 20 m tile grid; 0 where no WorldCover tile."""
    tr = from_origin(x0, y1, RES, RES)
    lon0, lat0, lon1, lat1 = gpd.GeoSeries([shapely.box(x0, y1 - n * RES, x0 + n * RES, y1)], crs=32643).to_crs(4326).total_bounds
    out = np.zeros((n, n), bool)
    for la in range(3 * int(np.floor(lat0 / 3)), int(np.ceil(lat1)), 3):
        for lo in range(3 * int(np.floor(lon0 / 3)), int(np.ceil(lon1)), 3):
            name = f"{'N' if la >= 0 else 'S'}{abs(la):02d}{'E' if lo >= 0 else 'W'}{abs(lo):03d}"
            for k in range(4):
                try:
                    with rasterio.open(WC.format(name)) as src, WarpedVRT(src, crs="EPSG:32643", transform=tr, width=n, height=n,
                                                                         resampling=Resampling.nearest, nodata=0) as v:
                        a = v.read(1)
                    out |= (a == 10) | (a == 20)
                    break
                except rasterio.errors.RasterioIOError as e:
                    if "does not exist" in str(e) or "404" in str(e) or k == 3:
                        if k == 3: print("worldcover failed", name, e, flush=True)
                        break
    return out


def main():
    H = W.history()
    H = H[H.status == "scar"].copy()
    H["year"] = [d.year for d in H.acq_date]
    md = np.array([(d.month, d.day) for d in H.acq_date])
    H = H[((md[:, 0] > 2) | ((md[:, 0] == 2) & (md[:, 1] >= 15))) & ((md[:, 0] < 6) | ((md[:, 0] == 6) & (md[:, 1] <= 15)))]
    HG = W.history_geoms()
    H = H.assign(geometry=HG.reindex(H.event_id).values)
    print("events", len(H), "without outline", H.geometry.isna().sum(), flush=True)
    H = H[H.geometry.notna()]
    g = gpd.GeoDataFrame(H[["year"]], geometry=list(H.geometry), crs=4326).to_crs(32643)
    years = sorted(g.year.unique())
    rows, tot = [], {y: [0, 0] for y in years}
    n = T * K
    for ti, (r, c) in enumerate(G["tiles"]):
        x0, y1 = X0 + c * T * S, Y1 - r * T * S
        box = shapely.box(x0, y1 - T * S, x0 + T * S, y1)
        sub = g[g.intersects(box)]
        if not len(sub):
            continue
        f = forest(x0, y1, n)
        fc = f.reshape(T, K, T, K).mean(axis=(1, 3))
        cell = (r * T + np.arange(T))[:, None] * NC + (c * T + np.arange(T))[None, :]
        for y in years:
            sy = sub[sub.year == y]
            if not len(sy):
                continue
            m = rasterize(((s, 1) for s in sy.geometry.intersection(box)), out_shape=(n, n),
                          transform=from_origin(x0, y1, RES, RES), fill=0, dtype="uint8").astype(bool)
            tot[y][0] += m.sum(); tot[y][1] += (m & f).sum()
            b = m.reshape(T, K, T, K).mean(axis=(1, 3)); bf = (m & f).reshape(T, K, T, K).mean(axis=(1, 3))
            k = b > 0
            rows.append(pd.DataFrame(dict(cell=cell[k], year=y, burned=b[k].astype("float32"),
                                          burned_forest=bf[k].astype("float32"), forest=fc[k].astype("float32"))))
        print(ti, len(G["tiles"]), flush=True)
    D = pd.concat(rows, ignore_index=True)
    D = D[(D.cell // NC < G["H"]) & (D.cell % NC < NC)]
    D.to_parquet(OUT + "cell_year.parquet.tmp", index=False); os.replace(OUT + "cell_year.parquet.tmp", OUT + "cell_year.parquet")
    F = pd.DataFrame([dict(year=y, burned_ha=round(a * RES * RES / 1e4), burned_forest_ha=round(b * RES * RES / 1e4)) for y, (a, b) in tot.items()])
    F.to_csv(OUT + "forest_ha_by_year.csv", index=False); print(F.to_string(index=False))


if __name__ == "__main__":
    main()
