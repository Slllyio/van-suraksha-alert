"""Step 6: a diurnal spread-rate curve from displacement data alone.
Segments of the day, each a set of pairs of looks of the same fire (each detection keeps its own sensor and time):
  13:00-14:30 VIIRS->VIIRS small gaps (day)        01:30-03:00 VIIRS->VIIRS small gaps (night)
  10:40->13:30 Terra->VIIRS (day, ~2.8 h)          22:10->01:50 Terra->VIIRS (night, ~3.5 h)
  13:30->01:30 VIIRS->VIIRS 12 h (day->night)      01:30->13:30 VIIRS->VIIRS 12 h (night->day)
Displacement is bias-corrected with static-site offsets for that ordered sensor pair (small VIIRS: per-sensor model;
MODIS and 12 h: static mean of that ordered pair x day/night), then projected on the outward direction u = M - E.
Pooled outward speed per segment (bootstrap by fire cluster), static null through the same code.
Fit r(h) = b + a*exp(-dh^2/2s^2) (dh = hours from peak pk) to the segment means by weighted least squares, integrating
r over each pair's own interval. Out: results/diurnal_*.csv/json, figure."""
import json, os
import numpy as np, pandas as pd
SC = os.environ.get('POOL_SCRATCH', '/tmp/claude-0/-home-user/be9b8f54-cc26-52cb-bdbb-9c8008a24baf/scratchpad/r19_pool')
HERE = os.path.dirname(os.path.abspath(__file__)); OUT = f'{HERE}/results'
rng = np.random.default_rng(4); CLIP = 3000.0
R = pd.read_parquet(f'{SC}/ctx.parquet'); R = R[R.nE > 0].copy()
TAG = ''
if os.environ.get('EXCL_RATAPANI'):   # spatially held-out version: drop everything within ~60 km of Ratapani
    R = R[~(R.lonA.between(76.9, 78.5) & R.latA.between(22.4, 23.5))].copy(); TAG = '_noratapani'
V = {'S-NPP', 'NOAA-20', 'NOAA-21'}
R['vv'] = R.sA.isin(V) & R.sB.isin(V); R['gap_h'] = R.gap_min / 60; R['pair'] = R.sA + '>' + R.sB
R['cl'] = R.season.astype(str) + '_' + (R.mx / 5000).round().astype(int).astype(str) + '_' + (R.my / 5000).round().astype(int).astype(str)
R.loc[R.typ == 2, 'cl'] = 's' + R.loc[R.typ == 2, 'site']
R['dir'] = np.where(R.istA.between(8, 20), 'day>night', 'night>day')
bs_ = pd.read_csv(f'{OUT}/bias_table_small.csv'); bm = pd.read_csv(f'{OUT}/bias_table_modis.csv'); b12 = pd.read_csv(f'{OUT}/bias_table_12h.csv')
summ = json.load(open(f'{OUT}/pooled_summary.json'))
off = {tuple(k.split(' ')): v for k, v in summ['offsets_static'].items()}
def seg(df):
    out = np.full(len(df), 'none', object)
    sm = df.vv & (df.gap_min <= 120) & (df.sA != df.sB)
    out[(sm & (df.dn == 'D')).values] = 'VIIRS day small gap'; out[(sm & (df.dn == 'N')).values] = 'VIIRS night small gap'
    t = (df.sA == 'Terra') & df.sB.isin(V) & (df.gap_min.between(100, 240))
    out[(t & (df.dn == 'D')).values] = 'Terra 10:40 -> VIIRS 13:30'; out[(t & (df.dn == 'N')).values] = 'Terra 22:10 -> VIIRS 01:50'
    l = df.vv & (df.gap_min >= 600)
    out[(l & (df.dir == 'day>night')).values] = 'VIIRS 13:30 -> 01:30 (12 h)'; out[(l & (df.dir == 'night>day')).values] = 'VIIRS 01:30 -> 13:30 (12 h)'
    return out
