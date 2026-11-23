"""Step 4: features known at alert time (first look = v1) and by first look + 15 h (v2), fire growth curves (VIIRS cells),
and fire-level VIIRS footprint size. No information later than the issue time enters a feature.
Out (scratch): alerts.parquet (one row per alert), growth.parquet (fire, hours since first look, cumulative 375 m cells)"""
import numpy as np, pandas as pd, rasterio
from rasterio.windows import from_bounds
from scipy.spatial import cKDTree
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components
from scipy.ndimage import uniform_filter
import pyproj
ROOT = '/mnt/project-files'; SC = '/tmp/claude-0/-home-user/be9b8f54-cc26-52cb-bdbb-9c8008a24baf/scratchpad/r21_big'
SCR = '/tmp/claude-0/-home-user/be9b8f54-cc26-52cb-bdbb-9c8008a24baf/scratchpad'
P = pd.read_parquet(f'{SC}/pts_f.parquet').sort_values('t').reset_index(drop=True)
P['th'] = (P.t - pd.Timestamp('2017-01-01')).dt.total_seconds() / 3600
P['blk'] = np.sqrt(P.scan * P.track) * 1000
f0 = P.groupby('fire').th.transform('min'); P['h'] = P.th - f0
V2H = 15.0
# ---------- growth curves and VIIRS footprint size (within 7 days) ----------
Q = P[P.h <= 168].copy()
Q['cell'] = (np.floor(Q.x / 375).astype(np.int64) * 100000 + np.floor(Q.y / 375).astype(np.int64))
Q = Q.sort_values(['fire', 'h'])
Q['newcell'] = ~Q.duplicated(['fire', 'cell'])
gr = Q.groupby(['fire', 'look']).agg(h=('h', 'min'), new=('newcell', 'sum')).reset_index()
gr['cum'] = gr.groupby('fire').new.cumsum()
gr[['fire', 'look', 'h', 'cum']].to_parquet(f'{SC}/growth.parquet')
FS = Q.groupby('fire').agg(cells7=('newcell', 'sum'), dots7=('t', 'size'), looks7=('look', 'nunique'), days7=('h', lambda s: s.max() / 24))
# ---------- v1: first-look alert features ----------
A1 = P[P.alert >= 0]
def extent(g):
    if len(g) == 1: return g.blk.iloc[0]
    X = np.c_[g.x, g.y]; d = np.sqrt(((X[:, None] - X[None]) ** 2).sum(-1)).max()
    return d + g.blk.mean()
grp = A1.groupby('alert')
A = grp.agg(fire=('fire', 'first'), season=('season', 'first'), t0=('t', 'min'), sensor=('sensor', 'first'), n1=('t', 'size'),
            frp_sum1=('frp', 'sum'), frp_max1=('frp', 'max'), blk1=('blk', 'mean'), night=('daynight', lambda s: (s == 'N').mean()),
            x=('x', 'mean'), y=('y', 'mean'), lat=('latitude', 'mean'), lon=('longitude', 'mean'),
            Division=('Division', lambda s: s.mode().iloc[0]), slope1=('slope', 'mean'), slope_max1=('slope', 'max'), elev1=('elev', 'mean'),
            bt4_max1=('bright_ti4', 'max'))
A['ext1'] = grp.apply(extent)
VT = A1.vtm.values
A1 = A1.assign(g_grass=((VT >= 115) & (VT < 150)), g_teak=np.isin(VT, [25, 28, 37]), g_sal=np.isin(VT, [24, 27, 36]),
               g_dry=np.isin(VT, [26, 29]), g_moist=(VT == 23), g_degr=(VT == 106), g_bamboo=np.isin(VT, [30, 40]), g_nonforest=(VT >= 150))
for c in ['g_grass', 'g_teak', 'g_sal', 'g_dry', 'g_moist', 'g_degr', 'g_bamboo', 'g_nonforest']:
    A[c + '_dots'] = A1.groupby('alert')[c].mean()
A = A.reset_index()
A['n_alerts_in_fire'] = A.groupby('fire').alert.transform('size')
A['hour'] = A.t0.dt.hour + A.t0.dt.minute / 60
A['doy'] = A.t0.dt.dayofyear
A['days_since_15feb'] = (A.t0 - pd.to_datetime(A.season.astype(str) + '-02-15')).dt.total_seconds() / 86400
A['month'] = A.t0.dt.month
A['th0'] = (A.t0 - pd.Timestamp('2017-01-01')).dt.total_seconds() / 3600
# neighbourhood vegetation (Roy et al. VTM 60 m) in a 1 km window round the alert centre
tp = pyproj.Transformer.from_crs(4326, 32643, always_xy=True).transform
ux, uy = tp(A.lon.values, A.lat.values)
with rasterio.open(f'{SCR}/r14_types_data/vtm.tif') as r:
    w = from_bounds(ux.min() - 2000, uy.min() - 2000, ux.max() + 2000, uy.max() + 2000, r.transform)
    arr = r.read(1, window=w); tr = r.window_transform(w)
