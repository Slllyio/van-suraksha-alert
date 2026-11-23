"""Step 2. Statewide allocation (greedy knapsack over every patch's next cut) and held-out scoring of five line strategies at the same
statewide budgets (100 / 250 / 500 / 1000 km), all with the same k0 scoring rule.
  comp      - compartment cuts (k1, chosen on 2017-21). Each patch's cuts are taken in greedy order; across patches the next cut
              (grouped on the upper concave hull of the patch's benefit-vs-km curve) with the highest 2017-21 patch-forest ha
              saved per km per year goes first, until the budget is spent. n* = cuts taken + 1. lambda = marginal ha/km/yr at the budget.
  rand      - random cuts: same patches, same number of cuts per patch as 'comp', random direction and offset (5 draws)
  randkm    - random cuts: same patches, random cuts added until their length is closest to the 'comp' km of that patch (5 draws)
  entry     - round-26 entry-side lines (618 lines, 649 km, chosen on 2017-21), ranked statewide by 2017-21 patch ha saved per km
  ring      - whole perimeter ring of 2017-21 repeat patches, ranked statewide by 2017-21 patch ha saved per km
  corridor  - round-25 plan (corridor) lines, ranked statewide by their own in-sample ha/km/yr (rest of MP chosen on 2019-21)
Run: python k2_score.py lines   (per-line 2017-21 values for entry and ring, per division)
     python k2_score.py alloc   (statewide allocation per strategy and budget)
     python k2_score.py score   (per division: per-fire saved ha for every strategy x budget, test 2022-25 and train 2017-21)
Also (score): the 500 km sets re-scored with the conservative start rule (every new front its own start, k0.fronts).
Out (scratch r27): lines_<div>.pkl, alloc.pkl, score_<div>.pkl"""
import pickle, sys, glob, os
import numpy as np, pandas as pd
from multiprocessing import Pool
import k0 as K
from k1_cuts import regrid

KEYS = sorted(p.split('cuts_tr3_')[1][:-4] for p in glob.glob(K.SC + 'cuts_tr3_*.pkl'))


def r26_lines(key):
    """entry-side lines (r26, consistent patches) and perimeter rings of all tr3 patches: list of (kind, patch, cells, km)."""
    S = pd.read_parquet(K.SC26 + 'patches_tr3.parquet'); S = S[S.key == key]
    RG = pickle.load(open(K.SC26 + 'rings_tr3.pkl', 'rb'))
    rings = RG['rings'].get(key, {}); meta = RG['meta'].get(key, {})
    out = []
    for _, s in S[S.consistent].iterrows():
        p = int(s.patch); ring, seg = rings[p]; m = int(s.mode_seg)
        out.append(('entry', p, ring[seg == m].astype(np.int64), float(meta[p]['seg_km'][m])))
    for p, (ring, seg) in rings.items():
        out.append(('ring', int(p), ring.astype(np.int64), float(meta[p]['ring_km'])))
    return out


def corridor(key, L):
    """round-25 plan lines in plan order: list of (rank, cells on this grid, km, in-sample ha/km/yr)."""
    try:
        R = pickle.load(open(K.SC25 + f'sel_{key}.pkl', 'rb'))
    except FileNotFoundError:
        return []
    g = R['grid']; gains = dict(R['gain_train']['plan']); ny = len(R['tr_years']); out = []
    for i, k in enumerate(R['sel']['plan']):
        ln = R['lines'][k]; r, c, ok = regrid(ln['cells'], g, L)
        out.append((i, (r[ok] * L['W'] + c[ok]).astype(np.int64), float(ln['km']), float(gains[k]) / ny))
    return out


def setup(key):
    L, FOR, Z = K.load_div(key); H, W = L['H'], L['W']
    LAB = K.lab60(Z, 'tr3', H, W).ravel()
    yrs = np.array([f['year'] for f in L['fires']])
    Ftr = K.Fires(L, np.nonzero(np.isin(yrs, K.TRAIN))[0]); Fte = K.Fires(L, np.nonzero(np.isin(yrs, K.TEST))[0])
    return L, FOR, LAB, Ftr, Fte


def lines_one(key):
    L, FOR, LAB, Ftr, Fte = setup(key); W = L['W']
    LM = np.zeros(L['H'] * W, bool); rows = []
    allf = np.arange(Ftr.n, dtype=np.int64)
    for kind, p, cells, km in r26_lines(key):
        LM[cells] = True
        o, byp = K.eval_fires_bypatch(allf, *Ftr.args(), W, LM, LAB, FOR, K.P_STOP, int(LAB.max()))
        LM[cells] = False
        rows.append(dict(key=key, kind=kind, patch=p, km=km, train_patch=o[:, 0].sum() * K.CELL_HA / len(K.TRAIN), train_forest=o[:, 1].sum() * K.CELL_HA / len(K.TRAIN)))
    pickle.dump(dict(rows=rows, corridor=[(i, km, g) for i, _, km, g in corridor(key, L)], test_forest_ha=Fte.forest_ha.sum(), test_ha=Fte.ha.sum(),
                     train_forest_ha=Ftr.forest_ha.sum(), n_test=Fte.n, n_train=Ftr.n), open(K.SC + f'lines_{key}.pkl', 'wb'))
    print(key, 'lines', len(rows), flush=True)


