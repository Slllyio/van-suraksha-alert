"""Step 2b: two sharper checks on the cluster question.
  (1) Baseline for the pair correlation: two lone detections of the SAME pass but different places (shared weather and
      geometry, separate fires). If adjacent pixels correlate far more, they see the same heat.
  (2) Same fire, two satellites ~50 min apart (S-NPP / NOAA-20 / NOAA-21 passes of one fire within 100 min). The fire
      barely changes in 50 min. If the cluster's summed FRP follows the number of pixels the satellite happened to
      light up (slope ~1), pixels double count; if it stays put (slope ~0), the sum is a fair total.
  (3) Near-duplicates (closer than 0.75 pixel) by pixel size: overlap of neighbouring scans.
Out: results/cluster_tests2.json
"""
import json, numpy as np, pandas as pd
from scipy.stats import spearmanr
from h0_lib import RES, r_clock
v = pd.read_csv(f'{RES}/clusters.csv', parse_dates=['t'])
v['pass'] = v.sensor + v.t.dt.strftime('%Y%m%d%H%M')
out = {}
rng = np.random.default_rng(1)
# (1)
lo = v[v.n_cl == 1]
pa = []
for _, g in lo.groupby('pass'):
    if len(g) < 2: continue
    i = rng.permutation(len(g))[:2]; pa.append(g.frp.values[i])
pa = np.array(pa)
out['lone_pairs_same_pass'] = dict(n=len(pa), rho=round(spearmanr(pa[:, 0], pa[:, 1])[0], 3))
# adjacent pairs again, for the table
two = v[v.n_cl == 2].sort_values(['cl', 'frp'])
out['adjacent_pairs'] = dict(n=len(two) // 2, rho=round(spearmanr(two.frp.values[0::2], two.frp.values[1::2])[0], 3))
print('rank corr of FRP: adjacent pair', out['adjacent_pairs'], '| two separate lone fires, same pass', out['lone_pairs_same_pass'])
# (2)
f = v.dropna(subset=['fire'])
P = f.groupby(['fire', 'pass']).agg(sensor=('sensor', 'first'), t=('t', 'first'), n=('frp', 'size'), frp=('frp', 'sum'),
                                     pix=('scan_m', lambda s: 0), pixa=('scan_m', 'mean')).reset_index()
P['pixa'] = f.groupby(['fire', 'pass']).apply(lambda g: (g.scan_m * g.track_m).mean() / 1e6, include_groups=False).values
P = P.sort_values(['fire', 't'])
rows = []
for fire, g in P.groupby('fire'):
    g = g.reset_index(drop=True)
    for i in range(len(g) - 1):
        a, b = g.iloc[i], g.iloc[i + 1]
        dtm = (b.t - a.t).total_seconds() / 60
        if a.sensor != b.sensor and 20 <= dtm <= 100:
            rows.append(dict(fire=fire, dt_min=dtm, n_a=a.n, n_b=b.n, frp_a=a.frp, frp_b=b.frp, pix_a=a.pixa, pix_b=b.pixa,
                             clock=float(r_clock(b.t)[0] / r_clock(a.t)[0])))
Q = pd.DataFrame(rows)
Q['l_frp'] = np.log(Q.frp_b / Q.frp_a) - np.log(Q.clock); Q['l_n'] = np.log(Q.n_b / Q.n_a); Q['l_pix'] = np.log(Q.pix_b / Q.pix_a)
import statsmodels.formula.api as smf
m1 = smf.ols('l_frp ~ l_n', Q).fit(); m2 = smf.ols('l_frp ~ l_n + l_pix', Q).fit(); m3 = smf.ols('l_n ~ l_pix', Q).fit()
out['two_sat'] = dict(pairs=len(Q), fires=Q.fire.nunique(),
                      slope_sumFRP_on_npix=round(m1.params.l_n, 3), ci=m1.conf_int().loc['l_n'].round(3).tolist(),
                      slope_with_pix=round(m2.params.l_n, 3), slope_pix=round(m2.params.l_pix, 3), slope_pix_ci=m2.conf_int().loc['l_pix'].round(3).tolist(),
                      npix_on_pixsize=round(m3.params.l_pix, 3), npix_on_pixsize_ci=m3.conf_int().loc['l_pix'].round(3).tolist(),
                      same_n_share=round((Q.n_a == Q.n_b).mean(), 3),
                      median_abs_log_frp_ratio=round(np.median(np.abs(Q.l_frp)), 3),
                      rho_frp=round(spearmanr(Q.frp_a, Q.frp_b)[0], 3), rho_n=round(spearmanr(Q.n_a, Q.n_b)[0], 3))
# twice as many pixels -> how much more summed FRP
print('same fire, two satellites ~50 min apart:', out['two_sat'])
# (3)
mind, band = [], []
for _, g in v[v.n_cl > 1].groupby('cl'):
    X, Y = g.x.values, g.y.values; D = np.hypot(X[:, None] - X[None], Y[:, None] - Y[None]); np.fill_diagonal(D, 1e9)
    mind += list(D.min(1) / g.pix.values); band += list(g.pix_band.values)
M = pd.DataFrame(dict(d=mind, band=band))
t = M.groupby('band').d.agg(n='size', share_closer_075=lambda s: (s < .75).mean(), median='median').round(3)
print(t); out['near_dup_by_band'] = t.reset_index().to_dict('records')
json.dump(out, open(f'{RES}/cluster_tests2.json', 'w'), indent=1, default=float)
