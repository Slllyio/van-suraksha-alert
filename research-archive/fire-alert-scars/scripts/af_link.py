"""Use Sentinel-2/Landsat active-fire pixels (af_scan.py) to date burn scars to the day.

Outputs (out/af/):
  af_pixels_clean.csv     all AF pixels, fixed sources (> 4 dates at one pixel) dropped, with cell_id and
                          a fire cluster id (same date, within 60 m), and whether a FIRMS alert lies within
                          1 km on the same or next day
  first_burn_days.csv     per season and cell: first-burn window from the research labels (burned >= 0.5 ha),
                          with the day from (a) S-NPP VIIRS only, (b) all FIRMS sensors (S-NPP, NOAA-20, MODIS;
                          750 m, window [ws, we+1], clipped), (c) S2/Landsat AF pixels inside the cell on a date in
                          (ws, we], and best_day = AF day if any, else the earliest FIRMS day
  af_summary.json         dated shares and agreement
Usage: python af_link.py
"""
import glob, json, os
import numpy as np, pandas as pd, geopandas as gpd
from scipy.spatial import cKDTree
from scipy.ndimage import label
from pyproj import Transformer

P = "/mnt/project-files/"
AF = P + "fire-alert-scars/out/af/"
TO = Transformer.from_crs("EPSG:4326", "EPSG:32643", always_xy=True)


