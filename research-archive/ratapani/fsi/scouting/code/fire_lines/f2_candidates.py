"""Step 2. Static layers and candidate fire lines per division (60 m VTM lattice, EPSG:32643).
Layers: forest (VTM tree forest or scrub), elevation (AWS terrarium z10 ~140 m, bilinear, smoothed), Overture roads (2026-09),
beat boundaries (mp_beats), training spread flow (2017-21 fires only).
Candidate lines = 8-connected cell chains, cut into windows of 1, 2 and 4 km (every 0.5 km along the chain):
  road     - along existing Overture roads/tracks (merged at junctions)
  beat     - along beat boundaries
  valley   - D8 drainage lines with > 1 km2 upslope area
  ridge    - drainage lines of the flipped surface (> 1 km2 'upslope' = ridge crests)
  neck     - straight lines (1, 2, 3 km; 4 directions) through peaks of the 2017-21 spread-flow map (where many training
             fires passed through a narrow piece of forest)
  straight - baseline lattice: 2 km straight lines, 4 directions, centred every 2 km in forest
  random   - baseline: 3,000 random 2 km straight lines centred in forest (random direction)
Only windows with >= 60% forest cells and >= 80% inside the division polygon are kept.
Training spread flow uses the division's training seasons (common.years).
Out (scratch): cand_<div>.pkl (table + cells CSR + polyline cell chains), layers_<div>.npz (forest, flow, elev)."""
import pickle, sys, glob
import numpy as np, pandas as pd, geopandas as gpd, shapely, rasterio
from rasterio.windows import Window
from scipy.ndimage import map_coordinates, gaussian_filter, maximum_filter
import pyarrow.parquet as pq
import common as C, fl_lib as K

RNG = np.random.default_rng(25)


def layers(L):
    x0, y1, W, H = L['x0'], L['y1'], L['W'], L['H']
    r = rasterio.open(C.VTM)
    col0 = int(round((x0 - C.VX0) / C.RES)); row0 = int(round((C.VY1 - y1) / C.RES))
    A = r.read(1, window=Window(col0, row0, W, H), boundless=True, fill_value=0)
    forest = ((A >= 11) & (A <= 115)) | ((A >= 150) & (A <= 163)) | ((A >= 120) & (A <= 134))
    D = np.load(C.DEM); E = D['elev']; n = 256 * 2 ** 10
    cc, rr = np.meshgrid(np.arange(W), np.arange(H))
    lon, lat = C.TB.transform(x0 + (cc + .5) * C.RES, y1 - (rr + .5) * C.RES)
    px = (lon + 180) / 360 * n - .5 - 256 * int(D['x0'])
    py = (1 - np.arcsinh(np.tan(np.radians(lat))) / np.pi) / 2 * n - .5 - 256 * int(D['y0'])
    Ef = np.nan_to_num(E, nan=float(np.nanmean(E)))
    z = map_coordinates(Ef, [py.ravel(), px.ravel()], order=1, mode='nearest').reshape(H, W)
    z = gaussian_filter(z, 1.5)
    return forest, z, lon, lat


def flowmap(L, tr_years):
    F = np.zeros((L['H'], L['W']))
    for f in L['fires']:
        if f['year'] not in tr_years: continue
        M = np.unpackbits(f['M'])[:f['shape'][0] * f['shape'][1]].reshape(f['shape']).astype(bool)
        sub, seen = K.flow(M, f['ign'].astype(np.int64))
        F[f['r0']:f['r0'] + M.shape[0], f['c0']:f['c0'] + M.shape[1]] += sub * C.CELL_HA
    return F


def line_chain(g, L):
    """LineString (UTM) -> list of flat cells (8-connected, consecutive duplicates removed)."""
    g = shapely.segmentize(g, 15.0); xy = shapely.get_coordinates(g)
    c = np.floor((xy[:, 0] - L['x0']) / C.RES).astype(int); r = np.floor((L['y1'] - xy[:, 1]) / C.RES).astype(int)
    ok = (c >= 0) & (c < L['W']) & (r >= 0) & (r < L['H'])
    out = []
    # split where the line leaves the window
    cur = []
    for k in range(len(c)):
        if not ok[k]:
            if len(cur) > 1: out.append(cur)
            cur = []; continue
        f = r[k] * L['W'] + c[k]
        if not cur or cur[-1] != f: cur.append(f)
    if len(cur) > 1: out.append(cur)
    return [np.array(o, np.int64) for o in out]


def windows(chain, W, forest, kind, out, lens=(1.0, 2.0, 4.0)):
    if len(chain) < 2: return
    r, c = chain // W, chain % W
    step = np.hypot(np.diff(r), np.diff(c)) * C.RES / 1000
    cum = np.r_[0, np.cumsum(step)]; tot = cum[-1]
    fo = forest.ravel()[chain]
    if tot < 0.5: return
    for Lk in lens:
        if tot < Lk:
            if Lk == lens[0]:
                if fo.mean() >= .6: out.append((kind, tot, chain))
            continue
        for s in np.arange(0, tot - Lk + 1e-9, 0.5):
            i0 = np.searchsorted(cum, s); i1 = np.searchsorted(cum, s + Lk)
            seg = chain[i0:i1 + 1]
            if len(seg) > 1 and fo[i0:i1 + 1].mean() >= .6: out.append((kind, cum[min(i1, len(cum) - 1)] - cum[i0], seg))


def straight(L, xc, yc, th, Lkm):
    d = Lkm * 500.0
    g = shapely.LineString([(xc - d * np.cos(th), yc - d * np.sin(th)), (xc + d * np.cos(th), yc + d * np.sin(th))])
    return line_chain(g, L)


