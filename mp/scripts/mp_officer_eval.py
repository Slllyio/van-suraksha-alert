"""MP officer-style evaluation (usage: python mp_officer_eval.py <feats_dir> <tag>, e.g. feats_multi 3sat / feats_s20 s20).
Per division: train 2019-2021, test 2022-2024, .npz 10-day HLS dryness added. Two models:
  own    - the division's own data
  borrow - own data (weight 3) + the neighbouring divisions' data (boundaries within 5 km, weight 1)
Rule fixed in advance: a division is 'weak' if it has < 1000 training fire cell-days; the recommended model is
'borrow' for weak divisions and 'own' otherwise (both are reported for every division).
Flags: top 10% of the division's test cell-days (pooled over the test seasons, so more on bad days).
Metrics:
  cell_recall      fire cell-days (issue-day label: fire on t+1..t+2) with a flagged cell within 1 cell (as before)
  flagged_pct      mean daily share of the division's cells that are flagged
  covered_pct      mean daily share of cells that are flagged OR next to a flagged cell (ground an officer covers)
  Fire events (each fire once): actual fire cell-days (detection on day d), linked across adjacent cells and
  consecutive days into one event. Events starting on the first 2 days of a season have no forecast and are skipped.
    event_recall_first  STRICT: caught only if a first-day cell had a flag within 1 cell on the issues of day -1 or -2
    event_recall_any    LOOSE: caught if any fire cell-day of the event had such a flag 1-2 days before it
  Beat episodes: a run of consecutive burning days in a beat (a fire in any of its cells).
    beat_recall_first   STRICT: the beat had >= 1 flagged cell on the issues of the episode's first day -1 or -2
    beat_recall_any     LOOSE: any day of the episode was preceded (by 1-2 days) by a flag in the beat
  beats_flagged_per_range_day   mean flagged beats per range per day (officer workload)
  beat_share_flagged            mean daily share of beats with >= 1 flagged cell"""
import json, sys, time, zlib
from pathlib import Path
import numpy as np
import pandas as pd
import geopandas as gpd
import lightgbm as lgb
from scipy.ndimage import maximum_filter, label

FEATS, TAG = sys.argv[1], sys.argv[2]
MP = Path(r"E:\FIRE\mp"); OUT = MP / "results_officer"; OUT.mkdir(exist_ok=True)
SEASONS, TRAIN_Y, TEST_Y = range(2019, 2025), range(2019, 2022), range(2022, 2025)
FUT = {f"{c}_f{h}" for h in (1, 2) for c in ("tmax", "vpd_max", "wind", "prcp_mm", "rh")}
P = dict(objective="binary", feature_fraction=0.7, bagging_fraction=0.8, bagging_freq=1, verbose=-1, seed=0,
         num_leaves=255, min_data_in_leaf=100, learning_rate=0.03, lambda_l2=5)
DRY = ["hls_ndvi", "hls_ndmi", "hls_nbr", "hls_clear", "hls_ndvi_d10", "hls_ndmi_d10", "hls_nbr_d10",
       "hls_ndvi_d30", "hls_ndmi_d30", "hls_nbr_d30"]
WEAK_FIRES = 1000
NB = json.loads((MP / "neighbours.json").read_text())
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


def grid_of(dv):
    return gpd.read_file(MP / dv / "grid_500m.geojson").drop(columns="geometry")


def train_sample(dv):
    """cached training sample (all fire cell-days + 3% of the rest) with dryness."""
    f = MP / dv / f"train_{TAG}.parquet"
    if f.exists():
        return pd.read_parquet(f)
    rng = np.random.default_rng(zlib.crc32(dv.encode()))  # deterministic per division
    grid = grid_of(dv)
    parts = []
    for yr in TRAIN_Y:
        x = pd.read_parquet(MP / dv / FEATS / f"season_{yr}.parquet")
        parts.append(add_dry(x[(x.y == 1) | (rng.random(len(x)) < 0.03)], grid, yr))
    x = pd.concat(parts, ignore_index=True)
    x.to_parquet(f, index=False)
    return x


def lagged(A, dates):
    """P[d] = A[d-1] | A[d-2] using true calendar days (False where those issue days are not in the test window)."""
    di = pd.Series(np.arange(len(dates)), index=dates)
    P = np.zeros_like(A)
    for lag in (1, 2):
        src = pd.DatetimeIndex(dates) - pd.Timedelta(days=lag)
        k = di.reindex(src).to_numpy()
        ok = ~np.isnan(k)
        P[ok] |= A[k[ok].astype(int)]
    return P


