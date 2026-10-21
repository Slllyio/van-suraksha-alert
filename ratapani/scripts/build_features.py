"""Ratapani 500 m cell-day table for the 2-day fire outlook.

Issue time = evening of local day t (after the afternoon VIIRS pass).
Target y = any VIIRS SNPP detection in the cell on local day t+1 or t+2.
Every feature uses data available by day t, except the *_f1/_f2 weather columns, which use ERA5-Land
reanalysis as a stand-in for a 1-2 day forecast (operationally: WeatherNext). Train both with and without them.
"""
from pathlib import Path
import numpy as np
import pandas as pd
import geopandas as gpd
from scipy.ndimage import uniform_filter
from sklearn.decomposition import PCA

R = Path(r"E:\FIRE\ratapani")
EE = R / "ee"
OUT = R / "model"
OUT.mkdir(exist_ok=True)
YEARS = range(2013, 2025)
SEASON_MONTHS = (1, 2, 3, 4, 5)

grid = gpd.read_file(R / "grid_500m.geojson").drop(columns="geometry")
cells = grid.cell_id.to_numpy()
NI, NJ = grid.i.max() + 1, grid.j.max() + 1
gi, gj = grid.i.to_numpy(), grid.j.to_numpy()
cell_pos = pd.Series(np.arange(len(grid)), index=grid.cell_id)

