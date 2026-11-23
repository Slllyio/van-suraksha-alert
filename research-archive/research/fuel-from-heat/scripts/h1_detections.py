"""Step 1: every VIIRS detection in Ratapani with all its FIRMS fields, tied to the big-fires fire id and pass id.
Each satellite pass stays separate (S-NPP, NOAA-20, NOAA-21 are never merged).
Out: results/viirs_det.csv
"""
import glob, os
import numpy as np, pandas as pd, pyproj
from h0_lib import ROOT, RES, BF

tp = pyproj.Transformer.from_crs(4326, 32643, always_xy=True).transform
SAT = {'viirs-snpp': 'S-NPP', 'viirs-jpss1': 'NOAA-20', 'viirs-noaa21': 'NOAA-21'}
v = pd.concat([pd.read_csv(f).assign(sensor=SAT[os.path.basename(f).rsplit('_', 1)[0]])
               for f in glob.glob(f'{ROOT}/fire-alert-scars/alerts/viirs-*.csv')], ignore_index=True)
v = v.dropna(subset=['acq_time'])
v['t'] = pd.to_datetime(v.acq_date) + pd.to_timedelta(v.acq_time.astype(int) // 100, 'h') + pd.to_timedelta(v.acq_time.astype(int) % 100, 'min')
v['x'], v['y'] = tp(v.longitude.values, v.latitude.values)
d = pd.read_csv(f'{BF}/detections.csv', parse_dates=['t'])
d = d[d.sensor.isin(SAT.values())]
key = lambda df, a, b: df.sensor + '|' + df.t.dt.strftime('%Y%m%d%H%M') + '|' + df[a].round(4).astype(str) + '|' + df[b].round(4).astype(str)
v['k'] = key(v, 'latitude', 'longitude'); d['k'] = key(d, 'lat', 'lon')
d = d.drop_duplicates('k')
m = v.merge(d[['k', 'fire', 'pass_id']], on='k', how='left')
print('VIIRS alerts', len(v), '| tied to a fire', m.fire.notna().sum(), 'of', len(d), 'big-fires detections')
m['scan_m'] = m.scan.fillna(0.375) * 1000; m['track_m'] = m.track.fillna(0.375) * 1000
m['sat_i4'] = m.bright_ti4 >= 366.9
cols = ['fire', 'pass_id', 'sensor', 't', 'x', 'y', 'latitude', 'longitude', 'frp', 'bright_ti4', 'bright_ti5', 'confidence',
        'daynight', 'scan_m', 'track_m', 'sat_i4']
m[cols].sort_values(['t', 'x']).to_csv(f'{RES}/viirs_det.csv', index=False)
print(m.groupby('sensor').agg(n=('frp', 'size'), frp_med=('frp', 'median'), i4_sat=('sat_i4', 'mean'), in_fire=('fire', lambda s: s.notna().mean())).round(3))
