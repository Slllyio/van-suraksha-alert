"""List timing (round 23): score daily / twice-daily list schedules on one common set of fires with pass-time rules.

Fires: the strict mp_check events of system_rebuild/evalr.py (10 divisions; 3x3 x consecutive-day components of target
fire square-days; brand-new flag unchanged). New here, each fire gets a FIRST DETECTION TIME T_f (earliest VIIRS
target detection, IST) and its first-pass squares S_f (first-day squares whose earliest detection is in the same pass
slot as T_f: night ~01:30 or day ~13:30).
Lists: a schedule is a series of lists, each = (issue time, information state, issue item). Information states
(lt_train.py): MD = detections through the day pass of day D; MN = also the night pass of D+1.
Rule (the same for every schedule): a fire is caught if any list issued in the 48 h before T_f flags, or is next to a
flag (3x3), one of its first-pass squares. Daily schedules thus use their 2 latest lists, twice-daily ones their 4.
Flags: per division and per information state, the top (1-q) of its test square-lists (one cut over the test seasons).
Ground: per list = share of the division's squares flagged or next to a flag (as before); in force = share flagged or
next to a flag on ANY list a fire would be scored against (union of lists issued in the last 48 h), time-weighted.
Schedules are compared at matched in-force ground (the q is found per schedule), paired by fire against A20."""
import sys, os, pickle
sys.path.insert(0, '/mnt/project-files/ratapani/fsi/scouting/code/system_rebuild')
import numpy as np, pandas as pd
from scipy.ndimage import maximum_filter
from multiprocessing import Pool
import common as C
C.SC = '/tmp/claude-0/-home-user/be9b8f54-cc26-52cb-bdbb-9c8008a24baf/scratchpad/r23/'
import evalr as E, features as Fe
SC = C.SC
H = pd.Timedelta('1h'); D1 = pd.Timedelta('1D')

# schedule name -> list of (state, hour of issue, day offset of issue relative to item day D)
SCHED = {
    'A20':  [('MD', 20, 0)],                  # current: after the day pass, NASA NRT (13:30 + ~5 h), 20:00 day t
    'A16f': [('MD', 16, 0)],                  # same information, FSI speed: 16:00 day t
    'B06f': [('MN', 6, 1)],                   # 06:00 day t+1 with the night pass (FSI speed)
    'B06n': [('MD', 6, 1)],                   # 06:00 day t+1 with NASA NRT: night pass not in yet (= A20, 10 h later)
    'B09n': [('MN', 9, 1)],                   # 09:00 day t+1, NASA NRT has the night pass by ~07:00-09:30
    'C_f':  [('MN', 6, 1), ('MD', 16, 1)],    # twice daily, FSI: 06:00 (night pass) + 16:00 (day pass)
    'C_n':  [('MD', 6, 1), ('MN', 16, 1)],    # twice daily at the same clock times, NASA NRT delays
}
LABEL = {'A20': 'A  20:00, day pass (now)', 'A16f': "A' 16:00, day pass, FSI", 'B06f': 'B  06:00 +night pass, FSI',
         'B06n': 'B  06:00, NASA (night not in)', 'B09n': "B' 09:00 +night pass, NASA", 'C_f': 'C  06:00+16:00, FSI',
         'C_n': 'C  06:00+16:00, NASA'}


def cubes(period):
    out = {}
    for st in ('MD', 'MN'):
        fn = SC + (f'cube_{st}_{period}.pkl' if not (st == 'MD' and period == 'held') else 'cube_L2_static_held_sub.pkl')
        out[st] = pickle.load(open(fn, 'rb'))
    return out


