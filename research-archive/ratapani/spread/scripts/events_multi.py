"""Group active-fire detections from all sensors (VIIRS S-NPP, NOAA-20, NOAA-21; MODIS Terra/Aqua) into fire events:
single-linkage within 1.2 km and 30 h, as events.py does for S-NPP alone. Files: FIRMS CSV exports pulled by the burn
scar thread (/mnt/project-files/fire-alert-scars/alerts/). Usage: events_multi.py out.parquet [sensors]
sensors: comma list of viirs-snpp, viirs-jpss1, viirs-noaa21, modis (default all)."""
import numpy as np, pandas as pd, sys, glob, os
from pyproj import Transformer
from scipy.sparse.csgraph import connected_components
from scipy.sparse import coo_matrix
from scipy.spatial import cKDTree
A = '/mnt/project-files/fire-alert-scars/alerts'
sensors = sys.argv[2].split(',') if len(sys.argv) > 2 else ['viirs-snpp', 'viirs-jpss1', 'viirs-noaa21', 'modis']
parts = []
for s in sensors:
    for f in sorted(glob.glob(f'{A}/{s}_20*.csv')):
        yr = int(f[-8:-4])
        y0, y1 = (int(x) for x in os.environ.get('YEARS', '2017-2024').split('-'))     # forward test: YEARS=2025-2026
        if yr < y0 or yr > y1:
            continue
        d = pd.read_csv(f, dtype={'acq_time': float, 'confidence': str}, low_memory=False)
        d = d[d.acq_time.notna() & d.satellite.notna()].copy(); d['acq_time'] = d.acq_time.astype(int)   # 2026 NRT files: MODIS rows carry no time or satellite
        if not len(d):
            continue
        if s == 'modis':
            d = d[(pd.to_numeric(d.confidence, errors='coerce') >= 30) & (d.scan <= 2.0)]   # pixel <= ~2 km
        else:
            d = d[d.confidence != 'l']
        d['sensor'] = s; parts.append(d)
v = pd.concat(parts, ignore_index=True)
v['t'] = pd.to_datetime(v.acq_date.astype(str)) + pd.to_timedelta(v.acq_time // 100, 'h') + pd.to_timedelta(v.acq_time % 100, 'm')
v['year'], v['month'] = v.t.dt.year, v.t.dt.month
v = v[(v.year >= 2017) & (v.month <= 6)].copy()
# keep the sanctuary: the FIRMS exports cover a wider box than the burn labels and the S-NPP parquet
import geopandas as gpd
from shapely.geometry import Point
aoi = gpd.read_file('/mnt/project-files/ratapani/ratapani_aoi.geojson').to_crs(4326).union_all()
v = v[[aoi.contains(Point(lo, la)) for lo, la in zip(v.longitude, v.latitude)]].copy()
x, y = Transformer.from_crs(4326, 32643, always_xy=True).transform(v.longitude.values, v.latitude.values)
v['x'], v['y'] = x, y
v['season'] = np.where(v.month >= 12, v.year + 1, v.year)
v = v.sort_values('t').reset_index(drop=True)
th = (v.t - v.t.min()).dt.total_seconds().values / 3600
P = np.c_[v.x, v.y, th * 40.0]
tree = cKDTree(P); pairs = tree.query_pairs(1200 * np.sqrt(2), output_type='ndarray')
d = np.abs(P[pairs[:, 0]] - P[pairs[:, 1]])
ok = (np.hypot(d[:, 0], d[:, 1]) <= 1200) & (d[:, 2] <= 1200)
pairs = pairs[ok]
n = len(v); M = coo_matrix((np.ones(len(pairs)), (pairs[:, 0], pairs[:, 1])), shape=(n, n))
_, lab = connected_components(M, directed=False); v['event'] = lab + int(os.environ.get('EVENT_OFFSET', 0))   # offset keeps forward-test ids apart
v['overpass'] = v.t.dt.floor('h')     # S-NPP and Aqua share the 13:30/01:30 orbit; NOAA-20/21 and Terra are their own passes
g = v.groupby('event').agg(n=('x', 'size'), n_pass=('overpass', 'nunique'), t0=('t', 'min'), t1=('t', 'max'))
g['hours'] = (g.t1 - g.t0).dt.total_seconds() / 3600
print(sensors, len(v), 'detections', v.sensor.value_counts().to_dict(), len(g), 'events')
print('events with >=2 overpasses:', (g.n_pass >= 2).sum(), ' >=3:', (g.n_pass >= 3).sum(), ' spanning >=20h:', (g.hours >= 20).sum())
v[['latitude', 'longitude', 'x', 'y', 't', 'year', 'month', 'season', 'sensor', 'satellite', 'confidence', 'frp', 'daynight', 'event', 'overpass']].to_parquet(sys.argv[1])
