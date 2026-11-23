"""Step 2: link VIIRS points into fires (single linkage: within 1.2 km and 30 h, the spread thread's events_multi rule),
then define ALERTS = connected groups (1.2 km) of a fire's dots in its first satellite pass (what an official would see as
one new fire at the first look). Out (scratch): pts_f.parquet (points with fire id, look index), alerts_raw.parquet"""
import numpy as np, pandas as pd
from scipy.spatial import cKDTree
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components
SC = '/tmp/claude-0/-home-user/be9b8f54-cc26-52cb-bdbb-9c8008a24baf/scratchpad/r21_big'
LINK, GAP = 1200.0, 30.0
P = pd.read_parquet(f'{SC}/pts.parquet').sort_values('t').reset_index(drop=True)
P['th'] = (P.t - pd.Timestamp('2017-01-01')).dt.total_seconds() / 3600
fire = np.full(len(P), -1, np.int64); off = 0
for s, idx in P.groupby('season').indices.items():
    X = np.c_[P.x.values[idx], P.y.values[idx], P.th.values[idx] * (LINK / GAP)]
    pr = cKDTree(X).query_pairs(LINK, p=np.inf, output_type='ndarray')
    d = np.hypot(X[pr[:, 0], 0] - X[pr[:, 1], 0], X[pr[:, 0], 1] - X[pr[:, 1], 1])
    pr = pr[d <= LINK]
    n, lab = connected_components(coo_matrix((np.ones(len(pr)), (pr[:, 0], pr[:, 1])), shape=(len(idx),) * 2), directed=False)
    fire[idx] = lab + off; off += n
P['fire'] = fire
# looks: each fire's distinct passes in time order
P['look'] = P.groupby('fire').t.rank(method='dense').astype(int)  # pass times within a fire are distinct per pass
pt = P.groupby(['fire', 'pass_id']).t.min().rename('pt').reset_index()
pt['look'] = pt.groupby('fire').pt.rank(method='first').astype(int)
P = P.drop(columns='look').merge(pt[['fire', 'pass_id', 'look']], on=['fire', 'pass_id'])
# alerts: connected groups of first-look dots
F1 = P[P.look == 1].copy(); F1['alert'] = -1; aoff = 0
for f, idx in F1.groupby('fire').indices.items():
    if len(idx) == 1:
        F1.iloc[idx[0], F1.columns.get_loc('alert')] = aoff; aoff += 1; continue
    X = np.c_[F1.x.values[idx], F1.y.values[idx]]
    pr = cKDTree(X).query_pairs(LINK, output_type='ndarray')
    n, lab = connected_components(coo_matrix((np.ones(len(pr)), (pr[:, 0], pr[:, 1])), shape=(len(idx),) * 2), directed=False)
    F1.iloc[idx, F1.columns.get_loc('alert')] = lab + aoff; aoff += n
P = P.merge(F1[['sensor', 'pass_id', 'x', 'y', 't', 'alert']], on=['sensor', 'pass_id', 'x', 'y', 't'], how='left')
P['alert'] = P.alert.fillna(-1).astype(int)
P.to_parquet(f'{SC}/pts_f.parquet')
nf = P.groupby('fire').agg(n=('t', 'size'), looks=('look', 'max'), t0=('t', 'min'), t1=('t', 'max'))
print('points', len(P), 'fires', len(nf), 'alerts', aoff)
print('fires by looks', nf.looks.clip(upper=6).value_counts().sort_index().to_dict())
print('dots per fire p50/p90/p99/max', nf.n.quantile([.5, .9, .99]).tolist(), nf.n.max())
print('duration h of biggest 5', ((nf.t1 - nf.t0).dt.total_seconds() / 3600).sort_values().tail(5).round(0).tolist())
