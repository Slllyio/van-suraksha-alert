"""Step 4. Held-out test of entry-side lines (patches, entries and lines from 2017-21 only; scored on 2022-25 fires).
Benefit of a line for a test fire = round-25 rule: ground the fire could reach from its start (round-25 start cells) only by crossing
the line, inside its own outline, x stop chance (0.35; 1.0 = upper bound). Reported two ways:
  all ha   - all protected ground of the fire (comparable with round 25)
  patch ha - protected forest inside the line's own patch (Akkshay's question: does the line save the patch?)
Line sets per division: entry (the proposed entry-segment lines), ring (whole perimeter of the same patches), road (nearest existing
road/track window to each entry segment), rand_edge (another edge segment of the same patch, 200 draws), r25_same_km (round-25 plan
lines, first lines up to the same km), r25_20km. 95% ranges: resample test fires within each division (1,000 times).
Run: python r4_test.py tr3 (held-out) ; python r4_test.py all5 (final list, in-sample over 2017-25).
Out (scratch r26): test_<set>_<div>.pkl"""
import pickle, glob, sys
import numpy as np, pandas as pd
from multiprocessing import Pool
import c26 as C
import f3_select as S3

RNG = np.random.default_rng(4)
PS = (0.35, 1.0)


def regrid(cells, g_old, L):
    r, c = cells // g_old['W'], cells % g_old['W']
    r = r + int(round((L['y1'] - g_old['y1']) / C.RES)); c = c + int(round((g_old['x0'] - L['x0']) / C.RES))
    ok = (r >= 0) & (r < L['H']) & (c >= 0) & (c < L['W'])
    return (r[ok] * L['W'] + c[ok]).astype(np.int64)


