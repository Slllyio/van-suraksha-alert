"""MP step 2: do NOAA-20/21 VIIRS detections (on top of S-NPP) improve the division models?
Two feature/label sets per division, seasons 2019-2024 (NOAA-20 complete from the 2019 season):
  S = S-NPP only (feats/), M = S-NPP + NOAA-20 + NOAA-21 (feats_multi/); both get the .npz HLS dryness.
Division's own model, train 2019-2021, test 2022-2024. Scored against both truths:
  'snpp truth' = fires seen by S-NPP, 'all-sat truth' = fires seen by any of the three satellites."""
import importlib.util, json, time
from pathlib import Path
import numpy as np
import pandas as pd
import geopandas as gpd
import lightgbm as lgb
from scipy.ndimage import maximum_filter

SCR = Path(__file__).parent
spec = importlib.util.spec_from_file_location("dry", SCR / "mp_dryness_npz.py")
MP = Path(r"E:\FIRE\mp"); OUT = MP / "results_step2"; OUT.mkdir(exist_ok=True)
DIVS = ["Obedullahganj", "Guna", "Shivpuri", "Khandwa", "Satpura_TR", "Kanha_Tiger_Reserve", "Dindori", "South_Panna", "Singrauli"]
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


def recall(sub, s, ycol):
    NI, NJ = sub.i.max() + 1, sub.j.max() + 1
    flag = s >= np.quantile(s, 0.90); c = np.zeros(len(sub), bool)
    for _, idx in sub.groupby("date").indices.items():
        g = sub.iloc[idx]; r = np.zeros((NI, NJ), bool); r[g.i, g.j] = flag[idx]
        c[idx] = maximum_filter(r, 3)[g.i, g.j]
    p = sub[ycol].to_numpy() == 1; new = p & (sub.fdist_d7.to_numpy() > 5)
    return int(p.sum()), c[p].mean(), int(new.sum()), (c[new].mean() if new.any() else np.nan)


rng = np.random.default_rng(0)
rows = []
for dv in DIVS:
    t0 = time.time()
    grid = gpd.read_file(MP / dv / "grid_500m.geojson").drop(columns="geometry")
    data = {}
    for tag, sub in (("S", "feats"), ("M", "feats_multi")):
        tr, te = [], []
        for yr in SEASONS:
            x = pd.read_parquet(MP / dv / sub / f"season_{yr}.parquet")
            if yr in TRAIN_Y:
                x = x[(x.y == 1) | (rng.random(len(x)) < 0.03)]
            (tr if yr in TRAIN_Y else te).append(add_dry(x, grid, yr))
        data[tag] = (pd.concat(tr, ignore_index=True), pd.concat(te, ignore_index=True))
    # attach the all-satellite truth to the S-NPP test rows (same date/cell order is not guaranteed -> merge)
    teS, teM = data["S"][1], data["M"][1]
    teS = teS.merge(teM[["date", "cell_id", "y"]].rename(columns={"y": "y_all"}), on=["date", "cell_id"], how="left")
    teM = teM.merge(teS[["date", "cell_id", "y"]].rename(columns={"y": "y_snpp"}), on=["date", "cell_id"], how="left")
    cols = None
    for tag, te in (("S", teS), ("M", teM)):
        tr = data[tag][0]
        cols = sorted(set(tr.columns) - {"date", "cell_id", "i", "j", "y", "y3", "y_all", "y_snpp"} - FUT)
        s = lgb.train(P, lgb.Dataset(tr[cols], tr.y), 600).predict(te.reindex(columns=cols))
        for truth, ycol in (("snpp truth", "y" if tag == "S" else "y_snpp"), ("all-sat truth", "y_all" if tag == "S" else "y")):
            n, r, nn, rn = recall(te, s, ycol)
            rows.append(dict(division=dv, model="S-NPP only" if tag == "S" else "3 satellites", truth=truth,
                             n_pos=n, recall=r, n_new=nn, recall_new=rn))
    print(dv, f"{time.time() - t0:.0f}s", rows[-4:], flush=True)
    pd.DataFrame(rows).to_csv(OUT / "multisat_by_division.csv", index=False)
R = pd.DataFrame(rows)
S = R.groupby(["truth", "model"]).apply(lambda g: pd.Series(dict(fire_celldays=g.n_pos.sum(),
        recall=np.average(g.recall, weights=g.n_pos), recall_new=np.average(g.recall_new.fillna(0), weights=g.n_new))),
        include_groups=False).round(3)
S.to_csv(OUT / "multisat_summary.csv"); print(S.to_string())
