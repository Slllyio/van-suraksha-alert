"""Research round 8 (features = r3 set 5 + leaf-fall from r5).
1. Capacity sweep (LOYO): large LightGBM configs -> where does it stop improving?
2. Strict transfer: hold out a west-to-east strip AND a 3-year block together (train never sees either).
3. Calibration of the best LOYO model: predicted risk vs observed fire rate (after undoing the 10% negative sampling)."""
import json, time
from pathlib import Path
import numpy as np
import pandas as pd
import lightgbm as lgb
from scipy.ndimage import maximum_filter
from sklearn.metrics import brier_score_loss

M = Path(r"E:\FIRE\ratapani\model")
OUT = M / "r8"; OUT.mkdir(exist_ok=True)
df = pd.read_parquet(M / "celldays_v2.parquet")
df["cls"] = pd.read_parquet(M / "r3" / "oof_preds.parquet", columns=["cls"])["cls"].to_numpy()
G = json.loads((M / "r3" / "feature_groups.json").read_text())
year = df.date.dt.year.to_numpy()

# leaf-fall features (same as r5)
m = pd.read_csv(Path(r"E:\FIRE\ratapani\ee\modis_ndvi_ndmi.csv"), parse_dates=["date"])
m = m[m.date.dt.month >= 9]
peak = m.groupby([m.date.dt.year + 1, "cell_id"]).ndvi.quantile(0.9).rename("ndvi_peak")
peak.index.names = ["season", "cell_id"]
df["season"] = year
df = df.join(peak, on=["season", "cell_id"])
df["leaf_loss"] = 1 - df.ndvi / df.ndvi_peak
df = df.sort_values(["cell_id", "date"]).reset_index(drop=True)
for k in (16, 32):
    for c in ("ndvi", "ndmi"):
        df[f"{c}_chg{k}"] = df[c] - df.groupby(["cell_id", "season"])[c].shift(k)
LEAF = ["ndvi_peak", "leaf_loss", "ndvi_chg16", "ndvi_chg32", "ndmi_chg16", "ndmi_chg32"]
COLS = sum((G[g] for g in ["fire", "static", "modis", "alphaearth", "weather"]), []) + LEAF
year = df.date.dt.year.to_numpy()
NI, NJ = df.i.max() + 1, df.j.max() + 1
block = pd.qcut(df.j, 6, labels=False).to_numpy()
NEG_RATE = 0.10
neg = np.random.default_rng(0).random(len(df)) < NEG_RATE
ypos = (df.y == 1).to_numpy()
B = dict(objective="binary", feature_fraction=0.7, bagging_fraction=0.8, bagging_freq=1, verbose=-1, seed=0)
CONFIGS = {
    "large_255x600": (B | dict(num_leaves=255, min_data_in_leaf=100, learning_rate=0.03, lambda_l2=5), 600),
    "xl_511x1000": (B | dict(num_leaves=511, min_data_in_leaf=50, learning_rate=0.02, lambda_l2=10), 1000),
    "deep_255x1500_slow": (B | dict(num_leaves=255, min_data_in_leaf=100, learning_rate=0.01, lambda_l2=5), 1500),
}


def score(sub, s):
    flag = s >= np.quantile(s, 0.90)
    c = np.zeros(len(sub), bool)
    for _, idx in sub.groupby("date").indices.items():
        g = sub.iloc[idx]; r = np.zeros((NI, NJ), bool); r[g.i, g.j] = flag[idx]
        c[idx] = maximum_filter(r, 3)[g.i, g.j]
    p = sub.y.to_numpy() == 1; new = p & (sub.cls.to_numpy() == "new")
    return dict(n_pos=int(p.sum()), n_new=int(new.sum()), recall=c[p].mean(),
                recall_new=c[new].mean() if new.any() else np.nan)


def summarise(R):
    return R.groupby("exp").apply(lambda g: pd.Series(dict(
        recall=np.average(g.recall, weights=g.n_pos), recall_new=np.average(g.recall_new.fillna(0), weights=g.n_new),
        recall_min=g.recall.min(), recall_max=g.recall.max(), folds=len(g))), include_groups=False).round(3)


rows, oof = [], {}
for name, (p, n) in CONFIGS.items():
    o = np.zeros(len(df), np.float32)
    for yv in range(2013, 2025):
        t0 = time.time()
        tr = (year != yv) & (ypos | neg); te = year == yv
        o[te] = lgb.train(p, lgb.Dataset(df.loc[tr, COLS], df.y[tr]), n).predict(df.loc[te, COLS])
        rows.append(dict(exp=f"LOYO {name} +leaf", fold=yv, **score(df[te], o[te])))
        print(rows[-1]["exp"], yv, round(rows[-1]["recall"], 3), f"{time.time() - t0:.0f}s", flush=True)
    oof[name] = o
    pd.DataFrame(rows).to_csv(OUT / "r8_folds.csv", index=False)
S1 = summarise(pd.DataFrame(rows)); print(S1.to_string(), flush=True)
best = S1.recall.idxmax().replace("LOYO ", "").replace(" +leaf", "")

# 2. strict transfer: unseen strip x unseen 3-year block
p, n = CONFIGS[best]
for yb in [(2013, 2015), (2016, 2018), (2019, 2021), (2022, 2024)]:
    yin = (year >= yb[0]) & (year <= yb[1])
    for b in range(6):
        t0 = time.time()
        tr = (block != b) & ~yin & (ypos | neg); te = (block == b) & yin
        s = lgb.train(p, lgb.Dataset(df.loc[tr, COLS], df.y[tr]), n).predict(df.loc[te, COLS])
        rows.append(dict(exp=f"strict strip+years {best}", fold=f"b{b}_{yb[0]}-{yb[1]}", **score(df[te], s)))
        print(rows[-1]["exp"], rows[-1]["fold"], round(rows[-1]["recall"], 3), f"{time.time() - t0:.0f}s", flush=True)
R = pd.DataFrame(rows); R.to_csv(OUT / "r8_folds.csv", index=False)
S = summarise(R); S.to_csv(OUT / "r8_summary.csv"); print(S.to_string())

# 3. calibration of best LOYO model: undo negative subsampling q = p*r / (p*r + 1 - p)
pr = oof[best].astype(float)
q = pr * NEG_RATE / (pr * NEG_RATE + 1 - pr)
bins = pd.cut(q, [0, 0.001, 0.003, 0.01, 0.03, 0.1, 0.3, 1], include_lowest=True)
cal = pd.DataFrame({"bin": bins, "q": q, "y": df.y.to_numpy(), "y3": df.y3.to_numpy()}).groupby("bin", observed=True).agg(
    n=("y", "size"), mean_predicted=("q", "mean"), observed_fire_rate=("y", "mean"), observed_fire_within_1cell=("y3", "mean"))
cal.round(4).to_csv(OUT / "r8_calibration.csv")
print(cal.round(4).to_string())
print("brier", brier_score_loss(df.y, q), "base-rate brier", brier_score_loss(df.y, np.full(len(df), df.y.mean())))
pd.DataFrame({"date": df.date, "cell_id": df.cell_id, "y": df.y, "cls": df.cls, "q_best": q}).to_parquet(OUT / "oof_best.parquet")
