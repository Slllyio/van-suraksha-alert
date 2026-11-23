"""Step 1. Internal cut lines that split each repeat-burn patch into compartments, chosen greedily on the defining seasons.
Patches: round-26 sets 'tr3' (burnt in >= 3 of 5 seasons 2017-21; cuts chosen on 2017-21 fires, scored later on 2022-25) and
'all5' (>= 5 of 9 seasons 2017-25; final in-sample list on 2017-25 fires).
Candidate cuts inside a compartment (8-connected cell chains, 60 m VTM lattice):
  straight - chords at 8 directions (every 22.5 deg), offsets every max(2 cells, width/30) across the compartment
  ridge / valley / track - round-25 ridge, valley and Overture road/track chains, where they cross the compartment
Each run of a chain inside the compartment (plus up to 2 cells beyond the patch edge, never into another compartment) is one
candidate if removing it leaves >= 2 pieces of >= 2 ha. Length = chain length (60 m steps, 85 m diagonal).
Greedy (lazy): repeatedly add the cut with the most extra repeat-patch forest saved per km per year (k0 scoring rule, p = 0.35,
only this patch's cuts, only this patch's forest) until no cut saves anything or 20 cuts. n = compartments (pieces >= 2 ha).
Recorded per cut: marginal saved (patch / forest / ground, p = 0.35 and 1.0, per year), km, kind, compartments after.
tr3 also: the same prefixes scored on 2022-25 fires (per patch, independent of other patches), and 5 random cut sequences per patch
(random direction and offset, same validity rule, no fire data) for the random-cut baseline.
Run: python k1_cuts.py tr3|all5 [div ...]   Out (scratch r27): cuts_<set>_<div>.pkl"""
import pickle, sys, glob, heapq, time
import numpy as np, pandas as pd
from scipy import ndimage as ndi
from multiprocessing import Pool
import k0 as K

MINC = int(np.ceil(K.MIN_PIECE_HA / K.CELL_HA))
S4 = np.array([[0, 1, 0], [1, 1, 1], [0, 1, 0]], bool)


def regrid(cells, g_old, L):
    r, c = cells // g_old['W'], cells % g_old['W']
    r = r + int(round((L['y1'] - g_old['y1']) / K.RES)); c = c + int(round((g_old['x0'] - L['x0']) / K.RES))
    ok = (r >= 0) & (r < L['H']) & (c >= 0) & (c < L['W'])
    return r, c, ok


def terrain_chains(key, L):
    """round-25 ridge / valley / road windows -> list of (kind, rows, cols) on this grid (ordered chains)."""
    try:
        cand = pickle.load(open(K.SC25 + f'cand_{key}.pkl', 'rb')); g = pickle.load(open(K.SC25 + f'sel_{key}.pkl', 'rb'))['grid']
    except FileNotFoundError:
        return []
    tab = cand['tab']; out = []
    for k in np.nonzero(tab.kind.isin(['ridge', 'valley', 'road']).values)[0]:
        cl = cand['cells'][cand['ptr'][k]:cand['ptr'][k + 1]]
        r, c, ok = regrid(cl, g, L)
        if ok.sum() < 3: continue
        out.append(({'road': 'track'}.get(tab.kind.values[k], tab.kind.values[k]), r[ok], c[ok]))
    return out


def chord(ctr, th, off, half):
    u = np.array([np.cos(th), np.sin(th)]); nv = np.array([-np.sin(th), np.cos(th)])
    t = np.arange(-half, half + 0.4, 0.4)
    pts = ctr + off * nv + t[:, None] * u
    c = np.round(pts[:, 0]).astype(int); r = np.round(pts[:, 1]).astype(int)
    keep = np.r_[True, (np.diff(c) != 0) | (np.diff(r) != 0)]
    return r[keep], c[keep]


