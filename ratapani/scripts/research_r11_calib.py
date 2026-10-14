"""Round 11: calibrated risk numbers. Starting from r8 LOYO out-of-fold scores (large LightGBM + leaf-fall),
fit an isotonic map on the other 11 years and apply it to the held-out year (nested, no peeking).
Two targets: P(fire in this 500 m cell on t+1..t+2) and P(fire in this cell or its 8 neighbours = within ~1.5 km)."""
from pathlib import Path
import numpy as np
import pandas as pd
from sklearn.isotonic import IsotonicRegression
from sklearn.metrics import brier_score_loss, roc_auc_score

M = Path(r"E:\FIRE\ratapani\model"); OUT = M / "r11"; OUT.mkdir(exist_ok=True)
o = pd.read_parquet(M / "r8" / "oof_best.parquet")
o = o.merge(pd.read_parquet(M / "celldays_v2.parquet", columns=["date", "cell_id", "y3"]), on=["date", "cell_id"])
year = o.date.dt.year.to_numpy()
BINS = [0, 0.005, 0.01, 0.02, 0.05, 0.10, 0.20, 0.30, 0.50, 1.0]
summary, tables = [], []
for target in ("y", "y3"):
    cal = np.zeros(len(o))
    for yv in range(2013, 2025):
        tr, te = year != yv, year == yv
        iso = IsotonicRegression(out_of_bounds="clip", y_min=0, y_max=1).fit(o.q_best[tr], o[target][tr])
        cal[te] = iso.predict(o.q_best[te])
    yt = o[target].to_numpy()
    base = yt.mean()
    bs, bs0 = brier_score_loss(yt, cal), brier_score_loss(yt, np.full(len(yt), base))
    t = (pd.DataFrame({"risk": pd.cut(cal, BINS, include_lowest=True), "p": cal, "y": yt})
         .groupby("risk", observed=True).agg(cell_days=("y", "size"), mean_predicted=("p", "mean"), observed=("y", "mean")))
    t["share_of_all_fires"] = (pd.DataFrame({"risk": pd.cut(cal, BINS, include_lowest=True), "y": yt})
                               .groupby("risk", observed=True).y.sum() / yt.sum())
    t["cell_days_per_season_day"] = t.cell_days / len(np.unique(o.date))
    t.insert(0, "target", {"y": "this cell", "y3": "within 1.5 km"}[target])
    tables.append(t.reset_index())
    ece = np.average(np.abs(t.mean_predicted - t.observed), weights=t.cell_days)
    summary.append(dict(target=target, base_rate=round(base, 5), brier=round(bs, 6), brier_skill=round(1 - bs / bs0, 3),
                        expected_calibration_error=round(ece, 5), auc=round(roc_auc_score(yt, cal), 3),
                        max_risk=round(cal.max(), 3)))
    o[f"risk_{target}"] = cal
T = pd.concat(tables)
T.round(4).to_csv(OUT / "reliability.csv", index=False)
pd.DataFrame(summary).to_csv(OUT / "summary.csv", index=False)
o[["date", "cell_id", "y", "y3", "risk_y", "risk_y3"]].to_parquet(OUT / "calibrated_oof.parquet")
print(pd.DataFrame(summary).to_string()); print(T.round(4).to_string())
