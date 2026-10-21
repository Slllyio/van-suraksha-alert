"""MP step 1b: can pooling beat the local model? (follow-up to mp_transfer.py)
  D 'pooled + division id'   - all 9 pooled, division as a categorical feature
  E 'pooled, own x5 weight'  - all 9 pooled, the test division's own rows weighted 5x
Based on: MP step 1 experiment: does one model work across MP divisions?
Train seasons 2014-2021, test seasons 2022-2024, per test division:
  A 'other 8 only'  - trained on the other 8 divisions (pure spatial transfer)
  B 'own only'      - trained on the same division (local baseline)
  C 'all 9 pooled'  - trained on all 9 divisions (does pooling help?)
Large LightGBM (255 leaves x 600, as Ratapani r8), features = Ratapani set (fire history, static + access, MODIS,
AlphaEarth, weather without forecast, leaf-fall). Training rows: all positives + 3% of other cell-days.
Metric (as Ratapani rounds 1-12): flag the top 10% of the division's test cell-days, a fire counts if a flagged cell
is within 1 cell; plus recall on brand-new fires (no fire within 5 km in the last 7 days) and per-division base rate."""
import json, time
from pathlib import Path
import numpy as np
import pandas as pd
import lightgbm as lgb
from scipy.ndimage import maximum_filter

MP = Path(r"E:\FIRE\mp"); OUT = MP / "results_step1b"; OUT.mkdir(exist_ok=True)
DIVS = ["Obedullahganj", "Guna", "Shivpuri", "Khandwa", "Satpura_TR", "Kanha_Tiger_Reserve", "Dindori", "South_Panna", "Singrauli"]
TRAIN_Y, TEST_Y = range(2014, 2022), range(2022, 2025)
FUT = {f"{c}_f{h}" for h in (1, 2) for c in ("tmax", "vpd_max", "wind", "prcp_mm", "rh")}
P = dict(objective="binary", feature_fraction=0.7, bagging_fraction=0.8, bagging_freq=1, verbose=-1, seed=0,
         num_leaves=255, min_data_in_leaf=100, learning_rate=0.03, lambda_l2=5)
rng = np.random.default_rng(0)

# ---- training samples ----
samples = []
for dv in DIVS:
    for yr in TRAIN_Y:
        f = MP / dv / "feats" / f"season_{yr}.parquet"
        x = pd.read_parquet(f)
        x = x[(x.y == 1) | (rng.random(len(x)) < 0.03)]
        samples.append(x.assign(division=dv))
    print("sampled", dv, flush=True)
T = pd.concat(samples, ignore_index=True)
COLS = sorted(set(T.columns) - {"date", "cell_id", "i", "j", "y", "y3", "division"} - FUT)
print("train rows", len(T), "pos", int(T.y.sum()), "features", len(COLS), flush=True)
(OUT / "features.json").write_text(json.dumps(COLS))


def score(sub, s):
    NI, NJ = sub.i.max() + 1, sub.j.max() + 1
    flag = s >= np.quantile(s, 0.90); c = np.zeros(len(sub), bool)
    for _, idx in sub.groupby("date").indices.items():
        g = sub.iloc[idx]; r = np.zeros((NI, NJ), bool); r[g.i, g.j] = flag[idx]
        c[idx] = maximum_filter(r, 3)[g.i, g.j]
    p = sub.y.to_numpy() == 1; new = p & (sub.fdist_d7.to_numpy() > 5)
    return dict(n_pos=int(p.sum()), n_new=int(new.sum()), base_rate=p.mean(), recall=c[p].mean(),
                recall_new=c[new].mean() if new.any() else np.nan)


def fit(mask):
    return lgb.train(P, lgb.Dataset(T.loc[mask, COLS], T.y[mask]), 600)


DIV_CODE = {d: k for k, d in enumerate(DIVS)}
T["div_id"] = T.division.map(DIV_CODE).astype("int32")
COLS_D = COLS + ["div_id"]
t0 = time.time()
pooled_id = lgb.train(P, lgb.Dataset(T[COLS_D], T.y, categorical_feature=["div_id"]), 600)
print("pooled+id model", f"{time.time() - t0:.0f}s", flush=True)
rows = []
for dv in DIVS:
    wts = np.where(T.division == dv, 5.0, 1.0)
    weighted = lgb.train(P, lgb.Dataset(T[COLS], T.y, weight=wts), 600)
    test = pd.concat([pd.read_parquet(MP / dv / "feats" / f"season_{yr}.parquet") for yr in TEST_Y], ignore_index=True)
    X = test.reindex(columns=COLS)
    rows.append(dict(division=dv, model="D pooled + division id", **score(test, pooled_id.predict(X.assign(div_id=DIV_CODE[dv])))))
    rows.append(dict(division=dv, model="E pooled, own x5 weight", **score(test, weighted.predict(X))))
    print(rows[-2], rows[-1], flush=True)
    pd.DataFrame(rows).to_csv(OUT / "pooling_by_division.csv", index=False)
R = pd.concat([pd.read_csv(MP / "results_step1" / "transfer_by_division.csv"), pd.DataFrame(rows)], ignore_index=True)
S = R.groupby("model").apply(lambda g: pd.Series(dict(recall=np.average(g.recall, weights=g.n_pos),
        recall_new=np.average(g.recall_new.fillna(0), weights=g.n_new), worst_division=g.recall.min(),
        best_division=g.recall.max())), include_groups=False).round(3)
S.to_csv(OUT / "pooling_summary.csv"); print(S.to_string())
print(R.pivot(index="division", columns="model", values="recall").round(3).to_string())