def runs(r, c, st):
    """split an ordered chain by status (1 = in compartment, 2 = allowed beyond the patch edge, 0 = stop) into candidate runs."""
    out = []; n = len(st); i = 0
    while i < n:
        if st[i] == 0: i += 1; continue
        j = i
        while j < n and st[j] != 0: j += 1
        seg = np.arange(i, j); s = st[i:j]
        if (s == 1).any():
            a = np.nonzero(s == 1)[0]; lo = max(a[0] - K.EXT, 0); hi = min(a[-1] + K.EXT + 1, len(s))
            seg = seg[lo:hi]
            out.append((r[seg], c[seg]))
        i = j
    return out


def chain_km(r, c):
    if len(r) < 2: return 0.06
    st = np.hypot(np.diff(r), np.diff(c))
    return float(st.sum() * K.RES / 1000 + 0.06)


class Patch:
    def __init__(self, P, rb, cb, W):
        self.P = P; self.rb, self.cb, self.W = rb, cb, W
        self.comp, n = ndi.label(P, S4)            # compartments (4-connected); start = the patch (1 piece, possibly several parts)
        self.ncomp = n; self.line = np.zeros_like(P)
        self.allow = np.zeros_like(P)

    def status(self, r, c, cid):
        h, w = self.P.shape; ok = (r >= 0) & (r < h) & (c >= 0) & (c < w)
        st = np.zeros(len(r), np.int8)
        rr, cc = r[ok], c[ok]
        inC = (self.comp[rr, cc] == cid) & ~self.line[rr, cc]
        ext = self.ext[cid][rr, cc] & ~self.P[rr, cc] & ~self.line[rr, cc]
        st[ok] = np.where(inC, 1, np.where(ext, 2, 0))
        return st

    def valid(self, r, c, cid):
        """cells (r, c) cut compartment cid into >= 2 pieces of >= MINC cells? returns pieces label array or None."""
        R = self.comp == cid
        R2 = R.copy(); R2[r, c] = False
        lab, n = ndi.label(R2, S4)
        if n < 2: return None
        sz = np.bincount(lab.ravel())[1:]
        if (sz >= MINC).sum() < 2: return None
        return lab, sz

    def set_ext(self, cid):
        R = self.comp == cid
        self.ext[cid] = ndi.binary_dilation(R, np.ones((3, 3), bool), iterations=K.EXT)


def gen_cands(pt, cid, chains, rng=None, nrand=0):
    """candidate cuts for compartment cid: list of (rows, cols, km, kind). rng given: nrand random chords only."""
    R = pt.comp == cid
    rr, cc = np.nonzero(R)
    if len(rr) < 2 * MINC: return []
    ctr = np.array([cc.mean(), rr.mean()]); half = np.hypot(*R.shape) + 4
    out = []; seen = set()
    def add(r, c, kind):
        st = pt.status(r, c, cid)
        for a, b in runs(r, c, st):
            keyc = np.sort(a.astype(np.int64) * 100000 + b).tobytes()
            if keyc in seen: continue
            seen.add(keyc)
            if pt.valid(a, b, cid) is None: continue
            out.append((a, b, chain_km(a, b), kind))
    if rng is not None:
        tries = 0
        while len(out) < nrand and tries < 60:
            tries += 1; th = rng.uniform(0, np.pi)
            nv = np.array([-np.sin(th), np.cos(th)]); pr = (np.c_[cc, rr] - ctr) @ nv
            off = rng.uniform(pr.min(), pr.max())
            r, c = chord(ctr, th, off, half)
            n0 = len(out); add(r, c, 'straight')
            if len(out) > n0 + 1: del out[n0 + 1:]
        return out
    for th in np.radians(K.ANGLES):
        nv = np.array([-np.sin(th), np.cos(th)]); pr = (np.c_[cc, rr] - ctr) @ nv
        step = max(2.0, (pr.max() - pr.min()) / 30)
        for off in np.arange(pr.min() + 1, pr.max() - 0.5, step):
            r, c = chord(ctr, th, off, half); add(r, c, 'straight')
    for kind, r, c in chains:
        r = r - pt.rb; c = c - pt.cb; h, w = R.shape
        if not ((r >= 0) & (r < h) & (c >= 0) & (c < w)).any(): continue
        add(r, c, kind)
    return out


