"""Step 2: why does a cluster of same-sensor detections carry much more FRP than a lone detection?
Candidate reasons (coordinator, unchecked, 16 Oct 20:56Z): (a) more burning ground, (b) sensor blur spilling a hot pixel's
heat into its neighbours, (c) overlapping / swath-edge pixels double counting, (d) one fire split across a pixel border.

Cluster = detections of ONE satellite pass (same sensor, same minute) linked when closer than 1.6 x pixel size.
Tests
  T1 lone vs cluster: FRP per detection, peak pixel, cluster sum.
  T2 blur: in 2-pixel clusters, is the weaker pixel a steady fraction of the stronger one (blur) or independent (real
     separate burning)? Along-scan (east-west) neighbours vs along-track (north-south) neighbours.
  T3 scar under the footprint: how much of each pixel's footprint lies inside the fire's final scar outline (v2). Blur-only
     neighbours sit over less scar.
  T4 swath edge: cluster size and FRP vs pixel size; near-duplicate pairs (closer than half a pixel).
Out: results/clusters.csv (one row per detection), results/cluster_tests.json
"""
import json
import numpy as np, pandas as pd
from scipy.sparse.csgraph import connected_components
from scipy.sparse import coo_matrix
from scipy.stats import spearmanr
from shapely.geometry import box
from shapely import STRtree
from h0_lib import RES, scars

v = pd.read_csv(f'{RES}/viirs_det.csv', parse_dates=['t'])
v['pass'] = v.sensor + v.t.dt.strftime('%Y%m%d%H%M')
v['pix'] = np.sqrt(v.scan_m * v.track_m)
cl = np.zeros(len(v), int); base = 0
for _, g in v.groupby('pass'):
    i = g.index.values; X, Y = g.x.values, g.y.values
    D = np.hypot(X[:, None] - X[None], Y[:, None] - Y[None])
    lim = 1.6 * np.maximum(g.pix.values[:, None], g.pix.values[None])
    a, b = np.where((D < lim) & (D > 0))
    n, lab = connected_components(coo_matrix((np.ones(len(a)), (a, b)), shape=(len(i), len(i))), directed=False)
    cl[i] = lab + base; base += n
v['cl'] = cl
v['n_cl'] = v.groupby('cl').frp.transform('size')
v['cl_sum'] = v.groupby('cl').frp.transform('sum')
v['cl_max'] = v.groupby('cl').frp.transform('max')
v['is_peak'] = v.frp == v.cl_max
v['role'] = np.where(v.n_cl == 1, 'lone', np.where(v.is_peak, 'peak', 'neighbour'))
out = {}

# T1
c = v.drop_duplicates('cl')
t1 = c.assign(size=pd.cut(c.n_cl, [0, 1, 2, 4, 8, 999], labels=['1', '2', '3-4', '5-8', '9+'])).groupby('size', observed=True).agg(
    clusters=('cl', 'size'), sum_frp_median=('cl_sum', 'median'), peak_frp_median=('cl_max', 'median'))
t1['per_pixel_median'] = v.assign(size=pd.cut(v.n_cl, [0, 1, 2, 4, 8, 999], labels=['1', '2', '3-4', '5-8', '9+'])).groupby('size', observed=True).frp.median()
print('T1 cluster size vs FRP (MW)\n', t1.round(1)); out['T1'] = t1.round(2).reset_index().to_dict('records')
out['T1_role_median_frp'] = v.groupby('role').frp.median().round(2).to_dict()

# T2 pairs
two = v[v.n_cl == 2].sort_values(['cl', 'frp'])
a, b = two.iloc[0::2].reset_index(drop=True), two.iloc[1::2].reset_index(drop=True)   # a = weaker, b = stronger
dx, dy = np.abs(b.x - a.x), np.abs(b.y - a.y)
P = pd.DataFrame(dict(weak=a.frp, strong=b.frp, ratio=a.frp / b.frp, dir=np.where(dx > dy, 'east-west (along scan)', 'north-south (along track)'),
                      pix=b.pix, sat4=b.sat_i4 | a.sat_i4, i4w=a.bright_ti4, i4s=b.bright_ti4))
