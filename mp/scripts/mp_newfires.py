"""Brand-new fires, strict each-fire-once, model vs the 'fires nearby' rule; saves test predictions per cell-day.
Usage: python mp_newfires.py <feats_dir> <tag> <archive.parquet>[;...]   (same arguments as mp_seasonal.py)
Setting: seasonal rules (targets 15 Feb-31 May, early-burn input, control burns dropped), recommended model
(own data; neighbour borrowing for weak divisions), train 2019-2021, test 2022-2024, top 10% of test cell-days flagged.
  STRICT each-fire-once: caught only if a first-day cell had a flag within 1 cell on the issues of day -1 or -2.
  Brand-new fire: no detection of any kind (control burns included) within 5 km of any first-day cell in the 7 days
  before its first day; fires up to 5 km outside the division count (the raster is padded by 10 cells).
  'Fires nearby' rule: score = fires in the 7x7 block in the last 7 days (nb7_d7) + 0.01 x local burn climatology.
Predictions: results_officer/predictions_<tag>/<division>.parquet (date, cell_id, mp_cell, model score/flag,
rule score/flag, y = fire on t+1..t+2, fire_t = target fire on t)."""
import sys, time
from pathlib import Path
import numpy as np
import pandas as pd
import lightgbm as lgb
from scipy.ndimage import maximum_filter, label

_args = sys.argv[1:]
SCR = Path(__file__).parent
_src = (SCR / "mp_seasonal.py").read_text(encoding="utf-8")
exec(_src.split("divs = sorted(p.parent.name")[0])     # seasonal helpers + shared officer helpers
PRED = MP / "results_officer" / f"predictions_{TAG}"; PRED.mkdir(exist_ok=True)
OUTN = MP / "results_officer" / f"newfires_{TAG}.csv"
PAD, R5 = 10, 10                                         # 10 cells = 5 km
yy, xx = np.mgrid[-R5:R5 + 1, -R5:R5 + 1]; DISK = (xx ** 2 + yy ** 2) <= R5 ** 2


def all_fire_raster(grid):
    c0, r0 = grid.col.min() - PAD, grid.row.min() - PAD
    NI, NJ = grid.col.max() - c0 + 1 + PAD, grid.row.max() - r0 + 1 + PAD
    v = DET[(DET.col >= c0) & (DET.col < c0 + NI) & (DET.row >= r0) & (DET.row < r0 + NJ)]
    A = np.zeros((len(ALLDAYS), NI, NJ), bool)
    A[DI[v.d].to_numpy(), v.col - c0, v.row - r0] = True
    return A


def strict_events(te, flag, A):
    """per-event: strict caught flag and brand-new flag (events with a forecast 1-2 days before their first day)."""
    dates = np.sort(te.date.unique()); di = pd.Series(np.arange(len(dates)), index=dates)
    d_idx = te.date.map(di).to_numpy(); ii, jj = te.i.to_numpy(), te.j.to_numpy()
    T = len(dates); NI, NJ = ii.max() + 1, jj.max() + 1
    F = np.zeros((T, NI, NJ), bool); F[d_idx, ii, jj] = flag
    V = np.zeros((NI, NJ), bool); V[ii, jj] = True
    NEAR = maximum_filter(F, size=(1, 3, 3)) & V
    FR = np.zeros_like(F); FR[d_idx, ii, jj] = te.fire_t.to_numpy() > 0
    prior_ok = has_two_prior(dates)
    consec = np.r_[False, np.diff(pd.DatetimeIndex(dates).values).astype("timedelta64[D]").astype(int) == 1]
    lab = np.zeros(FR.shape, np.int64); n_ev = 0
    starts = np.flatnonzero(~consec); ends = np.r_[starts[1:], T]
    for a, z in zip(starts, ends):
        l, n = label(FR[a:z], structure=np.ones((3, 3, 3), bool))
        lab[a:z] = np.where(l > 0, l + n_ev, 0); n_ev += n
    if not n_ev:
        return np.zeros(0, bool), np.zeros(0, bool)
    dayidx = np.broadcast_to(np.arange(T)[:, None, None], FR.shape)
    first = np.full(n_ev + 1, T, int); np.minimum.at(first, lab[FR], dayidx[FR])
    valid = np.zeros(n_ev + 1, bool); valid[1:] = prior_ok[first[1:]]
    firstday = FR & (dayidx == first[lab])
    caught = np.bincount(lab[lagged(NEAR, dates) & firstday], minlength=n_ev + 1) > 0
    # brand-new: no detection within 5 km in the 7 days before the first day (A is padded by PAD cells)
    new = np.ones(n_ev + 1, bool); new[0] = False
    fd_t, fd_i, fd_j = np.nonzero(firstday)
    fd_lab = lab[fd_t, fd_i, fd_j]
    for t in np.unique(fd_t):
        g = DI[pd.Timestamp(dates[t])]
        recent = A[g - 7:g].any(axis=0)                    # days F-7 .. F-1
        near5 = maximum_filter(recent, footprint=DISK)
        m = fd_t == t
        hit = near5[fd_i[m] + PAD, fd_j[m] + PAD]
        new[np.unique(fd_lab[m][hit])] = False
    return caught[1:][valid[1:]], new[1:][valid[1:]]