R['seg'] = seg(R); R = R[R.seg != 'none'].copy()
# bias per row
bE = np.zeros(len(R)); bN = np.zeros(len(R)); src = np.empty(len(R), object)
sm = R.seg.str.contains('small').values
for i, (a, b, dn) in enumerate(zip(R.sA.values, R.sB.values, R.dn.values)):
    if sm[i]:
        bE[i] = off[(dn, 'dE')].get(b, 0) - off[(dn, 'dE')].get(a, 0); bN[i] = off[(dn, 'dN')].get(b, 0) - off[(dn, 'dN')].get(a, 0)
bmi = bm.set_index(['pair', 'dn']); b12i = b12.set_index(['pair', 'dir'])
k = R.seg.str.startswith('Terra').values
ix = list(zip(R.pair.values[k], R.dn.values[k])); bE[k] = [bmi.bE.get(z, 0.0) for z in ix]; bN[k] = [bmi.bN.get(z, 0.0) for z in ix]
k = R.seg.str.contains('12 h').values
ix = list(zip(R.pair.values[k], R.dir.values[k])); bE[k] = [b12i.bE.get(z, 0.0) for z in ix]; bN[k] = [b12i.bN.get(z, 0.0) for z in ix]
L = np.hypot(R.uE, R.uN); ue, un = R.uE / L, R.uN / L
R['p'] = (R.dE - bE) * ue + (R.dN - bN) * un; R['p_raw'] = R.dE * ue + R.dN * un
R['forest'] = ~R.vtm.isin([170, 180, 190, 191, 200])
def pooled(df, col='p', n=400):
    v = df[col].clip(-CLIP, CLIP).values; cl = pd.factorize(df.cl)[0]; nc = cl.max() + 1
    s = np.bincount(cl, v, nc); c = np.bincount(cl, minlength=nc).astype(float); m = s.sum() / c.sum()
    bs = np.array([s[k].sum() / c[k].sum() for k in (rng.integers(0, nc, nc) for _ in range(n))])
    return m, np.quantile(bs, .025), np.quantile(bs, .975), bs.std()
rows = []
for sub in ['all', 'forest']:
    for (typ, sg), g in R.groupby(['typ', 'seg']):
        if sub == 'forest': g = g[g.forest]
        if len(g) < 30: continue
        m, lo, hi, se = pooled(g); mr = pooled(g, 'p_raw')[0]; gh = g.gap_h.mean()
        rows.append(dict(subset=sub, set='fires' if typ == 0 else 'static null', segment=sg, n=len(g), clusters=g.cl.nunique(),
                         start_ist=round(g.istA.mean(), 2), end_ist=round((g.istA + g.gap_h).mean() % 24, 2), gap_h=round(gh, 2),
                         outward_m=round(m, 1), ci_m=f'{lo:.1f} to {hi:.1f}', se_m=round(se, 2), speed_m_h=round(m / gh, 1),
                         ci_m_h=f'{lo / gh:.1f} to {hi / gh:.1f}', raw_speed_m_h=round(mr / gh, 1)))
T = pd.DataFrame(rows); T.to_csv(f'{OUT}/diurnal_segments{TAG}.csv', index=False); pd.set_option('display.width', 250); print(T.to_string())
# fit the curve on fires (forest subset and all), integrating r(h) over each segment's mean interval
def integ(t0, gh, b, a, pk, s):
    hh = t0 + np.linspace(0, gh, 200); dh = (hh - pk + 12) % 24 - 12
    return np.trapezoid(b + a * np.exp(-dh ** 2 / (2 * s ** 2)), hh)
