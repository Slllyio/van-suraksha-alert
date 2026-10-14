"""Research round 6.
(e) Spatial transfer: hold out one of 6 west-to-east blocks (all years), train on the rest. If recall holds up,
    the model is learning transferable fire behaviour rather than memorising Ratapani's hot spots.
(f) Model family (LOYO): logistic regression vs LightGBM small / default / large.
Metric: recall with 3x3 tolerance when flagging the top 10% of cell-days of each held-out set (pooled)."""
import json, time
from pathlib import Path
import numpy as np
import pandas as pd
import lightgbm as lgb
from scipy.ndimage import maximum_filter
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.impute import SimpleImputer

M = Path(r"E:\FIRE\ratapani\model")
OUT = M / "r6"
OUT.mkdir(exist_ok=True)
df = pd.read_parquet(M / "celldays_v2.parquet")
df["cls"] = pd.read_parquet(M / "r3" / "oof_preds.parquet", columns=["cls"])["cls"].to_numpy()
G = json.loads((M / "r3" / "feature_groups.json").read_text())
COLS = sum((G[g] for g in ["fire", "static", "modis", "alphaearth", "weather"]), [])
NO_CLIM = [c for c in COLS if not c.startswith("clim_")]  # cell climatology is location memory
NI, NJ = df.i.max() + 1, df.j.max() + 1
year = df.date.dt.year.to_numpy()
block = pd.qcut(df.j, 6, labels=False).to_numpy()  # 6 west-to-east strips with equal cell counts
rng = np.random.default_rng(0)
neg = rng.random(len(df)) < 0.10
P = dict(objective="binary", learning_rate=0.05, num_leaves=63, min_data_in_leaf=200, feature_fraction=0.7,
         bagging_fraction=0.8, bagging_freq=1, lambda_l2=5, verbose=-1, seed=0)


def score(sub, s):
    flag = s >= np.quantile(s, 0.90)
    caught = np.zeros(len(sub), bool)
    for _, idx in sub.groupby("date").indices.items():
        g = sub.iloc[idx]
        r = np.zeros((NI, NJ), bool); r[g.i, g.j] = flag[idx]
        caught[idx] = maximum_filter(r, 3)[g.i, g.j]
    p = sub.y.to_numpy() == 1
    new = p & (sub.cls.to_numpy() == "new")
    return dict(n_pos=int(p.sum()), n_new=int(new.sum()), recall=caught[p].mean(),
                recall_new=caught[new].mean() if new.any() else np.nan, precision_strict=p[flag].mean())


def fit_predict(kind, tr, te, cols):
    X, y = df.loc[tr, cols], df.y[tr]
    if kind == "logistic":
        mdl = make_pipeline(SimpleImputer(strategy="median"), StandardScaler(), LogisticRegression(C=0.1, max_iter=500))
        mdl.fit(X, y)
        return mdl.predict_proba(df.loc[te, cols])[:, 1]
    p, n = {"lgbm_small": (P | {"num_leaves": 15, "min_data_in_leaf": 500}, 200),
            "lgbm_default": (P, 200),
            "lgbm_large": (P | {"num_leaves": 255, "min_data_in_leaf": 100, "learning_rate": 0.03}, 600)}[kind]
    return lgb.train(p, lgb.Dataset(X, y), n).predict(df.loc[te, cols])


rows = []
# (e) spatial blocks
for tag, cols in [("spatial_block, all feats", COLS), ("spatial_block, no cell climatology", NO_CLIM)]:
    for b in range(6):
        t0 = time.time()
        tr = (block != b) & ((df.y == 1).to_numpy() | neg)
        te = block == b
        rows.append(dict(exp=tag, fold=f"block{b}", **score(df[te], fit_predict("lgbm_default", tr, te, cols))))
        print(rows[-1], f"{time.time() - t0:.0f}s", flush=True)
# matching LOYO reference restricted to the same metric
for kind in ["logistic", "lgbm_small", "lgbm_default", "lgbm_large"]:
    for yv in range(2013, 2025):
        t0 = time.time()
        tr = (year != yv) & ((df.y == 1).to_numpy() | neg)
        te = year == yv
        rows.append(dict(exp=f"LOYO {kind}", fold=str(yv), **score(df[te], fit_predict(kind, tr, te, COLS))))
        print(rows[-1], f"{time.time() - t0:.0f}s", flush=True)

R6 = pd.DataFrame(rows)
R6.to_csv(OUT / "r6_folds.csv", index=False)
S = R6.groupby("exp").apply(lambda g: pd.Series(dict(
    recall=np.average(g.recall, weights=g.n_pos),
    recall_new=np.average(g.recall_new.fillna(0), weights=g.n_new),
    precision_strict=np.average(g.precision_strict, weights=g.n_pos),
    recall_min_fold=g.recall.min(), recall_max_fold=g.recall.max())), include_groups=False).round(3)
S.to_csv(OUT / "r6_summary.csv")
print(S.to_string())