col = ((ux - tr.c) / tr.a).astype(int); row = ((uy - tr.f) / tr.e).astype(int)
K = 17  # 17 x 60 m ~ 1 km
for name, cond in (('grass', (arr >= 115) & (arr < 150)), ('teak', np.isin(arr, [25, 28, 37])), ('sal', np.isin(arr, [24, 27, 36])),
                   ('forest', (arr >= 11) & (arr < 115)), ('agri', arr == 170)):
    m = uniform_filter(cond.astype(np.float32), K, mode='constant')
    A[f'{name}_1km'] = m[row.clip(0, arr.shape[0] - 1), col.clip(0, arr.shape[1] - 1)]
    del m
del arr
# terrain roughness: SD of elevation in ~1.5 km (DEM ~140 m)
D = dict(np.load(f'{SCR}/r19_pool/dem_mp.npz'))
E = np.nan_to_num(D['elev']); m1 = uniform_filter(E, 11); m2 = uniform_filter(E * E, 11); rough = np.sqrt(np.clip(m2 - m1 * m1, 0, None))
n = 256 * 2 ** 10
px = (A.lon.values + 180) / 360 * n - 256 * D['x0']; rr = np.radians(A.lat.values)
py = (1 - np.log(np.tan(rr) + 1 / np.cos(rr)) / np.pi) / 2 * n - 256 * D['y0']
A['rough1500'] = rough[np.clip(py.astype(int), 0, E.shape[0] - 1), np.clip(px.astype(int), 0, E.shape[1] - 1)]
del D, E, m1, m2, rough
# context from other dots: nearby in previous 3 days (10 km, 3 km), burned earlier this season within 2 km, statewide last 24 h
for s, ia in A.groupby('season').indices.items():
    ps = P[P.season == s]
    X3 = np.c_[ps.x, ps.y, ps.th * (10000 / 36)]
    tr3 = cKDTree(X3)
    q = np.c_[A.x.values[ia], A.y.values[ia], (A.th0.values[ia] - 36) * (10000 / 36)]
    L = tr3.query_ball_point(q, 10000, p=np.inf)
    px_, py_, pt_ = ps.x.values, ps.y.values, ps.th.values
    n10, n3 = np.zeros(len(ia)), np.zeros(len(ia))
    for j, (i, l) in enumerate(zip(ia, L)):
        l = np.asarray(l, int)
        if len(l) == 0: continue
        ok = pt_[l] < A.th0.values[i] - 0.05
        d = np.hypot(px_[l] - A.x.values[i], py_[l] - A.y.values[i])
        n10[j] = (ok & (d <= 10000)).sum(); n3[j] = (ok & (d <= 3000)).sum()
    A.loc[A.index[ia], 'near10_3d'] = n10; A.loc[A.index[ia], 'near3_3d'] = n3
    tr2 = cKDTree(np.c_[px_, py_])
    L2 = tr2.query_ball_point(np.c_[A.x.values[ia], A.y.values[ia]], 2000)
    A.loc[A.index[ia], 'burned_before_2km'] = [int((pt_[np.asarray(l, int)] < A.th0.values[i] - 0.05).sum()) if len(l) else 0 for i, l in zip(ia, L2)]
    ts = np.sort(pt_)
    A.loc[A.index[ia], 'state_24h'] = np.searchsorted(ts, A.th0.values[ia] - 0.05) - np.searchsorted(ts, A.th0.values[ia] - 24)
