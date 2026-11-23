"""Simple rules on the PC's FINAL officer scoring with the seasonal rules (van-suraksha-alert PR #1 commit 4cb67686,
mp/scripts/mp_seasonal.py + mp_officer_eval.py metrics()). Same as the PC:
  issue days 13 Feb - 30 May 2022-24; targets = fires 15 Feb - 31 May (3 satellites, type 0), likely control burns on
  15-28 Feb dropped; flagged = top 10% of ALL the division's test square-days (pooled); "near" = flag in the 3x3 block.
  cell_recall = target square-days (fire on t+1/t+2) near a flag.
  Fire events = target fire square-days on the issue days, linked over 3x3 x consecutive days; events starting without
  two prior issue days skipped. STRICT = a first-day square near a flag on day -1 or -2; LOOSE = any fire square-day of
  the event near a flag 1-2 days before it.
  Beat episodes = runs of burning days in a beat (cells -> beats from ratapani/mp_grid/mp_cells.parquet; ranges =
  beat_uid[:7]). STRICT = >= 1 flagged square in the beat on day -1/-2 before the first day; LOOSE = any day.
Rules: random / history / cal_hist / recent (as mp_simple_rules.py), plus early (recent ties broken by fewer early
burns, i.e. recent + cal_hist with burned-before-15-Feb squares pushed down). Out: simple_events_by_division.csv, simple_events_summary.json"""
import os; os.environ['MPV'] = 'season'
import json, numpy as np, pandas as pd
from scipy.ndimage import maximum_filter, uniform_filter, label
from multiprocessing import Pool
import mp_simple_rules as M
P, OUT = M.P, M.OUT
cells = pd.read_parquet(P + 'ratapani/mp_grid/mp_cells.parquet')[['row', 'col', 'beat_uid']]
BEAT = {(r, c): b for r, c, b in zip(cells.row, cells.col, cells.beat_uid)}