divs = sorted(p.parent.name for p in MP.glob("*/grid_500m.geojson")
              if len(list((p.parent / FEATS).glob("season_*.parquet"))) >= 6)
rows = pd.read_csv(OUTN).to_dict("records") if OUTN.exists() else []
done = {r["division"] for r in rows}
for dv in divs:
    if dv in done:
        continue
    t0 = time.time()
    own = train_seasonal(dv)
    weak = int(own.y.sum()) < WEAK_FIRES
    nbrs = [n for n in NB.get(dv, []) if n in divs] if weak else []
    data = pd.concat([own.assign(_w=3.0 if weak else 1.0)] + [train_seasonal(n).assign(_w=1.0) for n in nbrs], ignore_index=True)
    cols = sorted(set(data.columns) - {"date", "cell_id", "i", "j", "y", "y3", "_w", "fire_t"} - FUT)
    grid = grid_of(dv)
    te = seasonal_rows(dv, grid, TEST_Y)
    row = dict(division=dv, label_set=TAG, weak=weak, model_used="borrow" if weak else "own")
    if data.y.sum() < 20 or te.y.sum() == 0:
        rows.append(dict(row, note="too few fires")); pd.DataFrame(rows).to_csv(OUTN, index=False); continue
    m = lgb.train(P, lgb.Dataset(data.reindex(columns=cols), data.y, weight=data._w), 600)
    s_model = m.predict(te.reindex(columns=cols)).astype(np.float32)
    s_rule = (te.nb7_d7.to_numpy() + 0.01 * te.clim_nb7.to_numpy()).astype(np.float32)
    f_model, f_rule = s_model >= np.quantile(s_model, 0.90), s_rule >= np.quantile(s_rule, 0.90)
    A = all_fire_raster(grid)
    cm, new = strict_events(te, f_model, A)
    cr, _ = strict_events(te, f_rule, A)
    row.update(fires=len(cm), new_fires=int(new.sum()),
               strict_all_model=cm.mean() if len(cm) else np.nan, strict_all_rule=cr.mean() if len(cr) else np.nan,
               strict_new_model=cm[new].mean() if new.any() else np.nan, strict_new_rule=cr[new].mean() if new.any() else np.nan,
               strict_old_model=cm[~new].mean() if (~new).any() else np.nan, strict_old_rule=cr[~new].mean() if (~new).any() else np.nan)
    rows.append(row)
    mp_cell = grid.set_index("cell_id").mp_cell
    pd.DataFrame({"date": te.date.values, "cell_id": te.cell_id.values.astype(np.int32),
                  "mp_cell": mp_cell.reindex(te.cell_id).to_numpy().astype(np.int32),
                  "score_model": s_model, "flag_model": f_model, "score_rule": s_rule, "flag_rule": f_rule,
                  "y": te.y.values.astype(np.uint8), "fire_t": te.fire_t.values.astype(np.uint8)}
                 ).to_parquet(PRED / f"{dv}.parquet", index=False, compression="zstd")
    pd.DataFrame(rows).to_csv(OUTN, index=False)
    print(TAG, dv, f"{time.time() - t0:.0f}s", {k: (round(v, 3) if isinstance(v, float) else v) for k, v in row.items()}, flush=True)

R = pd.DataFrame(rows).dropna(subset=["fires"])
def w(c, n):
    g = R.dropna(subset=[c]); return round(np.average(g[c], weights=g[n]), 3) if g[n].sum() else np.nan
R["old_fires"] = R.fires - R.new_fires
summ = dict(label_set=TAG, divisions=len(R), fires=int(R.fires.sum()), new_fires=int(R.new_fires.sum()),
            new_share=round(R.new_fires.sum() / R.fires.sum(), 3),
            strict_all_model=w("strict_all_model", "fires"), strict_all_rule=w("strict_all_rule", "fires"),
            strict_new_model=w("strict_new_model", "new_fires"), strict_new_rule=w("strict_new_rule", "new_fires"),
            strict_old_model=w("strict_old_model", "old_fires"), strict_old_rule=w("strict_old_rule", "old_fires"))
pd.Series(summ).to_csv(MP / "results_officer" / f"newfires_{TAG}_summary.csv", header=False)
print(summ)
