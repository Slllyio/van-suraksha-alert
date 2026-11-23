"""Step 1. Fires (round-25 chaining, unchanged) from the now-complete statewide history plus the tiger reserves and Ratapani v2,
keeping what the entry-direction step needs:
  ign      - round-25 start cells (within 400 m of the first VIIRS look)  [used for scoring, as in round 25]
  dotc     - footprint cells holding the first-look dots themselves (nearest footprint cell, <= 200 m)  [used for 'started inside']
  dots     - all dots of the fire: local cell, hours after the first look
  day      - per footprint cell, days after the first look of the earliest chained daily event whose outline covers it
  forest   - VTM tree forest/scrub per footprint cell (same rule as round 25; the VTM is the source of static_gis lc_forest/lc_scrub)
Run: python r1_fires.py core ; python r1_fires.py rest
Out (scratch r26): fires_<div>.pkl, coverage.csv, fires_table_<set>.csv"""
import pickle, sys
import numpy as np, pandas as pd, shapely, rasterio
from multiprocessing import Pool
from rasterio import features
from rasterio.transform import Affine
from rasterio.windows import Window
from scipy.spatial import cKDTree
import c26 as C
import common as C25, f1_fires as F1

G = {}


def coverage():
    S = pd.read_csv(C25.P + 'fire-alert-scars/mp/out/set_rest_of_mp.csv', usecols=['event_id', 'Division'])
    H = pd.read_csv(C25.P + 'fire-alert-scars/mp/out/scars_mp_hist.csv', usecols=['event_id', 'status'])
    S['year'] = S.event_id.str[1:5].astype(int)
    st = S.event_id.map(H.set_index('event_id').status)
    S['done'] = st.isin(['scar', 'scar_faint', 'no_scar_seen', 'no_pre', 'error']); S['scar'] = st.eq('scar')
    cv = S.groupby(['Division', 'year']).agg(events=('done', 'size'), done=('done', 'sum'), scar=('scar', 'sum')).reset_index()
    cv['share'] = cv.done / cv.events; cv.to_csv(C.SC + 'coverage.csv', index=False)
    return cv


def forest_window(x0, y1, W, H):
    r = rasterio.open(C25.VTM)
    col0 = int(round((x0 - C25.VX0) / C.RES)); row0 = int(round((C25.VY1 - y1) / C.RES))
    A = r.read(1, window=Window(col0, row0, W, H), boundless=True, fill_value=0)
    return ((A >= 11) & (A <= 115)) | ((A >= 150) & (A <= 163)) | ((A >= 120) & (A <= 134))


def one_div(div):
    E, Ag = G['E'], G['Ag']
    Ed = E[E['div'] == div]
    xmin, ymin, xmax, ymax = Ed.total_bounds
    x0, y1, W, H = C25.snap_box(xmin - 3000, ymin - 3000, xmax + 3000, ymax + 3000)
    FOR = forest_window(x0, y1, W, H)
    fires, rows = [], []
    for fid, g in Ed.groupby('fire'):
        geom = shapely.union_all(g.geometry.values)
        D = pd.concat([Ag[e] for e in g.event_id if e in Ag]).sort_values('t')
        ign, fr, t0 = F1.starts(D)
        bx = geom.bounds
        c0 = max(int((bx[0] - x0) // C.RES) - 3, 0); c1 = min(int((bx[2] - x0) // C.RES) + 4, W)
        r0 = max(int((y1 - bx[3]) // C.RES) - 3, 0); r1 = min(int((y1 - bx[1]) // C.RES) + 4, H)
        Tl = Affine(C.RES, 0, x0 + c0 * C.RES, 0, -C.RES, y1 - r0 * C.RES)
        shp = (r1 - r0, c1 - c0)
        M = features.rasterize([(geom, 1)], out_shape=shp, transform=Tl, dtype='uint8').astype(bool)
        if M.sum() == 0: continue
        gd = g.assign(d=((g.t0 - t0) / pd.Timedelta(days=1)).clip(0, 250).astype(int)).sort_values('d', ascending=False)
        DY = features.rasterize([(gg, int(d) + 1) for gg, d in zip(gd.geometry, gd.d)], out_shape=shp, transform=Tl, dtype='uint8')
        rr, cc = np.nonzero(M)
        px = x0 + (c0 + cc + .5) * C.RES; py = y1 - (r0 + rr + .5) * C.RES
        tree = cKDTree(np.c_[px, py]); flat = rr * shp[1] + cc
        d, _ = cKDTree(ign).query(np.c_[px, py]); ig = flat[d <= 400]
        if len(ig) == 0: ig = flat[d <= 750]
        dd, ii = tree.query(ign); dotc = np.unique(flat[ii[dd <= 200]])
        dd2, ii2 = tree.query(D[['x', 'y']].values)
        th = ((D.t - t0) / pd.Timedelta(hours=1)).values.astype(np.float32)
        dots = np.c_[np.where(dd2 <= 200, flat[ii2], -1), th].astype(np.float32)
        day = (DY[rr, cc].astype(np.int16) - 1).clip(0, None).astype(np.uint8)
        fo = FOR[r0:r1, c0:c1][rr, cc]
        fires.append(dict(fire=f'{C.slug(div)}_{fid}', div=div, src=g.src.iloc[0], year=int(t0.year), t0=t0, r0=r0, c0=c0, M=np.packbits(M), shape=shp,
                          ign=ig.astype(np.int32), dotc=dotc.astype(np.int32), dots=dots, day=day, forest=np.packbits(fo), n_events=len(g),
                          ha=float(M.sum() * C.CELL_HA), forest_ha=float(fo.sum() * C.CELL_HA), n_dots=len(D)))
        rows.append(dict(fire=fires[-1]['fire'], div=div, src=g.src.iloc[0], year=int(t0.year), ha=fires[-1]['ha'], forest_ha=fires[-1]['forest_ha'], n_events=len(g)))
    pickle.dump(dict(div=div, x0=x0, y1=y1, W=W, H=H, fires=fires, forest=np.packbits(FOR)), open(C.SC + f'fires_{C.slug(div)}.pkl', 'wb'))
    print(div, len(fires), 'fires', round(sum(f['ha'] for f in fires)), 'ha', flush=True)
    return rows


def main(which):
    if which == 'rest':
        C25.SC = C.SC   # round-25 load_rest() writes its coverage_rest.csv to C25.SC: keep that in r26 scratch
        cv = coverage(); print(cv.groupby('year')[['events', 'done', 'scar']].sum().assign(share=lambda d: d.done / d.events), flush=True)
    E, A = F1.load() if which == 'core' else F1.load_rest()
    print('events', len(E), flush=True)
    E['fire'] = F1.chain(E)
    G['E'] = E; G['Ag'] = {k: g.sort_values('t') for k, g in A.groupby('event_id')}
    divs = sorted(E['div'].unique())
    with Pool(4) as p: rows = sum(p.map(one_div, divs, chunksize=1), [])
    pd.DataFrame(rows).to_csv(C.SC + f'fires_table_{which}.csv', index=False)


if __name__ == '__main__':
    main(sys.argv[1])
