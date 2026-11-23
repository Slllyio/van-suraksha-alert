"""Per 500 m cell and season: earliest burn day (days since 15 Feb) and the size of the biggest fire (scar_ha) that
reached it. Same clear scars and grid as burn_history.py. Out: regimes/cell_year_timing.parquet (cell, year, first_day, max_fire_ha)."""
import os, numpy as np, pandas as pd, geopandas as gpd, shapely
from rasterio.features import rasterize
from rasterio.transform import from_origin
import burn_history as B

OUT = "/mnt/project-files/fire-alert-scars/mp/regimes/cell_year_timing.parquet"


def main():
    H = B.W.history()
    H = H[H.status == "scar"].copy()
    H["year"] = [d.year for d in H.acq_date]
    md = np.array([(d.month, d.day) for d in H.acq_date])
    H = H[((md[:, 0] > 2) | ((md[:, 0] == 2) & (md[:, 1] >= 15))) & ((md[:, 0] < 6) | ((md[:, 0] == 6) & (md[:, 1] <= 15)))]
    H["day"] = [(pd.Timestamp(d) - pd.Timestamp(d.year, 2, 15)).days + 1 for d in H.acq_date]   # 1 = 15 Feb
    H = H.assign(geometry=B.W.history_geoms().reindex(H.event_id).values)
    H = H[H.geometry.notna()]
    g = gpd.GeoDataFrame(H[["year", "day", "scar_ha"]], geometry=list(H.geometry), crs=4326).to_crs(32643)
    n, rows = B.T * B.K, []
    for ti, (r, c) in enumerate(B.G["tiles"]):
        x0, y1 = B.X0 + c * B.T * B.S, B.Y1 - r * B.T * B.S
        box = shapely.box(x0, y1 - B.T * B.S, x0 + B.T * B.S, y1)
        sub = g[g.intersects(box)]
        if not len(sub):
            continue
        tr = from_origin(x0, y1, B.RES, B.RES)
        cell = (r * B.T + np.arange(B.T))[:, None] * B.NC + (c * B.T + np.arange(B.T))[None, :]
        for y, sy in sub.groupby("year"):
            geo = sy.geometry.intersection(box)
            o = np.argsort(-sy.day.values)        # earliest written last
            d = rasterize(((geo.iloc[i], int(sy.day.values[i])) for i in o), out_shape=(n, n), transform=tr, fill=0, dtype="int16")
            o = np.argsort(sy.scar_ha.fillna(0).values)   # biggest written last
            a = rasterize(((geo.iloc[i], float(sy.scar_ha.fillna(0).values[i])) for i in o), out_shape=(n, n), transform=tr, fill=0, dtype="float32")
            d4 = np.where(d > 0, d, 999).reshape(B.T, B.K, B.T, B.K).min(axis=(1, 3))
            a4 = a.reshape(B.T, B.K, B.T, B.K).max(axis=(1, 3))
            k = d4 < 999
            rows.append(pd.DataFrame(dict(cell=cell[k], year=y, first_day=d4[k].astype("int16"), max_fire_ha=a4[k])))
        print(ti, flush=True)
    D = pd.concat(rows).groupby(["cell", "year"], as_index=False).agg(first_day=("first_day", "min"), max_fire_ha=("max_fire_ha", "max"))
    D.to_parquet(OUT + ".tmp", index=False); os.replace(OUT + ".tmp", OUT); print(len(D), D.describe().to_string())


if __name__ == "__main__":
    main()
