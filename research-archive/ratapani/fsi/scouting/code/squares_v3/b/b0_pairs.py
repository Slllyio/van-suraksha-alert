"""B step 0: one table of every pair observation of every fire, all of MP, each look its own sensor and time.

Source: the pooled run's pairs with context (r19_pool/ctx.parquet, FIRMS type 0 only, pairs with earlier detections).
Segments (as squares_v2 p6): VIIRS small gaps (25-75 min, two different satellites, day or night), Terra 10:40 -> VIIRS,
Terra 22:10 -> VIIRS, VIIRS 12 h pairs (13:30 -> 01:30 and 01:30 -> 13:30, any two VIIRS incl. the same one).
Per pair:
  p_raw  outward move (m): (B - A centroid) minus the static-site sensor/pair bias, projected on u = M - E
         (E = centroid of detections 2-48 h before A; never uses A or B). edge = part A's per-pair edge-reach term
         (small gaps only; b1 subtracts it after clipping, as part A specifies).
  q      the perpendicular part (true value 0 by symmetry): the noise calibration for everything later.
  var2   noise variance of one projection from the static-site model (along scan k 0.59, 180 m; along track k 0.90,
         132 m; halved for one direction).
  K      clock hours: integral of the diurnal multiplier (mean 1) over the pair's own interval, so p = v_daily x K.
Fire id, all MP: pairs linked when their earlier looks are < 1.5 km and < 30 h apart (single linkage, per season).
Fire id, Ratapani: the big-fires fire (scar + 200 m rule, r19_track/det.parquet), matched through look A's detections.
Out (scratch r20_b): obs.parquet"""
import sys, os
import numpy as np, pandas as pd, pyproj
from scipy.spatial import cKDTree
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from b_lib import *
import json
R = pd.read_parquet(f'{POOL}/ctx.parquet')
R = R[(R.typ == 0) & (R.nE > 0)].copy()
R['vv'] = R.sA.isin(VIIRS) & R.sB.isin(VIIRS); R['gap_h'] = R.gap_min / 60; R['pair'] = R.sA + '>' + R.sB
R['dir'] = np.where(R.istA.between(8, 20), 'day>night', 'night>day')
seg = np.full(len(R), '', object)
sm = (R.vv & (R.gap_min <= 120) & (R.sA != R.sB)).values
seg[sm & (R.dn == 'D').values] = 'small_day'; seg[sm & (R.dn == 'N').values] = 'small_night'
t = ((R.sA == 'Terra') & R.sB.isin(VIIRS) & R.gap_min.between(100, 240)).values
seg[t & (R.dn == 'D').values] = 'terra_day'; seg[t & (R.dn == 'N').values] = 'terra_night'
l = (R.vv & (R.gap_min >= 600)).values
seg[l & (R.dir == 'day>night').values] = '12h_day>night'; seg[l & (R.dir == 'night>day').values] = '12h_night>day'
R['seg'] = seg; R = R[R.seg != ''].copy()
# ---- bias (static-site tables of squares_v2)
res = f'{V2}/pooled/results'
off = {tuple(k.split(' ')): v for k, v in json.load(open(f'{res}/pooled_summary.json'))['offsets_static'].items()}
bm = pd.read_csv(f'{res}/bias_table_modis.csv').set_index(['pair', 'dn']); b12 = pd.read_csv(f'{res}/bias_table_12h.csv').set_index(['pair', 'dir'])
bE = np.zeros(len(R)); bN = np.zeros(len(R))
s = R.seg.str.startswith('small').values
for i in np.where(s)[0]:
    a, b, dn = R.sA.values[i], R.sB.values[i], R.dn.values[i]
    bE[i] = off[(dn, 'dE')].get(b, 0) - off[(dn, 'dE')].get(a, 0); bN[i] = off[(dn, 'dN')].get(b, 0) - off[(dn, 'dN')].get(a, 0)