# 50 km day-speed map (squares v3 part A), value from the OTHER parity half of seasons (never the alert's own season)
C = pd.read_csv(f'{ROOT}/ratapani/fsi/scouting/code/squares_v3/a/results/a4_cells_50km.csv'); C = C[C.dn == 'D']
cx = (C.lon.values - 78) * 111.32 * np.cos(np.radians(23.5)); cy = (C.lat.values - 23.5) * 110.574
dd, ii = cKDTree(np.c_[cx, cy]).query(np.c_[A.x / 1000, A.y / 1000])
ev, od = C.speed_even.values[ii], C.speed_odd.values[ii]
A['speed50'] = np.where(A.season % 2 == 0, od, ev)
A.loc[dd > 40, 'speed50'] = np.nan
# control-burn flag, live version (control_burn_rule.py): 15-28 Feb, day-only, <= 2 dots, max FRP <= 5 MW
A['control_live'] = ((A.t0.dt.month == 2) & (A.t0.dt.day >= 15) & (A.night == 0) & (A.n1 <= 2) & (A.frp_max1 <= 5)).astype(int)
# MODIS Terra / Aqua seen within 1.5 km in the 12 h before the first VIIRS look (v1), and Terra between t0 and t0 + 15 h (v2)
M = pd.read_parquet(f'{SC}/modis.parquet'); M['th'] = (M.t - pd.Timestamp('2017-01-01')).dt.total_seconds() / 3600
trm = cKDTree(np.c_[M.x, M.y, M.th * (1500 / 6)])
L = trm.query_ball_point(np.c_[A.x, A.y, (A.th0 - 6) * (1500 / 6)], 1500, p=np.inf)
A['modis_before'] = [int(len(l) > 0) for l in L]
A['terra_before'] = [int(any(M.satellite.values[k] == 'Terra' for k in l)) for l in L]
# ---------- v2: everything by first look + 15 h, linked using only dots known by then ----------
W = P[P.h <= V2H]
multi = W.groupby('fire').look.transform('max') > 1
W1, Wm = W[~multi], W[multi]
v2 = {}
for f, g in Wm.groupby('fire'):
    X = np.c_[g.x.values, g.y.values, g.th.values * (1200 / 30)]
    pr = cKDTree(X).query_pairs(1200, p=np.inf, output_type='ndarray')
    if len(pr):
        d = np.hypot(X[pr[:, 0], 0] - X[pr[:, 1], 0], X[pr[:, 0], 1] - X[pr[:, 1], 1]); pr = pr[d <= 1200]
    nc, lab = connected_components(coo_matrix((np.ones(len(pr)), (pr[:, 0], pr[:, 1])), shape=(len(g),) * 2), directed=False)
    al = g.alert.values
    for a in np.unique(al[al >= 0]):
        cmp_ = np.unique(lab[al == a]); sel = np.isin(lab, cmp_); gg = g[sel]
        cells = np.unique(np.floor(gg.x / 375).astype(int) * 100000 + np.floor(gg.y / 375).astype(int))
        Xg = np.c_[gg.x, gg.y]; span = np.sqrt(((Xg[:, None] - Xg[None]) ** 2).sum(-1)).max() + gg.blk.mean() if len(gg) < 400 else np.nan
        later = gg[gg.look > 1]
        v2[a] = dict(n2=len(gg), looks2=gg.look.nunique(), cells2=len(cells), ext2=span, frp_sum2=gg.frp.sum(), frp_max2=gg.frp.max(),
                     n_later2=len(later), night_later2=int((later.daynight == 'N').any()), last_h2=gg.h.max())
V = pd.DataFrame.from_dict(v2, orient='index'); V.index.name = 'alert'; V = V.reset_index()
A = A.merge(V, on='alert', how='left')
A['n2'] = A.n2.fillna(A.n1); A['looks2'] = A.looks2.fillna(1); A['ext2'] = A.ext2.fillna(A.ext1); A['frp_sum2'] = A.frp_sum2.fillna(A.frp_sum1)
A['frp_max2'] = A.frp_max2.fillna(A.frp_max1); A['n_later2'] = A.n_later2.fillna(0); A['night_later2'] = A.night_later2.fillna(0)
A['cells2'] = A.cells2.fillna(np.nan)
A['seen_again2'] = (A.looks2 > 1).astype(int)
# Terra between t0 and t0 + 15 h within 1.5 km of the alert centre
L = trm.query_ball_point(np.c_[A.x, A.y, (A.th0 + V2H / 2) * (1500 / 6)], 1500 * max(1, V2H / 12), p=np.inf)
A['terra_between2'] = [int(any((M.satellite.values[k] == 'Terra') and (A.th0.values[i] < M.th.values[k] <= A.th0.values[i] + V2H)
                                and np.hypot(M.x.values[k] - A.x.values[i], M.y.values[k] - A.y.values[i]) <= 1500 for k in l)) for i, l in enumerate(L)]
A = A.merge(FS, left_on='fire', right_index=True, how='left')
A.to_parquet(f'{SC}/alerts.parquet')
print(A.shape); print(A.describe().T[['mean', '50%', 'max']].round(3).to_string())
