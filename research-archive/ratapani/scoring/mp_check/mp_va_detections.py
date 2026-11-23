"""Oblique-pass check, step 1 (Akkshay 17 Oct 08:55Z "do it", heat-thread hand-off): per VIIRS detection (3 satellites, type 0,
2019-24 + Oct-Dec before each test season) the view angle (h13_view_angle.view_zenith from FIRMS track) and Hansen GFC 2000
tree cover around the pixel (~390 m box). Hansen tiles live outside the shared folder (HANSEN dir, ~320 MB).
Out: $VA_OUT/va_det.parquet (big scratch, not in the shared folder)."""
import os, numpy as np, pandas as pd, rasterio
from rasterio.windows import from_bounds
from rasterio.enums import Resampling
from scipy.ndimage import uniform_filter
H = os.environ.get('HANSEN', '/tmp/claude-0/hansen'); OUT = os.environ.get('VA_OUT', '/tmp/claude-0/va')
P = '/mnt/project-files/'
RE, HS = 6371.0, 829.0
def view_zenith(track_m):   # copied from research/fuel-from-heat/scripts/h13_view_angle.py
    R = HS * np.clip(np.asarray(track_m, float) / 375.0, 1, None)
    ca = ((RE + HS) ** 2 + R ** 2 - RE ** 2) / (2 * R * (RE + HS))
    a = np.arccos(np.clip(ca, -1, 1))
    return np.degrees(np.arcsin(np.clip((RE + HS) / RE * np.sin(a), 0, 1)))
fs = []
for y in range(2019, 2025):
    for sat in ('snpp', 'jpss1', 'noaa21'):
        f = P + f'fire-alert-scars/alerts_mp/viirs-{sat}_{y}.csv'
        if os.path.exists(f):
            d = pd.read_csv(f, usecols=['latitude', 'longitude', 'track', 'scan', 'acq_date', 'acq_time', 'type', 'daynight', 'frp']); d['sat'] = sat; fs.append(d)
v = pd.concat(fs, ignore_index=True); v = v[v.type == 0].reset_index(drop=True)
v['theta'] = view_zenith(v.track * 1000)
D = 0.00125   # 5 Hansen pixels; 3x3 of these ~ 390 m
lat0, lat1, lon0, lon1 = 21.0, 27.0, 74.0, 83.0
NR, NC = int(round((lat1 - lat0) / D)), int(round((lon1 - lon0) / D)); TC = np.full((NR, NC), np.nan, np.float32)
for t, (a, b) in (('30N_070E', (74.0, 80.0)), ('30N_080E', (80.0, 83.0))):
    with rasterio.open(f'{H}/tc_{t}.tif') as r:
        w = from_bounds(a, lat0, b, lat1, r.transform); nc = int(round((b - a) / D))
        TC[:, int(round((a - lon0) / D)):int(round((a - lon0) / D)) + nc] = r.read(1, window=w, out_shape=(NR, nc), resampling=Resampling.average)
TC = uniform_filter(TC, 3, mode='nearest')
i = np.clip(((lat1 - v.latitude) / D).astype(int), 0, NR - 1); j = np.clip(((v.longitude - lon0) / D).astype(int), 0, NC - 1)
v['tc'] = TC[i, j]
v.drop(columns='type').to_parquet(f'{OUT}/va_det.parquet')
print(len(v), v.groupby('sat').size().to_dict()); print('theta q', v.theta.quantile([.05, .25, .5, .75, .95]).round(1).tolist())
print('tree cover q', v.tc.quantile([.25, .5, .75, .9, .95]).round(1).tolist(), 'share tc>=50', round((v.tc >= 50).mean(), 3), '>=60', round((v.tc >= 60).mean(), 3))
