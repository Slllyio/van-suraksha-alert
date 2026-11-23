"""Independent VIIRS fire tracks for Ratapani (all three satellites), from raw FIRMS points only.
Out: tracks.parquet (detections with fire id, look id), passes.parquet (satellite looks near Ratapani)."""
import pandas as pd, numpy as np, glob, json, sys
from pyproj import Transformer
from shapely.geometry import shape, Point
from shapely import contains_xy
from scipy.spatial import cKDTree
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components
D = sys.argv[1]; OUT = sys.argv[2]
TO = Transformer.from_crs(4326, 32643, always_xy=True)
aoi = shape(json.load(open('/mnt/project-files/ratapani/ratapani_aoi.geojson'))['features'][0]['geometry'])
A = pd.concat([pd.read_csv(f).assign(sat=f.split('/')[-1].split('_')[0]) for f in sorted(glob.glob(D + '/alerts/viirs-*.csv'))])
A['version'] = A.version.astype(str)
A['t'] = pd.to_datetime(A.acq_date) + pd.to_timedelta(A.acq_time // 100, 'h') + pd.to_timedelta(A.acq_time % 100, 'm')
A = A[contains_xy(aoi.buffer(0.01), A.longitude.values, A.latitude.values)]
A['season'] = A.t.dt.year
doy = A.t.dt.dayofyear
A = A[(A.t.dt.month >= 1) & (A.t.dt.month <= 6)].copy()
A['x'], A['y'] = TO.transform(A.longitude.values, A.latitude.values)
# look = local overpass slot: day (13:30 IST) or night (01:30 IST) of a given local date
loc = A.t + pd.Timedelta(hours=5.5)
A['look'] = np.where(A.daynight == 'D', loc.dt.strftime('%Y-%m-%d') + 'D', (loc - pd.Timedelta(hours=6)).dt.strftime('%Y-%m-%d') + 'N')
A = A.sort_values('t').reset_index(drop=True)
th = (A.t - A.t.min()).dt.total_seconds().values / 3600
P = np.c_[A.x, A.y, th * 40.0]   # 30 h == 1200 m
pr = cKDTree(P).query_pairs(1200 * np.sqrt(2), output_type='ndarray')
d = np.abs(P[pr[:, 0]] - P[pr[:, 1]])
pr = pr[(np.hypot(d[:, 0], d[:, 1]) <= 1200) & (d[:, 2] <= 1200)]
n = len(A); _, A['fire'] = connected_components(coo_matrix((np.ones(len(pr)), (pr[:, 0], pr[:, 1])), shape=(n, n)), directed=False)
A.to_parquet(OUT + '/tracks.parquet')
# satellite looks: any MP detection within ~300 km of Ratapani by that satellite in that slot
rows = []
for f in sorted(glob.glob('/mnt/project-files/fire-alert-scars/alerts_mp/viirs-*.csv')):
    m = pd.read_csv(f, usecols=['latitude', 'longitude', 'acq_date', 'acq_time', 'daynight', 'scan'])
    m = m[(abs(m.latitude - 22.95) < 2.5) & (abs(m.longitude - 77.7) < 2.5)]
    m['sat'] = f.split('/')[-1].split('_')[0]
    rows.append(m)
M = pd.concat(rows)
M['t'] = pd.to_datetime(M.acq_date) + pd.to_timedelta(M.acq_time // 100, 'h') + pd.to_timedelta(M.acq_time % 100, 'm')
loc = M.t + pd.Timedelta(hours=5.5)
M['look'] = np.where(M.daynight == 'D', loc.dt.strftime('%Y-%m-%d') + 'D', (loc - pd.Timedelta(hours=6)).dt.strftime('%Y-%m-%d') + 'N')
# pass time near Ratapani: median time of detections within 1 deg
M['near'] = (abs(M.latitude - 22.95) < 1) & (abs(M.longitude - 77.7) < 1)
Pz = M.groupby(['sat', 'look']).agg(t=('t', 'median'), n=('t', 'size'), n_near=('near', 'sum')).reset_index()
Pz.to_parquet(OUT + '/passes.parquet')
print(len(A), 'detections in AOI Jan-Jun;', A.fire.nunique(), 'fires;', len(Pz), 'satellite looks')
