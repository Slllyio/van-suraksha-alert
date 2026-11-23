"""OBLIQUE-PASS CHECK, step 3 (Akkshay 17 Oct 08:55Z "do it"). Same scoring as mp_simple_events.py (each fire once,
STRICT = a first-day square flagged or next to a flag on day -1/-2, season rules, 3 satellites), plus:
 Test A (labels): each fire event weighted by 1 / detection factor of its most detectable first-day square-day
   (WORST and MIX from mp_va_weights.py), or events whose first day was seen only beyond 56 deg in closed Feb-Mar
   canopy dropped.
 Test B (history): "burned before", "x time of year" and "fires nearby 7 d" rebuilt from weighted counts (1 / f_worst),
   so fires hidden on slant passes are counted up in the history.
Needs $VA_OUT/va_cellday_3sat.parquet. Out: va_score_by_division.csv, va_score_summary.json"""
import os; os.environ['MPV'] = 'season'
import json, numpy as np, pandas as pd
from scipy.ndimage import maximum_filter, uniform_filter, label
from multiprocessing import Pool
import mp_simple_rules as M
P, OUT = M.P, M.OUT
VAF = os.environ.get('VA_OUT', '/tmp/claude-0/va') + '/va_cellday_3sat.parquet'
cells = pd.read_parquet(P + 'ratapani/mp_grid/mp_cells.parquet')[['row', 'col']]
KS = ('random', 'history', 'cal_hist', 'recent', 'history_w', 'cal_hist_w', 'recent_w')

def score(args):
    name, rows, cols, v = args
    r0, c0 = rows.min(), cols.min(); NJ, NI = rows.max() - r0 + 1, cols.max() - c0 + 1
    gi, gj = rows - r0, cols - c0; n = len(gi)
    v = v[(v.row >= r0) & (v.row < r0 + NJ) & (v.col >= c0) & (v.col < c0 + NI)]
    rng = np.random.default_rng(0)
    def raster(d0, d1):
        days = pd.date_range(d0, d1); di = pd.Series(np.arange(len(days)), index=days)
        q = v[v.ld.isin(days)]; ix = (di[q.ld].values, q.row.values - r0, q.col.values - c0)
        FR = np.zeros((len(days), NJ, NI), bool); FR[ix] = True
        WR = np.zeros(FR.shape, np.float32); np.maximum.at(WR, ix, 1 / q.f_worst.values)
        md = q.ld.dt.month * 100 + q.ld.dt.day; q = q[~q.ctrl & (md >= 215) & (md <= 531)]
        ix = (di[q.ld].values, q.row.values - r0, q.col.values - c0)
        FT = np.zeros_like(FR); FT[ix] = True
        WT = np.zeros(FR.shape, np.float32); np.maximum.at(WT, ix, 1 / q.f_worst.values)
        FW = np.zeros(FR.shape, np.float32); np.maximum.at(FW, ix, q.f_worst.values)
        FM = np.zeros(FR.shape, np.float32); np.maximum.at(FM, ix, q.f_mix.values)
        return days, FR, FT, WR, WT, FW, FM
    hd = np.zeros((NJ, NI)); hdw = np.zeros((NJ, NI)); rate = np.zeros(400); ratew = np.zeros(400); nd = np.zeros(400)
    for y in M.TRAIN:
        days, FR, FT, WR, WT, FW, FM = raster(f'{y}-01-01', f'{y}-06-02'); m = (days.month * 100 + days.day >= 215) & (days.month <= 5)
        hd += FT[m].sum(0); hdw += WT[m].sum(0)
        np.add.at(rate, days.dayofyear[m], FT[:, gi, gj].sum(1)[m]); np.add.at(ratew, days.dayofyear[m], WT[:, gi, gj].sum(1)[m]); np.add.at(nd, days.dayofyear[m], 1)
    sm7 = lambda a: pd.Series(a / np.maximum(nd, 1)).rolling(7, center=True, min_periods=1).mean().values
    hist = uniform_filter(hd, 3, mode='constant')[gi, gj] * 9; histw = uniform_filter(hdw, 3, mode='constant')[gi, gj] * 9
    rate, ratew = sm7(rate), sm7(ratew)
    S_ = {k: [] for k in KS}; Y, FIRE, DAYS, FWL, FML = [], [], [], [], []
    for y in M.TEST:
        days, FR, FT, WR, WT, FW, FM = raster(f'{y - 1}-10-01', f'{y}-06-02')
        def win7(A):
            c = np.cumsum(uniform_filter(A.astype(np.float32), size=(1, 7, 7), mode='constant') * 49, 0); w = c.copy(); w[7:] -= c[:-7]; return w
        w7, w7w = win7(FR), win7(WR)
        md = days.month * 100 + days.day
        for t in np.where((md >= 213) & (md <= 530))[0]:
            ch = hist * rate[days[t].dayofyear] + 1e-6 * hist; chw = histw * ratew[days[t].dayofyear] + 1e-6 * histw
            S_['random'].append(rng.random(n)); S_['history'].append(hist + 1e-6 * rng.random(n)); S_['cal_hist'].append(ch + 1e-9 * rng.random(n))
            S_['recent'].append(w7[t][gi, gj] * 1e3 + ch / (ch.max() + 1e-9) + 1e-9 * rng.random(n))
            S_['history_w'].append(histw + 1e-6 * rng.random(n)); S_['cal_hist_w'].append(chw + 1e-9 * rng.random(n))
            S_['recent_w'].append(np.round(w7w[t][gi, gj], 3) * 1e3 + chw / (chw.max() + 1e-9) + 1e-9 * rng.random(n))
            Y.append((FT[t + 1] | FT[t + 2])[gi, gj]); FIRE.append(FT[t][gi, gj]); DAYS.append(days[t])
            FWL.append(FW[t][gi, gj]); FML.append(FM[t][gi, gj])
    Y = np.array(Y); FIRE = np.array(FIRE); DAYS = pd.DatetimeIndex(DAYS); T = len(DAYS); FWL = np.array(FWL); FML = np.array(FML)
    dset = set(DAYS); prior_ok = np.array([(d - pd.Timedelta('1D') in dset) and (d - pd.Timedelta('2D') in dset) for d in DAYS])
    consec = np.r_[False, (np.diff(DAYS.values).astype('timedelta64[D]').astype(int) == 1)]
    def lagged(A):
        Pz = np.zeros_like(A); Pz[1:] |= A[:-1] & consec[1:, None]
        Pz[2:] |= A[:-2] & (consec[2:] & consec[1:-1])[:, None]; return Pz
    FRg = np.zeros((T, NJ, NI), bool); FRg[:, gi, gj] = FIRE
    lab = np.zeros(FRg.shape, np.int64); n_ev = 0; starts = np.flatnonzero(~consec); ends = np.r_[starts[1:], T]
    for a, z in zip(starts, ends):
        l, k = label(FRg[a:z], structure=np.ones((3, 3, 3), bool)); lab[a:z] = np.where(l > 0, l + n_ev, 0); n_ev += k
    labc = lab[:, gi, gj]; dayidx = np.broadcast_to(np.arange(T)[:, None], FIRE.shape)
    first = np.full(n_ev + 1, T); np.minimum.at(first, labc[FIRE], dayidx[FIRE])
    valid = np.zeros(n_ev + 1, bool); valid[1:] = prior_ok[np.minimum(first[1:], T - 1)]
    firstday = FIRE & (dayidx == first[labc])
    efw = np.zeros(n_ev + 1); np.maximum.at(efw, labc[firstday], FWL[firstday])
    efm = np.zeros(n_ev + 1); np.maximum.at(efm, labc[firstday], FML[firstday])
    WW = np.where(valid, 1 / np.maximum(efw, 0.35), 0); WM = np.where(valid, 1 / np.maximum(efm, 0.35), 0); keep = valid & (efw > 0.35)
    res = {'division': name, 'n_events': int(valid.sum()), 'w_worst': float(WW.sum()), 'w_mix': float(WM.sum()), 'n_keep': int(keep.sum()),
           'n_closed_fm_events': int((valid & (efw < 1)).sum())}
    for k, lst in S_.items():
        s = np.array(lst); flag = s >= np.quantile(s, 0.90)
        NEAR = np.zeros_like(flag)
        for t in range(T):
            r = np.zeros((NJ, NI), bool); r[gi, gj] = flag[t]; NEAR[t] = maximum_filter(r, 3)[gi, gj]
        C = lagged(NEAR) & FIRE
        firc = np.bincount(labc[C & firstday], minlength=n_ev + 1) > 0
        ok = valid.any()
        res[f'{k}_ev_first'] = float(firc[valid].mean()) if ok else np.nan
        res[f'{k}_wworst'] = float((firc * WW).sum() / WW.sum()) if ok else np.nan
        res[f'{k}_wmix'] = float((firc * WM).sum() / WM.sum()) if ok else np.nan
        res[f'{k}_drop'] = float(firc[keep].mean()) if keep.any() else np.nan
        res[f'{k}_closed_fm'] = float(firc[valid & (efw < 1)].mean()) if (valid & (efw < 1)).any() else np.nan
        res[f'{k}_covered'] = float(NEAR.mean())
    print(name, res['n_events'], {k: (round(res[f'{k}_ev_first'], 3), round(res[f'{k}_wworst'], 3)) for k in S_}, flush=True)
    return res

