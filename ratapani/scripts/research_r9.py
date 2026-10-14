"""Research round 9: do standard Canadian FWI indices (from ERA5-Land 06 UTC = 11:30 IST + daily rain) add skill
over the raw weather features? LOYO, large LightGBM (255 leaves x 600), features = r3 set 5 + leaf-fall."""
import json, sys, time
from pathlib import Path
import numpy as np
import pandas as pd
import lightgbm as lgb
from scipy.ndimage import maximum_filter

sys.path.insert(0, r"E:\FIRE\.claude\worktrees\stoic-lumiere-ab3144\scripts")
from compute_fwi import compute_fwi_series  # repo implementation (Van Wagner 1987)

R = Path(r"E:\FIRE\ratapani"); M = R / "model"; OUT = M / "r9"; OUT.mkdir(exist_ok=True)

# ---- FWI from ERA5-Land ----
h = pd.read_csv(R / "ee" / "era5land_06utc.csv"); h["date"] = pd.to_datetime(h.time.str[:10])
d = pd.read_csv(R / "ee" / "era5land_daily.csv"); d["date"] = pd.to_datetime(d.time.str[:10])
es = lambda t: 0.6108 * np.exp(17.27 * t / (t + 237.3))
w = h[["date"]].copy()
w["temp_c"] = h.temperature_2m - 273.15
w["rh_pct"] = 100 * es(h.dewpoint_temperature_2m - 273.15) / es(w.temp_c)
w["wind_kmh"] = np.hypot(h.u_component_of_wind_10m, h.v_component_of_wind_10m) * 3.6
w = w.merge(d[["date", "total_precipitation_sum"]], on="date")
w["precip_mm"] = (w.pop("total_precipitation_sum") * 1000).clip(lower=0)
fwi = compute_fwi_series(w)[["date", "ffmc", "dmc", "dc", "isi", "bui", "fwi"]]
fwi["date"] = pd.to_datetime(fwi.date)
fwi["fwi_3"] = fwi.fwi.rolling(3, min_periods=1).mean()
fwi["fwi_rank_doy"] = fwi.groupby(fwi.date.dt.dayofyear // 7).fwi.rank(pct=True)  # how extreme for the week of year
fwi.to_csv(R / "ee" / "fwi_era5.csv", index=False)
FWI = [c for c in fwi.columns if c != "date"]
print(fwi.describe().round(1).to_string())

# ---- data + leaf features (as r8) ----
df = pd.read_parquet(M / "celldays_v2.parquet")
df["cls"] = pd.read_parquet(M / "r3" / "oof_preds.parquet", columns=["cls"])["cls"].to_numpy()
G = json.loads((M / "r3" / "feature_groups.json").read_text())
m = pd.read_csv(R / "ee" / "modis_ndvi_ndmi.csv", parse_dates=["date"]); m = m[m.date.dt.month >= 9]
peak = m.groupby([m.date.dt.year + 1, "cell_id"]).ndvi.quantile(0.9).rename("ndvi_peak"); peak.index.names = ["season", "cell_id"]
df["season"] = df.date.dt.year
df = df.join(peak, on=["season", "cell_id"]); df["leaf_loss"] = 1 - df.ndvi / df.ndvi_peak
df = df.sort_values(["cell_id", "date"]).reset_index(drop=True)
for k in (16, 32):
    for c in ("ndvi", "ndmi"):
        df[f"{c}_chg{k}"] = df[c] - df.groupby(["cell_id", "season"])[c].shift(k)
df = df.merge(fwi, on="date", how="left")
LEAF = ["ndvi_peak", "leaf_loss", "ndvi_chg16", "ndvi_chg32", "ndmi_chg16", "ndmi_chg32"]
BASE = sum((G[g] for g in ["fire", "static", "modis", "alphaearth", "weather"]), []) + LEAF
year = df.date.dt.year.to_numpy(); NI, NJ = df.i.max() + 1, df.j.max() + 1
neg = np.random.default_rng(0).random(len(df)) < 0.10; ypos = (df.y == 1).to_numpy()
P = dict(objective="binary", feature_fraction=0.7, bagging_fraction=0.8, bagging_freq=1, verbose=-1, seed=0,
         num_leaves=255, min_data_in_leaf=100, learning_rate=0.03, lambda_l2=5)


def score(sub, s):
    flag = s >= np.quantile(s, 0.90); c = np.zeros(len(sub), bool)
    for _, idx in sub.groupby("date").indices.items():
        g = sub.iloc[idx]; r = np.zeros((NI, NJ), bool); r[g.i, g.j] = flag[idx]
        c[idx] = maximum_filter(r, 3)[g.i, g.j]
    p = sub.y.to_numpy() == 1; new = p & (sub.cls.to_numpy() == "new")
    return dict(n_pos=int(p.sum()), n_new=int(new.sum()), recall=c[p].mean(), recall_new=c[new].mean() if new.any() else np.nan)


rows = []
for tag, cols in [("base (+leaf)", BASE), ("base + FWI", BASE + FWI), ("base - raw weather + FWI", [c for c in BASE if c not in G["weather"]] + FWI)]:
    for yv in range(2013, 2025):
        t0 = time.time(); tr = (year != yv) & (ypos | neg); te = year == yv
        s = lgb.train(P, lgb.Dataset(df.loc[tr, cols], df.y[tr]), 600).predict(df.loc[te, cols])
        rows.append(dict(exp=tag, fold=yv, **score(df[te], s)))
        print(tag, yv, round(rows[-1]["recall"], 3), f"{time.time() - t0:.0f}s", flush=True)
R9 = pd.DataFrame(rows); R9.to_csv(OUT / "r9_folds.csv", index=False)
S = R9.groupby("exp").apply(lambda g: pd.Series(dict(recall=np.average(g.recall, weights=g.n_pos),
        recall_new=np.average(g.recall_new.fillna(0), weights=g.n_new), recall_min=g.recall.min())), include_groups=False).round(3)
S.to_csv(OUT / "r9_summary.csv"); print(S.to_string())
