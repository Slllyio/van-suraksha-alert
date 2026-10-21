"""Train/evaluate the Ratapani 2-day fire outlook (LightGBM) against baselines.
Split by time: train 2013-2020, validate 2021-2022 (early stopping, threshold), test 2023-2024 (reported once)."""
import json, shutil
from pathlib import Path
import numpy as np
import pandas as pd
import geopandas as gpd
import lightgbm as lgb
from scipy.ndimage import maximum_filter
from sklearn.metrics import average_precision_score, roc_auc_score

R = Path(r"E:\FIRE\ratapani")
M = R / "model"
df = pd.read_parquet(M / "celldays.parquet")
grid = gpd.read_file(R / "grid_500m.geojson").drop(columns="geometry").set_index("cell_id")
df = df.join(grid[["i", "j"]], on="cell_id")
FUT = pd.read_csv(M / "future_weather_cols.csv", header=None)[0].tolist()
yr = df.date.dt.year
tr, va, te = yr <= 2020, yr.between(2021, 2022), yr >= 2023
BASE = [c for c in df.columns if c not in ("date", "cell_id", "y", "i", "j")]
NI, NJ = grid.i.max() + 1, grid.j.max() + 1
BUDGETS = (0.02, 0.05, 0.10)  # share of the 3,614 cells flagged per day
rng = np.random.default_rng(0)


def fit(cols, label):
    keep = tr & ((df.y == 1) | (rng.random(len(df)) < 0.15))  # all positives, 15% of negatives
    dtr = lgb.Dataset(df.loc[keep, cols], df.loc[keep, "y"])
    dva = lgb.Dataset(df.loc[va, cols], df.loc[va, "y"], reference=dtr)
    p = dict(objective="binary", learning_rate=0.03, num_leaves=63, min_data_in_leaf=200,
             feature_fraction=0.7, bagging_fraction=0.8, bagging_freq=1, lambda_l2=5,
             metric="average_precision", verbose=-1, seed=0)
    b = lgb.train(p, dtr, 3000, valid_sets=[dva], callbacks=[lgb.early_stopping(150, verbose=False)])
    print(label, "best iter", b.best_iteration)
    # refit on train+val with the chosen number of rounds, for the test year scores
    keep2 = (tr | va) & ((df.y == 1) | (rng.random(len(df)) < 0.15))
    b2 = lgb.train(p | {"metric": "none"}, lgb.Dataset(df.loc[keep2, cols], df.loc[keep2, "y"]), b.best_iteration)
    return b, b2


def daily_eval(sub, score, tol):
    """Per-day top-k% flags. Recall: share of fire cell-days caught. tol=1 counts a fire as caught if a
    flagged cell is within 1 cell (VIIRS geolocation ~375 m)."""
    out = {b: [0, 0, 0, 0] for b in BUDGETS}  # caught, positives, flagged-and-correct, flagged
    for _, g in sub.assign(s=score).groupby("date"):
        n = len(g)
        order = g.s.rank(ascending=False, method="first").to_numpy()
        pos = g.y.to_numpy() == 1
        for b in BUDGETS:
            flag = order <= int(round(b * n))
            if tol:
                fr = np.zeros((NI, NJ), bool); fr[g.i, g.j] = flag
                near = maximum_filter(fr, size=3)[g.i, g.j]
                yr_ = np.zeros((NI, NJ), bool); yr_[g.i, g.j] = pos
                ynear = maximum_filter(yr_, size=3)[g.i, g.j]
                caught, prec_hits = (pos & near).sum(), (flag & ynear).sum()
            else:
                caught, prec_hits = (pos & flag).sum(), (pos & flag).sum()
            o = out[b]; o[0] += caught; o[1] += pos.sum(); o[2] += prec_hits; o[3] += flag.sum()
    return {f"top{int(b*100)}%": dict(recall=round(o[0] / max(o[1], 1), 3), precision=round(o[2] / max(o[3], 1), 3))
            for b, o in out.items()}


def coarse(sub, score, f):
    """Re-score at coarser blocks (f x f cells): block score = max, label = any fire."""
    g = sub.assign(s=score, bi=sub.i // f, bj=sub.j // f).groupby(["date", "bi", "bj"]).agg(s=("s", "max"), y=("y", "max"))
    return dict(pr_auc=round(average_precision_score(g.y, g.s), 3), base_rate=round(g.y.mean(), 4),
                **{k: v for k, v in daily_eval(g.reset_index().rename(columns={"bi": "i", "bj": "j"}).assign(
                    cell_id=0), g.s.to_numpy(), 0).items()})


def report(name, sub, score):
    r = dict(pr_auc=round(average_precision_score(sub.y, score), 4), roc_auc=round(roc_auc_score(sub.y, score), 3),
             strict_500m=daily_eval(sub, score, 0), tolerant_500m=daily_eval(sub, score, 1))
    print(name, json.dumps(r))
    return r


res = {}
test = df[te]
res["baseline_recent_fire_nearby"] = report("recency", test, (test.nb7_d7 + 0.01 * test.clim_nb7).to_numpy())
res["baseline_climatology"] = report("climatology", test, test.clim_nb7.to_numpy())

models = {}
for label, cols in [("lgbm_no_forecast", [c for c in BASE if c not in FUT]), ("lgbm_with_forecast_weather", BASE)]:
    b, b2 = fit(cols, label)
    s = b2.predict(test[cols])
    res[label] = report(label, test, s)
    # threshold that gives 80% recall on validation, applied to test
    sv = b.predict(df.loc[va, cols]); yv = df.loc[va, "y"].to_numpy()
    thr = np.quantile(sv[yv == 1], 0.20)
    st = b.predict(test[cols])
    flag = st >= thr
    res[label]["thr_recall80_on_val"] = dict(threshold=float(thr), test_recall=round(test.y[flag].sum() / test.y.sum(), 3),
                                             test_precision=round(test.y[flag].mean(), 3),
                                             flagged_cells_per_day=round(flag.sum() / test.date.nunique(), 1))
    res[label]["coarser"] = {f"{f * 500}m": coarse(test, s, f) for f in (2, 4)}
    models[label] = (b2, cols)
    imp = pd.Series(b2.feature_importance("gain"), index=cols).sort_values(ascending=False)
    res[label]["top_features"] = (imp / imp.sum()).round(3).head(15).to_dict()
    b2.save_model(str(M / f"{label}.txt"))

(M / "results.json").write_text(json.dumps(res, indent=2))
shutil.copy(__file__, M / "train_eval.py")
shutil.copy(Path(__file__).with_name("build_features.py"), M / "build_features.py")
print(json.dumps(res, indent=1))
