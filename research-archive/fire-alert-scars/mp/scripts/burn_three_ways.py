"""Burned hectares per season counted three ways (same scars and 20 m grid as burn_history.py):
WorldCover tree/shrub, inside forest beats (ratapani/beats/mp_beats.geojson), and both together.
Out: burn_history/burned_ha_three_ways.csv. Usage: python burn_three_ways.py"""
import os, numpy as np, pandas as pd, geopandas as gpd, shapely
from rasterio.features import rasterize
from rasterio.transform import from_origin
import burn_history as B

OUT = B.OUT + "burned_ha_three_ways.csv"


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
    tot = {y: np.zeros(4, np.int64) for y in years}
    n = B.T * B.K
    for ti, (r, c) in enumerate(B.G["tiles"]):
        x0, y1 = B.X0 + c * B.T * B.S, B.Y1 - r * B.T * B.S
        box = shapely.box(x0, y1 - B.T * B.S, x0 + B.T * B.S, y1)
        sub = g[g.intersects(box)]
        if not len(sub):
            continue
        tr = from_origin(x0, y1, B.RES, B.RES)
        f = B.forest(x0, y1, n)
        bb = beats[beats.intersects(box)]
        bm = rasterize(((s, 1) for s in bb.geometry.intersection(box)), out_shape=(n, n), transform=tr,
                       fill=0, dtype="uint8").astype(bool) if len(bb) else np.zeros((n, n), bool)
        for y in years:
            sy = sub[sub.year == y]
            if not len(sy):
                continue
            m = rasterize(((s, 1) for s in sy.geometry.intersection(box)), out_shape=(n, n), transform=tr,
                          fill=0, dtype="uint8").astype(bool)
            tot[y] += [m.sum(), (m & f).sum(), (m & bm).sum(), (m & f & bm).sum()]
        print(ti, len(B.G["tiles"]), flush=True)
    ha = B.RES * B.RES / 1e4
    F = pd.DataFrame([dict(year=y, all_scar_ha=round(a * ha), worldcover_forest_ha=round(b * ha),
                           inside_beats_ha=round(c * ha), beats_and_worldcover_ha=round(d * ha))
                      for y, (a, b, c, d) in tot.items()])
    F.to_csv(OUT + ".tmp", index=False); os.replace(OUT + ".tmp", OUT); print(F.to_string(index=False))


if __name__ == "__main__":
    main()
