"""Append training chips around Sentinel-2/Landsat fire-pixel clusters (2019-2025 season, >= 2 pixels), >= 3 km or >= 45 days
from every test chip and not already a test cluster. Their fire pixels are labels that do not come from the NBR rule."""
import numpy as np, pandas as pd
from pyproj import Transformer
from lib import CODE
TO = Transformer.from_crs(4326, 32643, always_xy=True)
C = pd.read_csv(CODE + 'chips.csv'); test = C[~C.kind.str.startswith('train')].copy(); test['dd'] = pd.to_datetime(test.date)
af = pd.read_csv('/mnt/project-files/fire-alert-scars/out/af/af_pixels_clean.csv'); af['dd'] = pd.to_datetime(af.date)
af = af[(af.dd.dt.year >= 2019) & (af.dd.dt.year <= 2025) & (af.dd.dt.dayofyear >= 46) & (af.dd.dt.dayofyear <= 166)]
cl = af.groupby(['season', 'cluster', 'date']).agg(n=('row', 'size'), lon=('lon', 'mean'), lat=('lat', 'mean'), firms=('firms_nearby', 'max')).reset_index()
cl = cl[cl.n >= 2]; cl['x'], cl['y'] = TO.transform(cl.lon.values, cl.lat.values); cl['dd'] = pd.to_datetime(cl.date)
rows = []
for r in cl.sample(frac=1, random_state=21).itertuples():
    if len(rows) >= 200: break
    s = test[(test.dd - r.dd).abs() <= pd.Timedelta(days=45)]
    if len(s) and np.hypot(s.x - r.x, s.y - r.y).min() < 3000: continue
    if any(np.hypot(q['x'] - r.x, q['y'] - r.y) < 1500 and q['date'] == r.date for q in rows): continue
    rows.append(dict(kind='train_af', key=f'{r.season}_{r.cluster}_{r.date}', x=r.x, y=r.y, date=r.date, half=1500, scene_date=r.date, n_af=r.n))
N = pd.DataFrame(rows); N['chip'] = [f'c{i:04d}' for i in range(len(C), len(C) + len(N))]
pd.concat([C, N], ignore_index=True).to_csv(CODE + 'chips.csv', index=False); print(len(N), N.n_af.sum())
