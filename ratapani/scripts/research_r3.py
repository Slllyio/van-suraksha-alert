"""Research round 3 (Ratapani, 2-day outlook, 500 m).
A. What kind of fire are we asked to predict? Each next-2-day fire cell is classed by what was burning nearby
   in the 7 days before issue: 'continuation' (fire within 1.5 km in last 3 d), 'nearby' (within 5 km, last 7 d), 'new'.
B. Leave-one-year-out (12 folds) feature-group ablation, so results don't hinge on two quiet test years.
Metrics (3x3 = 1.5 km tolerance): recall when flagging 10% of cells every day ('fixed') and when flagging the top
10% of all cell-days of the season pooled ('dynamic'); recall split by fire class; strict PR-AUC."""
import json, time
from pathlib import Path
import numpy as np
import pandas as pd
import lightgbm as lgb
from scipy.ndimage import maximum_filter
from sklearn.metrics import average_precision_score

M = Path(r"E:\FIRE\ratapani\model")
OUT = M / "r3"
OUT.mkdir(exist_ok=True)
df = pd.read_parquet(M / "celldays_v2.parquet")
FUT = set(pd.read_csv(M / "future_weather_cols.csv", header=None)[0])
NI, NJ = df.i.max() + 1, df.j.max() + 1
year = df.date.dt.year.to_numpy()

# ---------- A: fire classes ----------
cls = np.full(len(df), "", object)
pos = df.y.to_numpy() == 1
cls[pos & (df.fdist_d3 <= 1.5)] = "continuation"
cls[pos & (cls == "") & (df.fdist_d7 <= 5)] = "nearby"
cls[pos & (cls == "")] = "new"
df["cls"] = cls
A = pd.crosstab(year[pos], cls[pos], normalize="index").round(3)
A["n_fire_celldays"] = pd.Series(year[pos]).value_counts().sort_index().to_numpy()
print(A.to_string())

# ---------- B: feature groups ----------
c = set(df.columns) - {"date", "cell_id", "y", "y3", "i", "j", "cls"}
G = {}
G["fire"] = sorted(x for x in c if x.startswith(("cell_d", "nb", "aoi_", "clim_", "fdist_")) or x in ("dsl", "doy", "spread_slope"))
G["static"] = sorted(x for x in c if x.startswith(("elev", "slope", "wc_", "pop", "dist_", "depth_")) or x == "forest_frac")
G["modis"] = sorted(x for x in c if x.startswith(("ndvi", "ndmi", "lst")))
G["alphaearth"] = sorted(x for x in c if x.startswith("ae"))
G["weather"] = sorted(x for x in c - FUT if x not in sum(G.values(), []))
G["fcst_weather"] = sorted(c & FUT)
assert not (c - set(sum(G.values(), []))), c - set(sum(G.values(), []))
SETS = {
    "1_fire": ["fire"],
    "2_+static": ["fire", "static"],
    "3_+modis": ["fire", "static", "modis"],
    "4_+alphaearth": ["fire", "static", "modis", "alphaearth"],
    "5_+weather": ["fire", "static", "modis", "alphaearth", "weather"],
    "6_+fcst_weather": ["fire", "static", "modis", "alphaearth", "weather", "fcst_weather"],
}
P = dict(objective="binary", learning_rate=0.05, num_leaves=63, min_data_in_leaf=200, feature_fraction=0.7,
         bagging_fraction=0.8, bagging_freq=1, lambda_l2=5, verbose=-1, seed=0)
rng = np.random.default_rng(0)
neg_keep = rng.random(len(df)) < 0.10


def tol_scores(sub, flag):
    """recall (3x3) overall and by class, precision (flag has y3 fire)."""
    caught = np.zeros(len(sub), bool)
    for _, idx in sub.groupby("date").indices.items():
        g = sub.iloc[idx]
        r = np.zeros((NI, NJ), bool); r[g.i, g.j] = flag[idx]
        caught[idx] = maximum_filter(r, 3)[g.i, g.j]
    p = sub.y.to_numpy() == 1
    out = dict(recall=round(caught[p].mean(), 3), precision=round(sub.y3.to_numpy()[flag].mean(), 3))
    for k in ("continuation", "nearby", "new"):
        m = p & (sub.cls.to_numpy() == k)
        out[f"recall_{k}"] = round(caught[m].mean(), 3) if m.any() else None
    return out


rows, preds = [], {}
for name, groups in SETS.items():
    cols = sum((G[g] for g in groups), [])
    oof = np.zeros(len(df), np.float32)
    for yv in range(2013, 2025):
        t0 = time.time()
        trm = (year != yv) & ((df.y.to_numpy() == 1) | neg_keep)
        b = lgb.train(P, lgb.Dataset(df.loc[trm, cols], df.y[trm]), 200)
        te = year == yv
        s = b.predict(df.loc[te, cols]).astype(np.float32)
        oof[te] = s
        sub = df[te]
        rank_day = sub.assign(s=s).groupby("date").s.rank(ascending=False, method="first").to_numpy()
        fixed = rank_day <= round(0.10 * 3614)
        dyn = s >= np.quantile(s, 0.90)
        rows.append(dict(set=name, year=yv, n_fire=int(sub.y.sum()),
                         pr_auc=round(average_precision_score(sub.y, s), 4) if sub.y.sum() else None,
                         **{f"fixed_{k}": v for k, v in tol_scores(sub, fixed).items()},
                         **{f"dyn_{k}": v for k, v in tol_scores(sub, dyn).items()}))
        print(name, yv, f"{time.time() - t0:.0f}s", rows[-1], flush=True)
    preds[name] = oof
    pd.DataFrame(rows).to_csv(OUT / "loyo_ablation.csv", index=False)

R = pd.DataFrame(rows)
# fire-weighted mean over years (each fire cell-day counts once)
num = [x for x in R.columns if x.startswith(("fixed_", "dyn_", "pr_auc"))]
summ = R.groupby("set").apply(lambda g: pd.Series({k: np.average(g[k].astype(float), weights=g.n_fire) for k in num}))
summ.round(3).to_csv(OUT / "loyo_summary.csv")
A.to_csv(OUT / "fire_classes_by_year.csv")
df[["date", "cell_id", "y", "y3", "cls"]].assign(**{k: v for k, v in preds.items()}).to_parquet(OUT / "oof_preds.parquet")
G_out = {k: v for k, v in G.items()}
(OUT / "feature_groups.json").write_text(json.dumps(G_out, indent=1))
print(summ.round(3).to_string())