if __name__ == '__main__':
    v = M.load_fires(); VA = pd.read_parquet(VAF, columns=['row', 'col', 'ld', 'f_worst', 'f_mix'])
    v = v.merge(VA, on=['row', 'col', 'ld'], how='left').fillna({'f_worst': 1.0, 'f_mix': 1.0})
    print('fires', len(v), 'with factor < 1:', int((v.f_worst < 1).sum()), flush=True)
    G = M.grids()
    with Pool(4) as p: R = pd.DataFrame(p.map(score, [(k, r, c, v) for k, (r, c) in G.items()], chunksize=1))
    R.to_csv(OUT + 'va_score_by_division.csv', index=False)
    ok = R[R.n_events > 0]
    sm = {'divisions': len(ok), 'events': int(ok.n_events.sum()), 'events_weighted_worst': round(ok.w_worst.sum()),
          'events_weighted_mix': round(ok.w_mix.sum()), 'events_kept_after_drop': int(ok.n_keep.sum()), 'closed_feb_mar_events_with_slant_best_look': int(ok.n_closed_fm_events.sum())}
    for k in KS:
        w = lambda c, wt: round(100 * np.average(ok[c].fillna(0), weights=ok[wt]), 1)
        sm[k] = {'strict': w(f'{k}_ev_first', 'n_events'), 'strict_weighted_worst': w(f'{k}_wworst', 'w_worst'),
                 'strict_weighted_mix': w(f'{k}_wmix', 'w_mix'), 'strict_drop_oblique_only': w(f'{k}_drop', 'n_keep'),
                 'strict_on_slant_closed_feb_mar_events': w(f'{k}_closed_fm', 'n_closed_fm_events'),
                 'covered_pct_mean_div': round(100 * ok[f'{k}_covered'].mean(), 1)}
    json.dump(sm, open(OUT + 'va_score_summary.json', 'w'), indent=1); print(json.dumps(sm, indent=1)); print('VA_DONE')
