"""Pick the chips. Test sets are chosen first; training chips must sit >= 3 km or >= 45 days from every test chip.
Season = 15 Feb - 15 Jun (day 46-166), 2019-2025. Out: chips.csv (one row per chip)."""
import json, numpy as np, pandas as pd, geopandas as gpd, glob, os
from shapely.geometry import Point, shape
from pyproj import Transformer
from lib import CODE
R = '/mnt/project-files/fire-alert-scars/'
TO = Transformer.from_crs(4326, 32643, always_xy=True); BK = Transformer.from_crs(32643, 4326, always_xy=True)
rng = np.random.default_rng(16)
inseason = lambda d: (d.dt.year >= 2019) & (d.dt.year <= 2025) & (d.dt.dayofyear >= 46) & (d.dt.dayofyear <= 166)

# all raw FIRMS alerts (for "no alert nearby" tests)
al = []
for f in glob.glob(R + 'alerts/*.csv'):
    if 'latitude' not in open(f).readline(): continue
    a = pd.read_csv(f, usecols=['latitude', 'longitude', 'acq_date']); a['sensor'] = os.path.basename(f).split('_')[0]; al.append(a)
AL = pd.concat(al); AL['d'] = pd.to_datetime(AL.acq_date); AL['x'], AL['y'] = TO.transform(AL.longitude.values, AL.latitude.values)
def no_alert(x, y, d, km, days):
    s = AL[(AL.d - d).abs() <= pd.Timedelta(days=days)]
    return not len(s) or np.hypot(s.x - x, s.y - y).min() >= km * 1000
grid = gpd.read_file('/mnt/project-files/ratapani/grid_500m.geojson').to_crs(32643)
forest = grid[grid.forest_frac >= 0.7].union_all()
rows = []

# Wayback real outlines (alert point, FIRMS, image <= 20 days after)
M = pd.read_csv(R + 'wayback/matches.csv'); M['dd'] = pd.to_datetime(M.d)
M = M[(M.src == 'firms') & inseason(M.dd) & (M.age <= 20)].drop_duplicates('event_id').reset_index(drop=True)
for r in M.itertuples():
    x, y = TO.transform(r.lon, r.lat)
    rows.append(dict(kind='wb_real', key=r.event_id, x=x, y=y, date=r.d, half=1500, release=r.release, zoom=int(min(r.MaxMapLevel, 18)),
                     img=r.img, age=r.age, status=r.status))
# Wayback decoys: 3 km away, in forest, no alert within 1.5 km / 30 days, on the same Wayback image (as wayback/sample.py)
F = gpd.read_file(R + 'wayback/footprints_clip.geojson')
nd = 0
for r in M.sample(frac=1, random_state=4).itertuples():
    if nd >= 160: break
    x, y = TO.transform(r.lon, r.lat); d = pd.Timestamp(r.d)
    fp = F[(F.release == r.release) & (F.layer == r.layer) & (pd.to_datetime(F.SRC_DATE.astype(str), format='%Y%m%d') == pd.Timestamp(r.img))]
    if not len(fp): continue
    got = []
    for _ in range(120):
        if len(got) >= 2: break
        th = rng.uniform(0, 2 * np.pi); dist = rng.uniform(3000, 5000); nx, ny = x + dist * np.cos(th), y + dist * np.sin(th)
        if any(np.hypot(nx - gx, ny - gy) < 2000 for gx, gy in got): continue
        lo, la = BK.transform(nx, ny)
        if forest.contains(Point(nx, ny)) and fp.geometry.iloc[0].contains(Point(lo, la)) and no_alert(nx, ny, d, 1.5, 30):
            got.append((nx, ny))
            rows.append(dict(kind='wb_decoy', key=f'D{len(got)}_{r.event_id}', x=nx, y=ny, date=r.d, half=1500, release=r.release,
                             zoom=int(min(r.MaxMapLevel, 18)), img=r.img, age=r.age, status='decoy')); nd += 1