def has_two_prior(dates):
    s = set(pd.DatetimeIndex(dates))
    return np.array([(d - pd.Timedelta(days=1) in s) and (d - pd.Timedelta(days=2) in s) for d in pd.DatetimeIndex(dates)])


def metrics(te, s, bm, fire_col="cell_d1"):
    dates = np.sort(te.date.unique()); di = pd.Series(np.arange(len(dates)), index=dates)
    d_idx = te.date.map(di).to_numpy(); ii, jj = te.i.to_numpy(), te.j.to_numpy()
    NI, NJ = ii.max() + 1, jj.max() + 1
    T = len(dates); prior_ok = has_two_prior(dates)
    flag = s >= np.quantile(s, 0.90)
    F = np.zeros((T, NI, NJ), bool); F[d_idx, ii, jj] = flag
    V = np.zeros((NI, NJ), bool); V[ii, jj] = True
    NEAR = maximum_filter(F, size=(1, 3, 3)) & V
    y = te.y.to_numpy() == 1
    out = dict(n_pos=int(y.sum()), cell_recall=NEAR[d_idx, ii, jj][y].mean() if y.any() else np.nan,
               flagged_pct=100 * flag.mean(), covered_pct=100 * NEAR.sum() / (V.sum() * T))
    # ---- fire events from actual fire days (cell_d1 = detection on the issue day itself) ----
    FR = np.zeros((T, NI, NJ), bool); FR[d_idx, ii, jj] = te[fire_col].to_numpy() > 0
    CAUGHT = lagged(NEAR, dates) & FR                         # fire cell-day flagged (within 1 cell) 1-2 days before
    consec = np.r_[False, np.diff(pd.DatetimeIndex(dates).values).astype("timedelta64[D]").astype(int) == 1]
    # label each run of consecutive dates separately so events never join across a season break
    lab = np.zeros(FR.shape, np.int64); n_ev = 0
    starts = np.flatnonzero(~consec); ends = np.r_[starts[1:], T]
    for a, z in zip(starts, ends):
        l, n = label(FR[a:z], structure=np.ones((3, 3, 3), bool))
        lab[a:z] = np.where(l > 0, l + n_ev, 0); n_ev += n
    if n_ev:
        dayidx = np.broadcast_to(np.arange(T)[:, None, None], FR.shape)
        first = np.full(n_ev + 1, T, int)
        np.minimum.at(first, lab[FR], dayidx[FR])
        valid = np.zeros(n_ev + 1, bool); valid[1:] = prior_ok[first[1:]]
        firstday = FR & (dayidx == first[lab])
        any_c = np.bincount(lab[CAUGHT], minlength=n_ev + 1) > 0
        first_c = np.bincount(lab[CAUGHT & firstday], minlength=n_ev + 1) > 0
        nv = int(valid.sum())
        out.update(n_events=nv, event_recall_first=first_c[valid].mean() if nv else np.nan,
                   event_recall_any=any_c[valid].mean() if nv else np.nan)
    # ---- beats ----
    b = te[["date", "cell_id"]].assign(flag=flag, fire=te[fire_col].to_numpy() > 0).merge(bm, on="cell_id", how="left")
    b = b.dropna(subset=["beat_id"])
    if len(b):
        beats = np.sort(b.beat_id.unique()); bi = pd.Series(np.arange(len(beats)), index=beats)
        g = b.groupby(["date", "beat_id"]).agg(fire=("fire", "max"), flag=("flag", "max")).reset_index()
        BF = np.zeros((T, len(beats)), bool); BG = np.zeros_like(BF)
        r, c = g.date.map(di).to_numpy(), g.beat_id.map(bi).to_numpy()
        BF[r, c] = g.fire.to_numpy(); BG[r, c] = g.flag.to_numpy()
        PB = lagged(BG, dates)
        prev = np.vstack([np.zeros((1, len(beats)), bool), BF[:-1]]) & consec[:, None]
        start_all = BF & ~prev                                                 # first burning day of each episode
        ep = np.cumsum(start_all.ravel(order="F")).reshape(BF.shape, order="F")  # ids run down each beat column
        ep = np.where(BF, ep, 0)
        start = start_all & prior_ok[:, None]                                  # episodes with a forecast 1-2 days before
        valid_ep = np.unique(ep[start])
        hit_any = np.intersect1d(np.unique(ep[BF & PB]), valid_ep)
        n_ep = len(valid_ep)
        rng_of = b.drop_duplicates("beat_id").set_index("beat_id").Range.reindex(beats).to_numpy()
        flagged_per_range = pd.DataFrame(BG, columns=rng_of).T.groupby(level=0).sum().T
        out.update(n_beats=len(beats), n_beat_episodes=n_ep,
                   beat_recall_first=(start & PB).sum() / n_ep if n_ep else np.nan,
                   beat_recall_any=len(hit_any) / n_ep if n_ep else np.nan,
                   beats_flagged_per_range_day=flagged_per_range.to_numpy().mean(),
                   beat_share_flagged=100 * BG.mean())
    return out