# ---- fire labels: VIIRS points -> cell, local (IST) date ----
v = pd.read_parquet(R / "viirs_snpp_2013_2024.parquet")
v = v[v.type == 0]
utc = pd.to_datetime(v.acq_date) + pd.to_timedelta(v.acq_time // 100, "h") + pd.to_timedelta(v.acq_time % 100, "m")
v["ldate"] = (utc + pd.Timedelta(hours=5, minutes=30)).dt.normalize()
pts = gpd.GeoDataFrame(v, geometry=gpd.points_from_xy(v.longitude, v.latitude), crs=4326)
poly = gpd.read_file(R / "grid_500m.geojson")[["cell_id", "geometry"]]
pts = gpd.sjoin(pts, poly, predicate="within", how="inner")
print("detections in grid:", len(pts), "of", len(v))

days = pd.date_range("2012-12-01", "2024-12-31", freq="D")
day_idx = pd.Series(np.arange(len(days)), index=days)
fire = np.zeros((len(days), len(grid)), dtype=np.uint8)  # fire[d, cell]
fire[day_idx[pts.ldate].to_numpy(), cell_pos[pts.cell_id].to_numpy()] = 1
print("fire cell-days:", int(fire.sum()))


def to_raster(a):  # (days, cells) -> (days, NI, NJ)
    r = np.zeros((a.shape[0], NI, NJ), np.float32)
    r[:, gi, gj] = a
    return r


def win_sum(a, k):  # trailing k-day sum ending at day d (inclusive)
    c = np.cumsum(a, axis=0, dtype=np.float32)
    out = c.copy()
    out[k:] = c[k:] - c[:-k]
    return out


fr = to_raster(fire.astype(np.float32))
nb = {}
for w in (3, 7):  # spatial windows: 3x3 = 1.5 km, 7x7 = 3.5 km (fraction of cells burning)
    s = uniform_filter(fr, size=(1, w, w), mode="constant")[:, gi, gj]
    for k in (1, 3, 7):
        nb[f"nb{w}_d{k}"] = win_sum(s, k) * w * w  # back to counts
cell_k = {f"cell_d{k}": win_sum(fire.astype(np.float32), k) for k in (1, 3, 7, 30)}
aoi_k = {f"aoi_d{k}": win_sum(fire.sum(1, keepdims=True).astype(np.float32), k) for k in (1, 3, 7)}

# days since last fire in cell (cap 400)
dsl = np.full(fire.shape, 400, np.float32)
last = np.full(len(grid), -10_000)
for d in range(len(days)):
    last = np.where(fire[d] > 0, d, last)
    dsl[d] = np.minimum(d - last, 400)

# target: fire on d+1 or d+2
y = np.zeros_like(fire)
y[:-2] = np.maximum(fire[1:-1], fire[2:])

# ---- static ----
st = grid[["cell_id", "forest_frac"]]
for f in ("terrain.csv", "worldcover.csv", "population.csv"):
    st = st.merge(pd.read_csv(EE / f), on="cell_id")
st = st.loc[:, st.nunique() > 1]

# AlphaEarth: PCA-16 of year (y-1) embedding (avoid same-year burn scars); 2017 is the earliest available.
ae = {yr: pd.read_csv(EE / f"alphaearth_{yr}.csv").sort_values("cell_id") for yr in range(2017, 2025)}
pca = PCA(16, random_state=0).fit(np.vstack([a.iloc[:, 1:].to_numpy() for a in ae.values()]))
ae_pc = {yr: pca.transform(a.iloc[:, 1:].to_numpy()).astype(np.float32) for yr, a in ae.items()}

# ---- ERA5-Land daily AOI weather ----
e = pd.read_csv(EE / "era5land_daily.csv")
e["d"] = pd.to_datetime(e.time.str[:10])
e = e.set_index("d").reindex(days)
tc, td = e.temperature_2m - 273.15, e.dewpoint_temperature_2m - 273.15
es = lambda t: 0.6108 * np.exp(17.27 * t / (t + 237.3))
w = pd.DataFrame(index=days)
w["tmax"] = e.temperature_2m_max - 273.15
w["rh"] = 100 * es(td) / es(tc)
w["vpd_max"] = es(w.tmax) - es(td)
w["wind"] = np.hypot(e.u_component_of_wind_10m, e.v_component_of_wind_10m)
w["prcp_mm"] = e.total_precipitation_sum.clip(lower=0) * 1000
w["swvl1"] = e.volumetric_soil_water_layer_1
w["prcp_7"] = w.prcp_mm.rolling(7, min_periods=1).sum()
w["prcp_30"] = w.prcp_mm.rolling(30, min_periods=1).sum()
wet = (w.prcp_mm > 1).to_numpy()
since = np.zeros(len(days)); c = 60
for k, wd in enumerate(wet):
    c = 0 if wd else min(c + 1, 60); since[k] = c
w["dry_days"] = since
w["vpd_3"] = w.vpd_max.rolling(3, min_periods=1).mean()
for h in (1, 2):  # "forecast" columns (oracle: reanalysis of t+1, t+2)
    for col in ("tmax", "vpd_max", "wind", "prcp_mm", "rh"):
        w[f"{col}_f{h}"] = w[col].shift(-h)
WX_FUT = [c for c in w.columns if c.endswith(("_f1", "_f2"))]


# ---- MODIS as-of (composite start + 8 d <= t), forward-filled per cell ----
def modis_asof(path, cols, lag):
    m = pd.read_csv(path, parse_dates=["date"])
    m["avail"] = m.date + pd.Timedelta(days=lag)
    piv = {c: m.pivot(index="avail", columns="cell_id", values=c).reindex(columns=cells) for c in cols}
    out = {}
    for c, p in piv.items():
        p = p.reindex(p.index.union(days)).sort_index().ffill(limit=40).reindex(days)
        out[c] = p.to_numpy(np.float32)
    return out


mod = modis_asof(EE / "modis_ndvi_ndmi.csv", ["ndvi", "ndmi"], 9)
mod.update(modis_asof(EE / "modis_lst.csv", ["lst_k"], 9))
for c in list(mod):  # anomaly vs. the cell's mean for the same 2-week of year (all years; mild leakage, slow-moving)
    a = pd.DataFrame(mod[c], index=days)
    clim = a.groupby(a.index.dayofyear // 14).transform("mean")
    mod[f"{c}_anom"] = (a - clim).to_numpy(np.float32)
mod["ndmi_d16"] = mod["ndmi"] - np.vstack([np.full((16, len(grid)), np.nan, np.float32), mod["ndmi"][:-16]])

# ---- assemble season rows ----
frames = []
for yr in YEARS:
    sel = np.where((days.year == yr) & days.month.isin(SEASON_MONTHS))[0]
    # prior-years climatology: fire-days per season in this cell from years < yr
    prev = (days.year < yr) & days.month.isin(SEASON_MONTHS)
    nyrs = max(1, len(set(days.year[prev])))
    clim_cell = fire[prev].sum(0) / nyrs
    clim_nb = uniform_filter(to_raster(clim_cell[None])[0], 7, mode="constant")[gi, gj] * 49
    pc = ae_pc[max(2017, yr - 1)]
    for d in sel:
        f = {"date": np.repeat(days[d], len(grid)), "cell_id": cells, "y": y[d],
             "doy": np.full(len(grid), days[d].dayofyear, np.int16),
             "dsl": dsl[d], "clim_cell": clim_cell, "clim_nb7": clim_nb}
        f.update({k: a[d] for k, a in cell_k.items()})
        f.update({k: a[d] for k, a in nb.items()})
        f.update({k: np.repeat(a[d, 0], len(grid)) for k, a in aoi_k.items()})
        f.update({k: a[d] for k, a in mod.items()})
        for col in w.columns:
            f[col] = np.repeat(np.float32(w[col].iat[d]), len(grid))
        for k in range(pc.shape[1]):
            f[f"ae{k:02d}"] = pc[:, k]
        frames.append(pd.DataFrame(f))
    print(yr, "rows", len(sel) * len(grid))

df = pd.concat(frames, ignore_index=True).merge(st, on="cell_id", how="left")
fcols = df.columns.difference(["date", "cell_id", "y"])
df[fcols] = df[fcols].astype(np.float32)
df.to_parquet(OUT / "celldays.parquet", index=False)
pd.Series(WX_FUT).to_csv(OUT / "future_weather_cols.csv", index=False, header=False)
print("table", df.shape, "positives", int(df.y.sum()), f"rate {df.y.mean():.4%}")