def hull(km, g):
    """upper concave hull of cumulative (km, benefit) from (0, 0): list of (first cut, last cut, km, benefit) segments, slope > 0."""
    X = np.r_[0, np.cumsum(km)]; Y = np.r_[0, np.cumsum(g)]; segs = []; i = 0; n = len(km)
    while i < n:
        sl = (Y[i + 1:] - Y[i]) / np.maximum(X[i + 1:] - X[i], 1e-9); j = int(np.argmax(sl)) + i + 1
        if sl[j - i - 1] <= 0: break
        segs.append((i, j, X[j] - X[i], Y[j] - Y[i])); i = j
    return segs


def take(items, B):
    """items: list of (owner, order, km, value) with order = position within owner (prefix rule). Greedy by value/km; stops at the
    first item that would exceed B."""
    items = sorted(items, key=lambda t: -t[3] / max(t[2], 1e-9)); tot = 0.0; got = []; blocked = set(); nxt = {}
    for it in items:
        ow, od, km, v = it
        if ow in blocked or nxt.get(ow, 0) != od: blocked.add(ow); continue
        if tot + km > B: break          # stop at the first cut that does not fit: every taken cut beats every cut left out (one lambda)
        got.append(it); tot += km; nxt[ow] = od + 1
    return got, tot


def alloc():
    A = {'budgets': K.BUDGETS}
    # compartments
    items = []; P = {}
    for key in KEYS:
        R = pickle.load(open(K.SC + f'cuts_tr3_{key}.pkl', 'rb'))
        for r in R['patches']:
            if not r['seq']: continue
            km = np.array([s['km'] for s in r['seq']]); g = np.array([s['g'][0] for s in r['seq']])
            P[(key, r['patch'])] = dict(km=km, g=g, test_cum=r['test_cum'][:, 0], n_fires=r['n_fires'], n_fires_test=r['n_fires_test'])
            for o, (i, j, k_, v) in enumerate(hull(km, g)): items.append(((key, r['patch']), o, k_, v, j))
    grid = np.r_[np.arange(10, 100, 10), np.arange(100, 1000, 50), np.arange(1000, 5001, 250)]
    curve = []
    for B in sorted(set(grid.tolist()) | set(K.BUDGETS)):
        got, tot = take([it[:4] for it in items], B)
        # n* per patch = end index of the last taken hull segment
        last = {}
        for ow, od, k_, v in got: last[ow] = max(last.get(ow, -1), od)
        segj = {(it[0], it[1]): it[4] for it in items}   # hull segment -> cuts taken up to its end
        nstar = {ow: segj[(ow, od)] for ow, od in last.items()}
        tr = sum(P[ow]['g'][:n].sum() for ow, n in nstar.items()); te = sum(P[ow]['test_cum'][n - 1] for ow, n in nstar.items())
        lam = min((v / k_ for _, _, k_, v in got), default=np.nan)
        curve.append(dict(budget=B, km=tot, patches=len(nstar), cuts=sum(nstar.values()), train_patch=tr, test_patch_indep=te, lam=lam))
        if B in K.BUDGETS: A[('comp', B)] = nstar
    A['curve'] = pd.DataFrame(curve); A['P'] = P
    # entry / ring / corridor
    LR = []; CR = []; tot = dict(test_forest_ha=0.0, test_ha=0.0, train_forest_ha=0.0, n_test=0, n_train=0)
    for key in KEYS:
        if not os.path.exists(K.SC + f'lines_{key}.pkl'): continue
        Q = pickle.load(open(K.SC + f'lines_{key}.pkl', 'rb')); LR += Q['rows']
        CR += [dict(key=key, rank=i, km=km, g=g) for i, km, g in Q['corridor']]
        for k in tot: tot[k] += Q[k]
    A['tot'] = tot
    LR = pd.DataFrame(LR); CR = pd.DataFrame(CR); A['line_rows'] = LR
    for kind in ('entry', 'ring'):
        d = LR[LR.kind == kind]
        for B in K.BUDGETS:
            got, t = take([((r.key, r.patch), 0, r.km, r.train_patch) for r in d.itertuples()], B)
            A[(kind, B)] = set(g[0] for g in got)
    for B in K.BUDGETS:
        got, t = take([((r.key, r.rank), 0, r.km, r.g * r.km) for r in CR.itertuples()], B)
        A[('corridor', B)] = set(g[0] for g in got)
    pickle.dump(A, open(K.SC + 'alloc.pkl', 'wb'))
    print(A['curve'][A['curve'].budget.isin(K.BUDGETS)], flush=True)
    for kind in ('entry', 'ring', 'corridor'): print(kind, [len(A[(kind, B)]) for B in K.BUDGETS])


