"""Per-cell static inputs, pseudo-beats and per-season fuel age for the 500 m grid.
Outputs: cells_static.csv (cell_id, beat, area_ha, elig_ha, tree/shrub/grass/crop frac, elev, slope, northness,
         eastness, d_built, d_crop, d_edge, d_aoi), fuel_age.csv (season, cell_id, age_mean, frac_burned_last,
         frac_burned_3y, frac_never) and cell_px.npy (cell id per AOI pixel).
Usage: python cells.py <static20m.npz> <burndir> <outdir> [beat_km2=12]
"""
import os, sys, glob
import numpy as np, pandas as pd, geopandas as gpd
from rasterio.features import rasterize
from sklearn.cluster import KMeans

sys.path.insert(0, "/mnt/project-files/research/ratapani-burn-labels/scripts")
import fetch, detect

I = fetch.INSIDE
PX_HA = fetch.RES ** 2 / 1e4


def main(static, burndir, outdir, beat_km2=12.0):
    os.makedirs(outdir, exist_ok=True)
    g = gpd.read_file("/mnt/project-files/ratapani/grid_500m.geojson").to_crs(fetch.CRS)
    cell = rasterize(((geom, int(c)) for geom, c in zip(g.geometry, g.cell_id)), out_shape=I.shape,
                     transform=fetch.TR, fill=-1, dtype="int32")[I]
    np.save(os.path.join(outdir, "cell_px.npy"), cell)
    z = np.load(static)
    wc = z["wc"][I]
    ok = cell >= 0
    n = int(cell.max()) + 1
    cnt = np.bincount(cell[ok], minlength=n).astype(float)
    def mean_of(v): return np.bincount(cell[ok], weights=v[I][ok], minlength=n) / np.maximum(cnt, 1)
    def frac_of(m): return np.bincount(cell[ok], weights=m[ok].astype(float), minlength=n) / np.maximum(cnt, 1)
    asp = np.radians(z["aspect"])
    df = pd.DataFrame(dict(cell_id=np.arange(n), area_ha=cnt * PX_HA,
                           elig_ha=np.bincount(cell[ok], weights=np.isin(wc, detect.LANDCOVER_OK)[ok].astype(float), minlength=n) * PX_HA,
                           tree=frac_of(wc == 10), shrub=frac_of(wc == 20), grass=frac_of(wc == 30), crop=frac_of(wc == 40),
                           elev=mean_of(z["elev"]), slope=mean_of(z["slope"]),
                           northness=mean_of(np.cos(asp)), eastness=mean_of(np.sin(asp)),
                           d_built=mean_of(z["d_built"]), d_crop=mean_of(z["d_crop"]), d_edge=mean_of(z["d_edge"]),
                           d_aoi=mean_of(z["d_aoi"])))
    df = df[df.area_ha > 0].copy()
    # pseudo-beats: k-means on cell centroids, ~beat_km2 each (real beat boundaries not available yet)
    cen = g.set_index("cell_id").loc[df.cell_id].geometry.centroid
    k = max(1, round(df.area_ha.sum() / 100 / beat_km2))
    df["beat"] = KMeans(k, n_init=4, random_state=0).fit_predict(np.c_[cen.x, cen.y])
    df.to_csv(os.path.join(outdir, "cells_static.csv"), index=False)
    print("cells", len(df), "beats", k, "cells/beat", round(len(df) / k, 1))
    # fuel age per season from the scar history (2017 is the first season we see)
    burned = {}
    for f in sorted(glob.glob(os.path.join(burndir, "burn_*.npz"))):
        burned[int(os.path.basename(f)[5:9])] = np.load(f)["end"] > -999
    years = sorted(burned)
    rows = []
    last = np.full(I.sum(), -1)
    for y in years:
        age = np.where(last >= 0, y - last, y - years[0] + 1).astype(float)   # censored: >= years since first season
        never = last < 0
        zero = np.zeros_like(never); b1 = burned.get(y - 1, zero)
        b3 = burned.get(y - 1, zero) | burned.get(y - 2, zero) | burned.get(y - 3, zero)
        rows.append(pd.DataFrame(dict(season=y, cell_id=np.arange(n), age_mean=mean_of_px(age, cell, ok, n),
                                      frac_burned_last=mean_of_px(b1.astype(float), cell, ok, n),
                                      frac_burned_3y=mean_of_px(np.asarray(b3).astype(float), cell, ok, n),
                                      frac_never=mean_of_px(never.astype(float), cell, ok, n))))
        last = np.where(burned[y], y, last)
    fa = pd.concat(rows); fa = fa[fa.cell_id.isin(df.cell_id)]
    fa.to_csv(os.path.join(outdir, "fuel_age.csv"), index=False)
    print(fa.groupby("season")[["age_mean", "frac_burned_last", "frac_never"]].mean().round(2))


def mean_of_px(v, cell, ok, n):
    return np.bincount(cell[ok], weights=v[ok], minlength=n) / np.maximum(np.bincount(cell[ok], minlength=n), 1)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], sys.argv[3], *(float(a) for a in sys.argv[4:5]))