def event_times(period):
    """Per division: event table (ev id, T_f, night_first, new, season) and first-pass cells."""
    fn = SC + f'evtimes_{period}.pkl'
    if os.path.exists(fn): return pickle.load(open(fn, 'rb'))
    R = E.prep(period); tr, te = C.PERIODS[period]
    v = C.load_det(te); v = v[(v.type == 0) & ~v.ctrl]
    md = v.ld.dt.month * 100 + v.ld.dt.day; v = v[(md >= 215) & (md <= 531)]
    v = v.assign(ist=v.utc + pd.Timedelta(hours=5, minutes=30)).sort_values('ist')
    first = v.groupby(['row', 'col', 'ld']).agg(ist=('ist', 'first'), dn=('daynight', 'first'), frp=('frp', 'first'), sat=('sat', 'first')).reset_index()
    out = {}
    for name, d in R.items():
        fdt, fdi, lab = d['fd']
        q = pd.DataFrame(dict(lab=lab, cell=fdi, row=d['rows'][fdi], col=d['cols'][fdi], ld=d['DAYS'][fdt]))
        q = q.merge(first, on=['row', 'col', 'ld'], how='left')
        assert q.ist.notna().all(), name
        q = q[d['valid'][q.lab.values]]
        tf = q.groupby('lab').ist.transform('min'); dnf = q.sort_values('ist').groupby('lab').dn.transform('first')
        q = q.assign(tf=tf, dnf=dnf)
        cells = q[q.dn == q.dnf][['lab', 'cell', 'tf']]
        ev = q.sort_values('ist').groupby('lab').agg(tf=('ist', 'first'), dn=('dn', 'first'), ld=('ld', 'first'), frp=('frp', 'first'), sat=('sat', 'first'),
                                                    nfirst=('cell', 'size')).reset_index()
        ev['new'] = d['newev'][ev.lab.values]; ev['season'] = d['ev_season'][ev.lab.values]; ev['division'] = name
        md_ = ev.ld.dt.month * 100 + ev.ld.dt.day
        ev['common'] = md_ >= 216     # every schedule has all its 48 h lists for fires from 16 Feb
        out[name] = dict(ev=ev, cells=cells)
    pickle.dump(out, open(fn, 'wb'), protocol=4); return out


def build_lists(sched, period, CU):
    """Sorted list table: issue time, state, cube season, row in that season's cube."""
    rows = []
    for st, hr, off in SCHED[sched]:
        for y in C.PERIODS[period][1]:
            days = pd.date_range(f'{y}-02-13', f'{y}-05-30'); assert len(days) == CU[st][y].shape[0]
            for i, dd in enumerate(days): rows.append((dd + off * D1 + hr * H, st, y, i))
    L = pd.DataFrame(rows, columns=['issue', 'state', 'y', 'i']).sort_values('issue').reset_index(drop=True)
    return L


_G = {}


