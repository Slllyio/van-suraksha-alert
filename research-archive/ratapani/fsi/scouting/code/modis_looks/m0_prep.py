"""Load all-MP FIRMS points (VIIRS S-NPP/NOAA-20/NOAA-21 and Terra/Aqua MODIS SP, type 0, Jan-Jun) into two parquets
in the scratch folder (ML_SCRATCH). Adds t (UTC), x/y (UTM 43N, m), season, sensor, look/pass ids.
VIIRS look = all VIIRS points of a season within 2 h gaps (MP-wide schedule); MODIS pass = one satellite within 15 min."""
import glob, os, numpy as np, pandas as pd, pyproj
ROOT = '/mnt/project-files/fire-alert-scars/alerts_mp'; S = os.environ['ML_SCRATCH']
tr = pyproj.Transformer.from_crs(4326, 32643, always_xy=True)
def load(pat, sensor_of):
    out = []
    for f in sorted(glob.glob(f'{ROOT}/{pat}')):
        d = pd.read_csv(f, dtype={'acq_time': int, 'confidence': str})
        d = d[d.type.fillna(0) == 0]
        d['sensor'] = sensor_of(f, d)
        out.append(d)
    d = pd.concat(out, ignore_index=True)
    d['t'] = pd.to_datetime(d.acq_date) + pd.to_timedelta(d.acq_time // 100, 'h') + pd.to_timedelta(d.acq_time % 100, 'min')
    d = d[(d.t + pd.Timedelta(hours=5.5)).dt.month <= 6]
    d['season'] = d.t.dt.year
    d['x'], d['y'] = tr.transform(d.longitude.values, d.latitude.values)
    d['ist_h'] = ((d.t.dt.hour + d.t.dt.minute / 60 + 5.5) % 24).round(2)
    return d.sort_values('t').reset_index(drop=True)
V = load('viirs-*.csv', lambda f, d: os.path.basename(f).split('_')[0])
V = V[['t', 'season', 'x', 'y', 'latitude', 'longitude', 'frp', 'scan', 'track', 'daynight', 'sensor', 'ist_h']]
V['look'] = V.groupby('season').t.transform(lambda s: (s.diff().dt.total_seconds().fillna(1e9) > 7200).cumsum())
V['look'] = V.season * 10000 + V.look
M = load('modis_*.csv', lambda f, d: d.satellite.values)
M = M[['t', 'season', 'x', 'y', 'latitude', 'longitude', 'frp', 'scan', 'track', 'daynight', 'sensor', 'ist_h', 'confidence']]
M['pass'] = M.groupby(['season', 'sensor']).t.transform(lambda s: (s.diff().dt.total_seconds().fillna(1e9) > 900).cumsum())
M['pass'] = M.season * 100000 + (M.sensor == 'Terra') * 50000 + M['pass']
V.to_parquet(f'{S}/viirs_mp.parquet'); M.to_parquet(f'{S}/modis_mp.parquet')
print(len(V), 'VIIRS', V.sensor.value_counts().to_dict(), V.look.nunique(), 'looks')
print(len(M), 'MODIS', M.groupby(['sensor', 'daynight']).ist_h.agg(['size', 'median']))
lk = V.groupby('look').agg(t=('t', 'min'), h=('ist_h', 'median'))
print('VIIRS look IST hour quantiles', lk.h.quantile([.05, .25, .5, .75, .95]).to_dict())
