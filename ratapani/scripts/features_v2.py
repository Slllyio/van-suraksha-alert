"""v2 feature table (v1 + proximity, nearest-recent-fire, spread terms, 3x3 label y3) -> model/celldays_v2.parquet"""
import json, shutil
from pathlib import Path
import numpy as np
import pandas as pd
import geopandas as gpd
import lightgbm as lgb
from scipy.ndimage import distance_transform_edt, maximum_filter
from sklearn.metrics import average_precision_score, roc_auc_score

R = Path(r"E:\FIRE\ratapani")
M = R / "model"
grid = gpd.read_file(R / "grid_500m.geojson")
NI, NJ = grid.i.max() + 1, grid.j.max() + 1
gi, gj = grid.i.to_numpy(), grid.j.to_numpy()
df = pd.read_parquet(M / "celldays.parquet").merge(grid[["cell_id", "i", "j"]], on="cell_id")
FUT = pd.read_csv(M / "future_weather_cols.csv", header=None)[0].tolist()

# ---------- (b) new features ----------
prox = R / "ee" / "proximity.csv"
if prox.exists():
    df = df.merge(pd.read_csv(prox), on="cell_id", how="left")

v = pd.read_parquet(R / "viirs_snpp_2013_2024.parquet")
v = v[v.type == 0]
utc = pd.to_datetime(v.acq_date) + pd.to_timedelta(v.acq_time // 100, "h") + pd.to_timedelta(v.acq_time % 100, "m")
v["ldate"] = (utc + pd.Timedelta(hours=5, minutes=30)).dt.normalize()
pts = gpd.sjoin(gpd.GeoDataFrame(v, geometry=gpd.points_from_xy(v.longitude, v.latitude), crs=4326),
                grid[["cell_id", "geometry"]], predicate="within")
days = pd.date_range("2012-12-01", "2024-12-31")
di = pd.Series(np.arange(len(days)), index=days)
pos_of = pd.Series(np.arange(len(grid)), index=grid.cell_id)
fire = np.zeros((len(days), NI, NJ), bool)
fire[di[pts.ldate].to_numpy(), gi[pos_of[pts.cell_id]], gj[pos_of[pts.cell_id]]] = True

def recent_dist(k):  # km from each cell to the nearest fire in the last k days (incl. today), cap 30 km
    out = np.full((len(days), len(grid)), 30, np.float32)
    c = np.cumsum(fire, axis=0)
    for d in range(len(days)):
        win = c[d] - (c[d - k] if d >= k else 0) > 0
        if win.any():
            out[d] = np.minimum(distance_transform_edt(~win)[gi, gj] * 0.5, 30)
    return out

dmap = df.date.map(di).to_numpy()
cmap = pos_of[df.cell_id].to_numpy()
for k in (3, 7, 30):
    df[f"fdist_d{k}"] = recent_dist(k)[dmap, cmap]
df["spread_vpd"] = df.nb7_d3 * df.vpd_max
df["spread_slope"] = df.nb3_d3 * df.slope_deg_mean
df["dry_nearfire"] = df.dry_days / (1 + df.fdist_d7)

# smoothed label: fire within the 3x3 neighbourhood on t+1..t+2 (training variant + tolerant evaluation)
ynb = np.zeros_like(fire)
ynb[:-2] = maximum_filter(fire[1:-1] | fire[2:], size=(1, 3, 3))
df["y3"] = ynb[dmap, gi[cmap], gj[cmap]].astype(np.uint8)
df.to_parquet(M / "celldays_v2.parquet", index=False)
print(df.shape)
