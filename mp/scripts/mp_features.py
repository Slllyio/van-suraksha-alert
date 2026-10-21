"""Cell-day feature tables for one MP division (usage: python mp_features.py <division_dir>).
Same features as the Ratapani v2 table (build_features.py + features_v2.py) plus leaf-fall (r5/r8), written per season:
<dir>/feats/season_<Y>.parquet for Y = 2014..2024, issue days Jan-May.
Labels/history from the MP-wide VIIRS S-NPP archive; detections are placed on the shared MP grid (EPSG:32643,
X0=399000, Y1=2996000, 500 m) over the division's bounding box, so neighbourhood / distance features also see fires
just outside the division. y = fire in the cell on t+1..t+2; y3 = fire within the 3x3 block on t+1..t+2."""
import sys, time
from pathlib import Path
import numpy as np
import pandas as pd
import geopandas as gpd
from scipy.ndimage import uniform_filter, distance_transform_edt, maximum_filter
from sklearn.decomposition import PCA

import os
# Optional overrides (defaults = S-NPP only, feats/, 2014-2024):
#   MP_FIRE_SOURCES  ';'-separated parquet archives with latitude/longitude/acq_date/acq_time/type columns
#   MP_FEATS_DIR     output folder name inside the division dir
#   MP_YEARS         'first-last' seasons
D = Path(sys.argv[1]); EE = D / "ee"; OUT = D / os.environ.get("MP_FEATS_DIR", "feats"); OUT.mkdir(exist_ok=True)
X0, Y1, S = 399000.0, 2996000.0, 500.0
_y0, _y1 = os.environ.get("MP_YEARS", "2014-2024").split("-")
YEARS = range(int(_y0), int(_y1) + 1)
SOURCES = os.environ.get("MP_FIRE_SOURCES",
                         r"E:\FIRE\data_lake\fire_detections\firms_mp_viirs\firms_mp_consolidated.parquet").split(";")
t00 = time.time()
grid = gpd.read_file(D / "grid_500m.geojson").drop(columns="geometry")
n = len(grid); cells = grid.cell_id.to_numpy()
c0, r0 = grid.col.min(), grid.row.min()
NI, NJ = grid.col.max() - c0 + 1, grid.row.max() - r0 + 1        # raster over the bbox: axis0 = col, axis1 = row
gi, gj = (grid.col - c0).to_numpy(), (grid.row - r0).to_numpy()

# ---- fire raster from the MP archive (local IST date) ----
v = pd.concat([pd.read_parquet(p, columns=["latitude", "longitude", "acq_date", "acq_time", "type"]) for p in SOURCES],
              ignore_index=True)