fits = {}
for sub in ['all', 'forest']:
    G = T[(T.subset == sub) & (T.set == 'fires')]
    best = None
    for pk in np.arange(11, 19.01, .25):
        for s in np.arange(1.5, 8.01, .25):
            Xm = np.array([[g.gap_h, integ(g.start_ist, g.gap_h, 0, 1, pk, s)] for g in G.itertuples()])
            w = 1 / G.se_m.values ** 2; co, *_ = np.linalg.lstsq(Xm * np.sqrt(w)[:, None], G.outward_m.values * np.sqrt(w), rcond=None)
            chi = (w * (G.outward_m.values - Xm @ co) ** 2).sum()
            if best is None or chi < best[0]: best = (chi, pk, s, co)
    chi, pk, s, (b, a) = best
    hh = np.arange(0, 24, .25); dh = (hh - pk + 12) % 24 - 12; r = b + a * np.exp(-dh ** 2 / (2 * s ** 2))
    fits[sub] = dict(base_m_h=round(b, 1), amp_m_h=round(a, 1), peak_ist=float(pk), width_h=float(s), chi2=round(chi, 1), dof=len(G) - 4,
                     daily_mean_m_h=round(r.mean(), 1), min_m_h=round(r.min(), 1), max_m_h=round(r.max(), 1),
                     multiplier_by_hour={f'{int(h):02d}': round(float(np.interp(h, hh, r) / r.mean()), 2) for h in range(0, 24, 2)},
                     share_of_daily_spread_01_30_to_10_30=round(float(r[(hh >= 1.5) & (hh < 10.5)].sum() / r.sum()), 3))
    # parametric bootstrap of the fit from the segment SEs
    bsr = []
    for _ in range(200):
        y = G.outward_m.values + rng.normal(0, G.se_m.values)
        bb = None
        for pk2 in np.arange(11, 19.01, .5):
            for s2 in np.arange(1.5, 8.01, .5):
                Xm = np.array([[g.gap_h, integ(g.start_ist, g.gap_h, 0, 1, pk2, s2)] for g in G.itertuples()])
                w = 1 / G.se_m.values ** 2; co, *_ = np.linalg.lstsq(Xm * np.sqrt(w)[:, None], y * np.sqrt(w), rcond=None)
                ch = (w * (y - Xm @ co) ** 2).sum()
                if bb is None or ch < bb[0]: bb = (ch, pk2, s2, co)
        rr = bb[3][0] + bb[3][1] * np.exp(-(((hh - bb[1] + 12) % 24 - 12) ** 2) / (2 * bb[2] ** 2)); bsr.append(rr)
    bsr = np.array(bsr); fits[sub]['curve_ci'] = {f'{int(h):02d}': f'{np.quantile(bsr[:, int(h * 4)], .025):.1f} to {np.quantile(bsr[:, int(h * 4)], .975):.1f}' for h in range(0, 24, 2)}
    fits[sub]['curve'] = {f'{h:.2f}': round(float(v), 2) for h, v in zip(hh, r)}
json.dump(fits, open(f'{OUT}/diurnal_fit{TAG}.json', 'w'), indent=1); print(json.dumps({k: {q: w for q, w in v.items() if q != 'curve'} for k, v in fits.items()}, indent=1))
# figure
import matplotlib; matplotlib.use('Agg'); import matplotlib.pyplot as plt
fig, ax = plt.subplots(1, 2, figsize=(12, 4.5))
for j, sub in enumerate(['forest', 'all']):
    G = T[(T.subset == sub)]
    for st, col in [('fires', 'C3'), ('static null', 'grey')]:
        g = G[G.set == st]
        for r in g.itertuples():
            lo, hi = [float(x) for x in r.ci_m_h.split(' to ')]
            t0, t1 = r.start_ist, r.start_ist + r.gap_h
            xs = [t0, t1] if t1 <= 24 else [t0, 24]
            ax[j].plot(xs, [r.speed_m_h] * 2, color=col, lw=2.5); ax[j].fill_between(xs, lo, hi, color=col, alpha=.2)
            if t1 > 24: ax[j].plot([0, t1 - 24], [r.speed_m_h] * 2, color=col, lw=2.5); ax[j].fill_between([0, t1 - 24], lo, hi, color=col, alpha=.2)
    c = fits[sub]['curve']; ax[j].plot([float(h) for h in c], list(c.values()), 'k--', label='fitted curve')
    ax[j].axhline(0, color='k', lw=.5); ax[j].set_xlim(0, 24); ax[j].set_xticks(range(0, 25, 3))
    ax[j].set_xlabel('hour of day (IST)'); ax[j].set_ylabel('pooled outward speed, m/h'); ax[j].legend(loc='upper left')
    ax[j].set_title(f'{"forest and scrub" if sub == "forest" else "all fires incl. farm"}: red = fires, grey = static null')
plt.tight_layout(); plt.savefig(f'{OUT}/fig_diurnal{TAG}.png', dpi=120)
