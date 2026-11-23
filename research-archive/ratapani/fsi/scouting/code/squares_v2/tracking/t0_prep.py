"""Tracking step 0: data tables for the multi-pass sub-square reconstruction.

Reads the FIRMS standard-processing (SP) archive for all MP (fire-alert-scars/alerts_mp: S-NPP, NOAA-20, NOAA-21 VIIRS and
Terra/Aqua MODIS). Every detection stays its own row with its own time and sensor; a "pass" is one satellite's overpass
(rows of one sensor less than 15 min apart). Nothing is merged across sensors or passes.

Outputs (scratch, TR_SCRATCH):
  det.parquet     every detection in the Ratapani box (+5 km) 2017-2026 with x, y (UTM 43N), scan_m, track_m, heading,
                  pass key, fire id (big-fires rule: inside scar + 200 m, day before first event to 2 days after last).
  passes.parquet  every overpass of every sensor that viewed Ratapani (detections within 250 km or on both sides), with
                  the local pixel size at Ratapani (scan_m, track_m) read from that pass's own detections nearest in
                  the along-scan direction (pixel size depends only on the along-scan position).
  static.parquet  FIRMS type 2 (static industrial) detections, all MP, for the geolocation calibration.
"""
import glob, os, pickle
import numpy as np, pandas as pd, pyproj
from shapely.geometry import Point
from shapely.strtree import STRtree
ROOT = '/mnt/project-files'
SC = os.environ.get('TR_SCRATCH', '/tmp/claude-0/-home-user/be9b8f54-cc26-52cb-bdbb-9c8008a24baf/scratchpad/r19_track')
R17 = '/tmp/claude-0/-home-user/be9b8f54-cc26-52cb-bdbb-9c8008a24baf/scratchpad/r17_exp_code'   # scars.pkl (round 17, same rule as big-fires b1)
tp = pyproj.Transformer.from_crs(4326, 32643, always_xy=True).transform
RX, RY = tp(77.7, 22.95)
SENS = {'viirs-snpp': 'S-NPP', 'viirs-jpss1': 'NOAA-20', 'viirs-noaa21': 'NOAA-21'}

def heading(sensor, dn):
    """Along-track heading (deg from north) at 23 N. VIIRS and Aqua: ascending by day (347), descending by night (193).
    Terra: descending by day, ascending by night. Measured from the pixel grid in round 17 (orient.py)."""
    terra = sensor == 'Terra MODIS'
    day = dn == 'D'
    return np.where(day ^ terra, 347.0, 193.0)

def axes(h):
    h = np.radians(np.asarray(h, float))
    return np.stack([np.cos(h), -np.sin(h)], -1), np.stack([np.sin(h), np.cos(h)], -1)   # along scan, along track

rows = []
for f in sorted(glob.glob(f'{ROOT}/fire-alert-scars/alerts_mp/*.csv')):
    b = os.path.basename(f); pre, yr = b[:-9], int(b[-8:-4])
    if yr < 2017: continue
    a = pd.read_csv(f)
    if pre == 'modis':
        a['sensor'] = a.satellite.astype(str) + ' MODIS'; a = a.rename(columns={'brightness': 'bt4', 'bright_t31': 'bt5'})
    else:
        a['sensor'] = SENS[pre]; a = a.rename(columns={'bright_ti4': 'bt4', 'bright_ti5': 'bt5'})
    a['confidence'] = a.confidence.astype(str); a['version'] = a.version.astype(str)
    rows.append(a[['latitude', 'longitude', 'bt4', 'bt5', 'scan', 'track', 'acq_date', 'acq_time', 'confidence', 'frp', 'daynight', 'type', 'sensor', 'version']])
A = pd.concat(rows, ignore_index=True)
A['t'] = pd.to_datetime(A.acq_date) + pd.to_timedelta(A.acq_time // 100, 'h') + pd.to_timedelta(A.acq_time % 100, 'min')
A['x'], A['y'] = tp(A.longitude.values, A.latitude.values)
A['scan_m'] = A.scan * 1000; A['track_m'] = A.track * 1000
A['kind'] = np.where(A.sensor.str.contains('MODIS'), 'modis', 'viirs')
A['heading'] = heading(A.sensor.values, A.daynight.values)
A = A.sort_values(['sensor', 't']).reset_index(drop=True)
A['pass_key'] = A.sensor + '|' + ((A.groupby('sensor').t.diff().dt.total_seconds().fillna(1e9) > 900).groupby(A.sensor).cumsum()).astype(str)
print(len(A), 'MP detections 2017-2026')
A[A.type == 2][['sensor', 'kind', 't', 'x', 'y', 'scan_m', 'track_m', 'heading', 'daynight', 'frp', 'bt4', 'pass_key']].to_parquet(f'{SC}/static.parquet')

# ---- passes that viewed Ratapani, with the local pixel size there
P = []
for pk, g in A.groupby('pass_key', sort=False):
    us, ut = axes(g.heading.iloc[0])
    ds = (g.x.values - RX) * us[0] + (g.y.values - RY) * us[1]       # along-scan offset from Ratapani (m)
    dt = (g.x.values - RX) * ut[0] + (g.y.values - RY) * ut[1]
    ok = np.abs(dt) < 400e3
    if not ok.any(): continue
    near = np.hypot(ds, dt) < 250e3
    both = (ds[ok] < 0).any() and (ds[ok] > 0).any()
    if not (near.any() or both): continue
    o = np.argsort(np.abs(ds[ok]))[:10]
    P.append(dict(pass_key=pk, sensor=g.sensor.iloc[0], kind=g.kind.iloc[0], t=g.t.median(), daynight=g.daynight.iloc[0],
                  heading=g.heading.iloc[0], scan_m=float(np.median(g.scan_m.values[ok][o])), track_m=float(np.median(g.track_m.values[ok][o])),
                  scan_gap_km=float(np.abs(ds[ok][o[0]]) / 1e3), n_mp=len(g)))
P = pd.DataFrame(P); P.to_parquet(f'{SC}/passes.parquet'); print(len(P), 'viewing passes', P.groupby('sensor').size().to_dict())

# ---- Ratapani box detections + fire assignment (big-fires b1 rule)
B = A[A.latitude.between(22.73, 23.20) & A.longitude.between(77.25, 78.16)].copy()
B = B[(B.t.dt.month <= 6)]
S = pickle.load(open(f'{R17}/scars.pkl', 'rb'))
F = pd.read_csv(f'{ROOT}/research/big-fires/results/fires.csv', parse_dates=['date0', 'date1'])
B['date'] = B.t.dt.normalize(); B = B.reset_index(drop=True); B['fire'] = -1
tree = STRtree([Point(a, b) for a, b in zip(B.x, B.y)])
for r in F.itertuples():
    idx = tree.query(S[r.fire].buffer(200), predicate='contains')
    sub = B.iloc[idx]; ok = (sub.date >= r.date0 - pd.Timedelta(days=1)) & (sub.date <= r.date1 + pd.Timedelta(days=2)) & (sub.type.fillna(0) != 2)
    B.loc[sub.index[ok & (B.loc[sub.index, 'fire'] < 0)], 'fire'] = r.fire
B.drop(columns=['acq_date', 'acq_time']).to_parquet(f'{SC}/det.parquet')
print(len(B), 'box detections;', (B.fire >= 0).sum(), 'on fires', B[B.fire >= 0].groupby('sensor').size().to_dict())