def score_one(key):
    A = pickle.load(open(K.SC + 'alloc.pkl', 'rb'))
    L, FOR, LAB, Ftr, Fte = setup(key); W = L['W']; npat = int(LAB.max())
    R = pickle.load(open(K.SC + f'cuts_tr3_{key}.pkl', 'rb')); byp = {r['patch']: r for r in R['patches']}
    rl = {(kd, p): (c, km) for kd, p, c, km in r26_lines(key)}
    cor = {i: (c, km) for i, c, km, g in corridor(key, L)}
    sets = {}
    for B in K.BUDGETS:
        ns = {p: n for (k, p), n in A[('comp', B)].items() if k == key}
        sets[('comp', B, 0)] = [byp[p]['seq'][i]['cells'] for p, n in ns.items() for i in range(n)], sum(byp[p]['seq'][i]['km'] for p, n in ns.items() for i in range(n))
        for d in range(5):
            cl = []; km = 0.0
            for p, n in ns.items():
                dr = byp[p]['rand'][d][:n]; cl += [s['cells'] for s in dr]; km += sum(s['km'] for s in dr)
            sets[('rand', B, d)] = cl, km
        for d in range(5):   # random cuts in the same patches, matched to the compartment km of each patch (closest cumulative length)
            cl = []; km = 0.0
            for p, n in ns.items():
                tgt = sum(s['km'] for s in byp[p]['seq'][:n]); dr = byp[p]['rand'][d]
                if not dr: continue
                cum = np.cumsum([s['km'] for s in dr]); m = int(np.argmin(np.abs(cum - tgt))) + 1
                cl += [s['cells'] for s in dr[:m]]; km += float(cum[m - 1])
            sets[('randkm', B, d)] = cl, km
        for kind in ('entry', 'ring'):
            ps = [p for (k, p) in A[(kind, B)] if k == key]
            sets[(kind, B, 0)] = [rl[(kind, p)][0] for p in ps], sum(rl[(kind, p)][1] for p in ps)
        ids = [i for (k, i) in A[('corridor', B)] if k == key and i in cor]
        sets[('corridor', B, 0)] = [cor[i][0] for i in ids], sum(cor[i][1] for i in ids)
    LM = np.zeros(L['H'] * W, bool); out = dict(key=key, div=L['div'], test_year=Fte.year, test_forest_ha=Fte.forest_ha, test_ha=Fte.ha, n_test=Fte.n, n_train=Ftr.n, res={})
    for s, (cells, km) in sets.items():
        if not cells: out['res'][s] = None; continue
        cc = np.concatenate(cells); LM[cc] = True
        r = {'km': km}
        for per, F in (('test', Fte), ('train', Ftr)):
            for p in K.PS:
                o, bp = K.eval_fires_bypatch(np.arange(F.n, dtype=np.int64), *F.args(), W, LM, LAB, FOR, p, npat)
                r[(per, p)] = (o[:, :3] * K.CELL_HA).astype(np.float32)
                if per == 'test' and s[0] == 'comp': r[('byp', p)] = bp[:, 0] * K.CELL_HA
        LM[cc] = False; out['res'][s] = r
    # conservative start rule (every new front its own start), 500 km budget, test seasons, p = 0.35
    yrs = np.array([f['year'] for f in L['fires']]); Ffr = K.Fires(L, np.nonzero(np.isin(yrs, K.TEST))[0], 'fronts')
    out['fronts'] = {}
    for s, (cells, km) in sets.items():
        if s[1] != 500 or not cells: continue
        cc = np.concatenate(cells); LM[cc] = True
        o, _ = K.eval_fires_bypatch(np.arange(Ffr.n, dtype=np.int64), *Ffr.args(), W, LM, LAB, FOR, K.P_STOP, npat)
        out['fronts'][s] = ((o[:, :3] * K.CELL_HA).astype(np.float32), km); LM[cc] = False
    pickle.dump(out, open(K.SC + f'score_{key}.pkl', 'wb'))
    print(key, 'scored', flush=True)


if __name__ == '__main__':
    mode = sys.argv[1]; keys = sys.argv[2:] or KEYS
    keys = sorted(keys, key=lambda k: -os.path.getsize(K.SC26 + f'fires_{k}.pkl'))
    if mode == 'alloc': alloc()
    else:
        with Pool(4) as pool: pool.map(lines_one if mode == 'lines' else score_one, keys, chunksize=1)