v["acq_date"] = pd.to_datetime(v.acq_date)
v = v[v.type == 0]
xy = gpd.GeoSeries(gpd.points_from_xy(v.longitude, v.latitude), crs=4326).to_crs(32643)
col = np.floor((xy.x.to_numpy() - X0) / S).astype(int) - c0; row = np.floor((Y1 - xy.y.to_numpy()) / S).astype(int) - r0
ok = (col >= 0) & (col < NI) & (row >= 0) & (row < NJ)
utc = pd.to_datetime(v.acq_date[ok]) + pd.to_timedelta(v.acq_time[ok] // 100, "h") + pd.to_timedelta(v.acq_time[ok] % 100, "m")
ldate = (utc + pd.Timedelta(hours=5, minutes=30)).dt.normalize()
days = pd.date_range("2013-12-01", "2024-12-31", freq="D")
di = pd.Series(np.arange(len(days)), index=days)
keep = ldate.isin(days).to_numpy()
FR = np.zeros((len(days), NI, NJ), bool)
FR[di[ldate[keep]].to_numpy(), col[ok][keep], row[ok][keep]] = True
fire = FR[:, gi, gj].astype(np.uint8)                             # (days, cells) inside the division
print("detections in bbox:", int(ok.sum()), "fire cell-days in division:", int(fire.sum()), flush=True)


def win_sum(a, k):
    c = np.cumsum(a, axis=0, dtype=np.float32); out = c.copy(); out[k:] = c[k:] - c[:-k]; return out


frf = FR.astype(np.float32)
nb = {}
for w in (3, 7):
    s = uniform_filter(frf, size=(1, w, w), mode="constant")[:, gi, gj]
    for k in (1, 3, 7):
        nb[f"nb{w}_d{k}"] = win_sum(s, k) * w * w
del frf
cell_k = {f"cell_d{k}": win_sum(fire.astype(np.float32), k) for k in (1, 3, 7, 30)}
aoi_k = {f"aoi_d{k}": win_sum(fire.sum(1, keepdims=True).astype(np.float32), k) for k in (1, 3, 7)}
dsl = np.full(fire.shape, 400, np.float32); last = np.full(n, -10_000)
for d in range(len(days)):
    last = np.where(fire[d] > 0, d, last); dsl[d] = np.minimum(d - last, 400)
y = np.zeros_like(fire); y[:-2] = np.maximum(fire[1:-1], fire[2:])
YN = np.zeros_like(FR); YN[:-2] = maximum_filter(FR[1:-1] | FR[2:], size=(1, 3, 3))
y3 = YN[:, gi, gj].astype(np.uint8); del YN
cum = np.cumsum(FR, axis=0, dtype=np.int32)


def recent_dist(d, k):
    win = (cum[d] - (cum[d - k] if d >= k else 0)) > 0
    return np.minimum(distance_transform_edt(~win)[gi, gj] * 0.5, 30).astype(np.float32) if win.any() else np.full(n, 30, np.float32)


# ---- static + proximity ----
st = grid[["cell_id"]]
for f in ("terrain.csv", "worldcover.csv", "population.csv", "proximity.csv"):
    if (EE / f).exists():
        st = st.merge(pd.read_csv(EE / f), on="cell_id", how="left")
st["forest_frac"] = st.get("wc_10", np.nan)
st = st.loc[:, (st.nunique() > 1) | (st.columns == "cell_id")]

# ---- AlphaEarth PCA-16 of year y-1 ----
ae = {yr: pd.read_csv(EE / f"alphaearth_{yr}.csv").set_index("cell_id").reindex(cells) for yr in range(2017, 2025)}
pca = PCA(16, random_state=0).fit(np.vstack([a.fillna(a.mean()).to_numpy() for a in ae.values()]))
ae_pc = {yr: pca.transform(a.fillna(a.mean()).to_numpy()).astype(np.float32) for yr, a in ae.items()}

# ---- ERA5-Land daily (division mean) ----
e = pd.read_csv(EE / "era5land_daily.csv"); e["d"] = pd.to_datetime(e.time.str[:10]); e = e.set_index("d").reindex(days)
tc, td = e.temperature_2m - 273.15, e.dewpoint_temperature_2m - 273.15
es = lambda t: 0.6108 * np.exp(17.27 * t / (t + 237.3))
w = pd.DataFrame(index=days)
w["tmax"] = e.temperature_2m_max - 273.15; w["rh"] = 100 * es(td) / es(tc); w["vpd_max"] = es(w.tmax) - es(td)
w["wind"] = np.hypot(e.u_component_of_wind_10m, e.v_component_of_wind_10m)
w["prcp_mm"] = e.total_precipitation_sum.clip(lower=0) * 1000; w["swvl1"] = e.volumetric_soil_water_layer_1
w["prcp_7"] = w.prcp_mm.rolling(7, min_periods=1).sum(); w["prcp_30"] = w.prcp_mm.rolling(30, min_periods=1).sum()
since = np.zeros(len(days)); cnt = 60
for k, wd in enumerate((w.prcp_mm > 1).to_numpy()):
    cnt = 0 if wd else min(cnt + 1, 60); since[k] = cnt
w["dry_days"] = since; w["vpd_3"] = w.vpd_max.rolling(3, min_periods=1).mean()
for h in (1, 2):
    for c_ in ("tmax", "vpd_max", "wind", "prcp_mm", "rh"):
        w[f"{c_}_f{h}"] = w[c_].shift(-h)


# ---- MODIS as-of + anomalies + leaf-fall ----
def modis_asof(path, cols, lag):
    m = pd.read_csv(path, parse_dates=["date"]); m["avail"] = m.date + pd.Timedelta(days=lag)
    out = {}
    for c_ in cols:
        p = m.pivot(index="avail", columns="cell_id", values=c_).reindex(columns=cells)
        out[c_] = p.reindex(p.index.union(days)).sort_index().ffill(limit=40).reindex(days).to_numpy(np.float32)
    return out, m


mod, mraw = modis_asof(EE / "modis_ndvi_ndmi.csv", ["ndvi", "ndmi"], 9)
lst, _ = modis_asof(EE / "modis_lst.csv", ["lst_k"], 9); mod.update(lst)
for c_ in list(mod):
    a = pd.DataFrame(mod[c_], index=days)
    mod[f"{c_}_anom"] = (a - a.groupby(a.index.dayofyear // 14).transform("mean")).to_numpy(np.float32)
shift = lambda a, k: np.vstack([np.full((k, n), np.nan, np.float32), a[:-k]])
mod["ndmi_d16"] = mod["ndmi"] - shift(mod["ndmi"], 16)
for k in (16, 32):
    mod[f"ndvi_chg{k}"] = mod["ndvi"] - shift(mod["ndvi"], k); mod[f"ndmi_chg{k}"] = mod["ndmi"] - shift(mod["ndmi"], k)
mp_ = mraw[mraw.date.dt.month >= 9]
peak = mp_.groupby([mp_.date.dt.year + 1, "cell_id"]).ndvi.quantile(0.9).unstack().reindex(columns=cells)
print("prep done", f"{time.time() - t00:.0f}s", flush=True)

# ---- write one parquet per season ----
SM = (1, 2, 3, 4, 5)
for yr in YEARS:
    f_out = OUT / f"season_{yr}.parquet"
    if f_out.exists():
        continue
    sel = np.where((days.year == yr) & days.month.isin(SM))[0]
    prev = (days.year < yr) & days.month.isin(SM)
    nyrs = max(1, len(set(days.year[prev])))
    clim_cell = fire[prev].sum(0) / nyrs
    rc = np.zeros((NI, NJ), np.float32); rc[gi, gj] = clim_cell
    clim_nb = uniform_filter(rc, 7, mode="constant")[gi, gj] * 49
    pc = ae_pc[max(2017, yr - 1)]
    pk = peak.loc[yr].to_numpy(np.float32) if yr in peak.index else np.full(n, np.nan, np.float32)
    frames = []
    for d in sel:
        f = {"date": np.repeat(days[d], n), "cell_id": cells, "i": gi, "j": gj, "y": y[d], "y3": y3[d],
             "doy": np.full(n, days[d].dayofyear, np.float32), "dsl": dsl[d], "clim_cell": clim_cell, "clim_nb7": clim_nb}
        f.update({k: a[d] for k, a in cell_k.items()}); f.update({k: a[d] for k, a in nb.items()})
        f.update({k: np.repeat(a[d, 0], n) for k, a in aoi_k.items()}); f.update({k: a[d] for k, a in mod.items()})
        for c_ in w.columns:
            f[c_] = np.repeat(np.float32(w[c_].iat[d]), n)
        for k in range(16):
            f[f"ae{k:02d}"] = pc[:, k]
        for k in (3, 7, 30):
            f[f"fdist_d{k}"] = recent_dist(d, k)
        f["ndvi_peak"] = pk; f["leaf_loss"] = 1 - mod["ndvi"][d] / pk
        frames.append(pd.DataFrame(f))
    df = pd.concat(frames, ignore_index=True).merge(st, on="cell_id", how="left")
    df["spread_vpd"] = df.nb7_d3 * df.vpd_max
    df["spread_slope"] = df.nb3_d3 * df.get("slope_deg_mean", np.nan)
    df["dry_nearfire"] = df.dry_days / (1 + df.fdist_d7)
    fc = df.columns.difference(["date", "cell_id", "i", "j", "y", "y3"])
    df[fc] = df[fc].astype(np.float32)
    df.to_parquet(f_out, index=False)
    print(yr, df.shape, "pos", int(df.y.sum()), f"{time.time() - t00:.0f}s", flush=True)