# Sentinel-2 / Landsat fire-pixel clusters (independent of VIIRS and of the NBR rule); >= 2 pixels
af = pd.read_csv(R + 'out/af/af_pixels_clean.csv'); af['dd'] = pd.to_datetime(af.date)
af = af[inseason(af.dd)]
cl = af.groupby(['season', 'cluster', 'date']).agg(n=('row', 'size'), lon=('lon', 'mean'), lat=('lat', 'mean'),
                                                   firms=('firms_nearby', 'max'), scene=('scene', 'first')).reset_index()
cl = cl[cl.n >= 2]
for fl, k in ((False, 90), (True, 90)):
    s = cl[cl.firms == fl].sample(min(k, (cl.firms == fl).sum()), random_state=5)
    for r in s.itertuples():
        x, y = TO.transform(r.lon, r.lat)
        rows.append(dict(kind='af_firms' if fl else 'af_nofirms', key=f'{r.season}_{r.cluster}_{r.date}', x=x, y=y, date=r.date, half=1500,
                         scene_date=r.date, n_af=r.n))

# Mid-fire photos (fuel thread chips), 2019-2024 in season
ms = pd.read_parquet('/mnt/project-files/fuel-map/ratapani/timing/midscar.parquet'); ms = ms[ms.status == 'ok']
ms['TT'] = pd.to_datetime(ms['T']); ms = ms[inseason(ms.TT)]
import rasterio
with rasterio.open('/mnt/project-files/research/ratapani-burn-labels/rasters/burn_2017.tif') as s: TRB = s.transform
TD = '/mnt/project-files/fuel-map/ratapani/timing/chips/'
for r in ms.sample(min(len(ms), 180), random_state=6).itertuples():
    f = f'{TD}{r.event}_{r.scene[:40]}.npz'
    if not os.path.exists(f): continue
    z = np.load(f); S = z['S']; i0, j0 = int(z['i0']), int(z['j0']); h, w = S.shape
    xa, ya = TRB * (j0, i0); xb, yb = TRB * (j0 + w, i0 + h)
    half = max(1500, max(xb - xa, ya - yb) / 2 + 400)
    if half > 4000: continue
    rows.append(dict(kind='photo', key=f'{r.event}_{r.scene[:40]}', x=(xa + xb) / 2, y=(ya + yb) / 2, date=r.TT.strftime('%Y-%m-%d'), half=half,
                     scene_date=r.TT.strftime('%Y-%m-%d'), T=str(r.TT)))
test = pd.DataFrame(rows); test['dd'] = pd.to_datetime(test.date)

# training: FIRMS events with a VIIRS alert, plus control points
L = pd.read_csv(R + 'reference/v2_2026-10-16/firms_alert_scar_lookup.csv'); L['dd'] = pd.to_datetime(L.acq_date)
L = L[inseason(L.dd) & L.sensor.str.startswith('viirs')].sort_values(['event_id', 'acq_date', 'acq_time']).drop_duplicates('event_id')
L['x'], L['y'] = TO.transform(L.longitude.values, L.latitude.values)
def far_from_test(x, y, d):
    s = test[(test.dd - d).abs() <= pd.Timedelta(days=45)]
    return not len(s) or np.hypot(s.x - x, s.y - y).min() >= 3000
tr = []
for r in L.sample(frac=1, random_state=7).itertuples():
    if len(tr) >= 330: break
    if far_from_test(r.x, r.y, r.dd):
        tr.append(dict(kind='train_alert', key=r.event_id, x=r.x, y=r.y, date=r.acq_date, half=1500, status=r.scar_status))
nc = 0
for r in pd.DataFrame(tr).sample(frac=1, random_state=8).itertuples():
    if nc >= 130: break
    d = pd.Timestamp(r.date)
    for _ in range(30):
        th = rng.uniform(0, 2 * np.pi); nx, ny = r.x + 3000 * np.cos(th), r.y + 3000 * np.sin(th)
        if forest.contains(Point(nx, ny)) and no_alert(nx, ny, d, 1.5, 15) and far_from_test(nx, ny, d):
            tr.append(dict(kind='train_control', key=f'C_{r.key}', x=nx, y=ny, date=r.date, half=1500)); nc += 1; break
out = pd.concat([test.drop(columns='dd'), pd.DataFrame(tr)], ignore_index=True)
out['chip'] = [f'c{i:04d}' for i in range(len(out))]
out.to_csv(CODE + 'chips.csv', index=False)
print(out.kind.value_counts())
