"""What land cover the burned ground inside forest beats is (ESA WorldCover 2021 class of each burned 20 m pixel).
Same scars and grid as burn_three_ways.py. Out: burn_history/burned_inside_beats_by_cover.csv (ha per season per class)."""
import os, numpy as np, pandas as pd, geopandas as gpd, shapely, rasterio
from rasterio.features import rasterize
from rasterio.transform import from_origin
from rasterio.vrt import WarpedVRT
from rasterio.enums import Resampling
import burn_history as B

OUT = B.OUT + "burned_inside_beats_by_cover.csv"
NAMES = {0: "no data", 10: "tree", 20: "shrub", 30: "grass", 40: "farmland", 50: "built", 60: "bare", 70: "snow",
         80: "water", 90: "wetland", 95: "mangrove", 100: "moss"}


def cover(x0, y1, n):
    """WorldCover class (nearest) on the 20 m tile grid; 0 where no tile."""
    tr = from_origin(x0, y1, B.RES, B.RES)
    lon0, lat0, lon1, lat1 = gpd.GeoSeries([shapely.box(x0, y1 - n * B.RES, x0 + n * B.RES, y1)], crs=32643).to_crs(4326).total_bounds
    out = np.zeros((n, n), np.uint8)
    for la in range(3 * int(np.floor(lat0 / 3)), int(np.ceil(lat1)), 3):
        for lo in range(3 * int(np.floor(lon0 / 3)), int(np.ceil(lon1)), 3):
            name = f"N{la:02d}E{lo:03d}"
            for k in range(4):
                try:
                    with rasterio.open(B.WC.format(name)) as src, WarpedVRT(src, crs="EPSG:32643", transform=tr, width=n, height=n,
                                                                           resampling=Resampling.nearest, nodata=0) as v:
                        a = v.read(1)
                    out = np.where(out == 0, a, out)
                    break
                except rasterio.errors.RasterioIOError as e:
                    if "does not exist" in str(e) or "404" in str(e) or k == 3:
                        if k == 3: print("worldcover failed", name, e, flush=True)
                        break
    return out


def main():
    H = B.W.history()
    H = H[H.status == "scar"].copy()
    H["year"] = [d.year for d in H.acq_date]
    md = np.array([(d.month, d.day) for d in H.acq_date])
    H = H[((md[:, 0] > 2) | ((md[:, 0] == 2) & (md[:, 1] >= 15))) & ((md[:, 0] < 6) | ((md[:, 0] == 6) & (md[:, 1] <= 15)))]
    H = H.assign(geometry=B.W.history_geoms().reindex(H.event_id).values)
    H = H[H.geometry.notna()]
    g = gpd.GeoDataFrame(H[["year"]], geometry=list(H.geometry), crs=4326).to_crs(32643)
    beats = gpd.read_file("/mnt/project-files/ratapani/beats/mp_beats.geojson").to_crs(32643)
    beats = beats[beats.geometry.notna() & ~beats.geometry.is_empty]
    years = sorted(g.year.unique())
    tot = {y: np.zeros(256, np.int64) for y in years}
    n = B.T * B.K
    for ti, (r, c) in enumerate(B.G["tiles"]):
        x0, y1 = B.X0 + c * B.T * B.S, B.Y1 - r * B.T * B.S
        box = shapely.box(x0, y1 - B.T * B.S, x0 + B.T * B.S, y1)
        sub = g[g.intersects(box)]
        bb = beats[beats.intersects(box)]
        if not len(sub) or not len(bb):
            continue
        tr = from_origin(x0, y1, B.RES, B.RES)
        cv = cover(x0, y1, n)
        bm = rasterize(((s, 1) for s in bb.geometry.intersection(box)), out_shape=(n, n), transform=tr, fill=0, dtype="uint8").astype(bool)
        for y in years:
            sy = sub[sub.year == y]
            if not len(sy):
                continue
            m = rasterize(((s, 1) for s in sy.geometry.intersection(box)), out_shape=(n, n), transform=tr, fill=0, dtype="uint8").astype(bool)
            tot[y] += np.bincount(cv[m & bm], minlength=256)
        print(ti, flush=True)
    ha = B.RES * B.RES / 1e4
    rows = [dict(year=y, cover=NAMES.get(k, str(k)), ha=round(v[k] * ha)) for y, v in tot.items() for k in np.nonzero(v)[0]]
    F = pd.DataFrame(rows)
    F["share"] = (F.ha / F.groupby("year").ha.transform("sum")).round(4)
    F.to_csv(OUT + ".tmp", index=False); os.replace(OUT + ".tmp", OUT)
    print(F.pivot(index="cover", columns="year", values="share").fillna(0).round(3).to_string())


if __name__ == "__main__":
    main()