def main(div_key):
    L = pickle.load(open(C.SC + f'fires_{div_key}.pkl', 'rb')); W, H = L['W'], L['H']
    forest, z, lon, lat = layers(L)
    tr_years, _ = C.years(div_key)
    F = flowmap(L, tr_years)
    from rasterio import features as rf
    from rasterio.transform import Affine
    DV = gpd.read_file(C.P + 'fire-alert-scars/mp/out/mp_divisions.geojson').to_crs(32643)
    DV = DV[DV.Division.map(C.slug) == div_key]
    inside = rf.rasterize([(g, 1) for g in DV.geometry], out_shape=(H, W), transform=Affine(C.RES, 0, L['x0'], 0, -C.RES, L['y1']), dtype='uint8').astype(bool)
    forest_in = forest & inside
    cands = []
    bb = shapely.box(L['x0'], L['y1'] - H * C.RES, L['x0'] + W * C.RES, L['y1'])
    bb4326 = shapely.box(*gpd.GeoSeries([bb], crs=32643).to_crs(4326).total_bounds)
    # roads
    t = pq.read_table(C.ROADS); g = shapely.from_wkb(t.column('geometry').to_numpy(zero_copy_only=False))
    keep = shapely.intersects(g, bb4326)
    rg = gpd.GeoSeries(g[keep], crs=4326).to_crs(32643).values
    merged = shapely.line_merge(shapely.union_all(rg))
    for part in shapely.get_parts(merged):
        for ch in line_chain(part, L): windows(ch, W, forest, 'road', cands)
    nroad = len(cands); print(div_key, 'road windows', nroad, flush=True)
    # beats
    B = gpd.read_file(C.BEATS, bbox=tuple(bb4326.bounds)).to_crs(32643)
    bl = shapely.line_merge(shapely.union_all(shapely.boundary(B.geometry.values)))
    for part in shapely.get_parts(bl):
        for ch in line_chain(part, L): windows(ch, W, forest, 'beat', cands)
    print(div_key, 'beat windows', len(cands) - nroad, flush=True)
    # valleys / ridges
    for kind, zz in (('valley', z), ('ridge', -z)):
        rec = K.d8(zz.astype(np.float64)); acc = K.accum(zz.astype(np.float64), rec)
        chan = acc * C.CELL_HA / 100 >= 1.0
        cells, st = K.trace(chan, rec, W)
        n0 = len(cands)
        for a, b in zip(st[:-1], st[1:]): windows(cells[a:b], W, forest, kind, cands)
        print(div_key, kind, 'windows', len(cands) - n0, flush=True)
    # necks: peaks of the training flow map in forest
    pk = (F == maximum_filter(F, size=17)) & (F >= 50) & forest_in
    rr, cc = np.nonzero(pk); o = np.argsort(-F[rr, cc])[:400]; rr, cc = rr[o], cc[o]
    n0 = len(cands)
    for r_, c_ in zip(rr, cc):
        xc = L['x0'] + (c_ + .5) * C.RES; yc = L['y1'] - (r_ + .5) * C.RES
        for th in np.radians([0, 45, 90, 135]):
            for Lk in (1.0, 2.0, 3.0):
                for ch in straight(L, xc, yc, th, Lk):
                    if forest.ravel()[ch].mean() >= .6: cands.append(('neck', Lk, ch))
    print(div_key, 'neck lines', len(cands) - n0, flush=True)
    # straight lattice and random baselines
    n0 = len(cands)
    for r_ in range(17, H, 33):
        for c_ in range(17, W, 33):
            if not forest_in[r_, c_]: continue
            xc = L['x0'] + (c_ + .5) * C.RES; yc = L['y1'] - (r_ + .5) * C.RES
            for th in np.radians([0, 45, 90, 135]):
                for ch in straight(L, xc, yc, th, 2.0):
                    if forest.ravel()[ch].mean() >= .6: cands.append(('straight', 2.0, ch))
    fr, fc = np.nonzero(forest_in); k = 0; tries = 0
    while k < 3000 and tries < 20000:
        tries += 1; i = RNG.integers(len(fr))
        xc = L['x0'] + (fc[i] + RNG.random()) * C.RES; yc = L['y1'] - (fr[i] + RNG.random()) * C.RES
        for ch in straight(L, xc, yc, RNG.random() * np.pi, 2.0):
            if forest.ravel()[ch].mean() >= .6 and len(ch) > 20: cands.append(('random', 2.0, ch)); k += 1
    print(div_key, 'straight+random', len(cands) - n0, flush=True)
    ins = inside.ravel()
    cands = [c for c in cands if ins[c[2]].mean() >= 0.8]   # lines must lie (80%+) inside the division: scar data cover only it
    kinds = np.array([c[0] for c in cands]); km = np.array([c[1] for c in cands])
    ptr = np.r_[0, np.cumsum([len(c[2]) for c in cands])]; cells = np.concatenate([c[2] for c in cands])
    tab = pd.DataFrame(dict(kind=kinds, km=km, n=np.diff(ptr)))
    pickle.dump(dict(tab=tab, ptr=ptr, cells=cells), open(C.SC + f'cand_{div_key}.pkl', 'wb'))
    np.savez_compressed(C.SC + f'layers_{div_key}.npz', forest=forest, inside=inside, flow=F.astype(np.float32), elev=z.astype(np.float32))
    print(div_key, tab.groupby('kind').km.agg(['size', 'sum']).to_dict(), flush=True)


if __name__ == '__main__':
    for k in (sys.argv[1:] or [p.split('fires_')[1][:-4] for p in sorted(glob.glob(C.SC + 'fires_*.pkl'))]):
        main(k)