def main():
    D = pd.concat([pd.read_csv(f) for f in sorted(glob.glob(AF + "af_20??.csv")) if os.path.getsize(f) > 10],
                  ignore_index=True)
    D["date"] = pd.to_datetime(D.date)
    nd = D.groupby(["row", "col"]).date.nunique()
    fixed = set(nd[nd > 4].index)
    D = D[[(r, c) not in fixed for r, c in zip(D.row, D.col)]].reset_index(drop=True)
    D["season"] = np.where(D.date.dt.month == 12, D.date.dt.year + 1, D.date.dt.year)
    D["x"], D["y"] = TO.transform(D.lon.values, D.lat.values)
    grid = gpd.read_file(P + "ratapani/grid_500m.geojson").to_crs(32643)
    j = gpd.sjoin(gpd.GeoDataFrame(D[[]], geometry=gpd.points_from_xy(D.x, D.y), crs=32643),
                  grid[["cell_id", "geometry"]], how="left", predicate="within")
    D["cell_id"] = j[~j.index.duplicated()].cell_id.values
    # clusters: same date, 8-connected within 3 px (60 m)
    D["cluster"] = -1
    k = 0
    for d, g in D.groupby("date"):
        t = cKDTree(g[["row", "col"]].values)
        pairs = t.query_pairs(3)
        parent = list(range(len(g)))

        def f(i):
            while parent[i] != i:
                parent[i] = parent[parent[i]]
                i = parent[i]
            return i
        for a, b in pairs:
            parent[f(a)] = f(b)
        roots = np.array([f(i) for i in range(len(g))])
        _, inv = np.unique(roots, return_inverse=True)
        D.loc[g.index, "cluster"] = inv + k
        k += inv.max() + 1
    # FIRMS alerts near each AF cluster (same or next day, 1 km)
    A = pd.concat([pd.read_csv(f, dtype={"acq_time": str, "confidence": str}).assign(sensor=os.path.basename(f).split("_")[0])
                   for f in glob.glob(P + "fire-alert-scars/alerts/*.csv")], ignore_index=True)
    A = A.drop_duplicates(["latitude", "longitude", "acq_date", "acq_time", "sensor"])
    A["date"] = pd.to_datetime(A.acq_date)
    c = A.confidence.astype(str).str.lower()
    A = A[np.where(A.sensor == "modis", pd.to_numeric(c, errors="coerce") >= 30, c != "l")]
    A["x"], A["y"] = TO.transform(A.longitude.values, A.latitude.values)
    D["firms_nearby"] = False
    for d, g in D.groupby("date"):
        a = A[(A.date >= d) & (A.date <= d + pd.Timedelta("1D"))]
        if len(a):
            dd, _ = cKDTree(a[["x", "y"]].values).query(g[["x", "y"]].values)
            D.loc[g.index, "firms_nearby"] = dd <= 1000
    D.drop(columns=["x", "y"]).to_csv(AF + "af_pixels_clean.csv", index=False)

    # first-burn windows and their days
    bw = pd.read_csv(P + "research/ratapani-burn-labels/burn_windows.csv", parse_dates=["window_start", "window_end"])
    bw = bw[bw.burned == 1].sort_values(["season", "cell_id", "window_end"]).drop_duplicates(["season", "cell_id"])
    cen = np.c_[grid.geometry.centroid.x, grid.geometry.centroid.y]
    cid = grid.cell_id.values
    tree = cKDTree(cen)

    def firms_day(sub):
        pairs = [(cid[cc], sub.date.iloc[i]) for i, nb in enumerate(tree.query_ball_point(sub[["x", "y"]].values, 750)) for cc in nb]
        vp = pd.DataFrame(pairs, columns=["cell_id", "vd"]).drop_duplicates()
        x = bw.reset_index().merge(vp, on="cell_id")
        x = x[(x.vd >= x.window_start) & (x.vd <= x.window_end + pd.Timedelta("1D"))].sort_values("vd")
        x = x.drop_duplicates(["season", "cell_id"])
        x["d"] = x.vd.clip(lower=x.window_start + pd.Timedelta("1D"), upper=x.window_end)
        return x.set_index(["season", "cell_id"]).d

    bw = bw.set_index(["season", "cell_id"])
    bw["day_snpp"] = firms_day(A[A.sensor == "viirs-snpp"])
    bw["day_firms"] = firms_day(A)
    af = D.dropna(subset=["cell_id"]).astype({"cell_id": int}).merge(bw.reset_index()[["season", "cell_id", "window_start", "window_end"]],
                                                                     on=["season", "cell_id"])
    af = af[(af.date > af.window_start) & (af.date <= af.window_end)]
    g = af.groupby(["season", "cell_id"])
    bw["day_af"] = g.date.min()
    bw["af_px"] = g.size()
    bw["af_sensor"] = g.sensor.first()
    bw["best_day"] = bw.day_af.fillna(bw.day_firms)
    bw = bw.reset_index()
    bw.to_csv(AF + "first_burn_days.csv", index=False)

    s = {}
    for name, sub in (("2017-2024", bw[bw.season <= 2024]), ("2017-2026", bw)):
        s[name] = dict(first_burns=len(sub), snpp_dated=round(sub.day_snpp.notna().mean(), 3),
                       firms_dated=round(sub.day_firms.notna().mean(), 3), af_dated=round(sub.day_af.notna().mean(), 3),
                       any_dated=round(sub.best_day.notna().mean(), 3),
                       af_only=round((sub.day_af.notna() & sub.day_firms.isna()).mean(), 3))
    both = bw.dropna(subset=["day_af", "day_firms"])
    diff = (both.day_firms - both.day_af).dt.days
    s["af_vs_firms_days"] = dict(n=len(both), same_day=round((diff == 0).mean(), 3), within_1=round((diff.abs() <= 1).mean(), 3),
                                 firms_later_median=float(diff.median()))
    cl = D.groupby("cluster").agg(firms=("firms_nearby", "max"), px=("row", "size"))
    s["af_clusters"] = dict(n=len(cl), with_firms_alert=round(cl.firms.mean(), 3),
                            small_lt5px_with_firms=round(cl[cl.px < 5].firms.mean(), 3), fixed_sources_dropped=len(fixed))
    s["by_season_af_dated"] = bw.groupby("season").day_af.apply(lambda x: round(x.notna().mean(), 3)).to_dict()
    json.dump(s, open(AF + "af_summary.json", "w"), indent=1, default=str)
    print(json.dumps(s, indent=1, default=str))


if __name__ == "__main__":
    main()
