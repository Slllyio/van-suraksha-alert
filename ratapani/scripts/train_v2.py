"""v2: (a) AOI-wide 2-day alert level + dynamic patrol area, (b) access/proximity + nearest-recent-fire + spread
features, (c) 3x3 (1.5 km) tolerance as the headline metric. Model choice is made on 2021-22; 2023-24 is test."""
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

yr = df.date.dt.year
tr, va, te = yr <= 2020, yr.between(2021, 2022), yr >= 2023
DROP = {"date", "cell_id", "y", "y3", "i", "j"}
ALL = [c for c in df.columns if c not in DROP]
NOFUT = [c for c in ALL if c not in FUT]
rng = np.random.default_rng(0)
P = dict(objective="binary", learning_rate=0.03, num_leaves=63, min_data_in_leaf=200, feature_fraction=0.7,
         bagging_fraction=0.8, bagging_freq=1, lambda_l2=5, verbose=-1, seed=0)


def train(cols, label, rows):
    keep = rows & ((df[label] == 1) | (rng.random(len(df)) < 0.15))
    return keep


def fit(cols, label):
    k = train(cols, label, tr)
    b = lgb.train(P | {"metric": "average_precision"}, lgb.Dataset(df.loc[k, cols], df.loc[k, label]), 3000,
                  valid_sets=[lgb.Dataset(df.loc[va, cols], df.loc[va, label])],
                  callbacks=[lgb.early_stopping(150, verbose=False)])
    k2 = train(cols, label, tr | va)
    b2 = lgb.train(P, lgb.Dataset(df.loc[k2, cols], df.loc[k2, label]), b.best_iteration)
    return b, b2


def tol_eval(sub, s, flag_fn):
    """Headline metric. recall = fire cells (next 2 days) with a flagged cell within 1 cell;
    precision = flagged cells with a fire within 1 cell."""
    caught = npos = hits = nflag = 0
    per_day = []
    for d, g in sub.assign(s=s).groupby("date"):
        flag = flag_fn(g)
        fr = np.zeros((NI, NJ), bool); fr[g.i, g.j] = flag
        near = maximum_filter(fr, 3)[g.i, g.j]
        pos = g.y.to_numpy() == 1
        caught += (pos & near).sum(); npos += pos.sum()
        hits += (flag & (g.y3.to_numpy() == 1)).sum(); nflag += flag.sum()
        per_day.append(flag.mean())
    return dict(recall=round(caught / max(npos, 1), 3), precision=round(hits / max(nflag, 1), 3),
                mean_area_pct=round(100 * np.mean(per_day), 1), max_area_pct=round(100 * np.max(per_day), 1))


def topk(b):
    return lambda g: g.s.rank(ascending=False, method="first").to_numpy() <= round(b * len(g))


def evaluate(name, b, b2, cols):
    sv, st = b.predict(df.loc[va, cols]), b2.predict(df.loc[te, cols])
    vsub, tsub = df[va], df[te]
    out = dict(val_tol_recall_top10=tol_eval(vsub, sv, topk(0.10))["recall"],
               test_pr_auc_strict=round(average_precision_score(tsub.y, st), 4),
               test_roc_auc=round(roc_auc_score(tsub.y, st), 3))
    out["fixed_area"] = {f"top{int(x*100)}%": tol_eval(tsub, st, topk(x)) for x in (0.02, 0.05, 0.10)}
    # (a) dynamic area: one probability threshold, set on 2021-22 so the AVERAGE flagged area is 5% / 10%
    out["dynamic_area"] = {}
    for x in (0.05, 0.10):
        thr = np.quantile(sv, 1 - x)
        out["dynamic_area"][f"avg{int(x*100)}%"] = dict(threshold=float(thr), **tol_eval(tsub, st, lambda g, t=thr: g.s.to_numpy() >= t))
    print(name, json.dumps(out))
    return out, st


res, scores = {}, {}
for name, cols, label in [("v2_strict_label", NOFUT, "y"), ("v2_smoothed_label", NOFUT, "y3"),
                          ("v2_smoothed_label_fcst_wx", ALL, "y3")]:
    b, b2 = fit(cols, label)
    res[name], scores[name] = evaluate(name, b, b2, cols)
    imp = pd.Series(b2.feature_importance("gain"), index=cols).sort_values(ascending=False)
    res[name]["top_features"] = (imp / imp.sum()).round(3).head(12).to_dict()
    b2.save_model(str(M / f"{name}.txt"))

# ---------- (a) AOI-wide alert: will there be ANY fire in the sanctuary on t+1..t+2? ----------
day = df.groupby("date").agg(y=("y", "max"), n=("y", "sum"), **{c: (c, "first") for c in
      ["aoi_d1", "aoi_d3", "aoi_d7", "doy"] + [c for c in df.columns if c in
       ("tmax", "rh", "vpd_max", "wind", "prcp_7", "prcp_30", "dry_days", "vpd_3", "swvl1")]}).reset_index()
dy = day.date.dt.year
dcols = [c for c in day.columns if c not in ("date", "y", "n")]
ab = lgb.train(P | {"num_leaves": 15, "min_data_in_leaf": 20}, lgb.Dataset(day.loc[dy <= 2022, dcols], day.loc[dy <= 2022, "y"]), 300)
pd_ = ab.predict(day.loc[dy >= 2023, dcols]); dt = day[dy >= 2023]
lv = pd.cut(pd_, [-1, 0.3, 0.7, 2], labels=["normal", "high", "very_high"])
alert = dict(test_days=len(dt), test_roc_auc=round(roc_auc_score(dt.y, pd_), 3),
             levels={str(l): dict(days=int((lv == l).sum()), days_with_fire_pct=round(100 * dt.y[lv == l].mean(), 1),
                                  share_of_all_fire_cells_pct=round(100 * dt.n[lv == l].sum() / dt.n.sum(), 1))
                     for l in ["normal", "high", "very_high"]})
res["aoi_alert"] = alert
ab.save_model(str(M / "aoi_alert.txt"))
print("alert", json.dumps(alert))

(M / "results_v2.json").write_text(json.dumps(res, indent=2))
for f in ("train_v2.py", "ee_proximity.py"):
    shutil.copy(Path(__file__).with_name(f), M / f)
