"""Burn-scar answer key on the MP 500 m grid (rows/cols as ratapani/mp_grid), 15 Feb-31 May 2022-2025.
One row per (event, square): squares under the event's scar outline (>= 10% of the square burned) plus the alert's own square (is_alert).
Events = forest fire events of the scar thread (same day, within 1 km); date = IST date of the first alert.
Out: scar_key.parquet (event_id, ld, row, col, under_scar), scar_events.parquet (event_id, ld, status, scar_ha, division)."""
import sys, numpy as np, pandas as pd, geopandas as gpd, shapely
from shapely import wkt
sys.path.insert(0, '/mnt/project-files/ratapani/scoring/mp_check'); import mp_simple_rules as M
sys.path.insert(0, '/mnt/project-files/fire-alert-scars/mp/scripts'); from read_geom import read_hist_geom
O = '/mnt/project-files/fire-alert-scars/'; OUT = '/mnt/project-files/research/ceiling/scar_key/'
cols = ['event_id', 'latitude', 'longitude', 'acq_date', 'acq_time', 'Division']
E = pd.concat([pd.read_csv(O + 'mp/out/set_rest_of_mp.csv', usecols=cols), pd.read_csv(O + 'mp/out/set_tiger_reserves.csv', usecols=cols)], ignore_index=True)
utc = pd.to_datetime(E.acq_date) + pd.to_timedelta(E.acq_time // 100, 'h') + pd.to_timedelta(E.acq_time % 100, 'm')
E['ld'] = (utc + pd.Timedelta(hours=5, minutes=30)).dt.normalize()
md = E.ld.dt.month * 100 + E.ld.dt.day; E = E[(E.ld.dt.year >= 2022) & (md >= 215) & (md <= 531)]
S = pd.concat([pd.read_csv(O + 'mp/out/scars_mp_hist.csv', usecols=['event_id', 'status', 'scar_ha']),
               pd.read_csv(O + 'mp/out/scars_tiger_reserves.csv', usecols=['event_id', 'status', 'scar_ha'])]).drop_duplicates('event_id', keep='last')
E = E.merge(S, on='event_id', how='left'); E['status'] = E.status.fillna('not_run')
G = pd.concat([read_hist_geom()[['event_id', 'geometry']],
               pd.read_csv(O + 'mp/out/scars_tiger_reserves.csv', usecols=['event_id', 'geometry']).dropna()]).drop_duplicates('event_id', keep='last')
G = G[G.event_id.isin(E.event_id) & G.geometry.notna()]
print('events', len(E), E.status.value_counts().to_dict(), 'outlines', len(G), flush=True)
import json
from shapely.geometry import shape
def parse(t):
    t = str(t).strip()
    try: return shape(json.loads(t)) if t.startswith('{') else wkt.loads(t)
    except Exception: return None
geoms = gpd.GeoSeries([parse(t) for t in G.geometry.values], crs=4326).to_crs(32643).values
rows = []
for eid, g in zip(G.event_id.values, geoms):
    if g is None or g.is_empty: continue
    x0, y0, x1, y1 = g.bounds
    c0, c1 = int(np.floor((x0 - M.X0) / M.S)), int(np.floor((x1 - M.X0) / M.S)); r0, r1 = int(np.floor((M.Y1 - y1) / M.S)), int(np.floor((M.Y1 - y0) / M.S))
    rr, cc = np.mgrid[r0:r1 + 1, c0:c1 + 1]; rr, cc = rr.ravel(), cc.ravel()
    boxes = shapely.box(M.X0 + cc * M.S, M.Y1 - (rr + 1) * M.S, M.X0 + (cc + 1) * M.S, M.Y1 - rr * M.S)
    a = shapely.area(shapely.intersection(boxes, g)); k = a >= 0.10 * M.S * M.S
    rows.append(pd.DataFrame({'event_id': eid, 'row': rr[k], 'col': cc[k]}))
K = pd.concat(rows, ignore_index=True); K['under_scar'] = True; K['is_alert'] = False
x, y = M.TF.transform(E.longitude.values, E.latitude.values)
A = pd.DataFrame({'event_id': E.event_id.values, 'row': np.floor((M.Y1 - y) / M.S).astype(int), 'col': np.floor((x - M.X0) / M.S).astype(int), 'under_scar': False, 'is_alert': True})
K = pd.concat([K, A]).groupby(['event_id', 'row', 'col'], as_index=False)[['under_scar', 'is_alert']].max()
K = K.merge(E[['event_id', 'ld']], on='event_id')
K.to_parquet(OUT + 'scar_key.parquet', index=False)
E[['event_id', 'ld', 'status', 'scar_ha', 'Division', 'latitude', 'longitude']].to_parquet(OUT + 'scar_events.parquet', index=False)
print('key rows', len(K), 'squares per event median', K.groupby('event_id').size().median(), flush=True)
print(E.groupby(E.ld.dt.year).status.value_counts().unstack().to_string())
