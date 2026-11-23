"""SCAR-OUTLINE HISTORY vs VIIRS history (research/ceiling/scar_hist). Based on starts.py.
BRAND-NEW FIRES version of mp_simple_events.py: same scoring, plus each event tagged "new" when no fire
(any satellite/type-0 detection, any date incl. before 15 Feb and control burns) lies within 5 km of any first-day square
in the 7 days before the first day. Out: simple_events_new_by_division.csv, simple_events_new_summary.json.

Simple rules on the PC's FINAL officer scoring with the seasonal rules (van-suraksha-alert PR #1 commit 4cb67686,
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
from scipy.ndimage import maximum_filter, uniform_filter, label, gaussian_filter
from multiprocessing import Pool
import sys; sys.path.insert(0, '/mnt/project-files/ratapani/scoring/mp_check')
import mp_simple_rules as M
P = M.P; OUT = '/mnt/project-files/research/ceiling/scar_hist/'
SC = pd.read_parquet(OUT + 'scar_cells.parquet'); SC = SC[SC.frac >= 0.10]
PAD = 10; yy, xx = np.mgrid[-PAD:PAD + 1, -PAD:PAD + 1]; DISK = (yy ** 2 + xx ** 2) <= PAD ** 2  # 5 km at 500 m
cells = pd.read_parquet(P + 'ratapani/mp_grid/mp_cells.parquet')[['row', 'col', 'beat_uid']]
BEAT = {(r, c): b for r, c, b in zip(cells.row, cells.col, cells.beat_uid)}

def score(args):
    name, rows, cols, v = args
    vall = v
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
    sd = np.zeros((NJ, NI)); hd = np.zeros((NJ, NI)); rate = np.zeros(400); nd = np.zeros(400)
    for y in M.TRAIN:
        days, FR, FT = raster(y, f'{y}-01-01', f'{y}-06-02'); m = (days.month * 100 + days.day >= 215) & (days.month <= 5)
        nb = uniform_filter(FR.astype(np.float32), size=(1, 7, 7), mode='constant') * 49; cn = np.cumsum(nb, 0); w3 = cn.copy(); w3[3:] -= cn[:-3]
        prior3 = np.zeros_like(w3); prior3[1:] = w3[:-1]
        sd += (FT & (prior3 < 0.5))[m].sum(0)
        hd += FT[m].sum(0); fc = FT[:, gi, gj].sum(1); np.add.at(rate, days.dayofyear[m], fc[m]); np.add.at(nd, days.dayofyear[m], 1)
    hist = uniform_filter(hd, 3, mode='constant')[gi, gj] * 9
    sc = SC[(SC.row >= r0) & (SC.row < r0 + NJ) & (SC.col >= c0) & (SC.col < c0 + NI)]
    def scr(years):
        q = sc[sc.year.isin(years)]; A = np.zeros((NJ, NI)); np.add.at(A, (q.row.values - r0, q.col.values - c0), 1.0); return A
    sh_same = scr(M.TRAIN); sh_all = scr(range(2017, max(M.TRAIN) + 1))
    shs = uniform_filter(sh_same, 3, mode='constant')[gi, gj] * 9 + sh_same[gi, gj]   # own square counts double
    sha = uniform_filter(sh_all, 3, mode='constant')[gi, gj] * 9 + sh_all[gi, gj]
    k2 = gaussian_filter(sd, 4, mode='constant')[gi, gj]; k5 = gaussian_filter(sd, 10, mode='constant')[gi, gj]
    rk = lambda a: pd.Series(a).rank(pct=True).values
    hk2 = rk(hist) + rk(k2); hsc = rk(hist) + rk(sha)
    rate = pd.Series(rate / np.maximum(nd, 1)).rolling(7, center=True, min_periods=1).mean().values
    bid = np.array([BEAT.get((r, c), '') for r, c in zip(rows, cols)]); inb = bid != ''
    ub = np.unique(bid[inb]); bix = pd.Series(np.arange(len(ub)), index=ub); bcol = np.where(inb, bix.reindex(bid).fillna(-1).values, -1).astype(int)
    rng_of = np.array([b[:7] for b in ub])
    S_ = {k: [] for k in ('history', 'scar_same', 'scar_all', 'hist_scar', 'cal_history', 'cal_scar_all', 'cal_hist_scar')}; Y, FIRE, DAYS, CLEAR = [], [], [], []
    for y in M.TEST:
        days, FR, FT = raster(y, f'{y - 1}-10-01', f'{y}-06-02'); FRf = FR.astype(np.float32)
        q = vall[vall.ld.isin(days) & (vall.row >= r0 - PAD) & (vall.row < r0 + NJ + PAD) & (vall.col >= c0 - PAD) & (vall.col < c0 + NI + PAD)]
        di = pd.Series(np.arange(len(days)), index=days); PFR = np.zeros((len(days), NJ + 2 * PAD, NI + 2 * PAD), bool)
        PFR[di[q.ld].values, q.row.values - r0 + PAD, q.col.values - c0 + PAD] = True
        nb7 = uniform_filter(FRf, size=(1, 7, 7), mode='constant') * 49; c7 = np.cumsum(nb7, 0); w7 = c7.copy(); w7[7:] -= c7[:-7]
        md = days.month * 100 + days.day; early = FR[(md >= 1001) | (md <= 214)].sum(0)[gi, gj]
        for t in np.where((md >= 213) & (md <= 530))[0]:
            r_ = rate[days[t].dayofyear]; z = 1e-9 * rng.random(n)
            S_['history'].append(hist + z); S_['scar_same'].append(shs + z); S_['scar_all'].append(sha + z); S_['hist_scar'].append(hsc + z)
            S_['cal_history'].append(hist * r_ + 1e-6 * hist + z); S_['cal_scar_all'].append(sha * r_ + 1e-6 * sha + z); S_['cal_hist_scar'].append(hsc * r_ + 1e-6 * hsc + z)
            Y.append((FT[t + 1] | FT[t + 2])[gi, gj]); FIRE.append(FT[t][gi, gj]); DAYS.append(days[t])
            CLEAR.append(~maximum_filter(PFR[t - 7:t].any(0), footprint=DISK, mode='constant')[gi + PAD, gj + PAD])
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
    CLEAR = np.array(CLEAR); newev = np.bincount(labc[firstday & ~CLEAR], minlength=n_ev + 1) == 0; nvalid = valid & newev
    # beats
    BF = np.zeros((T, len(ub)), bool)
    for t in range(T): BF[t, np.unique(bcol[FIRE[t] & inb])] = True
    prev = np.vstack([np.zeros((1, len(ub)), bool), BF[:-1]]) & consec[:, None]; st = BF & ~prev
    ep = np.where(BF, np.cumsum(st.ravel(order='F')).reshape(BF.shape, order='F'), 0); stv = st & prior_ok[:, None]; vep = np.unique(ep[stv])
    res = {'division': name, 'n_pos': int(Y.sum()), 'n_events': int(valid.sum()), 'n_new': int(nvalid.sum()), 'n_beat_episodes': len(vep)}
    for k, lst in S_.items():
        s = np.array(lst); flag = (s >= np.quantile(s, float(os.environ.get('QFLAG', 0.90)), axis=1, keepdims=True)) if os.environ.get('DAILY') == '1' else (s >= np.quantile(s, 0.90))   # DAILY=1: top 10% of the division each day (no hindsight)
        NEAR = np.zeros_like(flag)
        for t in range(T):
            r = np.zeros((NJ, NI), bool); r[gi, gj] = flag[t]; NEAR[t] = maximum_filter(r, 3)[gi, gj]
        res[f'{k}_cell'] = float(NEAR[Y].mean()) if Y.any() else np.nan
        res[f'{k}_covered'] = float(NEAR.mean())
        C = lagged(NEAR) & FIRE
        anyc = np.bincount(labc[C], minlength=n_ev + 1) > 0; firc = np.bincount(labc[C & firstday], minlength=n_ev + 1) > 0
        res[f'{k}_ev_first'] = float(firc[valid].mean()) if valid.any() else np.nan
        res[f'{k}_ev_any'] = float(anyc[valid].mean()) if valid.any() else np.nan
        res[f'{k}_new_first'] = float(firc[nvalid].mean()) if nvalid.any() else np.nan
        res[f'{k}_new_any'] = float(anyc[nvalid].mean()) if nvalid.any() else np.nan
        res[f'{k}_old_first'] = float(firc[valid & ~newev].mean()) if (valid & ~newev).any() else np.nan
        BG = np.zeros((T, len(ub)), bool)
        for t in range(T): BG[t, np.unique(bcol[flag[t] & inb])] = True
        PB = lagged(BG)
        res[f'{k}_beat_first'] = float((stv & PB).sum() / max(1, len(vep)))
        res[f'{k}_beat_any'] = float(len(np.intersect1d(np.unique(ep[BF & PB]), vep)) / max(1, len(vep)))
        res[f'{k}_beats_per_range_day'] = float(pd.DataFrame(BG, columns=rng_of).T.groupby(level=0).sum().T.values.mean()) if len(ub) else np.nan
    print(name, res['n_events'], res['n_new'], {k: round(res[f'{k}_new_first'], 3) for k in S_}, flush=True)
    return res

if __name__ == '__main__':
    v = M.load_fires(); G = M.grids(); print('fires', len(v), flush=True)
    with Pool(4) as p: R = pd.DataFrame(p.map(score, [(k, r, c, v) for k, (r, c) in G.items()], chunksize=1))
    R.to_csv(OUT + 'scarhist_by_division' + ({'1': '_fwd', '2026': '_fwd2026'}.get(os.environ.get('FWD'), '')) + ('_daily' if os.environ.get('DAILY') == '1' else '') + ('_q' + os.environ['QFLAG'] if 'QFLAG' in os.environ else '') + '.csv', index=False)
    ok = R[R.n_events > 0]; sm = {'divisions': len(ok), 'events': int(ok.n_events.sum()), 'beat_episodes': int(ok.n_beat_episodes.sum()), 'new_events': int(ok.n_new.sum())}
    for k in ('history', 'scar_same', 'scar_all', 'hist_scar', 'cal_history', 'cal_scar_all', 'cal_hist_scar'):
        w = lambda c, wt: round(100 * np.average(ok[c].fillna(0), weights=ok[wt]), 1)
        oo = ok.assign(n_old=ok.n_events - ok.n_new)
        sm[k] = {'new_strict': round(100 * np.average(ok[f'{k}_new_first'].fillna(0), weights=ok.n_new), 1), 'new_loose': round(100 * np.average(ok[f'{k}_new_any'].fillna(0), weights=ok.n_new), 1),
                 'not_new_strict': round(100 * np.average(oo[f'{k}_old_first'].fillna(0), weights=oo.n_old), 1), 'cell': w(f'{k}_cell', 'n_pos'), 'events_strict': w(f'{k}_ev_first', 'n_events'), 'events_loose': w(f'{k}_ev_any', 'n_events'),
                 'beats_strict': w(f'{k}_beat_first', 'n_beat_episodes'), 'beats_loose': w(f'{k}_beat_any', 'n_beat_episodes'),
                 'covered_pct_mean_div': round(100 * ok[f'{k}_covered'].mean(), 1), 'beats_per_range_day': round(ok[f'{k}_beats_per_range_day'].mean(), 2)}
    json.dump(sm, open(OUT + 'scarhist_summary' + ({'1': '_fwd', '2026': '_fwd2026'}.get(os.environ.get('FWD'), '')) + ('_daily' if os.environ.get('DAILY') == '1' else '') + ('_q' + os.environ['QFLAG'] if 'QFLAG' in os.environ else '') + '.json', 'w'), indent=1); print(json.dumps(sm, indent=1)); print('EVENTS_DONE')
