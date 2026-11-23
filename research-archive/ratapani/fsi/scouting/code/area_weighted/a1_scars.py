"""Step 0: burn-scar table for the 10 round-22 divisions, 15 Feb-31 May 2019-2025.
Same sources and rules as the 'Is the project at its limit' key (research/ceiling/scar_key/build_scar_key.py): forest fire
events of the scar thread (same day, within 1 km; date = IST date of the first alert), status and scar_ha from the scar runs
(rest of MP + tiger reserves), outlines from read_hist_geom() + the tiger-reserve file. The ceiling key stops at 2022; the
scar runs now also hold 2019-21, which the size model needs for training. The stats files were copied once to scratch (the
scar run is still writing). Out (scratch r24): scar_ev.parquet (event_id, ld, status, scar_ha, row, col, geom_wkb in EPSG:32643)."""
import sys, json, numpy as np, pandas as pd, geopandas as gpd, shapely
from shapely import wkt
from shapely.geometry import shape
import aw_common as A
C = A.C
sys.path.insert(0, A.P + 'fire-alert-scars/mp/scripts'); from read_geom import read_hist_geom
O = A.P + 'fire-alert-scars/mp/out/'
cols = ['event_id', 'latitude', 'longitude', 'acq_date', 'acq_time']
Ev = pd.concat([pd.read_csv(O + 'set_rest_of_mp.csv', usecols=cols), pd.read_csv(O + 'set_tiger_reserves.csv', usecols=cols)], ignore_index=True).drop_duplicates('event_id')
utc = pd.to_datetime(Ev.acq_date) + pd.to_timedelta(Ev.acq_time // 100, 'h') + pd.to_timedelta(Ev.acq_time % 100, 'm')
Ev['ld'] = (utc + pd.Timedelta(hours=5, minutes=30)).dt.normalize()
md = Ev.ld.dt.month * 100 + Ev.ld.dt.day; Ev = Ev[(Ev.ld.dt.year >= 2019) & (Ev.ld.dt.year <= 2025) & (md >= 215) & (md <= 531)]
x, y = C.TF.transform(Ev.longitude.values, Ev.latitude.values)
Ev['row'] = np.floor((C.Y1 - y) / C.S).astype(int); Ev['col'] = np.floor((x - C.X0) / C.S).astype(int)
U = A.Fe.base()['U']; f = Ev.row.values * C.W + Ev.col.values
# keep events whose alert square is in, or within 2 squares of, the 10-division union
near = np.zeros(C.H * C.W, bool); ur, uc = U // C.W, U % C.W
for dr in range(-2, 3):
    for dc in range(-2, 3):
        rr, cc = np.clip(ur + dr, 0, C.H - 1), np.clip(uc + dc, 0, C.W - 1); near[rr * C.W + cc] = True
Ev = Ev[near[np.clip(f, 0, C.H * C.W - 1)]]
St = pd.concat([pd.read_csv(A.S24 + 'snap/scars_mp_hist.csv', usecols=['event_id', 'status', 'scar_ha']),
                pd.read_csv(A.S24 + 'snap/scars_tiger_reserves.csv', usecols=['event_id', 'status', 'scar_ha'])]).drop_duplicates('event_id', keep='last')
Ev = Ev.merge(St, on='event_id', how='left'); Ev['status'] = Ev.status.fillna('not_run')
G = pd.concat([read_hist_geom()[['event_id', 'geometry']],
               pd.read_csv(O + 'scars_tiger_reserves.csv', usecols=['event_id', 'geometry']).dropna()]).drop_duplicates('event_id', keep='last')
G = G[G.event_id.isin(Ev.event_id) & G.geometry.notna()]


def parse(t):
    t = str(t).strip()
    try: return shape(json.loads(t)) if t.startswith('{') else wkt.loads(t)
    except Exception: return None


g = gpd.GeoSeries([parse(t) for t in G.geometry.values], crs=4326).to_crs(32643)
G = pd.DataFrame({'event_id': G.event_id.values, 'geom_wkb': [None if (q is None or q.is_empty) else shapely.to_wkb(shapely.make_valid(q)) for q in g.values]})
Ev = Ev.merge(G, on='event_id', how='left')
Ev = Ev[['event_id', 'ld', 'status', 'scar_ha', 'row', 'col', 'geom_wkb']]
Ev.to_parquet(A.S24 + 'scar_ev.parquet', index=False)
print(len(Ev), 'events; outlines', Ev.geom_wkb.notna().sum())
print(pd.crosstab(Ev.ld.dt.year, Ev.status).to_string())
