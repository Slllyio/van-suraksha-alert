"""MP-wide evaluation of the best design: each division's own model on 3-satellite labels/fire history (feats_multi/)
plus the .npz 10-day HLS dryness; train seasons 2019-2021, test 2022-2024.
Metric as before: flag the top 10% of the division's test cell-days, a fire counts if a flagged cell is within 1 cell.
Writes E:/FIRE/mp/results_all/all_divisions.csv (one row per division) and a summary. Skips divisions already scored."""
import time
from pathlib import Path
import numpy as np
import pandas as pd
import geopandas as gpd
import lightgbm as lgb
from scipy.ndimage import maximum_filter

MP = Path(r"E:\FIRE\mp"); OUT = MP / "results_all"; OUT.mkdir(exist_ok=True)
SEASONS, TRAIN_Y, TEST_Y = range(2019, 2025), range(2019, 2022), range(2022, 2025)
FUT = {f"{c}_f{h}" for h in (1, 2) for c in ("tmax", "vpd_max", "wind", "prcp_mm", "rh")}
P = dict(objective="binary", feature_fraction=0.7, bagging_fraction=0.8, bagging_freq=1, verbose=-1, seed=0,
         num_leaves=255, min_data_in_leaf=100, learning_rate=0.03, lambda_l2=5)
DRY = ["hls_ndvi", "hls_ndmi", "hls_nbr", "hls_clear", "hls_ndvi_d10", "hls_ndmi_d10", "hls_nbr_d10",
       "hls_ndvi_d30", "hls_ndmi_d30", "hls_nbr_d30"]
_NPZ = {}


def dryness(grid, season):
    if season not in _NPZ:
        z = np.load(MP / "push" / f"mp_dry_{season}.npz")
        _NPZ[season] = (pd.to_datetime(z["steps"]), pd.Series(np.arange(len(z["cells"])), index=z["cells"]), z["X"])
    dates, pos, X = _NPZ[season]
    out = np.full((len(dates), len(grid), 4), np.nan, np.float32)
    have = np.isin(grid.mp_cell.to_numpy(), pos.index)
    if have.any():
        v = X[:, pos[grid.mp_cell.to_numpy()[have]].to_numpy()].astype(np.float32)
        idx = v[..., :3]; idx[(idx < -10000) | (idx > 10000)] = np.nan
        v[..., 3][(v[..., 3] < 0) | (v[..., 3] > 100)] = np.nan
        v[..., :3] = idx / 10000.0
        out[:, have] = v
    return dates, out


def add_dry(df, grid, season):
    dates, d = dryness(grid, season)
    pos = pd.Series(np.arange(len(grid)), index=grid.cell_id)[df.cell_id].to_numpy()
    k = np.searchsorted(dates.values, df.date.values, side="right") - 1
    kk = np.clip(k, 0, None)
    cur, p1, p3 = d[kk, pos], d[np.clip(kk - 1, 0, None), pos], d[np.clip(kk - 3, 0, None), pos]
    vals = np.full((len(df), len(DRY)), np.nan, np.float32)
    vals[:, 0:4] = cur; vals[:, 4:7] = cur[:, :3] - p1[:, :3]; vals[:, 7:10] = cur[:, :3] - p3[:, :3]
    vals[kk - 1 < 0, 4:7] = np.nan; vals[kk - 3 < 0, 7:10] = np.nan; vals[k < 0] = np.nan
    return df.assign(**{c: vals[:, j] for j, c in enumerate(DRY)})


def recall(sub, s):
    NI, NJ = sub.i.max() + 1, sub.j.max() + 1
    flag = s >= np.quantile(s, 0.90); c = np.zeros(len(sub), bool)
    for _, idx in sub.groupby("date").indices.items():
        g = sub.iloc[idx]; r = np.zeros((NI, NJ), bool); r[g.i, g.j] = flag[idx]
        c[idx] = maximum_filter(r, 3)[g.i, g.j]
    p = sub.y.to_numpy() == 1; new = p & (sub.fdist_d7.to_numpy() > 5)
    return dict(n_pos=int(p.sum()), recall=c[p].mean() if p.any() else np.nan, n_new=int(new.sum()),
                recall_new=c[new].mean() if new.any() else np.nan)


done_f = OUT / "all_divisions.csv"
rows = pd.read_csv(done_f).to_dict("records") if done_f.exists() else []
done = {r["division"] for r in rows}
rng = np.random.default_rng(0)
divs = sorted(p.parent.name for p in MP.glob("*/grid_500m.geojson")
              if len(list((p.parent / "feats_multi").glob("season_*.parquet"))) >= 6)
for dv in divs:
    if dv in done:
        continue
    t0 = time.time()
    grid = gpd.read_file(MP / dv / "grid_500m.geojson").drop(columns="geometry")
    tr, te = [], []
    for yr in SEASONS:
        x = pd.read_parquet(MP / dv / "feats_multi" / f"season_{yr}.parquet")
        if yr in TRAIN_Y:
            x = x[(x.y == 1) | (rng.random(len(x)) < 0.03)]
        (tr if yr in TRAIN_Y else te).append(add_dry(x, grid, yr))
    tr, te = pd.concat(tr, ignore_index=True), pd.concat(te, ignore_index=True)
    row = dict(division=dv, cells=len(grid), train_fires=int(tr.y.sum()))
    if tr.y.sum() < 20 or te.y.sum() == 0:
        row.update(note="too few fires to train/test")
    else:
        cols = sorted(set(tr.columns) - {"date", "cell_id", "i", "j", "y", "y3"} - FUT)
        m = lgb.train(P, lgb.Dataset(tr[cols], tr.y), 600)
        row.update(recall(te, m.predict(te.reindex(columns=cols))))
    rows.append(row)
    pd.DataFrame(rows).to_csv(done_f, index=False)
    print(dv, f"{time.time() - t0:.0f}s", row, flush=True)
R = pd.DataFrame(rows)
ok = R.dropna(subset=["recall"])
summary = dict(divisions_scored=len(ok), divisions_skipped=int(R.recall.isna().sum()),
               fires_test=int(ok.n_pos.sum()), recall_weighted=round(np.average(ok.recall, weights=ok.n_pos), 3),
               recall_new_weighted=round(np.average(ok.recall_new.fillna(0), weights=ok.n_new.clip(lower=0)), 3) if ok.n_new.sum() else None,
               recall_median_division=round(ok.recall.median(), 3), recall_min=round(ok.recall.min(), 3),
               recall_max=round(ok.recall.max(), 3))
pd.Series(summary).to_csv(OUT / "summary.csv", header=False)
print(summary)
