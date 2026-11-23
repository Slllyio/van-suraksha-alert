"""Strict officer scoring, refactored from ratapani/scoring/mp_check/mp_simple_events_new.py (same rule, verified to reproduce
its numbers). Labels/events are prepared once per period; any model is then scored from a score cube
cube[season] = float32 array (issue days 13 Feb-30 May, union cells U).
Rule: per division, flag the top 10% of all its test square-days (one cut over the test seasons); a fire event (3x3 x
consecutive-day component of target fire square-days, 15 Feb-31 May, 3 satellites, type 0, likely control burns dropped)
is caught STRICT when one of its first-day squares is flagged or next to a flag (3x3) on day -1 or -2. Brand-new = no
detection of any kind within 5 km of any first-day square in the 7 days before. Beat episode strict = >=1 flagged square in
the beat on day -1/-2 before the episode's first day. Ground share = share of test square-days flagged or next to a flag."""
import os, pickle, numpy as np, pandas as pd
from scipy.ndimage import maximum_filter, label
from multiprocessing import Pool
import common as C
PAD = 10; _yy, _xx = np.mgrid[-PAD:PAD + 1, -PAD:PAD + 1]; DISK = (_yy ** 2 + _xx ** 2) <= PAD ** 2


def _labels(period):
    tr, te = C.PERIODS[period]
    v = C.load_det(tr + te); v = v[v.type == 0][['row', 'col', 'ld', 'ctrl']].drop_duplicates()
    return v


def _prep_div(args):
    name, rows, cols, v, te = args
    vall = v
    r0, c0 = rows.min(), cols.min(); NJ, NI = rows.max() - r0 + 1, cols.max() - c0 + 1
    gi, gj = rows - r0, cols - c0; n = len(gi)
    v = v[(v.row >= r0) & (v.row < r0 + NJ) & (v.col >= c0) & (v.col < c0 + NI)]
    cells = pd.read_parquet(C.P + 'ratapani/mp_grid/mp_cells.parquet')[['row', 'col', 'beat_uid']]
    cells = cells[(cells.row >= r0) & (cells.row < r0 + NJ) & (cells.col >= c0) & (cells.col < c0 + NI)]
    BEAT = {(r, c): b for r, c, b in zip(cells.row, cells.col, cells.beat_uid)}
    def raster(d0, d1):
        days = pd.date_range(d0, d1); di = pd.Series(np.arange(len(days)), index=days)
        q = v[v.ld.isin(days)]; FR = np.zeros((len(days), NJ, NI), bool); FR[di[q.ld].values, q.row.values - r0, q.col.values - c0] = True
        md = q.ld.dt.month * 100 + q.ld.dt.day; q = q[~q.ctrl & (md >= 215) & (md <= 531)]
        FT = np.zeros_like(FR); FT[di[q.ld].values, q.row.values - r0, q.col.values - c0] = True
        return days, FR, FT
    bid = np.array([BEAT.get((r, c), '') for r, c in zip(rows, cols)]); inb = bid != ''
    ub = np.unique(bid[inb]); bix = pd.Series(np.arange(len(ub)), index=ub); bcol = np.where(inb, bix.reindex(bid).fillna(-1).values, -1).astype(int)
    rng_of = np.array([b[:7] for b in ub])
    Y, FIRE, DAYS, CLEAR, SEAS = [], [], [], [], []
    for y in te:
        days, FR, FT = raster(f'{y - 1}-10-01', f'{y}-06-02')
        q = vall[vall.ld.isin(days) & (vall.row >= r0 - PAD) & (vall.row < r0 + NJ + PAD) & (vall.col >= c0 - PAD) & (vall.col < c0 + NI + PAD)]
        di = pd.Series(np.arange(len(days)), index=days); PFR = np.zeros((len(days), NJ + 2 * PAD, NI + 2 * PAD), bool)
        PFR[di[q.ld].values, q.row.values - r0 + PAD, q.col.values - c0 + PAD] = True
        md = days.month * 100 + days.day
        for t in np.where((md >= 213) & (md <= 530))[0]:
            Y.append((FT[t + 1] | FT[t + 2])[gi, gj]); FIRE.append(FT[t][gi, gj]); DAYS.append(days[t]); SEAS.append(y)
            CLEAR.append(~maximum_filter(PFR[t - 7:t].any(0), footprint=DISK, mode='constant')[gi + PAD, gj + PAD])
    Y = np.array(Y); FIRE = np.array(FIRE); DAYS = pd.DatetimeIndex(DAYS); T = len(DAYS)
    dset = set(DAYS); prior_ok = np.array([(d - pd.Timedelta('1D') in dset) and (d - pd.Timedelta('2D') in dset) for d in DAYS])
    consec = np.r_[False, (np.diff(DAYS.values).astype('timedelta64[D]').astype(int) == 1)]
    FRg = np.zeros((T, NJ, NI), bool); FRg[:, gi, gj] = FIRE
    lab = np.zeros(FRg.shape, np.int64); n_ev = 0; starts = np.flatnonzero(~consec); ends = np.r_[starts[1:], T]
    for a, z in zip(starts, ends):
        l, k = label(FRg[a:z], structure=np.ones((3, 3, 3), bool)); lab[a:z] = np.where(l > 0, l + n_ev, 0); n_ev += k
    labc = lab[:, gi, gj]; dayidx = np.broadcast_to(np.arange(T)[:, None], FIRE.shape)
    first = np.full(n_ev + 1, T); np.minimum.at(first, labc[FIRE], dayidx[FIRE])
    valid = np.zeros(n_ev + 1, bool); valid[1:] = prior_ok[np.minimum(first[1:], T - 1)]
    firstday = FIRE & (dayidx == first[labc])
    CLEAR = np.array(CLEAR); newev = np.bincount(labc[firstday & ~CLEAR], minlength=n_ev + 1) == 0
    BF = np.zeros((T, len(ub)), bool)
    for t in range(T): BF[t, np.unique(bcol[FIRE[t] & inb])] = True
    prev = np.vstack([np.zeros((1, len(ub)), bool), BF[:-1]]) & consec[:, None]; st = BF & ~prev
    stv = st & prior_ok[:, None]
    ev_season = np.zeros(n_ev + 1, int); ev_season[labc[firstday]] = np.array(SEAS)[np.nonzero(firstday)[0]]
    # first-day squares of each event (for cell-level analyses), stored sparse
    fdt, fdi = np.nonzero(firstday)
    return dict(name=name, rows=rows, cols=cols, gi=gi, gj=gj, NJ=NJ, NI=NI, DAYS=DAYS, SEAS=np.array(SEAS), Y=Y, FIRE=FIRE,
                labc=labc, firstday=firstday, valid=valid, newev=newev, consec=consec, bcol=bcol, inb=inb, nub=len(ub),
                rng_of=rng_of, stv=stv, ev_season=ev_season, n_ev=n_ev, fd=(fdt, fdi, labc[fdt, fdi]), CLEAR=CLEAR)


