"""Grown burn-scar outlines from the scar thread (fire-alert-scars/event_scars.geojson, Oct 15: each scar grown into the
connected ground burned by the next clear image; 6% flagged grew_into_large_burn keep the first-image outline) matched to
this thread's S-NPP fire events through the alert lookup, rasterised to the 20 m grid.
  python3 grown.py build        -> data/grown_scars.pkl (event -> global pixel rows/cols) + data/grown_events.parquet
  import grown; grown.scar_footprint(o, ev)   drop-in for score.scar_footprint (window mask of the grown outline)"""
import numpy as np, pandas as pd, json, pickle, sys, os
import sim
D = sim.DATA; SRC = '/mnt/project-files/fire-alert-scars'
_store = None


def load():
    global _store
    if _store is None:
        _store = pickle.load(open(f"{D}/{os.environ.get('GROWN_STORE', 'grown_scars.pkl')}", 'rb'))
    return _store


def scar_footprint(o, ev):
    i0, i1, j0, j1 = o['win']; st = load(); e = int(ev.event.iloc[0])
    m = np.zeros((i1 - i0, j1 - j0), bool)
    if e in st:
        r, c = st[e]['rows'] - i0, st[e]['cols'] - j0
        ok = (r >= 0) & (r < m.shape[0]) & (c >= 0) & (c < m.shape[1]); m[r[ok], c[ok]] = True
    return m, int(st[e]['win_days']) if e in st else 0


def build():
    from shapely.geometry import shape
    from shapely.ops import transform, unary_union
    from pyproj import Transformer
    from rasterio import features
    import score
    look = pd.read_csv(f'{SRC}/alert_scar_lookup.csv', usecols=['alert_id', 'event_id', 'latitude', 'longitude', 'acq_date', 'acq_time', 'sensor'])
    look = look[look.sensor == 'viirs-snpp']
    v = pd.read_parquet(f'{D}/viirs_events.parquet')
    key = lambda d: d.latitude.round(5).astype(str) + '_' + d.longitude.round(5).astype(str) + '_' + d.acq_date.astype(str) + '_' + d.acq_time.astype(int).astype(str)
    look['key'] = key(look); v['key'] = key(v)
    mp = v[['event', 'key']].merge(look[['key', 'event_id']], on='key', how='left')
    print('detections', len(v), 'matched to a scar-thread alert', mp.event_id.notna().sum())
    ev2eid = mp.dropna().groupby('event').event_id.apply(lambda s: sorted(set(s)))
    g = json.load(open(f'{SRC}/event_scars.geojson'))
    tr = Transformer.from_crs('EPSG:4326', 'EPSG:32643', always_xy=True).transform
    polys = {}
    for f in g['features']:
        p = f['properties']; polys[p['event_id']] = (shape(f['geometry']), p)
    # window per event as in sim.run_event (pad 2600 m = footprint.CFG)
    _c = pd.read_parquet(f'{D}/rundir.parquet').event.values
    store, rows = {}, []
    pad = int(2600 / sim.RES)
    for e, eids in ev2eid.items():
        ev = v[v.event == e]
        r, c = sim.rc(ev.x.values, ev.y.values)
        i0, i1 = max(r.min() - pad, 0), min(r.max() + pad, sim.NY); j0, j1 = max(c.min() - pad, 0), min(c.max() + pad, sim.NX)
        geoms, props = [], []
        for eid in eids:
            if eid in polys:
                geoms.append(transform(tr, polys[eid][0])); props.append(polys[eid][1])
        if not geoms:
            continue
        u = unary_union(geoms)
        T = sim.rasterio_transform if hasattr(sim, 'rasterio_transform') else None
        from rasterio.transform import from_origin
        tfm = from_origin(sim.X0 + j0 * sim.RES, sim.Y0 - i0 * sim.RES, sim.RES, sim.RES)
        m = features.rasterize([(u, 1)], out_shape=(i1 - i0, j1 - j0), transform=tfm, fill=0, dtype='uint8', all_touched=False).astype(bool)
        S, win_days = score.scar_footprint(dict(win=(i0, i1, j0, j1), season=int(ev.season.iloc[0])), ev)
        rr, cc = np.nonzero(m)
        store[int(e)] = dict(rows=(rr + i0).astype(np.int32), cols=(cc + j0).astype(np.int32), win_days=win_days)
        rows.append(dict(event=int(e), season=int(ev.season.iloc[0]), n_eids=len(eids), n_polys=len(geoms), grown_px=int(m.sum()), raster_px=int(S.sum()),
                         first_ha=float(sum(p.get('scar_ha') or 0 for p in props)), post_ha=float(sum(p.get('scar_ha_post') or 0 for p in props)),
                         flagged=bool(any(p.get('grew_into_large_burn') for p in props)), status=';'.join(sorted(set(str(p.get('status')) for p in props))),
                         soren=score.soren(m, S), in_rundir=bool(e in _c)))
    pickle.dump(store, open(f'{D}/grown_scars.pkl', 'wb'))
    d = pd.DataFrame(rows); d.to_parquet(f'{D}/grown_events.parquet')
    print('events with a grown polygon', len(d), 'of which in the 1,223-fire set', int(d.in_rundir.sum()), 'flagged', int(d.flagged.sum()))
    q = d[d.in_rundir]
    print('median ha: grown polygon %.1f, raster label %.1f, first image %.1f; Sorensen raster vs grown: mean %.3f median %.3f' % (q.grown_px.median() * 0.04, q.raster_px.median() * 0.04, q.first_ha.median(), q.soren.mean(), q.soren.median()))
    print('grown/raster area ratio quartiles', (q.grown_px / q.raster_px.clip(lower=1)).quantile([.25, .5, .75]).round(2).tolist())
    print(q.status.value_counts().head(5).to_string())


