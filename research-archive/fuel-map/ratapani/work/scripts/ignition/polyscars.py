"""Rasterize the scar thread's grown per-event polygons (fire-alert-scars/event_scars.geojson) onto the spread engine's
20 m grid and link them to the all-sensor VIIRS events through the alert lookup."""
import json, sys, numpy as np, pandas as pd, pickle
sys.path.insert(0, '/tmp/claude-0/fuel/bsim/eng'); import sim
from rasterio.features import rasterize
from shapely.geometry import shape
from shapely.ops import transform as stx
from pyproj import Transformer
from affine import Affine
tr = Transformer.from_crs('EPSG:4326', 'EPSG:32643', always_xy=True).transform
with open('/mnt/project-files/fire-alert-scars/event_scars.geojson') as f: g = json.load(f)
P = {}
for ft in g['features']:
    geom = stx(tr, shape(ft['geometry'])); x0, y0, x1, y1 = geom.bounds
    j0, i0 = int((x0 - sim.X0) // 20), int((sim.Y0 - y1) // 20); j1, i1 = int((x1 - sim.X0) // 20) + 1, int((sim.Y0 - y0) // 20) + 1
    if j0 < 0 or i0 < 0 or j1 > sim.NX or i1 > sim.NY: continue
    m = rasterize([geom], out_shape=(i1 - i0, j1 - j0), transform=Affine(20, 0, sim.X0 + j0 * 20, 0, -20, sim.Y0 - i0 * 20), all_touched=False).astype(bool)
    pr = ft['properties']; P[pr['event_id']] = dict(i0=i0, j0=j0, m=m, grew=pr.get('grew_into_large_burn'), post=pr.get('post_date'), ha=pr.get('scar_ha'))
lk = pd.read_csv('/mnt/project-files/fire-alert-scars/alert_scar_lookup.csv', usecols=['event_id', 'latitude', 'longitude', 'acq_date', 'acq_time', 'sensor'])
lk = lk[lk.sensor.str.startswith('viirs')].dropna(subset=['acq_time'])
lk['k'] = lk.latitude.round(4).astype(str) + lk.longitude.round(4).astype(str) + lk.acq_date + lk.acq_time.astype(int).astype(str).str.zfill(4)
ev = pd.read_parquet('/mnt/project-files/ratapani/spread/data_shared/events_viirs.parquet')
ev['k'] = ev.latitude.round(4).astype(str) + ev.longitude.round(4).astype(str) + ev.t.dt.strftime('%Y-%m-%d%H%M')
ev = ev.merge(lk[['k', 'event_id']].drop_duplicates('k'), on='k', how='left')
print('alerts linked', ev.event_id.notna().mean().round(3))
link = ev.dropna(subset=['event_id']).groupby('event')['event_id'].apply(lambda s: sorted(set(s) & set(P)))
print('events with a polygon', (link.str.len() > 0).sum(), 'of', ev.event.nunique())
pickle.dump(dict(P=P, link=link.to_dict()), open('polyscars.pkl', 'wb'))
