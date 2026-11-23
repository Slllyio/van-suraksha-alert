"""Step 1. Multi-day FIRES statewide from daily scar events (clear scars, 2017-25): rest-of-MP history + 8 tiger reserves.
Same chaining rule as fire_lines f1_fires.py: outlines within 60 m and first-alert dates <= 4 days apart, same division.
Per fire: start time t0 (first VIIRS look, MODIS if no VIIRS), local IST start date, start cells on the 500 m grid (cells
holding a first-look dot), footprint on the 500 m grid (burned fraction per cell from a 50 m rasterisation), scar ha (all
ground) and forest ha (burned fraction x WorldCover tree+shrub share of the cell, cell_year.parquet).
Out (scratch): fires.pkl (list of dicts); results/fires_table.csv (one row per fire, no geometry)."""
import sys, pickle
import numpy as np, pandas as pd, geopandas as gpd, shapely
from rasterio import features
from rasterio.transform import Affine
import lf_common as C
sys.path.insert(0, C.P + 'fire-alert-scars/mp/scripts')
from read_geom import read_hist_geom
from pyproj import Transformer
TF = Transformer.from_crs(4326, 32643, always_xy=True)
MAXGAP_D, TOUCH_M = 4, 60.0
O = C.P + 'fire-alert-scars/mp/out/'


def load():
    S = pd.read_csv(O + 'set_rest_of_mp.csv', usecols=['event_id', 'Division'])
    H = pd.read_csv(O + 'scars_mp_hist.csv', usecols=['event_id', 'status'])
    G = read_hist_geom(); G = G[G.event_id.isin(set(H.event_id[H.status == 'scar']))]
    G = G.merge(S, on='event_id')
    G['geometry'] = shapely.from_wkt(G.geometry.values); G = G[~shapely.is_empty(G.geometry.values)]
    tr = gpd.read_file(O + 'tiger_reserve_scars.geojson')
    tr = tr[tr.status == 'scar'][['event_id', 'Division', 'geometry']]
    E = pd.concat([G[['event_id', 'Division', 'geometry']], pd.DataFrame(tr)], ignore_index=True).drop_duplicates('event_id')
    E = gpd.GeoDataFrame(E, geometry='geometry', crs=4326).to_crs(32643)
    E['geometry'] = shapely.make_valid(E.geometry.values)
    A = pd.read_csv(O + 'mp_alert_event.csv', usecols=['latitude', 'longitude', 'acq_date', 'acq_time', 'instrument', 'event_id'])
    A = A[A.event_id.isin(set(E.event_id))].copy(); A['viirs'] = A.instrument != 'MODIS'
    A['t'] = pd.to_datetime(A.acq_date) + pd.to_timedelta((A.acq_time.astype(float) // 100) * 60 + A.acq_time.astype(float) % 100, unit='min')
    A['x'], A['y'] = TF.transform(A.longitude.values, A.latitude.values)
    t0 = A.groupby('event_id').t.min(); E['t0'] = E.event_id.map(t0); E = E[E.t0.notna()].reset_index(drop=True)
    E['year'] = E.t0.dt.year
    return E, A


def chain(E):
    par = np.arange(len(E))
    def f(i):
        while par[i] != i:
            par[i] = par[par[i]]; i = par[i]
        return i
    g = E.geometry.values; tree = shapely.STRtree(g)
    a, b = tree.query(shapely.buffer(g, TOUCH_M), predicate='intersects'); m = a < b; a, b = a[m], b[m]
    dd = np.abs((E.t0.values[a] - E.t0.values[b]) / np.timedelta64(1, 'D'))
    ok = (dd <= MAXGAP_D) & (E.Division.values[a] == E.Division.values[b])
    for i, j in zip(a[ok], b[ok]):
        ri, rj = f(i), f(j)
        if ri != rj: par[max(ri, rj)] = min(ri, rj)
    return np.array([f(i) for i in range(len(E))])


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
        fs = FOR.reindex(cells).fillna(0).values
        ha = float(frac.sum() * 25); fha = float((frac * fs).sum() * 25)
        tl = t0 + pd.Timedelta(hours=5, minutes=30)
        d = dict(fire=int(fid), div=g.Division.iloc[0], year=int(tl.year), t0=t0, start_day=tl.normalize(), start_cells=sc.astype(np.int32),
                 cells=cells.astype(np.int32), frac=frac, ha=ha, forest_ha=fha, n_events=len(g), last_day=(g.t0.max() + pd.Timedelta(hours=5, minutes=30)).normalize())
        fires.append(d)
        rows.append({k: d[k] for k in ('fire', 'div', 'year', 't0', 'start_day', 'last_day', 'ha', 'forest_ha', 'n_events')} | dict(n_start_cells=len(sc), start_cell=int(sc[0])))
    pickle.dump(fires, open(C.SC + 'fires.pkl', 'wb'), protocol=4)
    T = pd.DataFrame(rows); T.to_csv(C.OUT + 'fires_table.csv', index=False)
    bins = [0, 10, 50, 100, 200, 500, 1000, 1e9]
    T['band'] = pd.cut(T.forest_ha, bins, right=False)
    s = T.groupby('band', observed=False).agg(n=('fire', 'size'), ha=('forest_ha', 'sum')); s['share_fires'] = s.n / s.n.sum(); s['share_ha'] = s.ha / s.ha.sum(); s['per_year'] = s.n / 9
    print(s, flush=True); print(T.groupby('year').agg(n=('fire', 'size'), big200=('forest_ha', lambda x: (x >= 200).sum()), big500=('forest_ha', lambda x: (x >= 500).sum())))


if __name__ == '__main__':
    main()
