"""A2b: where does a VIIRS look's centre sit relative to the fine-pixel flaming front, at (nearly) the same moment?
(a) Least-circular estimate from 30 m hot pixels: VIIRS looks 6-13 h before and 1-4.5 h after the scene only,
    p = o + vbar * dC (one common offset o, clock-mean speed vbar); fire bootstrap.
(b) ECOSTRESS 70 m visible passes (big-fires 14b) with a VIIRS pass within 60 min: signed offset of the VIIRS centre
    from the 70 m hot centre along u = hot - E (E = VIIRS detections 2-48 h before), after moving the VIIRS look to the
    ECOSTRESS minute with the pooled day speed (30 m/h; the correction is < 30 m).
Out: results/a2b_offset.json"""
import json, os
import numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__)); OUT = f'{HERE}/results'; rng = np.random.default_rng(23)
P = pd.read_csv(f'{OUT}/a2_hotpix_lags.csv')
d = P[(P.kind == 'viirs') & (P.dt_h.between(-13, -6) | P.dt_h.between(1, 4.5))]
X = np.c_[np.ones(len(d)), d.dC]; Y = d.p.values
co = np.linalg.lstsq(X, Y, rcond=None)[0]; fr = pd.factorize(d.fire)[0]; idx = [np.where(fr == k)[0] for k in range(fr.max() + 1)]; bs = []
for _ in range(2000):
    k = np.concatenate([idx[j] for j in rng.integers(0, len(idx), len(idx))]); bs.append(np.linalg.lstsq(X[k], Y[k], rcond=None)[0])
bs = np.array(bs); q = lambda a: [round(float(np.quantile(a, .025)), 1), round(float(np.quantile(a, .975)), 1)]
res = dict(hotpix_bracket_fit=dict(looks=len(d), fires=int(d.fire.nunique()), offset_o_m=round(co[0], 1), offset_ci=q(bs[:, 0]),
                                   clock_mean_speed_m_h=round(co[1], 1), speed_ci=q(bs[:, 1]),
                                   implied_13_30_speed_m_h=round(co[1] * 1.98, 1), implied_13_30_ci=q(bs[:, 1] * 1.98),
                                   implied_01_30_speed_m_h=round(co[1] * 0.36, 1),
                                   note='multipliers 1.98 (13:30) and 0.36 (01:30) are the pooled forest curve; only its SHAPE is assumed'))
# ECOSTRESS
E = pd.read_csv('/mnt/project-files/research/big-fires/results/ecostress_pass_stats.csv', parse_dates=['t0'])
E = E[E.visible10.astype(str) == 'True'].drop_duplicates(['fire', 't0'])
D = pd.read_csv('/mnt/project-files/research/big-fires/results/detections.csv', parse_dates=['t'])
V = D[D.sensor.isin(['S-NPP', 'NOAA-20', 'NOAA-21'])]
rows = []
for _, r in E.iterrows():
    v = V[V.fire == r.fire]
    if not len(v): continue
    gap = (v.t - r.t0).dt.total_seconds() / 60
    near = v[gap.abs() <= 60]
    if not len(near): continue
    pid = near.assign(a=gap[near.index].abs()).sort_values('a').pass_id.iloc[0]; L = v[v.pass_id == pid]
    tL = L.t.min(); t0 = min(tL, r.t0)
    e = v[(v.t >= t0 - pd.Timedelta(hours=48)) & (v.t <= t0 - pd.Timedelta(hours=2))]
    if not len(e): continue
    ux, uy = r.hot_cx - e.x.mean(), r.hot_cy - e.y.mean(); n = np.hypot(ux, uy)
    if n < 100: continue
    ux, uy = ux / n, uy / n; dt = (tL - r.t0).total_seconds() / 3600
    p = (L.x.mean() - r.hot_cx) * ux + (L.y.mean() - r.hot_cy) * uy - 30 * dt
    rows.append(dict(fire=r.fire, t0=r.t0, gap_min=dt * 60, n_viirs=len(L), n_hot=r.n_hot, p=p,
                     perp=-(L.x.mean() - r.hot_cx) * uy + (L.y.mean() - r.hot_cy) * ux))
T = pd.DataFrame(rows)
bs = [T.p.values[rng.integers(0, len(T), len(T))].mean() for _ in range(2000)]
res['ecostress_same_hour'] = dict(passes=len(T), fires=int(T.fire.nunique()), mean_offset_m=round(float(T.p.mean()), 1), ci=q(np.array(bs)),
                                  median_offset_m=round(float(T.p.median()), 1), share_viirs_behind=round(float((T.p < 0).mean()), 2),
                                  mean_perp_m=round(float(T.perp.mean()), 1))
T.to_csv(f'{OUT}/a2b_ecostress_offsets.csv', index=False)
json.dump(res, open(f'{OUT}/a2b_offset.json', 'w'), indent=1); print(json.dumps(res, indent=1)); print(T.round(0).to_string())
# figure: lag bins (from a2) with the bracket fit (this script) drawn only over the window it was fitted on
import matplotlib; matplotlib.use('Agg'); import matplotlib.pyplot as plt
import importlib.util
LB = pd.read_csv(f'{OUT}/a2_lag_bins.csv')
fig, ax = plt.subplots(figsize=(8.5, 4.8))
cols = {'viirs': '#2a6fdb', 'terra': '#d9822b', 'aqua': '#3aa676'}
for k, g in LB.groupby('kind'):
    ax.errorbar(g.mean_dt_h, g.p_m, yerr=[g.p_m - g.lo, g.hi - g.p_m], fmt='o', color=cols[k], capsize=3,
                label={'viirs': 'VIIRS looks', 'terra': 'Terra MODIS', 'aqua': 'Aqua MODIS'}[k])
dj = json.load(open('/mnt/project-files/ratapani/fsi/scouting/code/squares_v2/pooled/results/diurnal_fit_noratapani.json'))['forest']
hh = np.array(sorted(float(k) for k in dj['curve'])); rr = np.array([dj['curve'][f'{h:.2f}'] for h in hh]) / dj['daily_mean_m_h']
tt = np.arange(-13, 4.51, 0.05); ist = (10.75 + tt) % 24; m = np.interp(ist, hh, rr)
cc = np.cumsum(m) * 0.05; cc -= np.interp(0, tt, cc)
o, v = res['hotpix_bracket_fit']['offset_o_m'], res['hotpix_bracket_fit']['clock_mean_speed_m_h']
ax.plot(tt, o + v * cc, color='#2a6fdb', lw=1.5, label=f'fit on the -13..+4.5 h looks: centre {-o:.0f} m behind the 30 m front, mean speed {v:.0f} m/h')
ax.axhline(0, color='k', lw=.6); ax.axvline(0, color='k', lw=.6, ls=':')
ax.set_xlabel('hours from the 30 m hot-pixel scene (~10:45 IST)'); ax.set_ylabel('coarse-look centre minus 30 m hot-pixel centre,\nalong the outward direction (m)')
ax.set_title('Coarse looks vs 30 m hot pixels, Ratapani (95% CI by fire)', fontsize=10); ax.legend(fontsize=7.5, loc='lower right')
fig.tight_layout(); fig.savefig(f'{OUT}/fig_a2_lag.png', dpi=130)
