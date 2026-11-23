"""Step 7. Practical lines: every candidate cut is a least-cost path across the compartment that follows natural barriers and
access, instead of a straight chord. Cost per 60 m cell (lower = better ground for a line): existing road or track 0.20, valley /
nala line (D8 drainage > 1 km2) 0.30, forest edge 0.40, open ground 0.50, ridge crest 0.50, forest interior 1.00. The path's two
ends are where a chord (8 directions, offsets across the compartment) meets the compartment edge; the path itself is found with
Dijkstra inside the compartment plus a 120 m margin beyond the patch edge (never into another compartment). The round-25 ridge,
valley and track chains are candidates as before. Choice, scoring and the held-out test are those of m2 (objective = drop the best
training year; 'finalnat' = all nine seasons). Each cut records how much of its length lies on each kind of ground.
Run: python m7_natural.py tr3 lonat [div ...] | python m7_natural.py all5 finalnat     Out: scratch r28/cuts_<pset>_<obj>_<div>.pkl"""
import pickle, sys, glob, heapq, time, os
os.environ.setdefault('OMP_NUM_THREADS', '1')
import pyarrow as pa; pa.set_cpu_count(1); pa.set_io_thread_count(1)
import numpy as np
from scipy import ndimage as ndi
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import dijkstra
from multiprocessing import Pool
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import m0 as M
K = M.K
from k1_cuts import Patch, split, chord, runs, chain_km, terrain_chains   # noqa: E402
from m2_cuts import fires_by_patch   # noqa: E402

COST = {'road': 0.20, 'valley': 0.30, 'edge': 0.40, 'open': 0.50, 'ridge': 0.50, 'forest': 1.00}
KINDS = ('road', 'valley', 'edge', 'open', 'ridge', 'forest')
END_R = 3          # a path's ends may slide up to 3 cells (180 m) along the compartment edge from where the chord meets it
GRADE_K = 5.0     # a 20% grade along the line doubles its cost (lines run along contours, crests and nala floors, not up slopes)
N8 = [(-1, -1, 1.4142), (-1, 0, 1.0), (-1, 1, 1.4142), (0, -1, 1.0), (0, 1, 1.0), (1, -1, 1.4142), (1, 0, 1.0), (1, 1, 1.4142)]


def cost_raster(L, FOR, chains):
    """cost (H, W) and kind code (H, W) on the division grid, from the DEM (nala lines = D8 drainage >= 0.1 km2, ridge crests =
    the same on the flipped surface >= 0.2 km2), every Overture road/track rasterised, VTM forest edge and open ground."""
    from scipy.ndimage import map_coordinates, gaussian_filter
    import pyarrow.parquet as pq, shapely, geopandas as gpd
    from rasterio import features as rf
    from rasterio.transform import Affine
    from fl_lib import d8, accum
    C = K.C25; H, W = L['H'], L['W']; x0, y1 = L['x0'], L['y1']; F = FOR.reshape(H, W)
    kind = np.full((H, W), 5, np.int8)
    kind[~F] = 3
    edge = F & ~ndi.binary_erosion(F, np.array([[0, 1, 0], [1, 1, 1], [0, 1, 0]], bool), border_value=1)
    kind[edge] = 2
    # terrain
    D = np.load(C.DEM); E = D['elev']; n = 256 * 2 ** 10
    cc, rr = np.meshgrid(np.arange(W), np.arange(H))
    lon, lat = C.TB.transform(x0 + (cc + .5) * C.RES, y1 - (rr + .5) * C.RES)
    px = (lon + 180) / 360 * n - .5 - 256 * int(D['x0']); py = (1 - np.arcsinh(np.tan(np.radians(lat))) / np.pi) / 2 * n - .5 - 256 * int(D['y0'])
    Ef = np.nan_to_num(E, nan=float(np.nanmean(E)))
    z = gaussian_filter(map_coordinates(Ef, [py.ravel(), px.ravel()], order=1, mode='nearest').reshape(H, W), 1.0)
    for kd, zz, thr, code in (('ridge', -z, 0.2, 4), ('valley', z, 0.1, 1)):
        rec = d8(zz.astype(np.float64)); acc = accum(zz.astype(np.float64), rec)
        chan = (acc * C.CELL_HA / 100 >= thr).reshape(H, W)
        if code == 4: kind[chan & (kind == 5)] = 4
        else: kind[chan & (kind >= 2)] = 1
    # roads / tracks
    try:
        bb = shapely.box(x0, y1 - H * C.RES, x0 + W * C.RES, y1)
        bb4326 = shapely.box(*gpd.GeoSeries([bb], crs=32643).to_crs(4326).total_bounds)
        t = pq.read_table(C.ROADS); g = shapely.from_wkb(t.column('geometry').to_numpy(zero_copy_only=False))
        keep = shapely.intersects(g, bb4326)
        rg = gpd.GeoSeries(g[keep], crs=4326).to_crs(32643).values
        if len(rg):
            rm = rf.rasterize([(gg, 1) for gg in rg], out_shape=(H, W), transform=Affine(C.RES, 0, x0, 0, -C.RES, y1), dtype='uint8', all_touched=True).astype(bool)
            kind[rm] = 0
    except Exception as e:
        print('roads failed', e, flush=True)
    cost = np.array([COST[k] for k in KINDS], float)[kind]
    return cost, kind, z