def _div(args):
    name, q, near_extra = args
    d = _G['R'][name]; L = _G['L']; CU = _G['CU']; U = _G['U']; et = _G['ET'][name]
    idx = np.searchsorted(U, d['rows'] * C.W + d['cols']); gi, gj = d['gi'], d['gj']
    S = np.empty((len(L), len(gi)), np.float32)
    for k, (st, y, i) in enumerate(zip(L.state.values, L.y.values, L.i.values)): S[k] = CU[st][y][i, idx]
    flag = np.zeros(S.shape, bool)
    for st in L.state.unique():
        m = L.state.values == st; flag[m] = S[m] >= np.quantile(S[m], q)
    R3 = np.zeros((len(L), d['NJ'], d['NI']), bool); R3[:, gi, gj] = flag
    NEAR = maximum_filter(R3, size=(1, 3, 3))[:, gi, gj]
    EXT = {r: maximum_filter(R3, size=(1, 2 * r + 1, 2 * r + 1))[:, gi, gj] for r in near_extra}
    I = L.issue.values
    # ground: per list and in force (union of lists issued in the last 48 h), time-weighted to the next issue
    dur = np.r_[np.diff(I).astype('timedelta64[m]').astype(float), np.nan]
    dur[~(dur < 3 * 1440)] = np.nan; dur[np.isnan(dur)] = np.nanmedian(dur)   # last list of each season
    per_list = NEAR.mean(1)
    lo = np.searchsorted(I, I - np.timedelta64(48, 'h'), 'right')
    inforce = np.empty(len(L))
    for k in range(len(L)): inforce[k] = NEAR[lo[k]:k + 1].any(0).mean()
    # events
    ev = et['ev']; cells = et['cells']
    tf = cells.tf.values.astype('datetime64[ns]')
    hi = np.searchsorted(I, tf, 'left'); lo2 = np.searchsorted(I, tf - np.timedelta64(48, 'h'), 'right')
    labs = cells.lab.values; ci = cells.cell.values
    nmax = int((hi - lo2).max())
    hit_last = np.full(len(cells), -1); hit_first = np.full(len(cells), 1 << 30); ext_hit = {r: np.zeros(len(cells), bool) for r in near_extra}
    for j in range(nmax):
        k = hi - 1 - j; ok = k >= lo2; kk = np.where(ok, k, 0)
        h = ok & NEAR[kk, ci]
        hit_last = np.where(h & (hit_last < 0), k, hit_last); hit_first = np.where(h, np.minimum(hit_first, k), hit_first)
        for r in near_extra: ext_hit[r] |= ok & EXT[r][kk, ci]
    df = pd.DataFrame(dict(lab=labs, hl=hit_last, hf=hit_first, nl=hi - lo2, latest=hi - 1, **{f'ext{r}': ext_hit[r] for r in near_extra}))
    g = df.groupby('lab').agg(hl=('hl', 'max'), hf=('hf', 'min'), nl=('nl', 'min'), latest=('latest', 'max'), **{f'ext{r}': (f'ext{r}', 'max') for r in near_extra})
    e = ev.set_index('lab').join(g)
    e['caught'] = e.hl >= 0
    tfe = e.tf.values.astype('datetime64[ns]')
    e['lead_last_h'] = np.where(e.caught, (tfe - I[np.maximum(e.hl.values, 0)]) / np.timedelta64(1, 'h'), np.nan)
    e['lead_first_h'] = np.where(e.caught, (tfe - I[np.minimum(e.hf.values, len(I) - 1)]) / np.timedelta64(1, 'h'), np.nan)
    e['since_list_h'] = (tfe - I[e.latest.values]) / np.timedelta64(1, 'h')
    return dict(name=name, ev=e.reset_index(), per_list=np.average(per_list, weights=dur), inforce=np.average(inforce, weights=dur))


def evaluate(sched, period, q=0.90, near_extra=(), CU=None, workers=4):
    global _G
    CU = CU or cubes(period)
    _G = dict(R=E.prep(period), L=build_lists(sched, period, CU), CU=CU, U=Fe.base()['U'], ET=event_times(period))
    names = sorted(_G['R'])
    with Pool(workers) as p: out = p.map(_div, [(n, q, near_extra) for n in names])
    ev = pd.concat([o['ev'] for o in out], ignore_index=True); ev = ev[ev.common].reset_index(drop=True)
    has = set(ev.division)
    gl = np.mean([o['per_list'] for o in out if o['name'] in has]); gf = np.mean([o['inforce'] for o in out if o['name'] in has])
    return dict(sched=sched, period=period, q=q, ground_list=100 * gl, ground_inforce=100 * gf, all=100 * ev.caught.mean(),
                new=100 * ev.caught[ev.new].mean(), n=len(ev), n_new=int(ev.new.sum())), ev


def matched(sched, period, target, qs, CU, near_extra=()):
    rows = [evaluate(sched, period, q, CU=CU)[0] for q in qs]
    T = pd.DataFrame(rows).sort_values('ground_inforce')
    q = float(np.interp(target, T.ground_inforce, T.q))
    return evaluate(sched, period, q, near_extra=near_extra, CU=CU), T


def paired(ea, eb, B=2000, seed=0):
    ea = ea.set_index(['division', 'lab']); eb = eb.set_index(['division', 'lab']).loc[ea.index]
    rng = np.random.default_rng(seed); dd = eb.caught.values.astype(float) - ea.caught.values.astype(float); nw = ea.new.values
    o = {}
    for k, x in (('all', dd), ('new', dd[nw])):
        bs = [x[rng.integers(0, len(x), len(x))].mean() for _ in range(B)]
        o[k] = (100 * x.mean(), *(100 * np.percentile(bs, [2.5, 97.5])))
    return o


