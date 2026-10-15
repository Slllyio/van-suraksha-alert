"""MP step 1d: the same 10-day HLS dryness test as step 1c, read from the packaged per-cell files
E:/FIRE/mp/push/mp_dry_<season>.npz (identical values to the tiles; beat cells only) with overflow values masked.
Based on MP step 1c: do 10-day HLS fuel-dryness tiles (from the separate all-MP pull, E:/FIRE/mp/tiles) add skill?
Tiles: <season>_<MMDD>_<tr>_<tc>.npy, int16 (4, 128, 128) = ndvi, ndmi, nbr (x10000), clear % on the shared MP grid
(EPSG:32643, X0 399000, Y1 2996000, 500 m); each step d holds the median of clear looks in the 15 days before d.
As-of join: issue day t uses the latest step d <= t; plus the change since the previous step (~10 d) and 3 steps (~30 d).
Experiment: each division's own model (the best design from step 1), train seasons 2017-2021, test 2022-2024,
without vs with the dryness features."""
import json, time
from pathlib import Path
import numpy as np
import pandas as pd
import geopandas as gpd
import lightgbm as lgb
from scipy.ndimage import maximum_filter

MP = Path(r"E:\FIRE\mp"); TILES = MP / "tiles"; OUT = MP / "results_step1d"; OUT.mkdir(exist_ok=True)
DIVS = ["Obedullahganj", "Guna", "Shivpuri", "Khandwa", "Satpura_TR", "Kanha_Tiger_Reserve", "Dindori", "South_Panna", "Singrauli"]
SEASONS, TRAIN_Y, TEST_Y = range(2017, 2025), range(2017, 2022), range(2022, 2025)
T_ = 128
FUT = {f"{c}_f{h}" for h in (1, 2) for c in ("tmax", "vpd_max", "wind", "prcp_mm", "rh")}
DRY = ["hls_ndvi", "hls_ndmi", "hls_nbr", "hls_clear", "hls_ndvi_d10", "hls_ndmi_d10", "hls_nbr_d10",
       "hls_ndvi_d30", "hls_ndmi_d30", "hls_nbr_d30"]
P = dict(objective="binary", feature_fraction=0.7, bagging_fraction=0.8, bagging_freq=1, verbose=-1, seed=0,
         num_leaves=255, min_data_in_leaf=100, learning_rate=0.03, lambda_l2=5)


_NPZ = {}


def dryness(grid, season):
    """(steps, cells, 4) float32 from the packaged E:/FIRE/mp/push/mp_dry_<season>.npz (beat cells only; other cells NaN).
    int16 ndvi/ndmi/nbr x10000 and clear %; -32768 = no clear look; values outside +-10000 are overflow -> NaN."""
    if season not in _NPZ:
        z = np.load(MP / "push" / f"mp_dry_{season}.npz")
        _NPZ[season] = (pd.to_datetime(z["steps"]), pd.Series(np.arange(len(z["cells"])), index=z["cells"]), z["X"])
    dates, pos, X = _NPZ[season]
    out = np.full((len(dates), len(grid), 4), np.nan, np.float32)
    have = np.isin(grid.mp_cell.to_numpy(), pos.index)
    v = X[:, pos[grid.mp_cell.to_numpy()[have]].to_numpy()].astype(np.float32)
    idx = v[..., :3]
    idx[(idx < -10000) | (idx > 10000)] = np.nan
    v[..., 3][(v[..., 3] < 0) | (v[..., 3] > 100)] = np.nan
    v[..., :3] = idx / 10000.0
    out[:, have] = v
    return dates, out


def add_dry(df, grid, season):
    dates, d = dryness(grid, season)
    pos = pd.Series(np.arange(len(grid)), index=grid.cell_id)[df.cell_id].to_numpy()
    k = np.searchsorted(dates.values, df.date.values, side="right") - 1  # latest step <= issue day
    ok = k >= 0
    vals = np.full((len(df), len(DRY)), np.nan, np.float32)
    kk = np.clip(k, 0, None)
    cur = d[kk, pos]
    p1 = d[np.clip(kk - 1, 0, None), pos]; p3 = d[np.clip(kk - 3, 0, None), pos]
    vals[:, 0:4] = cur
    vals[:, 4:7] = cur[:, :3] - p1[:, :3]; vals[:, 7:10] = cur[:, :3] - p3[:, :3]
    vals[kk - 1 < 0, 4:7] = np.nan; vals[kk - 3 < 0, 7:10] = np.nan
    vals[~ok] = np.nan
    return df.assign(**{c: vals[:, j] for j, c in enumerate(DRY)})


def score(sub, s):
    NI, NJ = sub.i.max() + 1, sub.j.max() + 1
    flag = s >= np.quantile(s, 0.90); c = np.zeros(len(sub), bool)
    for _, idx in sub.groupby("date").indices.items():
        g = sub.iloc[idx]; r = np.zeros((NI, NJ), bool); r[g.i, g.j] = flag[idx]
        c[idx] = maximum_filter(r, 3)[g.i, g.j]
    p = sub.y.to_numpy() == 1; new = p & (sub.fdist_d7.to_numpy() > 5)
    return dict(n_pos=int(p.sum()), n_new=int(new.sum()), recall=c[p].mean(), recall_new=c[new].mean() if new.any() else np.nan)


rng = np.random.default_rng(0)
COLS = json.loads((MP / "results_step1" / "features.json").read_text())
rows = []
for dv in DIVS:
    t0 = time.time()
    grid = gpd.read_file(MP / dv / "grid_500m.geojson").drop(columns="geometry")
    tr_parts, te_parts = [], []
    for yr in SEASONS:
        x = pd.read_parquet(MP / dv / "feats" / f"season_{yr}.parquet")
        if yr in TRAIN_Y:
            x = x[(x.y == 1) | (rng.random(len(x)) < 0.03)]
        x = add_dry(x, grid, yr)
        (tr_parts if yr in TRAIN_Y else te_parts).append(x)
    Tr, Te = pd.concat(tr_parts, ignore_index=True), pd.concat(te_parts, ignore_index=True)
    cov = Te.hls_ndvi.notna().mean()
    for tag, cols in [("own model, base", COLS), ("own model, base + HLS dryness", COLS + DRY)]:
        m = lgb.train(P, lgb.Dataset(Tr.reindex(columns=cols), Tr.y), 600)
        rows.append(dict(division=dv, model=tag, dry_coverage=round(cov, 3), **score(Te, m.predict(Te.reindex(columns=cols)))))
        print(rows[-1], f"{time.time() - t0:.0f}s", flush=True)
    pd.DataFrame(rows).to_csv(OUT / "dryness_by_division.csv", index=False)
R = pd.DataFrame(rows)
S = R.groupby("model").apply(lambda g: pd.Series(dict(recall=np.average(g.recall, weights=g.n_pos),
        recall_new=np.average(g.recall_new.fillna(0), weights=g.n_new), worst_division=g.recall.min(),
        best_division=g.recall.max())), include_groups=False).round(3)
S.to_csv(OUT / "dryness_summary.csv"); print(S.to_string())
print(R.pivot(index="division", columns="model", values="recall").round(3).to_string())
