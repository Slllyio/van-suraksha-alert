"""Step 8b: next-look capture test in Ratapani (2017-2026, big-fires detections table, every VIIRS pass on its own).
Forecast at each VIIRS pass k of a fire: "the next VIIRS pass's detections lie within reach R of the detections seen so far".
Reach R = 375 m + v * tau, where tau is the time to the next pass measured on a clock:
   none  : tau = 0 (fixed reach; v unused)    clock : tau = hours    modis : tau = MODIS-count burning-clock hours
   pooled: tau = hours on this thread's pooled-displacement clock (fitted outside Ratapani, so spatially held out)
v is set so every method has the same mean reach over all forecasts (equal 'area budget', nothing fitted on capture).
Outward-drift prior: before measuring distance, every earlier detection is pushed away from the fire's centroid-so-far by
c * (pooled-clock outward distance since it was seen), c = 0 / 0.5 / 1.
Score: share of next-pass detections captured, and share of NEW next-pass detections (> 400 m from all earlier) captured;
95% CI by fire bootstrap. Out: results/nextlook.csv, nextlook_summary.json"""
import json, os
import numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__)); OUT = f'{HERE}/results'
rng = np.random.default_rng(9)
D = pd.read_csv('/mnt/project-files/research/big-fires/results/detections.csv', parse_dates=['t'])
D = D[D.sensor.isin(['S-NPP', 'NOAA-20', 'NOAA-21'])].copy()
FIT = json.load(open(f'{OUT}/diurnal_fit_noratapani.json'))['forest']
MOD = json.load(open('/mnt/project-files/research/fire-continuity/results/diurnal.json'))
def make_clock(b, pk, s, scale_mean=True, amp=None):
    hh = np.arange(0, 24, 1 / 60)
    dh = (hh - pk + 12) % 24 - 12
    r = (b + (1 - b) * np.exp(-dh ** 2 / (2 * s ** 2))) if amp is None else (b + amp * np.exp(-dh ** 2 / (2 * s ** 2)))
    if scale_mean: r = r / r.mean()
    return r
R_pool = make_clock(FIT['base_m_h'], FIT['peak_ist'], FIT['width_h'], scale_mean=False, amp=FIT['amp_m_h'])   # m/h
C = {'clock': np.ones(1440), 'modis': make_clock(MOD['base'], MOD['peak_ist'], MOD['width_h']), 'pooled': R_pool / R_pool.mean()}
cum = {k: np.concatenate([[0], np.cumsum(v)]) / 60 for k, v in C.items()}           # clock-hours from 00:00 IST
cum_pool_m = np.concatenate([[0], np.cumsum(R_pool)]) / 60                          # outward metres from 00:00 IST
def tau(kind, t0, t1, metres=False):
    """clock time between UTC timestamps t0 < t1 (arrays)"""
    m0 = ((t0.astype('datetime64[m]').astype(np.int64) + 330)); m1 = ((t1.astype('datetime64[m]').astype(np.int64) + 330))
    day0, day1 = m0 // 1440, m1 // 1440; i0, i1 = m0 % 1440, m1 % 1440
    c = cum_pool_m if metres else cum[kind]
    return (day1 - day0) * c[-1] + c[i1] - c[i0]
rows = []
for fire, g in D.groupby('fire'):
    P = g.groupby('pass_id').t.min().sort_values()
    if len(P) < 2: continue
    ids = P.index.values
    for k in range(len(ids) - 1):
        t0, t1 = P.iloc[k], P.iloc[k + 1]
        gap = (t1 - t0).total_seconds() / 3600
        if gap < 0.3 or gap > 36: continue
        S = g[g.t <= t0]; Nx = g[g.pass_id == ids[k + 1]]
        cx, cy = S.x.mean(), S.y.mean()
        rows.append(dict(fire=fire, season=t0.year, t0=t0, t1=t1, gap=gap, S=S[['x', 'y', 't']].values, N=Nx[['x', 'y']].values, cx=cx, cy=cy))
print('forecasts', len(rows))
T0 = np.array([r['t0'] for r in rows], dtype='datetime64[ns]'); T1 = np.array([r['t1'] for r in rows], dtype='datetime64[ns]')
taus = {k: tau(k, T0, T1) for k in C}; taus['none'] = np.zeros(len(rows))
BUDGET = 375 + 15.0 * np.mean(taus['clock'])     # mean reach = 375 m + 15 m/h x mean gap
v = {k: ((BUDGET - 375) / taus[k].mean() if taus[k].mean() > 0 else 0) for k in taus}
def dists(r, c):
    S = r['S']; X, Y = S[:, 0].astype(float), S[:, 1].astype(float)
    if c > 0:
        ts = S[:, 2].astype('datetime64[ns]'); push = c * tau(None, ts, np.full(len(ts), np.datetime64(r['t0'])), metres=True)
        ux, uy = X - r['cx'], Y - r['cy']; L = np.hypot(ux, uy) + 1e-6; X = X + push * ux / L; Y = Y + push * uy / L
    N = r['N']; d = np.hypot(N[:, 0, None] - X[None], N[:, 1, None] - Y[None]).min(1)
    d0 = np.hypot(N[:, 0, None] - S[None, :, 0].astype(float), N[:, 1, None] - S[None, :, 1].astype(float)).min(1)
    return d, d0 > 400