def score(args):
    name, rows, cols, v = args
    r0, c0 = rows.min(), cols.min(); NJ, NI = rows.max() - r0 + 1, cols.max() - c0 + 1
    gi, gj = rows - r0, cols - c0; n = len(gi)
    v = v[(v.row >= r0) & (v.row < r0 + NJ) & (v.col >= c0) & (v.col < c0 + NI)]
    rng = np.random.default_rng(0)
    def raster(y, d0, d1):
        days = pd.date_range(d0, d1); di = pd.Series(np.arange(len(days)), index=days)
        q = v[v.ld.isin(days)]; FR = np.zeros((len(days), NJ, NI), bool); FR[di[q.ld].values, q.row.values - r0, q.col.values - c0] = True
        md = q.ld.dt.month * 100 + q.ld.dt.day; q = q[~q.ctrl & (md >= 215) & (md <= 531)]
        FT = np.zeros_like(FR); FT[di[q.ld].values, q.row.values - r0, q.col.values - c0] = True
        return days, FR, FT
    hd = np.zeros((NJ, NI)); rate = np.zeros(400); nd = np.zeros(400)
    for y in M.TRAIN:
        days, FR, FT = raster(y, f'{y}-01-01', f'{y}-06-02'); m = (days.month * 100 + days.day >= 215) & (days.month <= 5)
        hd += FT[m].sum(0); fc = FT[:, gi, gj].sum(1); np.add.at(rate, days.dayofyear[m], fc[m]); np.add.at(nd, days.dayofyear[m], 1)
    hist = uniform_filter(hd, 3, mode='constant')[gi, gj] * 9
    rate = pd.Series(rate / np.maximum(nd, 1)).rolling(7, center=True, min_periods=1).mean().values
    bid = np.array([BEAT.get((r, c), '') for r, c in zip(rows, cols)]); inb = bid != ''
    ub = np.unique(bid[inb]); bix = pd.Series(np.arange(len(ub)), index=ub); bcol = np.where(inb, bix.reindex(bid).fillna(-1).values, -1).astype(int)
    rng_of = np.array([b[:7] for b in ub])
    S_ = {k: [] for k in ('random', 'history', 'cal_hist', 'recent', 'recent_early')}; Y, FIRE, DAYS = [], [], []
    for y in M.TEST:
        days, FR, FT = raster(y, f'{y - 1}-10-01', f'{y}-06-02'); FRf = FR.astype(np.float32)
        nb7 = uniform_filter(FRf, size=(1, 7, 7), mode='constant') * 49; c7 = np.cumsum(nb7, 0); w7 = c7.copy(); w7[7:] -= c7[:-7]
        md = days.month * 100 + days.day; early = FR[(md >= 1001) | (md <= 214)].sum(0)[gi, gj]
        for t in np.where((md >= 213) & (md <= 530))[0]:
            ch = hist * rate[days[t].dayofyear] + 1e-6 * hist
            S_['random'].append(rng.random(n)); S_['history'].append(hist + 1e-6 * rng.random(n)); S_['cal_hist'].append(ch + 1e-9 * rng.random(n))
            rec = w7[t][gi, gj] * 1e3 + ch / (ch.max() + 1e-9) + 1e-9 * rng.random(n)
            S_['recent'].append(rec); S_['recent_early'].append(rec - 0.5 * (early > 0) * (w7[t][gi, gj] == 0))
            Y.append((FT[t + 1] | FT[t + 2])[gi, gj]); FIRE.append(FT[t][gi, gj]); DAYS.append(days[t])
    Y = np.array(Y); FIRE = np.array(FIRE); DAYS = pd.DatetimeIndex(DAYS); T = len(DAYS)
    dset = set(DAYS); prior_ok = np.array([(d - pd.Timedelta('1D') in dset) and (d - pd.Timedelta('2D') in dset) for d in DAYS])
    consec = np.r_[False, (np.diff(DAYS.values).astype('timedelta64[D]').astype(int) == 1)]
    def lagged(A):
        Pz = np.zeros_like(A); Pz[1:] |= A[:-1] & consec[1:, None]
        Pz[2:] |= A[:-2] & (consec[2:] & consec[1:-1])[:, None]; return Pz
    # events
    FRg = np.zeros((T, NJ, NI), bool); FRg[:, gi, gj] = FIRE
    lab = np.zeros(FRg.shape, np.int64); n_ev = 0; starts = np.flatnonzero(~consec); ends = np.r_[starts[1:], T]
    for a, z in zip(starts, ends):
        l, k = label(FRg[a:z], structure=np.ones((3, 3, 3), bool)); lab[a:z] = np.where(l > 0, l + n_ev, 0); n_ev += k
    labc = lab[:, gi, gj]; dayidx = np.broadcast_to(np.arange(T)[:, None], FIRE.shape)
    first = np.full(n_ev + 1, T); np.minimum.at(first, labc[FIRE], dayidx[FIRE])
    valid = np.zeros(n_ev + 1, bool); valid[1:] = prior_ok[np.minimum(first[1:], T - 1)]
    firstday = FIRE & (dayidx == first[labc])
    # beats
    BF = np.zeros((T, len(ub)), bool)
    for t in range(T): BF[t, np.unique(bcol[FIRE[t] & inb])] = True
    prev = np.vstack([np.zeros((1, len(ub)), bool), BF[:-1]]) & consec[:, None]; st = BF & ~prev
    ep = np.where(BF, np.cumsum(st.ravel(order='F')).reshape(BF.shape, order='F'), 0); stv = st & prior_ok[:, None]; vep = np.unique(ep[stv])
    res = {'division': name, 'n_pos': int(Y.sum()), 'n_events': int(valid.sum()), 'n_beat_episodes': len(vep)}
    for k, lst in S_.items():
        s = np.array(lst); flag = s >= np.quantile(s, 0.90)
        NEAR = np.zeros_like(flag)
        for t in range(T):
            r = np.zeros((NJ, NI), bool); r[gi, gj] = flag[t]; NEAR[t] = maximum_filter(r, 3)[gi, gj]
        res[f'{k}_cell'] = float(NEAR[Y].mean()) if Y.any() else np.nan
        res[f'{k}_covered'] = float(NEAR.mean())
        C = lagged(NEAR) & FIRE
        anyc = np.bincount(labc[C], minlength=n_ev + 1) > 0; firc = np.bincount(labc[C & firstday], minlength=n_ev + 1) > 0
        res[f'{k}_ev_first'] = float(firc[valid].mean()) if valid.any() else np.nan
        res[f'{k}_ev_any'] = float(anyc[valid].mean()) if valid.any() else np.nan
        BG = np.zeros((T, len(ub)), bool)
        for t in range(T): BG[t, np.unique(bcol[flag[t] & inb])] = True
        PB = lagged(BG)
        res[f'{k}_beat_first'] = float((stv & PB).sum() / max(1, len(vep)))
        res[f'{k}_beat_any'] = float(len(np.intersect1d(np.unique(ep[BF & PB]), vep)) / max(1, len(vep)))
        res[f'{k}_beats_per_range_day'] = float(pd.DataFrame(BG, columns=rng_of).T.groupby(level=0).sum().T.values.mean()) if len(ub) else np.nan
    print(name, res['n_events'], {k: round(res[f'{k}_ev_first'], 3) for k in S_}, flush=True)
    return res

if __name__ == '__main__':
    v = M.load_fires(); G = M.grids(); print('fires', len(v), flush=True)
    with Pool(4) as p: R = pd.DataFrame(p.map(score, [(k, r, c, v) for k, (r, c) in G.items()], chunksize=1))
    R.to_csv(OUT + 'simple_events_by_division.csv', index=False)
    ok = R[R.n_events > 0]; sm = {'divisions': len(ok), 'events': int(ok.n_events.sum()), 'beat_episodes': int(ok.n_beat_episodes.sum())}
    for k in ('random', 'history', 'cal_hist', 'recent', 'recent_early'):
        w = lambda c, wt: round(100 * np.average(ok[c].fillna(0), weights=ok[wt]), 1)
        sm[k] = {'cell': w(f'{k}_cell', 'n_pos'), 'events_strict': w(f'{k}_ev_first', 'n_events'), 'events_loose': w(f'{k}_ev_any', 'n_events'),
                 'beats_strict': w(f'{k}_beat_first', 'n_beat_episodes'), 'beats_loose': w(f'{k}_beat_any', 'n_beat_episodes'),
                 'covered_pct_mean_div': round(100 * ok[f'{k}_covered'].mean(), 1), 'beats_per_range_day': round(ok[f'{k}_beats_per_range_day'].mean(), 2)}
    json.dump(sm, open(OUT + 'simple_events_summary.json', 'w'), indent=1); print(json.dumps(sm, indent=1)); print('EVENTS_DONE')