class Graph:
    """8-connected weighted graph over the allowed cells of one compartment crop."""
    def __init__(self, allow, cost, z):
        h, w = allow.shape; idx = -np.ones(allow.size, np.int64); nodes = np.nonzero(allow.ravel())[0]; idx[nodes] = np.arange(len(nodes))
        self.idx = idx; self.nodes = nodes; self.h, self.w = h, w
        rr, cc = nodes // w, nodes % w; cf = cost.ravel(); zf = z.ravel(); src = []; dst = []; wt = []
        for dr, dc, st in N8:
            r2 = rr + dr; c2 = cc + dc; ok = (r2 >= 0) & (r2 < h) & (c2 >= 0) & (c2 < w)
            j = np.where(ok, r2 * w + c2, 0); ok &= idx[j] >= 0
            grade = np.abs(zf[nodes[ok]] - zf[j[ok]]) / (st * K.RES)          # rise over run along the move
            src.append(np.arange(len(nodes))[ok]); dst.append(idx[j[ok]]); wt.append(0.5 * (cf[nodes[ok]] + cf[j[ok]]) * st * (1.0 + GRADE_K * grade))
        n = len(nodes)
        self.G = coo_matrix((np.concatenate(wt), (np.concatenate(src), np.concatenate(dst))), shape=(n, n)).tocsr()

    def path(self, A, B):
        """cheapest path from any cell of A to any cell of B (flat local indices)."""
        ia = self.idx[A]; ia = ia[ia >= 0]; ib = self.idx[B]; ib = ib[ib >= 0]
        if len(ia) == 0 or len(ib) == 0: return None
        d, pred, srcs = dijkstra(self.G, indices=ia, return_predecessors=True, min_only=True)
        if not np.isfinite(d[ib]).any(): return None
        t = ib[int(np.argmin(d[ib]))]; p = [t]
        while pred[p[-1]] >= 0: p.append(pred[p[-1]])
        g = self.nodes[np.array(p[::-1])]
        return g // self.w, g % self.w


def gen_cands_nat(pt, cid, chains, cost_loc, kind_loc, z_loc):
    R = pt.comp == cid; rr, cc = np.nonzero(R)
    if len(rr) < 2 * int(np.ceil(K.MIN_PIECE_HA / K.CELL_HA)): return []
    allow = (pt.comp == cid) | (pt.ext[cid] & ~pt.P & ~pt.line)
    allow &= ~pt.line
    gr = Graph(allow, cost_loc, z_loc)
    bnd = R & ~ndi.binary_erosion(R, np.ones((3, 3), bool), border_value=0); br, bc = np.nonzero(bnd); bflat = br * R.shape[1] + bc
    ctr = np.array([cc.mean(), rr.mean()]); half = np.hypot(*R.shape) + 4
    out = []; seen = set(); seen_ends = set()

    def add(r, c, kd):
        st = pt.status(r, c, cid)
        for a, b in runs(r, c, st):
            keyc = np.sort(a.astype(np.int64) * 100000 + b).tobytes()
            if keyc in seen: continue
            seen.add(keyc)
            if pt.valid(a, b, cid) is None: continue
            kk = kind_loc[a, b]; stp = np.r_[0.06, np.hypot(np.diff(a), np.diff(b)) * K.RES / 1000]
            feat = {k: float(stp[kk == i].sum()) for i, k in enumerate(KINDS)}
            zz = z_loc[a, b]; gr_ = np.abs(np.diff(zz)) / np.maximum(stp[1:] * 1000, 1)
            feat['grade_mean'] = float(gr_.mean()) if len(gr_) else 0.0; feat['km_steep'] = float(stp[1:][gr_ > 0.15].sum())
            out.append((a, b, chain_km(a, b), kd, feat))
    for th in np.radians(K.ANGLES):
        nv = np.array([-np.sin(th), np.cos(th)]); pr = (np.c_[cc, rr] - ctr) @ nv
        step = max(3.0, (pr.max() - pr.min()) / 12)
        for off in np.arange(pr.min() + 1.5, pr.max() - 1, step):
            r, c = chord(ctr, th, off, half)
            h, w = R.shape; ok = (r >= 0) & (r < h) & (c >= 0) & (c < w)
            r, c = r[ok], c[ok]
            inside = np.nonzero(R[r, c])[0]
            if len(inside) < 2: continue
            a = r[inside[0]] * w + c[inside[0]]; b = r[inside[-1]] * w + c[inside[-1]]
            if (a, b) in seen_ends: continue
            seen_ends.add((a, b))
            dA = np.hypot(br - r[inside[0]], bc - c[inside[0]]); dB = np.hypot(br - r[inside[-1]], bc - c[inside[-1]])
            A = bflat[(dA <= END_R) & (dA < dB)]; B = bflat[(dB <= END_R) & (dB < dA)]
            p = gr.path(A, B)
            if p is None: continue
            add(p[0], p[1], 'path')
    for kd, r, c in chains:
        r = r - pt.rb; c = c - pt.cb; h, w = R.shape
        if not ((r >= 0) & (r < h) & (c >= 0) & (c < w)).any(): continue
        add(r, c, kd)
    return out