res = {}; out = []
for c in [0.0, 0.5, 1.0]:
    DD = [dists(r, c) for r in rows]
    for k in ['none', 'clock', 'modis', 'pooled']:
        if c > 0 and k != 'pooled' and k != 'clock': continue
        Rr = 375 + v[k] * taus[k] if k != 'none' else np.full(len(rows), BUDGET)
        cap = np.array([(d <= R).mean() for (d, nw), R in zip(DD, Rr)])
        capn = np.array([(d[nw] <= R).mean() if nw.any() else np.nan for (d, nw), R in zip(DD, Rr)])
        nn = np.array([len(d) for d, nw in DD]); nnew = np.array([nw.sum() for d, nw in DD])
        out.append(pd.DataFrame(dict(method=f'{k}, drift c={c}', fire=[r['fire'] for r in rows], season=[r['season'] for r in rows], gap=[r['gap'] for r in rows],
                                     cap=cap, capn=capn, n=nn, nnew=nnew, reach=Rr)))
O = pd.concat(out); O.to_csv(f'{OUT}/nextlook.csv', index=False)
def wmean(g, col, wc): x = g[col].values; w = g[wc].values; m = np.isfinite(x); return np.sum(x[m] * w[m]) / np.sum(w[m])
base = O[O.method == 'clock, drift c=0.0'].reset_index(drop=True)
fires = base.fire.values; uf = np.unique(fires); fidx = [np.where(fires == f)[0] for f in uf]
summ = {'forecasts': len(rows), 'fires': len(uf), 'mean_reach_m': round(BUDGET), 'v_m_per_clock_h': {k: round(x, 1) for k, x in v.items()}}
for m, g in O.groupby('method'):
    g = g.reset_index(drop=True); r = dict(capture_all=round(wmean(g, 'cap', 'n'), 4), capture_new=round(wmean(g, 'capn', 'nnew'), 4))
    for col, wc in [('cap', 'n'), ('capn', 'nnew')]:
        dif = []
        for _ in range(500):
            k = np.concatenate([fidx[i] for i in rng.integers(0, len(fidx), len(fidx))])
            dif.append(wmean(g.iloc[k], col, wc) - wmean(base.iloc[k], col, wc))
        r[f'{col}_minus_plain_clock'] = f'{np.mean(dif):+.4f} ({np.quantile(dif, .025):+.4f} to {np.quantile(dif, .975):+.4f})'
    summ[m] = r
json.dump(summ, open(f'{OUT}/nextlook_summary.json', 'w'), indent=1); print(json.dumps(summ, indent=1))
# ---- area-matched check: pushing points outward also enlarges the forecast area. Compute each forecast's area (50 m grid,
# union of reach disks) and compare drift variants against the plain clock with its reach scaled up to the same total area.
from scipy.spatial import cKDTree
def area(r, R, c):
    S = r['S']; X, Y = S[:, 0].astype(float), S[:, 1].astype(float)
    if c > 0:
        ts = S[:, 2].astype('datetime64[ns]'); push = c * tau(None, ts, np.full(len(ts), np.datetime64(r['t0'])), metres=True)
        ux, uy = X - r['cx'], Y - r['cy']; L = np.hypot(ux, uy) + 1e-6; X = X + push * ux / L; Y = Y + push * uy / L
    gx = np.arange(X.min() - R, X.max() + R + 50, 50); gy = np.arange(Y.min() - R, Y.max() + R + 50, 50)
    GX, GY = np.meshgrid(gx, gy); d, _ = cKDTree(np.c_[X, Y]).query(np.c_[GX.ravel(), GY.ravel()], distance_upper_bound=R)
    return np.isfinite(d).sum() * 0.25     # ha
sub = rng.choice(len(rows), 1500, replace=False)
Rc = 375 + v['clock'] * taus['clock']
am = {}
for c in [0.0, 0.5, 1.0]:
    am[c] = np.array([area(rows[i], Rc[i], c) for i in sub])
scale_area = {}
for f in [1.0, 1.05, 1.1, 1.15, 1.2, 1.3]:
    a = np.array([area(rows[i], Rc[i] * f, 0.0) for i in sub])
    DD0 = [dists(rows[i], 0.0) for i in sub]
    cap = np.sum([(d <= Rc[i] * f).sum() for (d, nw), i in zip(DD0, sub)]) / np.sum([len(d) for d, nw in DD0])
    capn = np.sum([(d[nw] <= Rc[i] * f).sum() for (d, nw), i in zip(DD0, sub)]) / max(1, np.sum([nw.sum() for d, nw in DD0]))
    scale_area[f] = dict(area_ha=round(a.mean(), 1), capture_all=round(cap, 4), capture_new=round(capn, 4))
drift_area = {}
for c in [0.5, 1.0]:
    DDc = [dists(rows[i], c) for i in sub]
    cap = np.sum([(d <= Rc[i]).sum() for (d, nw), i in zip(DDc, sub)]) / np.sum([len(d) for d, nw in DDc])
    capn = np.sum([(d[nw] <= Rc[i]).sum() for (d, nw), i in zip(DDc, sub)]) / max(1, np.sum([nw.sum() for d, nw in DDc]))
    drift_area[c] = dict(area_ha=round(am[c].mean(), 1), capture_all=round(cap, 4), capture_new=round(capn, 4))
summ['area_matched (1500 forecasts)'] = dict(plain_clock_reach_scaled=scale_area, drift_prior=drift_area)
json.dump(summ, open(f'{OUT}/nextlook_summary.json', 'w'), indent=1); print(json.dumps(summ['area_matched (1500 forecasts)'], indent=1))