k = R.seg.str.startswith('terra').values
bE[k] = [bm.bE.get(z, 0.0) for z in zip(R.pair.values[k], R.dn.values[k])]; bN[k] = [bm.bN.get(z, 0.0) for z in zip(R.pair.values[k], R.dn.values[k])]
k = R.seg.str.startswith('12h').values
bE[k] = [b12.bE.get(z, 0.0) for z in zip(R.pair.values[k], R.dir.values[k])]; bN[k] = [b12.bN.get(z, 0.0) for z in zip(R.pair.values[k], R.dir.values[k])]
L = np.hypot(R.uE, R.uN); ue, un = (R.uE / L).values, (R.uN / L).values
cE, cN = R.dE.values - bE, R.dN.values - bN
edge, edge_src = edge_term(R.index)
R['p_raw'] = cE * ue + cN * un; R['edge'] = edge; R['p'] = R.p_raw - edge; R['q'] = -cE * un + cN * ue
R['edge_src'] = edge_src
R['var2'] = ((0.592 * (R.scanA ** 2 / R.nA + R.scanB ** 2 / R.nB) / 12 + 180 ** 2) + (0.899 * (R.trackA ** 2 / R.nA + R.trackB ** 2 / R.nB) / 12 + 132 ** 2)) / 2
R['K'] = clock_hours(R.istA.values, R.gap_h.values)
R['ftype'] = ftype(R.vtm.values); R['month'] = R.tA.dt.month
R['npix'] = R.nA + R.nB; R['frp2'] = R.frpA + R.frpB
# ---- all-MP fire clusters
R = R.reset_index().rename(columns={'index': 'ctx_row'})
R['th'] = (R.tA - pd.Timestamp('2018-01-01')).dt.total_seconds() / 3600
fid = np.full(len(R), -1, np.int64); base = 0
for season, g in R.groupby('season'):
    X = np.c_[g.ax.values, g.ay.values, g.th.values * 50.0]       # 30 h = 1.5 km
    e = cKDTree(X).query_pairs(1500.0, output_type='ndarray')
    M = coo_matrix((np.ones(len(e)), (e[:, 0], e[:, 1])), shape=(len(g), len(g)))
    nc, lab = connected_components(M, directed=False); fid[g.index.values] = lab + base; base += nc
R['fire_mp'] = fid
# ---- Ratapani fire ids (big-fires rule) via look A's detections
D = pd.read_parquet(f'{TRACK}/det.parquet'); D = D[(D.fire >= 0)]
tp = pyproj.Transformer.from_crs(4326, 32643, always_xy=True).transform
R['fire_rt'] = -1
box = R.latA.between(22.70, 23.25) & R.lonA.between(77.2, 78.2)
xa, ya = tp(R.lonA.values[box], R.latA.values[box]); ta = R.th.values[box]; sa = R.sA.values[box]
out = np.full(box.sum(), -1)
for sen, g in D.groupby('sensor'):
    gt = ((g.t - pd.Timestamp('2018-01-01')).dt.total_seconds() / 3600).values
    tr = cKDTree(np.c_[g.x.values, g.y.values, gt * 6000.0])     # 10 min = 1 km
    m = sa == sen
    if not m.any(): continue
    d, j = tr.query(np.c_[xa[m], ya[m], ta[m] * 6000.0], distance_upper_bound=1200)
    ok = np.isfinite(d); o = np.full(m.sum(), -1); o[ok] = g.fire.values[j[ok]]; out[m] = o
R.loc[box, 'fire_rt'] = out
keep = ['ctx_row', 'p_raw', 'edge', 'seg', 'sA', 'sB', 'dn', 'tA', 'tB', 'istA', 'gap_h', 'K', 'p', 'q', 'var2', 'nA', 'nB', 'npix', 'frpA', 'frpB', 'frp2',
        'scanA', 'trackA', 'scanB', 'trackB', 'areaA', 'areaB', 'age_h', 'u_len', 'vtm', 'ftype', 'cover', 'slope', 'elev', 'month', 'season',
        'latA', 'lonA', 'ax', 'ay', 'mx', 'my', 'wE', 'wN', 'upaz', 'fire_mp', 'fire_rt', 'edge_src']
R[keep].to_parquet(f'{SC}/obs.parquet')
print(len(R), 'pair observations'); print(R.seg.value_counts().to_string())
print('MP fires', R.fire_mp.nunique(), 'pairs per fire', R.groupby('fire_mp').size().describe().round(1).to_dict())
print('Ratapani fires matched', R[R.fire_rt >= 0].fire_rt.nunique(), 'pairs', (R.fire_rt >= 0).sum(), 'edge term:', edge_src, 'clock:', diurnal()['src'])