def run_patch(p, LAB, FORg, F, fires_p, LM, W, chains, obj, Fte, fires_te, COSTg, KINDg, Zg):
    rows, cols = np.nonzero(LAB == p)
    m = K.EXT + 2
    r0, r1 = max(rows.min() - m, 0), min(rows.max() + m + 1, LAB.shape[0]); c0, c1 = max(cols.min() - m, 0), min(cols.max() + m + 1, LAB.shape[1])
    P = LAB[r0:r1, c0:c1] == p; cost_loc = COSTg[r0:r1, c0:c1]; kind_loc = KINDg[r0:r1, c0:c1]; z_loc = Zg[r0:r1, c0:c1]
    pt = Patch(P, r0, c0, W); pt.ext = {}
    for cid in range(1, pt.ncomp + 1): pt.set_ext(cid)
    LABf = LAB.ravel(); args = F.args()
    fids = np.asarray(fires_p, np.int64)
    TRY = M.ALL if obj == 'finalnat' else M.TRAIN; objn = 'lo'
    yi = np.searchsorted(np.array(TRY), F.year[fids]); ny = len(TRY)

    def ev(cells_g):
        LM[cells_g] = True
        o = np.zeros((len(fids), 6)); K.eval_fires(fids, *args, W, LM, LABf, FORg, p, K.P_STOP, o); LM[cells_g] = False
        return o

    def per_year(o): return np.bincount(yi, weights=o[:, 0], minlength=ny) * M.CELL_HA

    def glob_(r, c): return (r + r0) * W + (c + c0)
    cur_cells = np.zeros(0, np.int64); cur_o = np.zeros((len(fids), 6)); cur_sy = np.zeros(ny); cur_obj = 0.0
    cands = {}; heap = []; cnt = 0; step = 0

    def gain(r, c):
        o = ev(np.r_[cur_cells, glob_(r, c)]); sy = per_year(o)
        return M.objective(sy, objn) - cur_obj, o, sy

    def push(cid):
        nonlocal cnt
        for (r, c, km, kind, feat) in gen_cands_nat(pt, cid, chains, cost_loc, kind_loc, z_loc):
            cands[cnt] = (cid, r, c, km, kind, feat)
            g, o, sy = gain(r, c); heapq.heappush(heap, (-g / km, cnt, step, g)); cnt += 1
    for cid in range(1, pt.ncomp + 1): push(cid)
    seq = []
    while heap and len(seq) < K.MAX_CUTS:
        ng, k, st, g = heapq.heappop(heap)
        cid, r, c, km, kind, feat = cands[k]
        if (pt.comp == cid).sum() == 0: continue
        if st != step:
            g, o, sy = gain(r, c); heapq.heappush(heap, (-g / km, k, step, g)); continue
        if g <= 1e-9: break
        if pt.valid(r, c, cid) is None: continue
        new = split(pt, r, c, cid)
        cg = glob_(r, c); cur_cells = np.r_[cur_cells, cg]
        cur_o = ev(cur_cells); cur_sy = per_year(cur_o); cur_obj = M.objective(cur_sy, objn)
        step += 1
        ncomp = int((np.unique(pt.comp[pt.comp > 0])).size)
        seq.append(dict(cells=cg.astype(np.int64), km=km, kind=kind, feat=feat, g=g, sy=cur_sy.copy(), obj=cur_obj,
                        train_mean=(cur_o.sum(0) * M.CELL_HA / ny)[:3], n_after=ncomp))
        for cid2 in new: pt.set_ext(cid2)
        for cid2 in new: push(cid2)
    res = dict(patch=int(p), seq=seq, n_patch_cells=int(P.sum()), box=(r0, r1, c0, c1), n_fires=len(fids), n_fires_test=len(fires_te))
    ft = np.asarray(fires_te, np.int64); args_te = Fte.args(); cells = np.zeros(0, np.int64)
    te_cum = np.zeros((len(seq), len(M.PS), 3)); te_fire = np.zeros((len(seq), len(ft)), np.float32)
    for i, s in enumerate(seq):
        cells = np.r_[cells, s['cells']]; LM[cells] = True
        for j, pp in enumerate(M.PS):
            o = np.zeros((len(ft), 6)); K.eval_fires(ft, *args_te, W, LM, LABf, FORg, p, pp, o)
            te_cum[i, j] = o.sum(0)[:3] * M.CELL_HA / len(M.TEST)
            if pp == K.P_STOP: te_fire[i] = o[:, 0] * M.CELL_HA
        LM[cells] = False
    res['test_cum'] = te_cum; res['test_fire'] = te_fire; res['test_fids'] = ft; res['test_year'] = Fte.year[ft] if len(ft) else np.zeros(0, int)
    return res


