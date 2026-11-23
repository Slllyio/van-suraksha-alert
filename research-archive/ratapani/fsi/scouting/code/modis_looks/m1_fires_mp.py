"""All-MP forest fires from VIIRS, with MODIS looks attached.
- VIIRS points kept if their 500 m MP cell is forest-department land (ratapani/mp_grid/mp_cells.parquet, >=50% beat cover).
- Fires: union-find, link if within LINK m and GAP h (default 1000 m / 48 h, the stopping note's main rule).
- Slots: the MP-wide VIIRS look schedule (looks = VIIRS points within 2 h gaps, ~01:30 and ~13:30 IST).
- MODIS point -> fire: the forest VIIRS point within R (1000 m; 1500 m if the MODIS pixel is >1.5 km) with the smallest |dt|
  (<= 36 h). MODIS points matching no fire are kept as unmatched.
Out (scratch): fires_mp.parquet, fire_slots_mp.parquet (fire x VIIRS slot), modis_fire_mp.parquet."""
import os, sys, numpy as np, pandas as pd
from scipy.spatial import cKDTree
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components
S = os.environ['ML_SCRATCH']; LINK = float(sys.argv[1]) if len(sys.argv) > 1 else 1000; GAP = float(sys.argv[2]) if len(sys.argv) > 2 else 48
V = pd.read_parquet(f'{S}/viirs_mp.parquet'); M = pd.read_parquet(f'{S}/modis_mp.parquet')
C = pd.read_parquet('/mnt/project-files/ratapani/mp_grid/mp_cells.parquet', columns=['cell'])
cell = np.floor((2996000 - V.y) / 500).astype(int) * 1829 + np.floor((V.x - 399000) / 500).astype(int)
V = V[cell.isin(set(C.cell))].reset_index(drop=True)
LK = V.groupby('look').agg(t=('t', 'min'), h=('ist_h', 'median')).reset_index()   # slots seen by forest points only
# full schedule from all points (forest subset could miss a look): rebuild from the full file
VA = pd.read_parquet(f'{S}/viirs_mp.parquet', columns=['t', 'look', 'ist_h', 'season'])
SCH = VA.groupby('look').agg(t=('t', 'min'), t1=('t', 'max'), h=('ist_h', 'median'), season=('season', 'first')).reset_index().sort_values('t').reset_index(drop=True)
SCH['slot'] = np.arange(len(SCH))
V = V.merge(SCH[['look', 'slot']], on='look')
V['th'] = (V.t - pd.Timestamp('2014-01-01')).dt.total_seconds() / 3600
fire = np.full(len(V), -1); off = 0
for s, g in V.groupby('season'):
    P = np.c_[g.x, g.y, g.th * LINK / GAP]
    pr = cKDTree(P).query_pairs(LINK, p=np.inf, output_type='ndarray')
    ok = np.hypot(P[pr[:, 0], 0] - P[pr[:, 1], 0], P[pr[:, 0], 1] - P[pr[:, 1], 1]) <= LINK
    pr = pr[ok]; n = len(g)
    A = coo_matrix((np.ones(len(pr)), (pr[:, 0], pr[:, 1])), shape=(n, n))
    k, lab = connected_components(A, directed=False)
    fire[g.index.values] = lab + off; off += k
V['fire'] = fire
F = V.groupby('fire').agg(season=('season', 'first'), n=('t', 'size'), t0=('t', 'min'), t1=('t', 'max'), s0=('slot', 'min'), s1=('slot', 'max'),
                          n_looks=('slot', 'nunique'), frp_max=('frp', 'max'), x=('x', 'mean'), y=('y', 'mean'),
                          ext_km=('x', lambda u: np.ptp(u) / 1000))
F['span_slots'] = F.s1 - F.s0 + 1
# Ratapani box (the bbox of fire-alert-scars/alerts) flag
import pyproj; tr = pyproj.Transformer.from_crs(32643, 4326, always_xy=True)
lon, lat = tr.transform(F.x.values, F.y.values)
R = pd.read_csv('/mnt/project-files/fire-alert-scars/alerts/viirs-snpp_2020.csv', usecols=['latitude', 'longitude'])
F['ratapani_box'] = (lon >= R.longitude.min()) & (lon <= R.longitude.max()) & (lat >= R.latitude.min()) & (lat <= R.latitude.max())
# MODIS -> fire
M['th'] = (M.t - pd.Timestamp('2014-01-01')).dt.total_seconds() / 3600
M['fire'] = -1; M['dt_h'] = np.nan; M['d_m'] = np.nan
for s, g in M.groupby('season'):
    vs = V[V.season == s]
    if not len(vs): continue
    tree = cKDTree(np.c_[vs.x, vs.y, vs.th * 1500 / 36])
    big = (np.maximum(g.scan, g.track) > 1.5).values
    cand = tree.query_ball_point(np.c_[g.x, g.y, g.th * 1500 / 36], 1500, p=np.inf)
    vx, vy, vt, vf = vs.x.values, vs.y.values, vs.th.values, vs.fire.values
    gx, gy, gt = g.x.values, g.y.values, g.th.values
    fi = np.full(len(g), -1); dtb = np.full(len(g), np.nan); dd = np.full(len(g), np.nan)
    for i, c in enumerate(cand):
        if not c: continue
        c = np.array(c); dist = np.hypot(vx[c] - gx[i], vy[c] - gy[i]); c, dist = c[dist <= (1500 if big[i] else 1000)], dist[dist <= (1500 if big[i] else 1000)]
        if not len(c): continue
        j = np.argmin(np.abs(vt[c] - gt[i]) + dist / 1e5)
        fi[i] = vf[c[j]]; dtb[i] = gt[i] - vt[c[j]]; dd[i] = dist[j]
    M.loc[g.index, 'fire'] = fi; M.loc[g.index, 'dt_h'] = dtb; M.loc[g.index, 'd_m'] = dd
M['kind'] = M.sensor + '_' + M.daynight
# fire x slot table: from first slot to last slot + 4 (about 2 days after the last VIIRS detection)
fs = V.groupby(['fire', 'slot']).agg(nv=('t', 'size'), frp=('frp', 'max')).reset_index()
rows = []
ff = F[F.n_looks >= 1]
s0, s1 = ff.s0.values, np.minimum(ff.s1.values + 4, len(SCH) - 1)
rep = s1 - s0 + 1
T = pd.DataFrame({'fire': np.repeat(ff.index.values, rep), 'slot': np.concatenate([np.arange(a, b + 1) for a, b in zip(s0, s1)])})
T = T.merge(fs, on=['fire', 'slot'], how='left'); T['nv'] = T.nv.fillna(0).astype(int)
T = T.merge(SCH[['slot', 't', 'h', 'season']], on='slot')
T = T[T.season == T.fire.map(F.season)]
F.to_parquet(f'{S}/fires_mp.parquet'); T.to_parquet(f'{S}/fire_slots_mp.parquet'); M.to_parquet(f'{S}/modis_fire_mp.parquet'); SCH.to_parquet(f'{S}/schedule.parquet')
print(len(V), 'forest VIIRS pts', len(F), 'fires;', (F.n_looks >= 2).sum(), 'multi-look;', ((F.n_looks >= 4) & (F.n >= 10)).sum(), 'big (>=4 looks,>=10 pts)')
print('ext_km quantiles multi-look', F[F.n_looks >= 2].ext_km.quantile([.5, .9, .99, 1]).round(1).to_dict())
print('MODIS matched share by kind', M.groupby('kind').fire.apply(lambda f: (f >= 0).mean()).round(3).to_dict())
print('Ratapani-box fires', F.ratapani_box.sum())
