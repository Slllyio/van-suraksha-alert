import pandas as pd, numpy as np, json, glob
from pyproj import Transformer
from scipy.spatial import cKDTree
A = pd.concat([pd.read_csv(f) for f in glob.glob('/mnt/project-files/fire-alert-scars/alerts/viirs-*.csv')])
A['utc'] = pd.to_datetime(A.acq_date + ' ' + A.acq_time.astype(float).astype(int).astype(str).str.zfill(4), format='%Y-%m-%d %H%M'); A['ist'] = A.utc + pd.Timedelta(hours=5.5)
t = Transformer.from_crs(4326, 32643, always_xy=True).transform; A['x'], A['y'] = t(A.longitude.values, A.latitude.values)
G = json.load(open('/mnt/project-files/ratapani/grid_500m.geojson'))['features']
cx = {f['properties']['cell_id']: (f['properties']['x0'] + 250, f['properties']['y0'] + 250) for f in G}
D = pd.read_csv('/mnt/project-files/fire-alert-scars/out/af/dated_first_burns.csv'); D = D[D.source == 'viirs'].copy(); D['fire_day'] = pd.to_datetime(D.fire_day)
print('viirs-dated cells', len(D), D.conf.value_counts().to_dict())
tr = cKDTree(A[['x', 'y']].values); res = []
for r in D.itertuples():
    x, y = cx[r.cell_id]; idx = tr.query_ball_point((x, y), 750)
    if not idx: continue
    s = A.iloc[idx]; s = s[(s.ist >= r.fire_day - pd.Timedelta(days=2)) & (s.ist < r.fire_day + pd.Timedelta(days=3))]
    if not len(s): continue
    f = s.sort_values('utc').iloc[0]; res.append((r.season, r.cell_id, r.conf, r.fire_day, f.utc, f.ist, f.daynight))
R = pd.DataFrame(res, columns=['season', 'cell', 'conf', 'fire_day', 'utc', 'ist', 'dn'])
R['eq_utc'] = R.utc.dt.normalize() == R.fire_day; R['eq_ist'] = R.ist.dt.normalize() == R.fire_day; R['ist_h'] = R.ist.dt.hour
print(len(R), 'fire_day = UTC date of first det', R.eq_utc.mean().round(3), '= IST date', R.eq_ist.mean().round(3))
print('first detection is a night pass', (R.dn == 'N').mean().round(3), '| high conf', (R[R.conf == 'high'].dn == 'N').mean().round(3))
print(R.groupby('dn').ist_h.median())
late = (R.dn == 'N') & (R.ist_h < 12) & R.eq_ist
print('after-midnight night first detections labelled on their IST date (ignition likely previous afternoon):', late.mean().round(3))
N = R[(R.dn == 'N') & (R.ist_h < 12)]
print('night after-midnight firsts', len(N), 'label = UTC date (prev IST day)', N.eq_utc.mean().round(3), '| = IST date', N.eq_ist.mean().round(3))