def prep(period):
    fn = C.SC + f'eval_{period}{C.TAG}.pkl'
    if os.path.exists(fn): return pickle.load(open(fn, 'rb'))
    if C.SUB and os.path.exists(C.SC + f'eval_{period}.pkl'):
        R = pickle.load(open(C.SC + f'eval_{period}.pkl', 'rb')); R = {k: v for k, v in R.items() if k in C.SUBSET}
        pickle.dump(R, open(fn, 'wb'), protocol=4); return R
    v = _labels(period); G = C.grids_active(); te = C.PERIODS[period][1]
    with Pool(4) as p: R = p.map(_prep_div, [(k, r, c, v, te) for k, (r, c) in G.items()], chunksize=1)
    R = {d['name']: d for d in R}; pickle.dump(R, open(fn, 'wb'), protocol=4); return R


_E = {}; _CUBE = {}; _U = None; _Q = 0.90


def _lagged(A, consec):
    Pz = np.zeros_like(A); Pz[1:] |= A[:-1] & consec[1:, None]
    Pz[2:] |= A[:-2] & (consec[2:] & consec[1:-1])[:, None]; return Pz


def _score_div(name):
    d = _E[name]; T = len(d['DAYS']); gi, gj = d['gi'], d['gj']
    idx = np.searchsorted(_U, d['rows'] * C.W + d['cols'])
    s = np.empty((T, len(gi)), np.float32); k = 0
    for y in np.unique(d['SEAS']):
        m = d['SEAS'] == y; s[m] = _CUBE[y][:, idx]
    flag = s >= np.quantile(s, _Q)
    R3 = np.zeros((T, d['NJ'], d['NI']), bool); R3[:, gi, gj] = flag
    NEAR = maximum_filter(R3, size=(1, 3, 3))[:, gi, gj]
    Y = d['Y']; labc = d['labc']; n_ev = d['n_ev']
    C_ = _lagged(NEAR, d['consec']) & d['FIRE']
    firc = np.bincount(labc[C_ & d['firstday']], minlength=n_ev + 1) > 0
    anyc = np.bincount(labc[C_], minlength=n_ev + 1) > 0
    ids = np.nonzero(d['valid'])[0]
    BG = np.zeros((T, d['nub']), bool)
    for t in range(T): BG[t, np.unique(d['bcol'][flag[t] & d['inb']])] = True
    PB = _lagged(BG, d['consec'])
    bpr = pd.DataFrame(BG, columns=d['rng_of']).T.groupby(level=0).sum().T.values.mean() if d['nub'] else np.nan
    return dict(name=name, ev_new=d['newev'][ids], ev_strict=firc[ids], ev_loose=anyc[ids], ev_season=d['ev_season'][ids],
                beat_hit=int((d['stv'] & PB).sum()), beat_n=int(d['stv'].sum()), covered=float(NEAR.mean()),
                cell=float(NEAR[Y].mean()) if Y.any() else np.nan, npos=int(Y.sum()), bpr=bpr)


