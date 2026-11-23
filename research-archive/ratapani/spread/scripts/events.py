"""Group VIIRS (S-NPP 375 m) detections into fire events: single-linkage within 1.2 km and 30 h.
Writes detections with event id and overpass time (UTC)."""
import numpy as np, pandas as pd, sys
from pyproj import Transformer
from scipy.sparse.csgraph import connected_components
from scipy.sparse import coo_matrix
from scipy.spatial import cKDTree
v = pd.read_parquet('/mnt/project-files/ratapani/viirs_snpp_2013_2024.parquet')
v = v[(v.confidence != 'l') & (v.year >= 2017) & (v.month <= 6)].copy()
v['t'] = pd.to_datetime(v.acq_date.astype(str)) + pd.to_timedelta(v.acq_time // 100, 'h') + pd.to_timedelta(v.acq_time % 100, 'm')
x, y = Transformer.from_crs(4326, 32643, always_xy=True).transform(v.longitude.values, v.latitude.values)
v['x'], v['y'] = x, y
v['season'] = np.where(v.month >= 12, v.year + 1, v.year)
v = v.sort_values('t').reset_index(drop=True)
th = (v.t - v.t.min()).dt.total_seconds().values / 3600
# scale time so that 30 h == 1200 m, then link within 1200 m in (x, y, t) space under a box check
P = np.c_[v.x, v.y, th * 40.0]
tree = cKDTree(P); pairs = tree.query_pairs(1200 * np.sqrt(2), output_type='ndarray')
d = np.abs(P[pairs[:, 0]] - P[pairs[:, 1]])
ok = (np.hypot(d[:, 0], d[:, 1]) <= 1200) & (d[:, 2] <= 1200)
pairs = pairs[ok]
n = len(v); A = coo_matrix((np.ones(len(pairs)), (pairs[:, 0], pairs[:, 1])), shape=(n, n))
_, lab = connected_components(A, directed=False); v['event'] = lab
v['overpass'] = v.t.dt.floor('2h')
g = v.groupby('event').agg(n=('x', 'size'), n_pass=('overpass', 'nunique'), t0=('t', 'min'), t1=('t', 'max'))
g['hours'] = (g.t1 - g.t0).dt.total_seconds() / 3600
print(len(v), 'detections,', len(g), 'events'); print(g.n_pass.value_counts().sort_index().head(10))
print('events with >=2 overpasses:', (g.n_pass >= 2).sum(), ' >=3:', (g.n_pass >= 3).sum(), ' spanning >=20h:', (g.hours >= 20).sum())
v.to_parquet(sys.argv[1])