divs = sorted(p.parent.name for p in MP.glob("*/grid_500m.geojson")
              if len(list((p.parent / FEATS).glob("season_*.parquet"))) >= 6)
t0 = time.time()
for dv in divs:
    train_sample(dv)
print(TAG, "training samples ready", len(divs), f"{time.time() - t0:.0f}s", flush=True)

res_f = OUT / f"officer_{TAG}.csv"
rows = pd.read_csv(res_f).to_dict("records") if res_f.exists() else []
done = {r["division"] for r in rows}
for dv in divs:
    if dv in done:
        continue
    t0 = time.time()
    own = train_sample(dv)
    nbrs = [n for n in NB.get(dv, []) if n in divs]
    pool = pd.concat([own.assign(_w=3.0)] + [train_sample(n).assign(_w=1.0) for n in nbrs], ignore_index=True)
    cols = sorted(set(pool.columns) - {"date", "cell_id", "i", "j", "y", "y3", "_w"} - FUT)
    grid = grid_of(dv)
    te = pd.concat([add_dry(pd.read_parquet(MP / dv / FEATS / f"season_{yr}.parquet"), grid, yr) for yr in TEST_Y],
                   ignore_index=True)
    bm = pd.read_csv(MP / dv / "beat_map.csv")[["cell_id", "Range", "beat_id"]]
    weak = int(own.y.sum()) < WEAK_FIRES
    base = dict(division=dv, label_set=TAG, train_fires=int(own.y.sum()), weak=weak, neighbours=len(nbrs))
    X = te.reindex(columns=cols)
    for model, data in (("own", own.assign(_w=1.0)), ("borrow", pool)):
        if data.y.sum() < 20 or te.y.sum() == 0:
            rows.append(dict(base, model=model, note="too few fires")); continue
        m = lgb.train(P, lgb.Dataset(data.reindex(columns=cols), data.y, weight=data._w), 600)
        rows.append(dict(base, model=model, recommended=(model == ("borrow" if weak else "own")),
                         **metrics(te, m.predict(X), bm)))
    pd.DataFrame(rows).to_csv(res_f, index=False)
    print(TAG, dv, f"{time.time() - t0:.0f}s", flush=True)

R = pd.DataFrame(rows)
def wavg(g, c, w):
    g = g.dropna(subset=[c]); return np.average(g[c], weights=g[w]) if len(g) and g[w].sum() else np.nan
summ = []
for name, g in (("own (all divisions)", R[R.model == "own"]), ("borrow (all divisions)", R[R.model == "borrow"]),
                ("recommended (borrow if weak)", R[R.get("recommended", False) == True]),
                ("weak divisions: own", R[(R.model == "own") & R.weak]), ("weak divisions: borrow", R[(R.model == "borrow") & R.weak])):
    summ.append(dict(view=name, divisions=int(g.division.nunique()), cell_recall=wavg(g, "cell_recall", "n_pos"),
                     event_recall_first=wavg(g, "event_recall_first", "n_events"),
                     event_recall_any=wavg(g, "event_recall_any", "n_events"),
                     beat_recall_first=wavg(g, "beat_recall_first", "n_beat_episodes"),
                     beat_recall_any=wavg(g, "beat_recall_any", "n_beat_episodes"),
                     covered_pct=g.covered_pct.mean(), flagged_pct=g.flagged_pct.mean(),
                     beats_flagged_per_range_day=g.beats_flagged_per_range_day.mean(),
                     beat_share_flagged=g.beat_share_flagged.mean()))
S = pd.DataFrame(summ).round(3)
S.to_csv(OUT / f"officer_{TAG}_summary.csv", index=False)
print(S.to_string(index=False))