def boot(ev, B=1000, seed=0):
    rng = np.random.default_rng(seed); s = ev.caught.values.astype(float); nw = ev.new.values
    A = [s[rng.integers(0, len(s), len(s))].mean() for _ in range(B)]; b = s[nw]
    Bn = [b[rng.integers(0, len(b), len(b))].mean() for _ in range(B)]
    return tuple(100 * np.percentile(A, [2.5, 97.5])), tuple(100 * np.percentile(Bn, [2.5, 97.5]))


if __name__ == '__main__':
    import json
    OUT = '/mnt/project-files/ratapani/fsi/scouting/code/list_timing/out/'; os.makedirs(OUT, exist_ok=True)
    per = sys.argv[1]; CU = cubes(per)
    base, eb = evaluate('A20', per, 0.90, near_extra=(2, 5), CU=CU); tg = base['ground_inforce']
    print('A20 base', base, flush=True)
    eb.to_parquet(SC + f'ev_A20_{per}.parquet')
    rows = []; grids = []
    for s in SCHED:
        qs = (0.86, 0.88, 0.90, 0.92, 0.94) if s.startswith('C') else (0.88, 0.90, 0.92)
        if s == 'A20': r, e = base, eb
        else:
            (r, e), T = matched(s, per, tg, qs, CU, near_extra=(2, 5)); T['sched'] = s; grids.append(T)
        e.to_parquet(SC + f'ev_{s}_{per}.parquet')
        ci_a, ci_n = boot(e); pd_ = paired(eb, e) if s != 'A20' else {'all': (0, 0, 0), 'new': (0, 0, 0)}
        c = e[e.caught]
        r.update(all_lo=ci_a[0], all_hi=ci_a[1], new_lo=ci_n[0], new_hi=ci_n[1], d_all=pd_['all'][0], d_all_lo=pd_['all'][1], d_all_hi=pd_['all'][2],
                 d_new=pd_['new'][0], d_new_lo=pd_['new'][1], d_new_hi=pd_['new'][2], night_all=100 * e.caught[e.dn == 'N'].mean(), day_all=100 * e.caught[e.dn == 'D'].mean(),
                 lead_last_med=c.lead_last_h.median(), lead_first_med=c.lead_first_h.median(), since_list_med=e.since_list_h.median(),
                 lead_last_p25=c.lead_last_h.quantile(0.25), lead_last_p75=c.lead_last_h.quantile(0.75))
        # same per-list ground as A20 (for twice daily: more ground in force)
        if s.startswith('C'):
            T = grids[-1]; q2 = float(np.interp(base['ground_list'], T.sort_values('ground_list').ground_list, T.sort_values('ground_list').q))
            r2, e2 = evaluate(s, per, q2, CU=CU); r['same_list_q'] = q2; r['same_list_all'] = r2['all']; r['same_list_new'] = r2['new']; r['same_list_inforce'] = r2['ground_inforce']
            r['same_list_list'] = r2['ground_list']
        rows.append(r); print(s, {k: (round(v, 2) if isinstance(v, float) else v) for k, v in r.items()}, flush=True)
    # control: the daily lists at the larger in-force ground that twice-daily lists reach when each keeps A20's size
    tg2 = [r for r in rows if r['sched'] == 'C_f'][0]['same_list_inforce']
    for s in ('A20', 'B06f'):
        (r, e), _ = matched(s, per, tg2, (0.86, 0.88, 0.90), CU); r['sched'] = s + '_atCground'; rows.append(r); print(r, flush=True)
    pd.DataFrame(rows).round(3).to_csv(OUT + f'schedules_{per}.csv', index=False)
    if grids: pd.concat(grids).round(3).to_csv(OUT + f'qgrid_{per}.csv', index=False)