def split(pt, r, c, cid):
    lab, sz = pt.valid(r, c, cid)
    pt.line[r, c] = True
    pt.comp[pt.comp == cid] = 0
    new = []
    for i, s in enumerate(sz, start=1):
        m = lab == i
        if s >= MINC:
            pt.ncomp += 1; pt.comp[m] = pt.ncomp; new.append(pt.ncomp)
        else:
            pt.comp[m] = -1        # sliver: stays patch, not a compartment of its own
    return new


def run_patch(p, LAB, FORg, F, fires_p, LM, W, chains, ny, Fte=None, fires_te=None, nrand=0, seed=0):
    rows, cols = np.nonzero(LAB == p)
    m = K.EXT + 2
    r0, r1 = max(rows.min() - m, 0), min(rows.max() + m + 1, LAB.shape[0]); c0, c1 = max(cols.min() - m, 0), min(cols.max() + m + 1, LAB.shape[1])
    P = LAB[r0:r1, c0:c1] == p
    pt = Patch(P, r0, c0, W); pt.ext = {}
    for cid in range(1, pt.ncomp + 1): pt.set_ext(cid)
    LABf = LAB.ravel(); args = F.args()
    fids = np.asarray(fires_p, np.int64)
    out = np.zeros((len(fids), 6))

    def ev(cells_g, fsel):
        LM[cells_g] = True
        o = np.zeros((len(fsel), 6)); K.eval_fires(fsel, *args, W, LM, LABf, FORg, p, K.P_STOP, o)
        return o

    def glob_(r, c): return (r + r0) * W + (c + c0)
    cur_cells = np.zeros(0, np.int64)
    cur = np.zeros((len(fids), 6))
    cands = {}; heap = []; cnt = 0; step = 0
    def push(cid):
        nonlocal cnt
        for (r, c, km, kind) in gen_cands(pt, cid, chains):
            cands[cnt] = (cid, r, c, km, kind)
            g = gain(r, c); heapq.heappush(heap, (-g[0] / km, cnt, step, g)); cnt += 1
    def gain(r, c):
        cg = glob_(r, c)
        o = ev(np.r_[cur_cells, cg], fids); LM[cg] = False; LM[cur_cells] = False
        d = (o - cur).sum(0) * K.CELL_HA / ny
        return d
    for cid in range(1, pt.ncomp + 1): push(cid)
    seq = []
    ncomp0 = pt.ncomp
    while heap and len(seq) < K.MAX_CUTS:
        ng, k, st, g = heapq.heappop(heap)
        cid, r, c, km, kind = cands[k]
        if (pt.comp == cid).sum() == 0: continue           # compartment already split: candidate dead
        if st != step:
            g = gain(r, c); heapq.heappush(heap, (-g[0] / km, k, step, g)); continue
        if g[0] <= 1e-9: break
        if pt.valid(r, c, cid) is None: continue
        new = split(pt, r, c, cid)
        cg = glob_(r, c); cur_cells = np.r_[cur_cells, cg]
        cur = ev(cur_cells, fids); LM[cur_cells] = False
        step += 1
        ncomp = int((np.unique(pt.comp[pt.comp > 0])).size) + 0
        seq.append(dict(cells=cg.astype(np.int64), km=km, kind=kind, g=g, n_after=ncomp))
        for cid2 in new: pt.set_ext(cid2)
        for cid2 in new: push(cid2)
    res = dict(patch=int(p), seq=seq, n_patch_cells=int(P.sum()), comp=None)
    # compartment raster of the final sequence (local), for maps
    res['box'] = (r0, r1, c0, c1); res['comp_final'] = pt.comp.astype(np.int16); res['line_final'] = pt.line.copy()
    if Fte is not None:
        te = []
        args_te = Fte.args(); ft = np.asarray(fires_te, np.int64)
        cells = np.zeros(0, np.int64)
        for s in seq:
            cells = np.r_[cells, s['cells']]; LM[cells] = True
            o = np.zeros((len(ft), 6)); K.eval_fires(ft, *args_te, W, LM, LABf, FORg, p, K.P_STOP, o); LM[cells] = False
            te.append(o.sum(0) * K.CELL_HA / len(K.TEST))
        res['test_cum'] = np.array(te).reshape(-1, 6)
    if nrand and seq:
        rng = np.random.default_rng(seed); draws = []
        for d in range(nrand):
            pt2 = Patch(P, r0, c0, W); pt2.ext = {}
            for cid in range(1, pt2.ncomp + 1): pt2.set_ext(cid)
            dseq = []
            for i in range(len(seq)):
                ids = [int(x) for x in np.unique(pt2.comp[pt2.comp > 0])]
                if not ids: break
                sz = np.array([(pt2.comp == x).sum() for x in ids], float)
                got = None
                for _ in range(8):
                    cid = ids[rng.choice(len(ids), p=sz / sz.sum())]
                    cs = gen_cands(pt2, cid, [], rng=rng, nrand=1)
                    if cs: got = (cid, cs[0]); break
                if got is None: break
                cid, (r, c, km, kind) = got
                split(pt2, r, c, cid)
                for cid2 in [x for x in np.unique(pt2.comp[pt2.comp > 0]) if x not in pt2.ext]: pt2.set_ext(cid2)
                dseq.append(dict(cells=((r + r0) * W + (c + c0)).astype(np.int64), km=km))
            draws.append(dseq)
        res['rand'] = draws
    return res