def score(cube, U, period, workers=4, q=0.90):
    """cube: {season: (n_issue_days, len(U)) float32}. Returns (summary dict, per-event DataFrame)."""
    global _E, _CUBE, _U, _Q
    _Q = q
    if not _E or _E.get('_period') != period:
        _E = prep(period); _E['_period'] = period
    _CUBE = cube; _U = U
    names = [k for k in _E if k != '_period']
    if workers > 1:
        with Pool(workers) as p: R = p.map(_score_div, names, chunksize=2)
    else: R = [_score_div(n) for n in names]
    ev = pd.concat([pd.DataFrame(dict(division=r['name'], new=r['ev_new'], strict=r['ev_strict'], loose=r['ev_loose'], season=r['ev_season'])) for r in R], ignore_index=True)
    dv = pd.DataFrame([{k: r[k] for k in ('name', 'beat_hit', 'beat_n', 'covered', 'cell', 'npos', 'bpr')} for r in R])
    return summarise(ev, dv), ev, dv


def summarise(ev, dv):
    ok = dv[dv.beat_n > 0] if len(dv) else dv
    has = set(ev.division)
    dvv = dv[dv.name.isin(has)]
    return dict(n_fires=len(ev), n_new=int(ev.new.sum()), all=100 * ev.strict.mean(), new=100 * ev.strict[ev.new].mean(),
                old=100 * ev.strict[~ev.new].mean(), loose=100 * ev.loose.mean(), beats=100 * dvv.beat_hit.sum() / max(1, dvv.beat_n.sum()),
                ground=100 * dvv.covered.mean(), cell=100 * np.average(dvv.cell.fillna(0), weights=dvv.npos), bpr=dvv.bpr.mean())


def boot(ev, B=1000, seed=0):
    """95% CI by resampling fires (events) with replacement: all and brand-new strict."""
    rng = np.random.default_rng(seed); s = ev.strict.values.astype(float); nw = ev.new.values
    a = s; b = s[nw]
    A = [a[rng.integers(0, len(a), len(a))].mean() for _ in range(B)]
    Bn = [b[rng.integers(0, len(b), len(b))].mean() for _ in range(B)]
    return dict(all_ci=tuple(100 * np.percentile(A, [2.5, 97.5])), new_ci=tuple(100 * np.percentile(Bn, [2.5, 97.5])))


def paired(ev_a, ev_b, B=2000, seed=0):
    """Paired bootstrap of the difference (b - a) in strict catch, same fires; all and brand-new. Returns diff and 95% CI."""
    assert len(ev_a) == len(ev_b)
    rng = np.random.default_rng(seed); d = ev_b.strict.values.astype(float) - ev_a.strict.values.astype(float); nw = ev_a.new.values
    out = {}
    for k, x in (('all', d), ('new', d[nw])):
        bs = [x[rng.integers(0, len(x), len(x))].mean() for _ in range(B)]
        out[k] = (100 * x.mean(), *(100 * np.percentile(bs, [2.5, 97.5])))
    return out


_QS = (0.90,)


def _score_div_q(name):
    """Same as _score_div for several flag fractions (top 1-q); returns per-q event hits and coverage."""
    d = _E[name]; T = len(d['DAYS']); gi, gj = d['gi'], d['gj']
    idx = np.searchsorted(_U, d['rows'] * C.W + d['cols'])
    s = np.empty((T, len(gi)), np.float32)
    for y in np.unique(d['SEAS']):
        m = d['SEAS'] == y; s[m] = _CUBE[y][:, idx]
    out = {}; ids = np.nonzero(d['valid'])[0]; labc = d['labc']; n_ev = d['n_ev']
    for q in _QS:
        flag = s >= np.quantile(s, q)
        R3 = np.zeros((T, d['NJ'], d['NI']), bool); R3[:, gi, gj] = flag
        NEAR = maximum_filter(R3, size=(1, 3, 3))[:, gi, gj]
        C_ = _lagged(NEAR, d['consec']) & d['FIRE']
        firc = np.bincount(labc[C_ & d['firstday']], minlength=n_ev + 1) > 0
        out[q] = (firc[ids], float(NEAR.mean()))
    return name, d['newev'][ids], out


def score_matched(cube, U, period, target_ground, qs=(0.86, 0.88, 0.90, 0.92, 0.94)):
    """Strict all / brand-new catch at a matched ground share: score at several flag fractions, interpolate linearly
    in ground share to target_ground (percent)."""
    global _E, _CUBE, _U, _QS
    if not _E or _E.get('_period') != period:
        _E = prep(period); _E['_period'] = period
    _CUBE = cube; _U = U; _QS = qs
    names = [k for k in _E if k != '_period']
    with Pool(4) as p: R = p.map(_score_div_q, names, chunksize=2)
    rows = []
    for q in qs:
        hits = np.concatenate([r[2][q][0] for r in R]); new = np.concatenate([r[1] for r in R])
        cov = np.mean([r[2][q][1] for r in R if len(r[1])])
        rows.append(dict(q=q, ground=100 * cov, all=100 * hits.mean(), new=100 * hits[new].mean()))
    T = pd.DataFrame(rows).sort_values('ground')
    res = dict(ground=target_ground, all=float(np.interp(target_ground, T.ground, T['all'])), new=float(np.interp(target_ground, T.ground, T['new'])))
    return res, T
