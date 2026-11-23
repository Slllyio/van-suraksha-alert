"""t1: burn-day clusters with the raw ingredients of every candidate control-burn rule, plus multi-day fire IDs.
Input : r15 point table (scratch) pts_feat2.parquet (VIIRS S-NPP/NOAA-20/NOAA-21 inside MP beats, Oct-Jun, seasons 2014-26),
        same clusters (cid: same fire-day, <=750 m) as code/early_burns.
Output: scratch r21_cb/clusters_t1.parquet (one row per cluster).
Per cluster: n, nsat, frp_max, day_only, night_near (night point <=1.5 km same fire-day), dmin_k = nearest other point (m) on
fire-day offset k (k=-3..+3, capped 5 km), earliest IST hour of day passes, satellites present, fire_id (clusters chained within
1 km on consecutive fire-days, transitively = one 'fire' for the bootstrap)."""
import numpy as np, pandas as pd
from scipy.spatial import cKDTree
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components
S = '/tmp/claude-0/-home-user/be9b8f54-cc26-52cb-bdbb-9c8008a24baf/scratchpad/'
d = pd.read_parquet(S + 'r15_firms_nd/pts_feat2.parquet')
d['key'] = d.season.astype(np.int64) * 1000 + d.fday
X = d[['x', 'y']].values
idx_by_key = d.groupby('key').indices
trees = {k: cKDTree(X[i]) for k, i in idx_by_key.items()}
CAP = 5000.0
dmin = {}
for k in range(-3, 4):
    if k == 0: continue
    out = np.full(len(d), CAP)
    for key, i in idx_by_key.items():
        t = trees.get(key + k)
        if t is None: continue
        dd, _ = t.query(X[i], k=1, distance_upper_bound=CAP)
        out[i] = np.minimum(dd, CAP)
    dmin[k] = out
for k, v in dmin.items(): d[f'dmin_{k:+d}'] = v
d['hour_ist'] = d.t_ist.dt.hour + d.t_ist.dt.minute / 60
d['dayhour'] = np.where(d.day, d.hour_ist, np.nan)
g = d.groupby('cid')
agg = dict(Division=('Division', 'first'), beat=('beat_uid', 'first'), season=('season', 'first'), fday=('fday', 'first'),
           date=('date_ist', 'min'), win=('win', 'first'), n=('frp', 'size'), nsat=('sat', 'nunique'), frp_max=('frp', 'max'),
           frp_sum=('frp', 'sum'), all_day=('day', 'all'), night_near=('night_near', 'any'), x=('x', 'mean'), y=('y', 'mean'),
           first_dayhour=('dayhour', 'min'), last_dayhour=('dayhour', 'max'), lat=('latitude', 'mean'), lon=('longitude', 'mean'),
           has_snpp=('sat', lambda s: (s == 'snpp').any()), d_road=('d_road', 'min'), d_track=('d_track', 'min'),
           d_edge=('d_beatedge', 'min'))
for k in dmin: agg[f'dmin_{k:+d}'] = (f'dmin_{k:+d}', 'min')
c = g.agg(**agg).reset_index()
c['day_only'] = c.all_day & ~c.night_near
# satellites available that season (rule depends on how many satellites fly)
c['era'] = np.select([c.season <= 2017, c.season <= 2022], ['1 S-NPP only', '2 S-NPP+N20'], '3 three sats')
# fire IDs: chain clusters within 1 km on fire-day offsets +1 (transitive)
pos = pd.Series(np.arange(len(c)), index=c.cid)
pc = pos.loc[d.cid.values].values          # cluster row of each point
rows, cols = [], []
for key, i in idx_by_key.items():
    t = trees.get(key + 1)
    if t is None: continue
    j = idx_by_key[key + 1]
    for a, lst in zip(i, t.query_ball_point(X[i], 1000)):
        for b in lst: rows.append(pc[a]); cols.append(pc[j[b]])
A = coo_matrix((np.ones(len(rows)), (rows, cols)), shape=(len(c), len(c)))
_, c['fire_id'] = connected_components(A, directed=False)
c['fire_ndays'] = c.groupby('fire_id').fday.transform(lambda s: s.max() - s.min() + 1)
c['fire_pts'] = c.groupby('fire_id').n.transform('sum')
m, dd = c.date.dt.month, c.date.dt.day
c['fn'] = np.select([m.isin([10, 11, 12]), m == 1, (m == 2) & (dd < 15), m == 2, (m == 3) & (dd <= 15), (m == 3) | m.isin([4, 5]), m == 6],
                    ['0 Oct-Dec', '1 Jan', '2 1-14 Feb', '3 15-28 Feb', '4 1-15 Mar', '5 16 Mar-May', '6 Jun'], 'x')
c.to_parquet(S + 'r21_cb/clusters_t1.parquet')
print(len(c), c.fn.value_counts().sort_index().to_dict())
print(c.groupby('fn')[['n', 'frp_max', 'day_only', 'fire_ndays']].mean().round(2))