rho = spearmanr(np.log(P.weak), np.log(P.strong))[0]
sl = np.polyfit(np.log(P.strong), np.log(P.weak), 1)[0]
# shuffle baseline: pair each strong pixel with a random weak pixel from another pair
rng = np.random.default_rng(0); rho0 = np.median([spearmanr(np.log(P.weak.values[rng.permutation(len(P))]), np.log(P.strong))[0] for _ in range(50)])
t2 = P.groupby('dir').agg(pairs=('ratio', 'size'), ratio_median=('ratio', 'median'), ratio_q25=('ratio', lambda s: s.quantile(.25)), ratio_q75=('ratio', lambda s: s.quantile(.75)))
print('\nT2 two-pixel clusters: weaker/stronger FRP\n', t2.round(2))
print('rank corr weak vs strong', round(rho, 2), '(shuffled', round(rho0, 2), ') | log-log slope', round(sl, 2))
out['T2'] = dict(table=t2.round(3).reset_index().to_dict('records'), rho=round(rho, 3), rho_shuffled=round(rho0, 3), slope=round(sl, 3),
                 ratio_median_by_strong_tercile=P.groupby(pd.qcut(P.strong, 3)).ratio.median().round(3).astype(float).tolist())

# T3 scar under the footprint
S = scars()
f = v.dropna(subset=['fire']).copy()
f['in_scar'] = [S[int(r.fire)].intersection(box(r.x - r.scan_m / 2, r.y - r.track_m / 2, r.x + r.scan_m / 2, r.y + r.track_m / 2)).area / (r.scan_m * r.track_m)
                for r in f.itertuples()]
# lone detections compared within the same pixel-size band
t3 = f.groupby('role').agg(n=('frp', 'size'), scar_share_median=('in_scar', 'median'), scar_share_mean=('in_scar', 'mean'),
                           share_under_10pct=('in_scar', lambda s: (s < .1).mean()), frp_median=('frp', 'median'))
print('\nT3 share of each footprint inside the final scar\n', t3.round(3)); out['T3'] = t3.round(3).reset_index().to_dict('records')
nb = f[f.role == 'neighbour']
t3b = nb.groupby(pd.qcut(nb.frp / nb.cl_max, 4)).agg(n=('frp', 'size'), scar_share=('in_scar', 'mean')).round(3)
print('neighbours by FRP share of their peak\n', t3b); out['T3_neighbour_by_ratio'] = t3b.reset_index().astype(str).to_dict('records')
# does more scar under a pixel mean more FRP? (all tied detections, rank corr)
out['T3_rho_frp_vs_scar_share'] = round(spearmanr(f.frp, f.in_scar)[0], 3)

# T4 swath edge
v['pix_band'] = pd.cut(v.scan_m * v.track_m / 1e6, [0, .2, .35, .55, 2], labels=['<0.2 km2 (near nadir)', '0.2-0.35', '0.35-0.55', '>0.55 (swath edge)'])
t4 = v.groupby('pix_band', observed=True).agg(detections=('frp', 'size'), frp_median=('frp', 'median'), lone_share=('n_cl', lambda s: (s == 1).mean()),
                                               mean_cluster=('n_cl', 'mean'))
t4['cluster_sum_median'] = v.drop_duplicates('cl').groupby('pix_band', observed=True).cl_sum.median()
mind = []
for _, g in v[v.n_cl > 1].groupby('cl'):
    X, Y = g.x.values, g.y.values; D = np.hypot(X[:, None] - X[None], Y[:, None] - Y[None]); np.fill_diagonal(D, 1e9)
    mind += list(D.min(1) / g.pix.values)
mind = np.array(mind)
print('\nT4 by pixel size\n', t4.round(2))
print('nearest same-pass neighbour distance / pixel size: share < 0.5 =', round((mind < .5).mean(), 3), '| median', round(np.median(mind), 2))
out['T4'] = t4.round(3).reset_index().astype(str).to_dict('records'); out['T4_neardup_share'] = round(float((mind < .5).mean()), 4)
out['T4_nn_dist_over_pix_quartiles'] = np.percentile(mind, [25, 50, 75]).round(2).tolist()
v.drop(columns=['pass']).merge(f[['in_scar']], left_index=True, right_index=True, how='left').to_csv(f'{RES}/clusters.csv', index=False)
json.dump(out, open(f'{RES}/cluster_tests.json', 'w'), indent=1, default=str)
