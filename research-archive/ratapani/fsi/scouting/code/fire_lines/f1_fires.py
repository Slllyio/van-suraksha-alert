"""Step 1. Build multi-day FIRES from daily scar events, and rasterise them on the 60 m VTM lattice per division.
Events (same-day alerts within 1 km, each with its own scar outline) are chained into one fire when their outlines touch
(within 60 m) and their dates are at most 4 days apart (chains can run longer). Fire footprint = union of its events' outlines.
Start = the first look: VIIRS dots of the earliest event within 2 h of its earliest VIIRS overpass (MODIS only if no VIIRS).
Also kept: 'fronts' = first look plus any later dot more than 750 m from every earlier dot (the README front rule) - used for a
conservative variant in which every new front counts as its own start.
Run: python f1_fires.py core ; python f1_fires.py rest
Out (scratch): fires_<div>.pkl with landscape window + per-fire crop masks; fires_table.csv (one row per fire)."""
import pickle, sys
import numpy as np, pandas as pd, geopandas as gpd, shapely
from rasterio import features
from rasterio.transform import Affine
from scipy.spatial import cKDTree
import common as C

MAXGAP_D, TOUCH_M = 4, 60.0


def load_rest():
    """Statewide rest-of-MP history (all forest events outside the 8 tiger-reserve divisions; Obedullahganj is left to the
    complete Ratapani v2 set). Read only through read_hist_geom(); rerunning picks up whatever has been built by then.
    Also writes coverage_rest.csv: per division and year, events in the work list vs events with a finished result."""
    sys.path.insert(0, C.P + 'fire-alert-scars/mp/scripts'); from read_geom import read_hist_geom
    S = pd.read_csv(C.P + 'fire-alert-scars/mp/out/set_rest_of_mp.csv', usecols=['event_id', 'Division'])
    S = S[~S.Division.isin(['Obedullahganj'])]
    H = pd.read_csv(C.P + 'fire-alert-scars/mp/out/scars_mp_hist.csv', usecols=['event_id', 'status'])
    S['year'] = S.event_id.str[1:5].astype(int); S['done'] = S.event_id.isin(set(H.event_id))
    cov = S.groupby(['Division', 'year']).done.agg(events='size', done='sum').reset_index(); cov['share'] = cov.done / cov.events
    cov.to_csv(C.SC + 'coverage_rest.csv', index=False)
    G = read_hist_geom(); G = G[G.event_id.isin(set(H.event_id[H.status == 'scar']))]
    G = G.merge(S[['event_id', 'Division']], on='event_id').rename(columns={'Division': 'div'})
    G['geometry'] = shapely.from_wkt(G.geometry.values); G = G[~shapely.is_empty(G.geometry.values)]
    G['src'] = 'rest_of_mp'
    ids = set(G.event_id)
    A = pd.read_csv(C.P + 'fire-alert-scars/mp/out/mp_alert_event.csv', usecols=['latitude', 'longitude', 'acq_date', 'acq_time', 'instrument', 'event_id'])
    A = A[A.event_id.isin(ids)].copy(); A['sensor'] = np.where(A.instrument == 'MODIS', 'modis', 'viirs')
    A['t'] = pd.to_datetime(A.acq_date) + pd.to_timedelta((A.acq_time.astype(float) // 100) * 60 + A.acq_time.astype(float) % 100, unit='min')
    A['x'], A['y'] = C.TF.transform(A.longitude.values, A.latitude.values)
    E = gpd.GeoDataFrame(G[['event_id', 'div', 'src', 'geometry']], geometry='geometry', crs=4326).to_crs(32643)
    E['geometry'] = shapely.make_valid(E.geometry.values)
    t0 = A.groupby('event_id').t.min(); E['t0'] = E.event_id.map(t0); E = E[E.t0.notna()].reset_index(drop=True)
    E['year'] = E.t0.dt.year
    return E, A


def load():
    tr = gpd.read_file(C.P + 'fire-alert-scars/mp/out/tiger_reserve_scars.geojson')
    tr = tr[tr.status == 'scar'][['event_id', 'Division', 'geometry']].rename(columns={'Division': 'div'})
    tr['src'] = 'tiger_reserve'
    ids = set(tr.event_id)
    A = pd.read_csv(C.P + 'fire-alert-scars/mp/out/mp_alert_event.csv', usecols=['latitude', 'longitude', 'acq_date', 'acq_time', 'instrument', 'event_id'])
    A = A[A.event_id.isin(ids)]
    A['sensor'] = np.where(A.instrument == 'MODIS', 'modis', 'viirs')
    rp = gpd.read_file(C.P + 'fire-alert-scars/reference/v2_2026-10-16/firms_event_scars.geojson')
    rp = rp[(rp.status == 'scar') & (rp.event_id.str[1:5].astype(int) <= 2025)][['event_id', 'geometry']]
    L = pd.read_csv(C.P + 'fire-alert-scars/reference/v2_2026-10-16/firms_alert_scar_lookup.csv',
                    usecols=['event_id', 'latitude', 'longitude', 'acq_date', 'acq_time', 'sensor', 'division'])
    dv = L.assign(division=L.division.fillna('none').astype(str)).groupby('event_id').division.agg(lambda s: s.value_counts().index[0])
    rp['div'] = rp.event_id.map(dv); rp = rp[rp['div'] == 'Obedullahganj']; rp['div'] = 'Obedullahganj (Ratapani)'; rp['src'] = 'ratapani_v2'
    L = L[L.event_id.isin(set(rp.event_id))].copy(); L['sensor'] = np.where(L.sensor == 'modis', 'modis', 'viirs')
    A = pd.concat([A[['event_id', 'latitude', 'longitude', 'acq_date', 'acq_time', 'sensor']], L[['event_id', 'latitude', 'longitude', 'acq_date', 'acq_time', 'sensor']]])
    A['t'] = pd.to_datetime(A.acq_date) + pd.to_timedelta((A.acq_time.astype(float) // 100) * 60 + A.acq_time.astype(float) % 100, unit='min')
    A['x'], A['y'] = C.TF.transform(A.longitude.values, A.latitude.values)
    E = pd.concat([tr, rp], ignore_index=True)
    E = gpd.GeoDataFrame(E, geometry='geometry', crs=4326).to_crs(32643)
    E['geometry'] = shapely.make_valid(E.geometry.values)
    t0 = A.groupby('event_id').t.min(); E['t0'] = E.event_id.map(t0); E = E[E.t0.notna()].reset_index(drop=True)
    E['year'] = E.t0.dt.year
    return E, A


def chain(E):
    """Union-find over events whose outlines touch and dates are <= MAXGAP_D apart (same division)."""
    par = np.arange(len(E))
    def f(i):
        while par[i] != i:
            par[i] = par[par[i]]; i = par[i]
        return i
    g = E.geometry.values; tree = shapely.STRtree(g)
    a, b = tree.query(shapely.buffer(g, TOUCH_M), predicate='intersects')
    m = a < b
    a, b = a[m], b[m]
    dd = np.abs((E.t0.values[a] - E.t0.values[b]) / np.timedelta64(1, 'D'))
    ok = (dd <= MAXGAP_D) & (E['div'].values[a] == E['div'].values[b])
    for i, j in zip(a[ok], b[ok]):
        ri, rj = f(i), f(j)
        if ri != rj: par[max(ri, rj)] = min(ri, rj)
    return np.array([f(i) for i in range(len(E))])


def starts(D):
    """D: dots of one fire sorted by time. first look and fronts (x, y arrays)."""
    v = D[D.sensor == 'viirs']; v = v if len(v) else D
    t0 = v.t.min(); first = v[v.t <= t0 + pd.Timedelta(hours=2)]
    fx = [first[['x', 'y']].values]
    seen = D[D.t <= t0 + pd.Timedelta(hours=2)][['x', 'y']].values
    later = D[D.t > t0 + pd.Timedelta(hours=2)]
    for t, g in later.groupby('t'):
        xy = g[['x', 'y']].values
        d, _ = cKDTree(seen).query(xy)
        new = xy[d > 750]
        if len(new): fx.append(new)
        seen = np.vstack([seen, xy])
    return first[['x', 'y']].values, np.vstack(fx), t0


def main(which):
    E, A = load() if which == 'core' else load_rest(); print('events', len(E), E.groupby('div').size().to_dict(), flush=True)
    E['fire'] = chain(E)
    Ag = {k: g.sort_values('t') for k, g in A.groupby('event_id')}
    rows = []
    for div, Ed in E.groupby('div'):
        xmin, ymin, xmax, ymax = Ed.total_bounds
        x0, y1, W, H = C.snap_box(xmin - 3000, ymin - 3000, xmax + 3000, ymax + 3000)
        T = Affine(C.RES, 0, x0, 0, -C.RES, y1)
        fires = []
        for fid, g in Ed.groupby('fire'):
            geom = shapely.union_all(g.geometry.values)
            D = pd.concat([Ag[e] for e in g.event_id if e in Ag]).sort_values('t')
            ign, fr, t0 = starts(D)
            bx = geom.bounds
            c0 = max(int((bx[0] - x0) // C.RES) - 3, 0); c1 = min(int((bx[2] - x0) // C.RES) + 4, W)
            r0 = max(int((y1 - bx[3]) // C.RES) - 3, 0); r1 = min(int((y1 - bx[1]) // C.RES) + 4, H)
            Tl = Affine(C.RES, 0, x0 + c0 * C.RES, 0, -C.RES, y1 - r0 * C.RES)
            M = features.rasterize([(geom, 1)], out_shape=(r1 - r0, c1 - c0), transform=Tl, dtype='uint8').astype(bool)
            if M.sum() == 0: continue
            def cells(xy, rad):
                rr, cc = np.nonzero(M)
                px = x0 + (c0 + cc + .5) * C.RES; py = y1 - (r0 + rr + .5) * C.RES
                d, _ = cKDTree(xy).query(np.c_[px, py])
                return (rr * M.shape[1] + cc)[d <= rad]
            ig = cells(ign, 400)
            if len(ig) == 0: ig = cells(ign, 750)
            fg = cells(fr, 400)
            fires.append(dict(fire=f'{C.slug(div)}_{fid}', div=div, src=g.src.iloc[0], year=int(t0.year), t0=t0, r0=r0, c0=c0, M=np.packbits(M), shape=M.shape,
                              ign=ig.astype(np.int32), fronts=np.union1d(fg, ig).astype(np.int32), n_events=len(g), ha=float(M.sum() * C.CELL_HA),
                              ha_poly=geom.area / 1e4, n_dots=len(D), n_fronts=len(np.unique(np.round(fr / 750), axis=0))))
            rows.append({k: v for k, v in fires[-1].items() if k not in ('M', 'ign', 'fronts', 'shape')} | dict(n_ign_cells=len(ig)))
        pickle.dump(dict(div=div, x0=x0, y1=y1, W=W, H=H, fires=fires), open(C.SC + f'fires_{C.slug(div)}.pkl', 'wb'))
        print(div, len(fires), 'fires', round(sum(f['ha'] for f in fires)), 'ha', 'grid', W, H, flush=True)
    pd.DataFrame(rows).to_csv(C.SC + f'fires_table_{which}.csv', index=False)


if __name__ == '__main__':
    main(sys.argv[1] if len(sys.argv) > 1 else 'core')   # 'core' (tiger reserves + Ratapani v2) or 'rest' (statewide history)