if __name__ == '__main__' and (len(sys.argv) < 2 or sys.argv[1] == 'build'):
    build()


def build_pre():
    """Same matching for the scar thread's pre-grow outlines (out/event_scars_pre_grow.csv) -> data/grown_pre_events.parquet:
    per fire, Sorensen and areas of raster label vs pre-grow polygon vs grown polygon."""
    from shapely.geometry import shape
    from shapely import transform as sh_transform
    from shapely.ops import unary_union
    from pyproj import Transformer
    from rasterio import features
    from rasterio.transform import from_origin
    import score
    look = pd.read_csv(f'{SRC}/alert_scar_lookup.csv', usecols=['event_id', 'latitude', 'longitude', 'acq_date', 'acq_time', 'sensor']); look = look[look.sensor == 'viirs-snpp']
    v = pd.read_parquet(f'{D}/viirs_events.parquet')
    key = lambda d: d.latitude.round(5).astype(str) + '_' + d.longitude.round(5).astype(str) + '_' + d.acq_date.astype(str) + '_' + d.acq_time.astype(int).astype(str)
    look['key'] = key(look); v['key'] = key(v)
    ev2eid = v[['event', 'key']].merge(look[['key', 'event_id']], on='key').groupby('event').event_id.apply(lambda s: sorted(set(s)))
    pre = pd.read_csv(f'{SRC}/out/event_scars_pre_grow.csv', usecols=['event_id', 'scar_ha', 'geometry']).dropna(subset=['geometry'])
    pre = pre.set_index('event_id')
    tr = Transformer.from_crs('EPSG:4326', 'EPSG:32643', always_xy=True)
    st = load(); rows = []; pad = int(2600 / sim.RES)
    for e, eids in ev2eid.items():
        if int(e) not in st:
            continue
        ev = v[v.event == e]; r, c = sim.rc(ev.x.values, ev.y.values)
        i0, i1 = max(r.min() - pad, 0), min(r.max() + pad, sim.NY); j0, j1 = max(c.min() - pad, 0), min(c.max() + pad, sim.NX)
        geoms = [sh_transform(shape(json.loads(pre.geometry[eid])), lambda xy: np.c_[tr.transform(xy[:, 0], xy[:, 1])]) for eid in eids if eid in pre.index]
        if not geoms:
            continue
        tfm = from_origin(sim.X0 + j0 * sim.RES, sim.Y0 - i0 * sim.RES, sim.RES, sim.RES)
        mp = features.rasterize([(unary_union(geoms), 1)], out_shape=(i1 - i0, j1 - j0), transform=tfm, fill=0, dtype='uint8').astype(bool)
        mg, _ = scar_footprint(dict(win=(i0, i1, j0, j1)), ev)
        S, _ = score.scar_footprint(dict(win=(i0, i1, j0, j1), season=int(ev.season.iloc[0])), ev)
        rows.append(dict(event=int(e), pre_px=int(mp.sum()), grown_px=int(mg.sum()), raster_px=int(S.sum()), sor_raster_pre=score.soren(S, mp), sor_raster_grown=score.soren(S, mg), sor_pre_grown=score.soren(mp, mg),
                         raster_in_pre=float((S & mp).sum() / max(S.sum(), 1)), raster_in_grown=float((S & mg).sum() / max(S.sum(), 1)), pre_in_raster=float((S & mp).sum() / max(mp.sum(), 1)), grown_in_raster=float((S & mg).sum() / max(mg.sum(), 1))))
    d = pd.DataFrame(rows); d.to_parquet(f'{D}/grown_pre_events.parquet')
    ok = pd.read_parquet(f'{D}/rundir.parquet').event.values; q = d[d.event.isin(ok)]
    print('fires', len(q)); print('median ha raster %.1f pre-grow %.1f grown %.1f' % (q.raster_px.median() * .04, q.pre_px.median() * .04, q.grown_px.median() * .04))
    print(q[['sor_raster_pre', 'sor_raster_grown', 'sor_pre_grown', 'raster_in_pre', 'raster_in_grown', 'pre_in_raster', 'grown_in_raster']].describe().loc[['mean', '25%', '50%', '75%']].round(3).to_string())


if __name__ == '__main__' and len(sys.argv) > 1 and sys.argv[1] == 'pre':
    build_pre()
