"""Step 0 (pooled small-gap analysis): every VIIRS (S-NPP, NOAA-20, NOAA-21) and MODIS (Terra, Aqua) point of the
all-MP FIRMS SP archive, Jan-Jun 2018-2026, with its own time, pass id, footprint size, local metric coordinates and
forest type (Roy et al. 2015 VTM, 60 m). Nothing is merged: one row per sensor detection.
Out (scratch): pts.parquet
"""
import glob, os
import numpy as np, pandas as pd, rasterio, pyproj
ROOT = '/mnt/project-files'; AM = f'{ROOT}/fire-alert-scars/alerts_mp'
SC = os.environ.get('POOL_SCRATCH', '/tmp/claude-0/-home-user/be9b8f54-cc26-52cb-bdbb-9c8008a24baf/scratchpad/r19_pool')
VTM = os.environ.get('VTM_TIF', '/tmp/claude-0/-home-user/be9b8f54-cc26-52cb-bdbb-9c8008a24baf/scratchpad/r14_types_data/vtm.tif')
rows = []
for f in sorted(glob.glob(f'{AM}/viirs-*.csv')) + sorted(glob.glob(f'{AM}/modis_*.csv')):
    yr = int(f[-8:-4])
    if yr < 2018: continue
    a = pd.read_csv(f)
    if 'bright_ti4' not in a: a = a.rename(columns={'brightness': 'bright_ti4', 'bright_t31': 'bright_ti5'})
    a['confidence'] = a.confidence.astype(str)
    rows.append(a[['latitude', 'longitude', 'bright_ti4', 'bright_ti5', 'scan', 'track', 'acq_date', 'acq_time',
                   'satellite', 'confidence', 'frp', 'daynight', 'type']])
A = pd.concat(rows, ignore_index=True)
A['sensor'] = A.satellite.astype(str).map({'N': 'S-NPP', '1': 'NOAA-20', 'N20': 'NOAA-20', 'N21': 'NOAA-21', 'Terra': 'Terra', 'Aqua': 'Aqua'})
print(A.satellite.astype(str).value_counts().to_dict())
A = A.dropna(subset=['sensor'])
A['t'] = pd.to_datetime(A.acq_date) + pd.to_timedelta(A.acq_time // 100, 'h') + pd.to_timedelta(A.acq_time % 100, 'min')
A = A.sort_values(['sensor', 't']).reset_index(drop=True)
A['pass_id'] = (A.groupby('sensor').t.diff().dt.total_seconds().fillna(1e9) > 600).cumsum().astype(np.int32)
# local metric coordinates: equirectangular about 23.5 N; displacements are recomputed with each point's own cos(lat)
A['x'] = (A.longitude - 78.0) * 111320.0 * np.cos(np.radians(23.5)); A['y'] = (A.latitude - 23.5) * 110574.0
A['scan_m'] = A.scan * 1000; A['track_m'] = A.track * 1000
A['season'] = A.t.dt.year.astype(np.int16); A['month'] = A.t.dt.month.astype(np.int8)
A['ist_h'] = ((A.t.dt.hour + A.t.dt.minute / 60 + 5.5) % 24).astype(np.float32)
# forest type
tp = pyproj.Transformer.from_crs(4326, 32643, always_xy=True).transform
ux, uy = tp(A.longitude.values, A.latitude.values)
with rasterio.open(VTM) as r:
    A['vtm'] = np.array([v[0] for v in r.sample(zip(ux, uy))], dtype=np.int16)
A['ux'], A['uy'] = ux, uy
keep = ['sensor', 'pass_id', 't', 'latitude', 'longitude', 'x', 'y', 'ux', 'uy', 'scan_m', 'track_m', 'bright_ti4', 'bright_ti5',
        'frp', 'confidence', 'daynight', 'type', 'season', 'month', 'ist_h', 'vtm']
A[keep].to_parquet(f'{SC}/pts.parquet')
print(len(A), A.groupby(['sensor', 'type']).size().unstack().to_string())
