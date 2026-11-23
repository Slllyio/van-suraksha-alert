"""Step 1: all-MP VIIRS points on forest-department land (inside MP beats, from mp_types/out/viirs_vtm.parquet, type 0),
15 Feb-15 Jun 2017-2026, joined to the FIRMS SP archive rows for scan/track/brightness, plus pass id, local metres,
DEM terrain, and MODIS points (Terra/Aqua) in the MP box. Out (scratch r21_big): pts.parquet, modis.parquet"""
import glob, os, sys
import numpy as np, pandas as pd
sys.path.insert(0, '/mnt/project-files/ratapani/fsi/scouting/code/squares_v2/pooled')
ROOT = '/mnt/project-files'; AM = f'{ROOT}/fire-alert-scars/alerts_mp'
SC = '/tmp/claude-0/-home-user/be9b8f54-cc26-52cb-bdbb-9c8008a24baf/scratchpad/r21_big'
V = pd.read_parquet(f'{ROOT}/ratapani/fsi/scouting/code/mp_types/out/viirs_vtm.parquet')
V = V[V.season.between(2017, 2026)]
md = V.t_ist.dt.month * 100 + V.t_ist.dt.day
V = V[(md >= 215) & (md <= 615)].copy()
SATMAP = {'snpp': 'S-NPP', 'jpss1': 'NOAA-20', 'noaa21': 'NOAA-21'}
V['sensor'] = V.sat.map(SATMAP)
raw = []
for f in sorted(glob.glob(f'{AM}/viirs-*.csv')):
    yr = int(f[-8:-4])
    if yr < 2017: continue
    a = pd.read_csv(f, usecols=['latitude', 'longitude', 'bright_ti4', 'scan', 'track', 'acq_date', 'acq_time', 'satellite', 'type'])
    a = a[a.type == 0]
    a['sensor'] = a.satellite.astype(str).map({'N': 'S-NPP', '1': 'NOAA-20', 'N20': 'NOAA-20', 'N21': 'NOAA-21'})
    raw.append(a.drop(columns=['satellite', 'type']))
R = pd.concat(raw, ignore_index=True)
for d in (V, R):
    d['k'] = (d.latitude.round(4).astype(str) + '_' + d.longitude.round(4).astype(str) + '_' + d.acq_date.astype(str) + '_'
              + d.acq_time.astype(int).astype(str) + '_' + d.sensor)
R = R.drop_duplicates('k')
V = V.merge(R[['k', 'bright_ti4', 'scan', 'track']], on='k', how='left')
print('points', len(V), 'matched to SP rows', round(V.scan.notna().mean(), 4))
V['scan'] = V.scan.fillna(0.45); V['track'] = V.track.fillna(0.45)
V['t'] = V.t_ist  # IST throughout
V = V.sort_values(['sensor', 't']).reset_index(drop=True)
V['pass_id'] = (V.groupby('sensor').t.diff().dt.total_seconds().fillna(1e9) > 600).cumsum().astype(np.int32)
V['pass_id'] = pd.factorize(V.sensor + '_' + V.pass_id.astype(str))[0]
V['x'] = (V.longitude - 78.0) * 111320.0 * np.cos(np.radians(23.5)); V['y'] = (V.latitude - 23.5) * 110574.0
from p_dem import sample
import p_dem; p_dem.SC = '/tmp/claude-0/-home-user/be9b8f54-cc26-52cb-bdbb-9c8008a24baf/scratchpad/r19_pool'
e, s, u = sample(V.latitude.values, V.longitude.values)
V['elev'], V['slope'] = e, s
keep = ['sensor', 'pass_id', 't', 'latitude', 'longitude', 'x', 'y', 'scan', 'track', 'bright_ti4', 'frp', 'daynight', 'season',
        'vtm', 'vtm_name', 'Division', 'beat_uid', 'elev', 'slope', 'acq_date', 'acq_time']
V[keep].to_parquet(f'{SC}/pts.parquet')
print(V.groupby(['season', 'sensor']).size().unstack())
# MODIS (Terra/Aqua), MP box, type 0, 2017-2026, Feb-Jun
M = []
for f in sorted(glob.glob(f'{AM}/modis_*.csv')):
    yr = int(f[-8:-4])
    if yr < 2017: continue
    a = pd.read_csv(f, usecols=['latitude', 'longitude', 'acq_date', 'acq_time', 'satellite', 'frp', 'daynight', 'type'])
    M.append(a[a.type == 0])
M = pd.concat(M, ignore_index=True)
M['t'] = pd.to_datetime(M.acq_date) + pd.to_timedelta(M.acq_time // 100, 'h') + pd.to_timedelta(M.acq_time % 100 + 330, 'min')
M = M[M.t.dt.month.between(2, 6)]
M['x'] = (M.longitude - 78.0) * 111320.0 * np.cos(np.radians(23.5)); M['y'] = (M.latitude - 23.5) * 110574.0
M[['satellite', 't', 'x', 'y', 'frp', 'daynight']].to_parquet(f'{SC}/modis.parquet')
print('modis', len(M), M.satellite.value_counts().to_dict())