def main(args):
    key, pset, obj = args
    fn = M.SC + f'cuts_{pset}_{obj}_{key}.pkl'
    if os.path.exists(fn): return key
    t0 = time.time()
    L, FOR, Z = K.load_div(key); H, W = L['H'], L['W']
    LAB = M.labels(Z, pset, H, W); npat = int(LAB.max())
    if npat == 0:
        pickle.dump(dict(key=key, div=L['div'], patches=[]), open(fn, 'wb')); return key
    yrs = np.array([f['year'] for f in L['fires']])
    F = K.Fires(L, np.nonzero(np.isin(yrs, M.ALL if obj == 'finalnat' else M.TRAIN))[0]); Fte = K.Fires(L, np.nonzero(np.isin(yrs, M.TEST))[0])
    FORg = FOR.copy(); LABf = LAB.ravel()
    fp = fires_by_patch(F, LABf, FORg, W); fpt = fires_by_patch(Fte, LABf, FORg, W)
    chains = terrain_chains(key, L)
    COSTg, KINDg, Zg = cost_raster(L, FOR, chains)
    LM = np.zeros(H * W, bool); out = []
    for p in range(1, npat + 1):
        if p not in fp: continue
        out.append(run_patch(p, LAB, FORg, F, fp[p], LM, W, chains, obj, Fte, fpt.get(p, []), COSTg, KINDg, Zg))
    patch_ha = {int(p): float(((LABf == p) & FORg).sum() * M.CELL_HA) for p in range(1, npat + 1)}
    pickle.dump(dict(key=key, div=L['div'], W=W, H=H, x0=L['x0'], y1=L['y1'], patches=out, patch_ha=patch_ha,
                     test_forest_ha=float(Fte.forest_ha.sum()), n_test=Fte.n, test_year=Fte.year), open(fn, 'wb'))
    ncut = sum(len(r['seq']) for r in out); km = sum(s['km'] for r in out for s in r['seq'])
    feat = {k: sum(s['feat'][k] for r in out for s in r['seq']) for k in KINDS + ('km_steep',)}
    print(key, pset, obj, npat, 'patches', ncut, 'cuts', round(km, 1), 'km', {k: round(v / max(km, 1e-9), 2) for k, v in feat.items()}, round(time.time() - t0), 's', flush=True)
    return key


if __name__ == '__main__':
    pset, obj = sys.argv[1], sys.argv[2]
    keys = sys.argv[3:] or sorted(p.split('cuts_tr3_')[1][:-4] for p in glob.glob(M.SC27 + 'cuts_tr3_*.pkl'))
    keys = sorted(keys, key=lambda k: -os.path.getsize(M.SC26 + f'fires_{k}.pkl'))
    with Pool(4) as pool: pool.map(main, [(k, pset, obj) for k in keys], chunksize=1)
