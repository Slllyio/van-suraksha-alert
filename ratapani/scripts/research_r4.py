"""Research round 4.
1. Label quality of 'new' fires: are brand-new fire cell-days mostly single, low-confidence, low-FRP VIIRS pixels
   (likely small/brief burns or false alarms) compared with continuing fires?
2. Dedicated new-ignition model (LOYO): trained only on 'new' positives; does it catch new fires better than the
   all-fires model at the same flagged area, and does a blend help overall?"""
from pathlib import Path
import numpy as np
import pandas as pd
import geopandas as gpd
import lightgbm as lgb
from scipy.ndimage import maximum_filter

R = Path(r"E:\FIRE\ratapani")
M = R / "model"
OUT = M / "r4"
OUT.mkdir(exist_ok=True)
df = pd.read_parquet(M / "celldays_v2.parquet")
oof = pd.read_parquet(M / "r3" / "oof_preds.parquet")
df["cls"] = oof["cls"].to_numpy()
df["s_all"] = oof["5_+weather"].to_numpy()  # best no-forecast set from r3
NI, NJ = df.i.max() + 1, df.j.max() + 1
year = df.date.dt.year.to_numpy()

# ---------- 1. what do the detections behind each fire class look like? ----------
grid = gpd.read_file(R / "grid_500m.geojson")[["cell_id", "geometry"]]
v = pd.read_parquet(R / "viirs_snpp_2013_2024.parquet")
v = v[v.type == 0]
utc = pd.to_datetime(v.acq_date) + pd.to_timedelta(v.acq_time // 100, "h") + pd.to_timedelta(v.acq_time % 100, "m")
v["ldate"] = (utc + pd.Timedelta(hours=5, minutes=30)).dt.normalize()
pts = gpd.sjoin(gpd.GeoDataFrame(v, geometry=gpd.points_from_xy(v.longitude, v.latitude), crs=4326), grid, predicate="within")
cd = pts.groupby(["ldate", "cell_id"]).agg(n_pix=("frp", "size"), frp_max=("frp", "max"),
                                           low_conf=("confidence", lambda s: (s == "l").all()),
                                           night=("daynight", lambda s: (s == "N").any())).reset_index()
# class of each fire cell-day = class assigned at issue days t = d-1 and d-2 (take the 'most continuing')
lab = df.loc[df.y == 1, ["date", "cell_id", "cls"]]
rank = {"continuation": 0, "nearby": 1, "new": 2}
rows = []
for lag in (1, 2):
    x = lab.copy(); x["ldate"] = x.date + pd.Timedelta(days=lag); rows.append(x)
lab2 = pd.concat(rows)
lab2 = cd.merge(lab2, on=["ldate", "cell_id"])
lab2["r"] = lab2.cls.map(rank)
lab2 = lab2.sort_values("r").drop_duplicates(["ldate", "cell_id"])
# did the same cell or a neighbour burn again within the next 3 days? (a real, persistent fire)
fire = set(zip(cd.ldate, cd.cell_id))
g = grid.merge(gpd.read_file(R / "grid_500m.geojson")[["cell_id", "i", "j"]], on="cell_id")
ij = dict(zip(g.cell_id, zip(g.i, g.j)))
cid = {v_: k for k, v_ in ij.items()}
def redetected(row):
    i, j = ij[row.cell_id]
    for dd in (1, 2, 3):
        d = row.ldate + pd.Timedelta(days=dd)
        for di in (-1, 0, 1):
            for dj in (-1, 0, 1):
                c = cid.get((i + di, j + dj))
                if c is not None and (d, c) in fire:
                    return True
    return False
lab2["redetected_3d"] = lab2.apply(redetected, axis=1)
T1 = lab2.groupby("cls").agg(fire_celldays=("cell_id", "size"), single_pixel=("n_pix", lambda s: (s == 1).mean()),
                             all_low_conf=("low_conf", "mean"), frp_median=("frp_max", "median"),
                             night_seen=("night", "mean"), burns_again_within_3d=("redetected_3d", "mean")).round(3)
print(T1.to_string())
T1.to_csv(OUT / "new_fire_label_quality.csv")

# ---------- 2. dedicated new-ignition model ----------
FUT = set(pd.read_csv(M / "future_weather_cols.csv", header=None)[0])
cols = [c for c in df.columns if c not in {"date", "cell_id", "y", "y3", "i", "j", "cls", "s_all"} | FUT]
df["y_new"] = ((df.y == 1) & (df.cls == "new")).astype(np.uint8)
# training rows for the new-fire model: only "quiet" contexts (no fire within 5 km in the last 7 days)
quiet = (df.fdist_d7 > 5).to_numpy()
P = dict(objective="binary", learning_rate=0.05, num_leaves=31, min_data_in_leaf=300, feature_fraction=0.7,
         bagging_fraction=0.8, bagging_freq=1, lambda_l2=10, verbose=-1, seed=0)
rng = np.random.default_rng(1)
neg = rng.random(len(df)) < 0.10
s_new = np.zeros(len(df), np.float32)
for yv in range(2013, 2025):
    trm = (year != yv) & quiet & ((df.y_new == 1).to_numpy() | neg)
    b = lgb.train(P, lgb.Dataset(df.loc[trm, cols], df.y_new[trm]), 200)
    te = year == yv
    s_new[te] = b.predict(df.loc[te, cols])
    if yv == 2024:
        imp = pd.Series(b.feature_importance("gain"), index=cols).sort_values(ascending=False)
        (imp / imp.sum()).round(3).head(15).to_csv(OUT / "new_model_top_features.csv")
df["s_new"] = s_new


def caught(sub, flag):
    out = np.zeros(len(sub), bool)
    for _, idx in sub.groupby("date").indices.items():
        g_ = sub.iloc[idx]
        r = np.zeros((NI, NJ), bool); r[g_.i, g_.j] = flag[idx]
        out[idx] = maximum_filter(r, 3)[g_.i, g_.j]
    return out


def rank_pct(x):  # within-year percentile rank, so different models are on one scale
    return pd.Series(x).rank(pct=True).to_numpy()


res = []
for yv in range(2013, 2025):
    sub = df[year == yv].reset_index(drop=True)
    p = sub.y.to_numpy() == 1
    isnew = p & (sub.cls.to_numpy() == "new")
    ra, rn = rank_pct(sub.s_all.to_numpy()), rank_pct(np.where(sub.fdist_d7 > 5, sub.s_new, 0))
    variants = {"all_fires_model": ra,
                "new_model_only": rn,
                # blend: keep 8% for the all-fires model, give 2% to the new-ignition model in quiet areas
                "blend_8+2": np.maximum(np.where(ra >= 0.92, 1, 0), np.where(rn >= 0.98, 1, 0))}
    for k, sc in variants.items():
        flag = sc >= np.quantile(sc, 0.90) if k != "blend_8+2" else sc.astype(bool)
        c = caught(sub, flag)
        res.append(dict(year=yv, variant=k, area_pct=round(100 * flag.mean(), 1), n_fire=int(p.sum()), n_new=int(isnew.sum()),
                        recall_all=c[p].mean(), recall_new=c[isnew].mean() if isnew.any() else np.nan))
R4 = pd.DataFrame(res)
R4.to_csv(OUT / "new_model_loyo.csv", index=False)
S = R4.groupby("variant").apply(lambda g: pd.Series(dict(
    area_pct=g.area_pct.mean(),
    recall_all=np.average(g.recall_all, weights=g.n_fire),
    recall_new=np.average(g.recall_new.fillna(0), weights=g.n_new)))).round(3)
S.to_csv(OUT / "new_model_summary.csv")
print(S.to_string())
print(pd.read_csv(OUT / "new_model_top_features.csv").to_string())
