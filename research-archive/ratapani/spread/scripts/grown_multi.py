"""Grown outlines (scar thread's event_scars.geojson) for a multi-satellite events file, keyed by its event ids: every detection of an event
(S-NPP, NOAA-20; NOAA-21 and MODIS are not in the lookup) is matched to the scar thread's alert lookup by position, date, time and sensor,
the matched scar-thread events' polygons are unioned and rasterised on the 20 m grid.
  python3 grown_multi.py events_viirs.parquet grown_scars_viirs.pkl   (-> data/<pkl> and data/<pkl>_events.parquet)
"""
import numpy as np, pandas as pd, json, pickle, sys, os
from shapely.geometry import shape
from shapely.ops import transform, unary_union
from pyproj import Transformer
from rasterio import features
from rasterio.transform import from_origin
import sim
SRC = '/mnt/project-files/fire-alert-scars'


def main(events_file, out_pkl):
    look = pd.read_csv(f'{SRC}/alert_scar_lookup.csv', usecols=['event_id', 'latitude', 'longitude', 'acq_date', 'acq_time', 'sensor'])
    if os.environ.get('SENSORS'):          # e.g. SENSORS=viirs-snpp matches through S-NPP detections only (how grown_scars_viirs.pkl was built)
        look = look[look.sensor.isin(os.environ['SENSORS'].split(','))]
    v = pd.read_parquet(f'{sim.DATA}/{events_file}')
    v['acq_date'] = v.t.dt.strftime('%Y-%m-%d'); v['acq_time'] = v.t.dt.hour * 100 + v.t.dt.minute
    key = lambda d: d.latitude.round(5).astype(str) + '_' + d.longitude.round(5).astype(str) + '_' + d.acq_date.astype(str) + '_' + d.acq_time.fillna(-1).astype(int).astype(str) + '_' + d.sensor.astype(str)
    look['key'] = key(look); v['key'] = key(v)
    mp = v[['event', 'key']].merge(look[['key', 'event_id']], on='key', how='left')
    print('detections', len(v), 'matched to a scar-thread alert', int(mp.event_id.notna().sum()), 'events', v.event.nunique())
    ev2eid = mp.dropna().groupby('event').event_id.apply(lambda s: sorted(set(s)))
    g = json.load(open(f'{SRC}/event_scars.geojson')); tr = Transformer.from_crs('EPSG:4326', 'EPSG:32643', always_xy=True).transform
    polys = {f['properties']['event_id']: (shape(f['geometry']), f['properties']) for f in g['features']}
    store, rows = {}, []; pad = int(float(os.environ.get('PAD_M', 2600)) / sim.RES)
    for e, eids in ev2eid.items():
        ev = v[v.event == e]; r, c = sim.rc(ev.x.values, ev.y.values)
        i0, i1 = max(r.min() - pad, 0), min(r.max() + pad, sim.NY); j0, j1 = max(c.min() - pad, 0), min(c.max() + pad, sim.NX)
        geoms = [transform(tr, polys[eid][0]) for eid in eids if eid in polys]
        if not geoms:
            continue
        u = unary_union(geoms); tfm = from_origin(sim.X0 + j0 * sim.RES, sim.Y0 - i0 * sim.RES, sim.RES, sim.RES)
        m = features.rasterize([(u, 1)], out_shape=(i1 - i0, j1 - j0), transform=tfm, fill=0, dtype='uint8', all_touched=False).astype(bool)
        rr, cc = np.nonzero(m)
        store[int(e)] = dict(rows=(rr + i0).astype(np.int32), cols=(cc + j0).astype(np.int32), win_days=0)
        rows.append(dict(event=int(e), season=int(ev.season.iloc[0]), n_eids=len(eids), grown_px=int(m.sum()), n_det=len(ev), n_pass=int(ev.overpass.nunique())))
    pickle.dump(store, open(f'{sim.DATA}/{out_pkl}', 'wb'))
    d = pd.DataFrame(rows); d.to_parquet(f"{sim.DATA}/{out_pkl.replace('.pkl', '')}_events.parquet")
    print('events with a grown polygon', len(d), 'median ha', round(d.grown_px.median() * 0.04, 1), 'with 2+ passes', int((d.n_pass >= 2).sum()))
    print(d.groupby('season').size().to_dict())


if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2])
