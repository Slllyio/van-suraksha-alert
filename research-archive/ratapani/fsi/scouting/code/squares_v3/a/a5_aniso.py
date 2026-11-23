"""A5: anisotropy. Pairs are grouped by the angle between their OUTWARD direction u (earlier detections -> pair
mid-point) and a terrain / fuel / fire axis at M; the corrected outward speed (A1) is pooled per group.
  aspect     : angle(u, upslope), slope >= 2 deg; 0 = spreading upslope, 180 = downslope
  grain      : axial angle(u, ridge/valley axis), coherence >= 0.3 and relief >= 15 m; 0 = along the grain (along valleys)
  canopy     : angle(u, direction of denser forest), forest-fraction gradient >= 0.1 per km; 0 = into forest, 180 = into open
  elongation : axial angle(u, long axis of earlier detections), axis ratio >= 2; 0 = along the fire's own long axis
Two versions: p_corr (A1) and 'centred' (also minus the mean displacement vector of the stratum sensor-order x day/night x
season x month projected on u; removes any constant vector bias, e.g. view geometry, that could alias with a common axis).
Contrasts (first bin minus last bin) with 95% CIs by fire-cluster bootstrap (the same clusters drawn for all bins).
Out: results/a5_aniso.csv, a5_aniso.json, fig_a5_aniso.png"""
import json, os
import numpy as np, pandas as pd
import matplotlib; matplotlib.use('Agg'); import matplotlib.pyplot as plt
HERE = os.path.dirname(os.path.abspath(__file__)); OUT = f'{HERE}/results'
SC = '/tmp/claude-0/-home-user/be9b8f54-cc26-52cb-bdbb-9c8008a24baf/scratchpad/r20_a'
rng = np.random.default_rng(25); NB = 500; CLIP = 2000
D = pd.read_parquet(f'{SC}/pairs_corr.parquet', columns=['pair_row', 'fire', 'dn', 'gap_h', 'p_corr', 'nuis_m', 'cl', 'cE', 'cN', 'uE', 'uN', 'u_len',
                                                          'sA', 'sB', 'season', 'month_', 'slope', 'upaz', 'forest'])
D = D[D.fire == 1].merge(pd.read_parquet(f'{SC}/feat.parquet').drop(columns=['fire', 'mx', 'my']), on='pair_row')
key = D.sA + D.sB + D.dn + D.season.astype(str) + D.month_.astype(str)
mE = D.cE.clip(-CLIP, CLIP).groupby(key).transform('mean'); mN = D.cN.clip(-CLIP, CLIP).groupby(key).transform('mean')
D['p_cent'] = D.p_corr - (mE * D.uE + mN * D.uN) / D.u_len
uaz = np.degrees(np.arctan2(D.uE, D.uN)) % 360
def ang(a, b): return np.abs((a - b + 180) % 360 - 180)                 # 0-180
def axial(a, b): x = np.abs((a - b) % 180); return np.minimum(x, 180 - x)  # 0-90
D['a_up'] = np.where(D.slope >= 2, ang(uaz, D.upaz), np.nan)
D['a_grain'] = np.where((D.grain_coh >= 0.3) & (D.relief >= 15), axial(uaz, D.grain_az), np.nan)
D['a_can'] = np.where(D.can_grad >= 0.1, ang(uaz, D.can_az), np.nan)
D['a_elong'] = np.where((D.elong_ratio >= 2) & (D.nE_elong >= 4), axial(uaz, D.elong_az), np.nan)
TESTS = {'a_up': ([0, 45, 90, 135, 180], ['upslope', 'cross-up', 'cross-down', 'downslope']),
         'a_grain': ([0, 30, 60, 90], ['along grain', 'oblique', 'across grain']),
         'a_can': ([0, 60, 120, 180], ['into forest', 'along edge', 'into open']),
         'a_elong': ([0, 30, 60, 90], ['along fire axis', 'oblique', 'across fire axis'])}
rows, res = [], {}
for t, (edges, labs) in TESTS.items():
    for dn in 'DN':
        d = D[(D.dn == dn) & np.isfinite(D[t])].copy()
        d['b'] = pd.cut(d[t], edges, labels=False, include_lowest=True)
        cl = pd.factorize(d.cl)[0]; nc = cl.max() + 1; nbin = len(labs)
        for col in ['p_corr', 'p_cent']:
            SV = np.zeros((nc, nbin)); SG = np.zeros((nc, nbin))
            for b in range(nbin):
                m = d.b.values == b
                SV[:, b] = np.bincount(cl[m], d[col].values[m], nc); SG[:, b] = np.bincount(cl[m], d.gap_h.values[m], nc)
            est = SV.sum(0) / SG.sum(0); bs = []
            for _ in range(NB):
                s = rng.integers(0, nc, nc); bs.append(SV[s].sum(0) / SG[s].sum(0))
            bs = np.array(bs)
            for b in range(nbin):
                rows.append(dict(test=t, dn=dn, version=col, bin=labs[b], n=int((d.b == b).sum()), speed=round(est[b], 1),
                                 lo=round(float(np.quantile(bs[:, b], .025)), 1), hi=round(float(np.quantile(bs[:, b], .975)), 1)))
            c = bs[:, 0] - bs[:, -1]
            res[f'{t} {dn} {col}'] = dict(contrast=f'{labs[0]} minus {labs[-1]}', m_h=round(est[0] - est[-1], 1),
                                         ci=[round(float(np.quantile(c, .025)), 1), round(float(np.quantile(c, .975)), 1)], n=len(d))
T = pd.DataFrame(rows); T.to_csv(f'{OUT}/a5_aniso.csv', index=False)
# grain axis sanity: dominant grain azimuth where relief is high
h = D[(D.relief >= 40) & (D.grain_coh >= 0.3)]
res['grain_axis_hist_relief40'] = np.histogram(h.grain_az, bins=[0, 30, 60, 90, 120, 150, 180])[0].tolist()
res['coverage'] = {t: int(np.isfinite(D[t]).sum()) for t in TESTS}
json.dump(res, open(f'{OUT}/a5_aniso.json', 'w'), indent=1); print(json.dumps(res, indent=1))
pd.set_option('display.width', 200); print(T[T.version == 'p_corr'].to_string())
fig, axs = plt.subplots(1, 4, figsize=(15, 4), sharey=True)
names = {'a_up': 'Slope aspect', 'a_grain': 'Terrain grain (ridge/valley axis)', 'a_can': 'Canopy-to-open gradient', 'a_elong': "Fire's own long axis"}
for ax, t in zip(axs, TESTS):
    for dn, colr, off in [('D', '#d9622b', -0.12), ('N', '#2a4fa0', 0.12)]:
        g = T[(T.test == t) & (T.dn == dn) & (T.version == 'p_corr')].reset_index(drop=True)
        ax.errorbar(np.arange(len(g)) + off, g.speed, yerr=[g.speed - g.lo, g.hi - g.speed], fmt='o', color=colr, capsize=3, label='day' if dn == 'D' else 'night')
    ax.set_xticks(range(len(TESTS[t][1]))); ax.set_xticklabels(TESTS[t][1], fontsize=8, rotation=15)
    ax.set_title(names[t], fontsize=10); ax.axhline(0, color='k', lw=.5)
axs[0].set_ylabel('corrected outward speed (m/h)'); axs[0].legend(fontsize=8)
fig.suptitle('Outward speed by spread direction relative to terrain, canopy and fire shape (all MP, 95% CI by fire cluster)', fontsize=11)
fig.tight_layout(); fig.savefig(f'{OUT}/fig_a5_aniso.png', dpi=130)