def main(args):
    key, pset = args
    t0 = time.time()
    L, FOR, Z = K.load_div(key); H, W = L['H'], L['W']
    LAB = K.lab60(Z, pset, H, W); npat = int(LAB.max())
    if npat == 0:
        pickle.dump(dict(key=key, div=L['div'], patches=[]), open(K.SC + f'cuts_{pset}_{key}.pkl', 'wb')); return key
    yrs = np.array([f['year'] for f in L['fires']])
    ys = K.TRAIN if pset == 'tr3' else K.ALL
    F = K.Fires(L, np.nonzero(np.isin(yrs, ys))[0])
    Fte = K.Fires(L, np.nonzero(np.isin(yrs, K.TEST))[0]) if pset == 'tr3' else None
    FORg = FOR.copy(); LABf = LAB.ravel()

    def fires_by_patch(FF):
        d = {}
        for f in range(FF.n):
            o = FF.off[f]; h, w = FF.H[f], FF.W[f]
            loc = np.nonzero(FF.D[o:o + h * w])[0]
            g = (loc // w + FF.r0[f]) * W + (loc % w + FF.c0[f])
            lb = LABf[g][FORg[g]]
            for p in np.unique(lb[lb > 0]): d.setdefault(int(p), []).append(f)
        return d
    fp = fires_by_patch(F); fpt = fires_by_patch(Fte) if Fte is not None else {}
    chains = terrain_chains(key, L)
    LM = np.zeros(H * W, bool)
    out = []
    for p in range(1, npat + 1):
        if p not in fp: continue
        r = run_patch(p, LAB, FORg, F, fp[p], LM, W, chains, len(ys), Fte, fpt.get(p, []), nrand=5 if pset == 'tr3' else 0, seed=p)
        r['n_fires'] = len(fp[p]); r['n_fires_test'] = len(fpt.get(p, []))
        out.append(r)
    pickle.dump(dict(key=key, div=L['div'], W=W, H=H, x0=L['x0'], y1=L['y1'], patches=out), open(K.SC + f'cuts_{pset}_{key}.pkl', 'wb'))
    ncut = sum(len(r['seq']) for r in out); km = sum(s['km'] for r in out for s in r['seq'])
    print(key, pset, npat, 'patches', ncut, 'cuts', round(km, 1), 'km', round(time.time() - t0), 's', flush=True)
    return key


if __name__ == '__main__':
    pset = sys.argv[1]
    keys = sys.argv[2:] or sorted(p.split('fires_')[1][:-4] for p in glob.glob(K.SC26 + 'fires_*.pkl') if 'table' not in p)
    # biggest first for load balance
    keys = sorted(keys, key=lambda k: -__import__('os').path.getsize(K.SC26 + f'fires_{k}.pkl'))
    with Pool(4) as pool: pool.map(main, [(k, pset) for k in keys], chunksize=1)
