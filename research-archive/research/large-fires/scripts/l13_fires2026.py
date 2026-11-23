"""Step 13a. 2026 multi-day fires from the 2026 scar run (l12, scratch scars2026/), same chaining and sizing as l1_fires.py.
Out (scratch): fires_2026.pkl; results/fires_table_2026.csv."""
import glob, pickle, numpy as np, pandas as pd, geopandas as gpd, shapely
from rasterio import features
from rasterio.transform import Affine
import lf_common as C
from l1_fires import chain, TF
O = C.SCARS26


def load():
    S = pd.read_csv(O + 'set_2026.csv', usecols=['event_id', 'Division'])
    H = pd.read_csv(O + 'scars_2026.csv', usecols=['event_id', 'status'])
    G = pd.concat([pd.read_csv(f) for f in sorted(glob.glob(O + 'scars_2026_geom/*.csv.gz'))], ignore_index=True).drop_duplicates('event_id', keep='last')
    G = G[G.event_id.isin(set(H.event_id[H.status == 'scar']))].merge(S, on='event_id')
    G['geometry'] = shapely.from_wkt(G.geometry.values); G = G[~shapely.is_empty(G.geometry.values)]
    E = gpd.GeoDataFrame(G, geometry='geometry', crs=4326).to_crs(32643); E['geometry'] = shapely.make_valid(E.geometry.values)
    A = pd.read_csv(O + 'alert_event_2026.csv', usecols=['latitude', 'longitude', 'acq_date', 'acq_time', 'instrument', 'event_id'])
    A = A[A.event_id.isin(set(E.event_id))].copy(); A['viirs'] = A.instrument != 'MODIS'
    A['t'] = pd.to_datetime(A.acq_date) + pd.to_timedelta((A.acq_time.astype(float) // 100) * 60 + A.acq_time.astype(float) % 100, unit='min')
    A['x'], A['y'] = TF.transform(A.longitude.values, A.latitude.values)
    E['t0'] = E.event_id.map(A.groupby('event_id').t.min()); E = E[E.t0.notna()].reset_index(drop=True)
    return E, A


def main():
    E, A = load(); print('events', len(E), flush=True)
    E['fire'] = chain(E); print('fires', E.fire.nunique(), flush=True)
    cy = pd.read_parquet(C.P + 'fire-alert-scars/mp/burn_history/cell_year.parquet', columns=['cell', 'year', 'forest'])
    FOR = cy.drop_duplicates('cell').set_index('cell').forest
    Ag = {k: g.sort_values('t') for k, g in A.groupby('event_id')}
    fires, rows = [], []
    for fid, g in E.groupby('fire'):
        geom = shapely.union_all(g.geometry.values)
        D = pd.concat([Ag[e] for e in g.event_id if e in Ag]).sort_values('t')
        v = D[D.viirs]; v = v if len(v) else D
        t0 = v.t.min(); first = v[v.t <= t0 + pd.Timedelta(hours=2)]
        sc = np.unique(np.floor((C.Y1 - first.y.values) / C.S).astype(int) * C.W + np.floor((first.x.values - C.X0) / C.S).astype(int))
        bx = geom.bounds
        c0 = int((bx[0] - C.X0) // C.S); c1 = int((bx[2] - C.X0) // C.S) + 1
        r0 = int((C.Y1 - bx[3]) // C.S); r1 = int((C.Y1 - bx[1]) // C.S) + 1
        T = Affine(50.0, 0, C.X0 + c0 * C.S, 0, -50.0, C.Y1 - r0 * C.S)
        M = features.rasterize([(geom, 1)], out_shape=((r1 - r0) * 10, (c1 - c0) * 10), transform=T, dtype='uint8')
        fr = M.reshape(r1 - r0, 10, c1 - c0, 10).mean((1, 3))
        rr, cc = np.nonzero(fr); cells = (rr + r0) * C.W + (cc + c0); frac = fr[rr, cc].astype(np.float32)
        fha = float((frac * FOR.reindex(cells).fillna(0).values).sum() * 25)
        tl = t0 + pd.Timedelta(hours=5, minutes=30)
        d = dict(fire=int(fid) + 10_000_000, div=g.Division.iloc[0], year=int(tl.year), t0=t0, start_day=tl.normalize(), start_cells=sc.astype(np.int32),
                 cells=cells.astype(np.int32), frac=frac, ha=float(frac.sum() * 25), forest_ha=fha, n_events=len(g),
                 last_day=(g.t0.max() + pd.Timedelta(hours=5, minutes=30)).normalize())
        fires.append(d); rows.append({k: d[k] for k in ('fire', 'div', 'year', 't0', 'start_day', 'last_day', 'ha', 'forest_ha', 'n_events')})
    pickle.dump(fires, open(C.SC + 'fires_2026.pkl', 'wb'), protocol=4)
    T = pd.DataFrame(rows); T.to_csv(C.OUT + 'fires_table_2026.csv', index=False)
    print('fires', len(T), '200+', int((T.forest_ha >= 200).sum()), '500+', int((T.forest_ha >= 500).sum()), 'forest ha', round(T.forest_ha.sum()))


if __name__ == '__main__':
    main()
