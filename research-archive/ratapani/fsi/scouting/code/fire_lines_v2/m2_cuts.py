"""Step 2. Compartment cuts inside repeat patches, chosen greedily on 2017-21 with a chosen objective, scored on 2022-25.
Same candidates, validity rule and lazy greedy as round-27 k1_cuts.py. New: (a) objective = sum | med | lo over the five training
years (m0.objective); (b) patch set tr3 or tr2; (c) held-out prefixes scored at p = 0.35 / 0.70 / 1.0, with per-fire test values at
p = 0.35 kept for fire bootstraps; (d) per-year training saving kept per prefix.
Run: python m2_cuts.py <pset> <obj> [div ...]      Out (scratch r28): cuts_<pset>_<obj>_<div>.pkl"""
import pickle, sys, glob, heapq, time, os
import numpy as np
from multiprocessing import Pool
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import m0 as M
K = M.K
from k1_cuts import Patch, gen_cands, split, terrain_chains   # noqa: E402


def run_patch(p, LAB, FORg, F, fires_p, LM, W, chains, obj, Fte, fires_te):
    rows, cols = np.nonzero(LAB == p)
    m = K.EXT + 2
    r0, r1 = max(rows.min() - m, 0), min(rows.max() + m + 1, LAB.shape[0]); c0, c1 = max(cols.min() - m, 0), min(cols.max() + m + 1, LAB.shape[1])
    P = LAB[r0:r1, c0:c1] == p
    pt = Patch(P, r0, c0, W); pt.ext = {}
    for cid in range(1, pt.ncomp + 1): pt.set_ext(cid)
    LABf = LAB.ravel(); args = F.args()
    fids = np.asarray(fires_p, np.int64)
    TRY = M.TEST if obj == 'oracle' else (M.ALL if obj == 'final' else M.TRAIN)   # 'oracle' = cuts chosen on the test fires themselves (hindsight ceiling); 'final' = all nine seasons, drop-best-year objective (the plan)
    objn = 'sum' if obj == 'oracle' else ('lo' if obj == 'final' else obj)
    yi = np.searchsorted(np.array(TRY), F.year[fids]); ny = len(TRY)

    def ev(cells_g):
        LM[cells_g] = True
        o = np.zeros((len(fids), 6)); K.eval_fires(fids, *args, W, LM, LABf, FORg, p, K.P_STOP, o); LM[cells_g] = False
        return o

    def per_year(o):
        return np.bincount(yi, weights=o[:, 0], minlength=ny) * M.CELL_HA / 1.0   # ha saved per year (patch forest, p = 0.35)

    def glob_(r, c): return (r + r0) * W + (c + c0)
    cur_cells = np.zeros(0, np.int64); cur_o = np.zeros((len(fids), 6)); cur_sy = np.zeros(ny); cur_obj = 0.0
    cands = {}; heap = []; cnt = 0; step = 0

    def gain(r, c):
        o = ev(np.r_[cur_cells, glob_(r, c)]); sy = per_year(o)
        return M.objective(sy, objn) - cur_obj, o, sy

    def push(cid):
        nonlocal cnt
        for (r, c, km, kind) in gen_cands(pt, cid, chains):
            cands[cnt] = (cid, r, c, km, kind)
            g, o, sy = gain(r, c); heapq.heappush(heap, (-g / km, cnt, step, g)); cnt += 1
    for cid in range(1, pt.ncomp + 1): push(cid)
    seq = []
    while heap and len(seq) < K.MAX_CUTS:
        ng, k, st, g = heapq.heappop(heap)
        cid, r, c, km, kind = cands[k]
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
        seq.append(dict(cells=cg.astype(np.int64), km=km, kind=kind, g=g, sy=cur_sy.copy(), obj=cur_obj,
                        train_mean=(cur_o.sum(0) * M.CELL_HA / ny)[:3], n_after=ncomp))
        for cid2 in new: pt.set_ext(cid2)
        for cid2 in new: push(cid2)
    res = dict(patch=int(p), seq=seq, n_patch_cells=int(P.sum()), box=(r0, r1, c0, c1), n_fires=len(fids), n_fires_test=len(fires_te))
    # held-out prefixes
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


def fires_by_patch(FF, LABf, FORg, W):
    d = {}
    for f in range(FF.n):
        o = FF.off[f]; h, w = FF.H[f], FF.W[f]
        loc = np.nonzero(FF.D[o:o + h * w])[0]
        g = (loc // w + FF.r0[f]) * W + (loc % w + FF.c0[f])
        lb = LABf[g][FORg[g]]
        for p in np.unique(lb[lb > 0]): d.setdefault(int(p), []).append(f)
    return d


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
    F = K.Fires(L, np.nonzero(np.isin(yrs, M.TEST if obj == 'oracle' else (M.ALL if obj == 'final' else M.TRAIN)))[0]); Fte = K.Fires(L, np.nonzero(np.isin(yrs, M.TEST))[0])
    FORg = FOR.copy(); LABf = LAB.ravel()
    fp = fires_by_patch(F, LABf, FORg, W); fpt = fires_by_patch(Fte, LABf, FORg, W)
    chains = terrain_chains(key, L)
    LM = np.zeros(H * W, bool); out = []
    for p in range(1, npat + 1):
        if p not in fp: continue
        out.append(run_patch(p, LAB, FORg, F, fp[p], LM, W, chains, obj, Fte, fpt.get(p, [])))
    patch_ha = {int(p): float(((LABf == p) & FORg).sum() * M.CELL_HA) for p in range(1, npat + 1)}
    pickle.dump(dict(key=key, div=L['div'], W=W, H=H, x0=L['x0'], y1=L['y1'], patches=out, patch_ha=patch_ha,
                     test_forest_ha=float(Fte.forest_ha.sum()), n_test=Fte.n, test_year=Fte.year), open(fn, 'wb'))
    ncut = sum(len(r['seq']) for r in out); km = sum(s['km'] for r in out for s in r['seq'])
    print(key, pset, obj, npat, 'patches', ncut, 'cuts', round(km, 1), 'km', round(time.time() - t0), 's', flush=True)
    return key


if __name__ == '__main__':
    pset, obj = sys.argv[1], sys.argv[2]
    keys = sys.argv[3:] or sorted(p.split('cuts_tr3_')[1][:-4] for p in glob.glob(M.SC27 + 'cuts_tr3_*.pkl'))
    keys = sorted(keys, key=lambda k: -os.path.getsize(M.SC26 + f'fires_{k}.pkl'))
    with Pool(4) as pool: pool.map(main, [(k, pset, obj) for k in keys], chunksize=1)
