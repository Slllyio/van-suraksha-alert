"""Step 0: one table of every VIIRS / MODIS detection on a Ratapani fire, with all FIRMS fields, its true footprint
(scan x track, rotated to the satellite track) and its pass. Also the fire outlines (v2) and the photo list.
2017-2025: fire-alert-scars/alerts (FIRMS standard files). 2026: alerts_mp (FIRMS archive, true points with scan/track),
instead of the Earth Engine centroids, which lack scan/track.
Footprint orientation: track heading 347 deg (day, ascending) / 193 deg (night, descending) at 23 N, from orbit geometry,
confirmed by the pixel grid of adjacent detections (orient.py). Out (scratch): det.parquet, scars.pkl
"""
import glob, json, os, pickle, sys
import numpy as np, pandas as pd, pyproj
from shapely.geometry import shape, Point
from shapely.ops import transform, unary_union
from shapely.strtree import STRtree
ROOT = '/mnt/project-files'; SC = os.environ.get('SQ_SCRATCH', os.path.dirname(os.path.abspath(__file__)))
V2 = f'{ROOT}/fire-alert-scars/reference/v2_2026-10-16'
tp = pyproj.Transformer.from_crs(4326, 32643, always_xy=True).transform
d = json.load(open(f'{V2}/firms_event_scars.geojson'))
G = {f['properties']['event_id']: transform(tp, shape(f['geometry'])).buffer(0) for f in d['features']}
F = pd.read_csv(f'{ROOT}/research/big-fires/results/fires.csv', parse_dates=['date0', 'date1'])
S = {int(r.fire): unary_union([G[e] for e in r.events.split(';')]).buffer(0) for r in F.itertuples()}
pickle.dump(S, open(f'{SC}/scars.pkl', 'wb'))
rows = []
for f in sorted(glob.glob(f'{ROOT}/fire-alert-scars/alerts/*.csv')):
    sat = os.path.basename(f).rsplit('_', 1)[0]; yr = int(f[-8:-4])
    if yr == 2026 and sat != 'modis':
        f = f'{ROOT}/fire-alert-scars/alerts_mp/{os.path.basename(f)}'
    a = pd.read_csv(f)
    if yr == 2026 and sat != 'modis':
        a = a[a.latitude.between(22.78, 23.15) & a.longitude.between(77.30, 78.11)]
    a['sat'] = sat; rows.append(a)
A = pd.concat(rows, ignore_index=True).dropna(subset=['acq_time'])
A['kind'] = np.where(A.sat == 'modis', 'modis', 'viirs')
A['bt4'] = A.bright_ti4.fillna(A.brightness); A['bt5'] = A.bright_ti5.fillna(A.bright_t31)
A['t'] = pd.to_datetime(A.acq_date) + pd.to_timedelta(A.acq_time.astype(int) // 100, 'h') + pd.to_timedelta(A.acq_time.astype(int) % 100, 'min')
A['x'], A['y'] = tp(A.longitude.values, A.latitude.values)
A['scan_m'] = (A.scan.fillna(pd.Series(np.where(A.kind == 'modis', 1.0, .375), index=A.index)) * 1000)
A['track_m'] = (A.track.fillna(pd.Series(np.where(A.kind == 'modis', 1.0, .375), index=A.index)) * 1000)
A['heading'] = np.where(A.daynight == 'D', 347.0, 193.0)    # along-track direction (deg from north); MODIS Terra day is descending
A.loc[(A.sat == 'modis') & (A.satellite == 'Terra'), 'heading'] = np.where(A.loc[(A.sat == 'modis') & (A.satellite == 'Terra'), 'daynight'] == 'D', 193.0, 347.0)
A['sensor'] = A.sat.map({'viirs-snpp': 'S-NPP', 'viirs-jpss1': 'NOAA-20', 'viirs-noaa21': 'NOAA-21'}).fillna(A.satellite.astype(str) + ' MODIS')
A = A.sort_values(['sensor', 't']).reset_index(drop=True)
A['pass_id'] = (A.groupby('sensor').t.diff().dt.total_seconds().fillna(1e9) > 900).cumsum()
A['date'] = pd.to_datetime(A.acq_date)
# fire assignment (big-fires b1 rule: inside scar + 200 m, day before first event to 2 days after last)
tree = STRtree([Point(a, b) for a, b in zip(A.x, A.y)]); A['fire'] = -1
for r in F.itertuples():
    idx = tree.query(S[r.fire].buffer(200), predicate='contains')
    sub = A.iloc[idx]; ok = (sub.date >= r.date0 - pd.Timedelta(days=1)) & (sub.date <= r.date1 + pd.Timedelta(days=2))
    A.loc[sub.index[ok & (A.loc[sub.index, 'fire'] < 0)], 'fire'] = r.fire
keep = ['sensor', 'kind', 't', 'x', 'y', 'latitude', 'longitude', 'bt4', 'bt5', 'frp', 'confidence', 'daynight', 'type',
        'scan_m', 'track_m', 'heading', 'pass_id', 'fire', 'version']
A['confidence'] = A.confidence.astype(str); A['version'] = A.version.astype(str)
A[keep].to_parquet(f'{SC}/det_all.parquet')
print(len(A), 'detections in box;', (A.fire >= 0).sum(), 'on fires;', A[A.fire >= 0].groupby('sensor').size().to_dict())