def one(key, pset='tr3'):
    S = pd.read_parquet(C.SC + f'patches_{pset}.parquet'); S = S[(S.key == key) & S.consistent]
    if not len(S): return None
    RG = pickle.load(open(C.SC + f'rings_{pset}.pkl', 'rb')); rings = RG['rings'][key]; meta = RG['meta'][key]
    L = pickle.load(open(C.SC + f'fires_{key}.pkl', 'rb')); H, W = L['H'], L['W']
    FOR = np.unpackbits(L['forest'])[:H * W].astype(bool)
    lab = np.load(C.SC + f'patches_{key}.npz')['lab_' + pset]
    lab60 = np.kron(lab, np.ones((C.AGG, C.AGG), np.int32))[:H, :W].ravel()
    lines = []   # (method, patch, cells, km, extra)
    for _, s in S.iterrows():
        p = int(s.patch); ring, seg = rings[p]; m = int(s.mode_seg)
        lines.append(('entry', p, ring[seg == m], meta[p]['seg_km'][m], dict(seg=m)))
        lines.append(('ring', p, ring, meta[p]['ring_km'], {}))
        for o in range(meta[p]['nseg']):
            if o != m: lines.append(('edge_other', p, ring[seg == o], meta[p]['seg_km'][o], dict(seg=o)))
    # nearest road window (round-25 candidates)
    try:
        cand25 = pickle.load(open(C.SC25 + f'cand_{key}.pkl', 'rb')); R25 = pickle.load(open(C.SC25 + f'sel_{key}.pkl', 'rb'))
    except FileNotFoundError:
        cand25 = R25 = None
    if cand25 is not None:
        g25 = R25['grid']; tab = cand25['tab']; rk = np.nonzero((tab.kind == 'road').values)[0]
        ctr = np.array([cand25['cells'][cand25['ptr'][k]:cand25['ptr'][k + 1]].mean() for k in rk]) if len(rk) else np.zeros(0)
        rc = np.array([[np.mean(cand25['cells'][cand25['ptr'][k]:cand25['ptr'][k + 1]] % g25['W']), np.mean(cand25['cells'][cand25['ptr'][k]:cand25['ptr'][k + 1]] // g25['W'])] for k in rk]) if len(rk) else np.zeros((0, 2))
        dc = (g25['x0'] - L['x0']) / C.RES; dr = (L['y1'] - g25['y1']) / C.RES
        for (mth, p, cells, km, ex) in [l for l in lines if l[0] == 'entry']:
            cx, cy = (cells % W).mean(), (cells // W).mean()
            if len(rk) == 0: continue
            d = np.hypot(rc[:, 0] + dc - cx, rc[:, 1] + dr - cy) * C.RES
            j = np.argmin(d + 1000 * np.abs(tab.km.values[rk] - km))   # nearest, preferring a similar length
            if d[j] <= 2000:
                k = rk[j]; lines.append(('road', p, regrid(cand25['cells'][cand25['ptr'][k]:cand25['ptr'][k + 1]], g25, L), float(tab.km.values[k]), dict(road_dist_m=float(d[j]))))
        plan = R25['sel']['plan']; ent_km = sum(l[3] for l in lines if l[0] == 'entry')
        for tag, budget in (('r25_same_km', ent_km), ('r25_20km', 20.0)):
            t = 0.0
            for k in plan:
                ln = R25['lines'][k]
                if t + ln['km'] > budget * 1.1 and t > 0: break
                lines.append((tag, -1, regrid(ln['cells'], g25, L), float(ln['km']), {})); t += ln['km']
    cand = dict(ptr=np.r_[0, np.cumsum([len(l[2]) for l in lines])].astype(np.int64), cells=np.concatenate([l[2] for l in lines]).astype(np.int64))
    yrs = np.array([f['year'] for f in L['fires']])
    out = dict(key=key, div=L['div'], lines=[(l[0], l[1], l[3], l[4]) for l in lines])
    for per, ys in ((('test', C.TEST), ('train', C.TRAIN)) if pset.startswith('tr') else (('all', C.ALL),)):
        F = S3.Fires(L, np.nonzero(np.isin(yrs, ys))[0])
        P = F.protect(cand, np.arange(len(lines)), 1)
        nf = len(F.idx)
        # per line, per fire saved (all / patch) at p=1 (single line: value = p * cells)
        allv = np.zeros((len(lines), nf)); patv = np.zeros((len(lines), nf))
        for k, lst in P.items():
            p = lines[k][1]
            for f, cl in lst:
                allv[k, f] = cl.size * C.CELL_HA
                if p > 0:
                    g = (cl // F.W[f] + F.r0[f]) * W + (cl % F.W[f] + F.c0[f]); patv[k, f] = ((lab60[g] == p) & FOR[g]).sum() * C.CELL_HA
        # combined sets (cells saved unless every cutting line fails)
        comb = {}
        for mth in ('entry', 'ring', 'road', 'r25_same_km', 'r25_20km'):
            ks = [k for k, l in enumerate(lines) if l[0] == mth]
            for pstop in PS:
                va = np.zeros(nf); vp = np.zeros(nf); Sx = {}
                for k in ks:
                    for f, cl in P.get(k, []):
                        Sx.setdefault(f, np.ones(F.H[f] * F.W[f]))[cl] *= (1 - pstop)
                pats = set(l[1] for l in lines if l[0] == 'entry')
                for f, s in Sx.items():
                    loc = np.nonzero(s < 1)[0]; va[f] = (1 - s[loc]).sum() * C.CELL_HA
                    g = (loc // F.W[f] + F.r0[f]) * W + (loc % F.W[f] + F.c0[f]); inp = np.isin(lab60[g], list(pats)) & FOR[g]
                    vp[f] = (1 - s[loc][inp]).sum() * C.CELL_HA
                comb[(mth, pstop)] = (va, vp, sum(l[3] for l in lines if l[0] == mth))
        # random other edge segment of the same patch: 200 draws, one per patch per draw (single segment per patch, so no overlap)
        pts = sorted(set(l[1] for l in lines if l[0] == 'entry'))
        oth = {p: [k for k, l in enumerate(lines) if l[0] == 'edge_other' and l[1] == p] for p in pts}
        for pstop in PS:
            va = np.zeros(nf); vp = np.zeros(nf); kmt = 0.0; nd = 200
            for d in range(nd):
                for p in pts:
                    if not oth[p]: continue
                    k = oth[p][RNG.integers(len(oth[p]))]
                    va += allv[k] * pstop; vp += patv[k] * pstop; kmt += lines[k][3]
            comb[('rand_edge', pstop)] = (va / nd, vp / nd, kmt / nd)
        out[per] = dict(fire_ha=F.ha, fire_year=F.year, allv=allv, patv=patv, comb=comb, n=nf)
    pickle.dump(out, open(C.SC + f'test_{pset}_{key}.pkl', 'wb'))
    t = out['test' if pset.startswith('tr') else 'all']; ny = len(C.TEST if pset.startswith('tr') else C.ALL)
    print(key, len(S), 'lines', {m: round(t['comb'][(m, 0.35)][0].sum() / max(t['comb'][(m, 0.35)][2], 1e-9) / ny, 2) for m in ('entry', 'ring', 'road', 'rand_edge', 'r25_same_km', 'r25_20km')}, flush=True)
    return key


def run(args):
    return one(*args)


if __name__ == '__main__':
    pset = sys.argv[1]
    S = pd.read_parquet(C.SC + f'patches_{pset}.parquet'); keys = sys.argv[2:] or sorted(S[S.consistent].key.unique())
    with Pool(4) as p: p.map(run, [(k, pset) for k in keys], chunksize=1)
