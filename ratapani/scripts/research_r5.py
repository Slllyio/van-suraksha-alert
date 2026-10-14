"""Research round 5 (LOYO 2013-2024, feature set '5_+weather' from r3 = no forecast weather).
(a) Horizon: target = fire on t+1 only / t+1..t+2 / t+1..t+3 / t+2 only. Skill per horizon.
(c) Leaf-fall features: NDVI loss vs the cell's post-monsoon peak (Sep-Dec of previous year), 16/32-day NDVI and
    NDMI change. Does it add skill, especially for brand-new fires?"""
import json
from pathlib import Path
import numpy as np
import pandas as pd
import geopandas as gpd
import lightgbm as lgb
from scipy.ndimage import maximum_filter

R = Path(r"E:\FIRE\ratapani")
M = R / "model"
OUT = M / "r5"
OUT.mkdir(exist_ok=True)
df = pd.read_parquet(M / "celldays_v2.parquet")
df["cls"] = pd.read_parquet(M / "r3" / "oof_preds.parquet", columns=["cls"])["cls"].to_numpy()
G = json.loads((M / "r3" / "feature_groups.json").read_text())
BASE = sum((G[g] for g in ["fire", "static", "modis", "alphaearth", "weather"]), [])
NI, NJ = df.i.max() + 1, df.j.max() + 1
year = df.date.dt.year.to_numpy()

# ---------- labels for each horizon ----------
grid = gpd.read_file(R / "grid_500m.geojson")
v = pd.read_parquet(R / "viirs_snpp_2013_2024.parquet"); v = v[v.type == 0]
utc = pd.to_datetime(v.acq_date) + pd.to_timedelta(v.acq_time // 100, "h") + pd.to_timedelta(v.acq_time % 100, "m")
v["ldate"] = (utc + pd.Timedelta(hours=5, minutes=30)).dt.normalize()
pts = gpd.sjoin(gpd.GeoDataFrame(v, geometry=gpd.points_from_xy(v.longitude, v.latitude), crs=4326),
                grid[["cell_id", "geometry"]], predicate="within")
days = pd.date_range("2012-12-01", "2025-01-10")
di = pd.Series(np.arange(len(days)), index=days)
pos_of = pd.Series(np.arange(len(grid)), index=grid.cell_id)
fire = np.zeros((len(days), len(grid)), bool)
fire[di[pts.ldate].to_numpy(), pos_of[pts.cell_id].to_numpy()] = True
dmap, cmap = df.date.map(di).to_numpy(), pos_of[df.cell_id].to_numpy()
H = {"t+1": [1], "t+1..t+2": [1, 2], "t+1..t+3": [1, 2, 3], "t+2_only": [2]}
for h, lags in H.items():
    df[f"y_{h}"] = np.any([fire[dmap + k, cmap] for k in lags], axis=0).astype(np.uint8)
assert (df["y_t+1..t+2"] == df.y).all()

# ---------- leaf-fall features ----------
m = pd.read_csv(R / "ee" / "modis_ndvi_ndmi.csv", parse_dates=["date"])
m["season"] = np.where(m.date.dt.month >= 9, m.date.dt.year + 1, np.nan)
peak = m.dropna(subset=["season"]).groupby(["season", "cell_id"]).ndvi.quantile(0.9).rename("ndvi_peak").reset_index()
df["season"] = year
df = df.merge(peak.astype({"season": int}), on=["season", "cell_id"], how="left")
df["leaf_loss"] = 1 - df.ndvi / df.ndvi_peak
df = df.sort_values(["cell_id", "date"]).reset_index(drop=True)
for k in (16, 32):
    for c in ("ndvi", "ndmi"):
        prev = df.groupby(["cell_id", "season"])[c].shift(k)  # rows are daily within a season
        df[f"{c}_chg{k}"] = df[c] - prev
LEAF = ["ndvi_peak", "leaf_loss", "ndvi_chg16", "ndvi_chg32", "ndmi_chg16", "ndmi_chg32"]
year = df.date.dt.year.to_numpy()

P = dict(objective="binary", learning_rate=0.05, num_leaves=63, min_data_in_leaf=200, feature_fraction=0.7,
         bagging_fraction=0.8, bagging_freq=1, lambda_l2=5, verbose=-1, seed=0)
rng = np.random.default_rng(0)
neg = rng.random(len(df)) < 0.10


def caught(sub, flag, ycol):
    """recall with 3x3 tolerance against label ycol; returns per-row caught flags."""
    out = np.zeros(len(sub), bool)
    for _, idx in sub.groupby("date").indices.items():
        g = sub.iloc[idx]
        r = np.zeros((NI, NJ), bool); r[g.i, g.j] = flag[idx]
        out[idx] = maximum_filter(r, 3)[g.i, g.j]
    return out


def loyo(cols, ycol, tag):
    rows = []
    for yv in range(2013, 2025):
        trm = (year != yv) & ((df[ycol] == 1).to_numpy() | neg)
        b = lgb.train(P, lgb.Dataset(df.loc[trm, cols], df.loc[trm, ycol]), 200)
        te = year == yv
        sub = df[te]
        s = b.predict(sub[cols])
        flag = s >= np.quantile(s, 0.90)
        c = caught(sub, flag, ycol)
        p = sub[ycol].to_numpy() == 1
        new = p & (sub.cls.to_numpy() == "new") if ycol == "y" else np.zeros_like(p)
        rows.append(dict(exp=tag, year=yv, n_pos=int(p.sum()), base_rate=p.mean(), recall=c[p].mean(),
                         precision_strict=p[flag].mean(), n_new=int(new.sum()),
                         recall_new=c[new].mean() if new.any() else np.nan))
        print(tag, rows[-1], flush=True)
    return rows


rows = []
for h in H:
    rows += loyo(BASE, f"y_{h}", f"horizon {h}")
rows += loyo(BASE + LEAF, "y", "leaf-fall (+6 feats), t+1..t+2")
R5 = pd.DataFrame(rows)
R5.to_csv(OUT / "r5_loyo.csv", index=False)
S = R5.groupby("exp").apply(lambda g: pd.Series(dict(
    base_rate_pct=100 * np.average(g.base_rate, weights=np.ones(len(g))),
    recall=np.average(g.recall, weights=g.n_pos),
    precision_strict=np.average(g.precision_strict, weights=g.n_pos),
    lift=np.average(g.precision_strict / g.base_rate, weights=g.n_pos),
    recall_new=np.average(g.recall_new.fillna(0), weights=g.n_new) if g.n_new.sum() else np.nan)), include_groups=False).round(3)
S.to_csv(OUT / "r5_summary.csv")
print(S.to_string())
