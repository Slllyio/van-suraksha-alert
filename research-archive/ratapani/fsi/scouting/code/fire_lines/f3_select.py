"""Step 3. Benefit of each candidate line, choose lines on training seasons, test on held-out seasons, per division.
Benefit of a line for one past fire = scar hectares that the fire could reach from its start only by crossing the line
(4-connected spread inside the fire's own outline, line cells removed), times P_STOP, the chance the line actually stops the
front. Several lines: a cell is saved unless every line that cuts it off fails: 1 - prod(1 - P_STOP).
Selection (lazy greedy, most extra hectares per km, at most 20% overlap with lines already chosen) on training seasons only;
then scored on the test seasons. Same km for every method:
  plan        - greedy over road, beat, valley, ridge and neck candidates
  road_only   - greedy over existing-road windows only
  straight_tr - greedy over the straight 2 km lattice only
  hotspot     - lines crossing the most burnt ground in training (per km), no cut logic
  rand_forest / rand_road / rand_beat - random 2 km lines (200 draws)
  plan_stable - as plan, but only lines that cut off ground in >= 2 different training seasons
  plan_plus   - greedy over the plan pool plus the straight lattice
  oracle      - greedy chosen on the test seasons themselves (ceiling, not a fair method)
Variant 'fronts': every new front (dot > 750 m from all earlier dots) counts as its own start (conservative).
Out (scratch): sel_<div>.pkl (per-fire test contributions, chosen lines, summary)."""
import pickle, sys, glob, heapq, time
import numpy as np, pandas as pd
from scipy.stats import spearmanr
import common as C, fl_lib as K

BUDGETS = (10, 20, 50)
POOL = ('road', 'beat', 'valley', 'ridge', 'neck')
RNG = np.random.default_rng(7)


class Fires:
    def __init__(self, L, idx, src='ign'):
        self.L = L; self.idx = idx; fs = [L['fires'][i] for i in idx]
        self.year = np.array([f['year'] for f in fs]); self.ha = np.array([f['ha'] for f in fs])
        Ds, offs, srcs, srcp = [], [0], [], [0]
        for f in fs:
            M = np.unpackbits(f['M'])[:f['shape'][0] * f['shape'][1]].reshape(f['shape']).astype(bool)
            s = f[src].astype(np.int64)
            seen = K.reach(M.ravel(), M.shape[0], M.shape[1], s, np.zeros(M.size, np.bool_))
            Ds.append(seen); offs.append(offs[-1] + seen.size); srcs.append(s); srcp.append(srcp[-1] + len(s))
        self.D = np.concatenate(Ds) if Ds else np.zeros(0, bool); self.off = np.array(offs[:-1], np.int64)
        self.H = np.array([f['shape'][0] for f in fs], np.int64); self.W = np.array([f['shape'][1] for f in fs], np.int64)
        self.r0 = np.array([f['r0'] for f in fs], np.int64); self.c0 = np.array([f['c0'] for f in fs], np.int64)
        self.srcs = np.concatenate(srcs) if srcs else np.zeros(0, np.int64); self.srcp = np.array(srcp, np.int64)
        self.base = np.array([d.sum() for d in Ds], np.int64); self.reach_ha = self.base * C.CELL_HA
        self.maxn = int((self.H * self.W).max()) if len(fs) else 1
        # global cell -> fire table
        g, fi = [], []
        for j, d in enumerate(Ds):
            loc = np.nonzero(d)[0]; r = loc // self.W[j] + self.r0[j]; c = loc % self.W[j] + self.c0[j]
            g.append(r * L['W'] + c); fi.append(np.full(len(loc), j))
        self.gc = np.concatenate(g) if g else np.zeros(0, np.int64); self.gf = np.concatenate(fi) if fi else np.zeros(0, np.int64)

    def pairs(self, cand, ks):
        """All (line, fire) pairs where line ks touches fire's reachable cells."""
        ptr, cells = cand['ptr'], cand['cells']
        lens = ptr[ks + 1] - ptr[ks]
        kc = np.repeat(ks, lens); cc = np.concatenate([cells[ptr[k]:ptr[k + 1]] for k in ks]) if len(ks) else np.zeros(0, np.int64)
        o = np.argsort(self.gc, kind='stable'); gs = self.gc[o]; fs = self.gf[o]
        lo = np.searchsorted(gs, cc, 'left'); hi = np.searchsorted(gs, cc, 'right'); m = hi > lo
        kc, lo, hi = kc[m], lo[m], hi[m]; n = hi - lo
        rep = np.repeat(np.arange(len(kc)), n); pos = np.repeat(lo, n) + (np.arange(n.sum()) - np.repeat(np.cumsum(n) - n, n))
        key = np.unique(kc[rep].astype(np.int64) * (len(self.idx) + 1) + fs[pos])
        return key // (len(self.idx) + 1), key % (len(self.idx) + 1)

    def protect(self, cand, ks, min_cells=1):
        """For lines ks: dict line -> list of (fire, protected local cells)."""
        pk, pf = self.pairs(cand, np.asarray(ks, np.int64))
        if len(pk) == 0: return {}
        cnt, _ = K.pair_counts(self.D, self.off, self.H, self.W, self.r0, self.c0, self.base, self.srcp, self.srcs,
                               cand['ptr'], cand['cells'], self.L['W'], pk, pf, self.maxn)
        m = cnt >= min_cells; pk, pf, cnt = pk[m], pf[m], cnt[m]
        outp = np.r_[0, np.cumsum(cnt)].astype(np.int64)
        res = K.pair_cells(self.D, self.off, self.H, self.W, self.r0, self.c0, self.srcp, self.srcs, cand['ptr'], cand['cells'],
                           self.L['W'], pk, pf, self.maxn, outp, int(outp[-1]))
        P = {}
        for i in range(len(pk)): P.setdefault(int(pk[i]), []).append((int(pf[i]), res[outp[i]:outp[i + 1]]))
        return P

    def value(self, P, lines, p=C.P_STOP):
        """Expected saved ha per fire for a set of lines (cells saved unless every cutting line fails)."""
        S = {}
        for k in lines:
            for f, cl in P.get(k, []):
                if f not in S: S[f] = np.ones(self.H[f] * self.W[f])
                S[f][cl] *= (1 - p)
        v = np.zeros(len(self.idx))
        for f, s in S.items(): v[f] = (1 - s).sum() * C.CELL_HA
        return v


def greedy(F, P, ks, km, cand, budget=max(BUDGETS), p=C.P_STOP):
    S = {}; chosen = []; used = set(); tot = 0.0
    def gain(k):
        g = 0.0
        for f, cl in P.get(k, []):
            s = S.get(f); g += cl.size if s is None else s[cl].sum()
        return g * p * C.CELL_HA
    h = [(-gain(k) / km[k], k) for k in ks if k in P]; heapq.heapify(h)
    while h and tot < budget:
        ng, k = heapq.heappop(h)
        g = gain(k) / km[k]
        if h and g < -h[0][0] - 1e-12: heapq.heappush(h, (-g, k)); continue
        if g <= 0: break
        cl = cand['cells'][cand['ptr'][k]:cand['ptr'][k + 1]]
        if np.isin(cl, list(used)).mean() > 0.2: continue
        chosen.append((k, g)); used.update(cl.tolist()); tot += km[k]
        for f, c in P.get(k, []):
            if f not in S: S[f] = np.ones(F.H[f] * F.W[f])
            S[f][c] *= (1 - p)
    return chosen


def prefix(lines, km, b):
    out, t = [], 0.0
    for k in lines:
        if t + km[k] > b * 1.1 and out: break
        out.append(k); t += km[k]
    return out, t


def main(key):
    t00 = time.time()
    L = pickle.load(open(C.SC + f'fires_{key}.pkl', 'rb')); cand = pickle.load(open(C.SC + f'cand_{key}.pkl', 'rb'))
    tab = cand['tab']; km = tab.km.values; kind = tab.kind.values
    tr_y, te_y = C.years(key)
    if not tr_y or not te_y: print(key, 'no complete train/test seasons', flush=True); return
    yrs = np.array([f['year'] for f in L['fires']])
    Ftr = Fires(L, np.nonzero(np.isin(yrs, tr_y))[0]); Fte = Fires(L, np.nonzero(np.isin(yrs, te_y))[0])
    allk = np.arange(len(tab))
    Ptr = Ftr.protect(cand, allk, 1); Pte = Fte.protect(cand, allk, 1)
    print(key, 'pairs done', len(Ptr), len(Pte), round(time.time() - t00), 's', flush=True)
    pool = [k for k in allk if kind[k] in POOL]
    R = dict(key=key, div=L['div'], tr_years=tr_y, te_years=te_y, test_fire_ha=Fte.ha, test_reach_ha=Fte.reach_ha, test_year=Fte.year,
             train_ha=Ftr.ha.sum(), test_ha=Fte.ha.sum(), n_train=len(Ftr.idx), n_test=len(Fte.idx), n_cand=len(tab))
    # lines that cut off ground in at least 2 different training seasons (a priori guard against one-off fire paths)
    ny = {k: len({int(Ftr.year[f]) for f, c in Ptr.get(k, []) if c.size >= 3}) for k in pool}
    stable = [k for k in pool if ny[k] >= 2]
    sel = {'plan_stable': greedy(Ftr, Ptr, stable, km, cand), 'plan': greedy(Ftr, Ptr, pool, km, cand), 'road_only': greedy(Ftr, Ptr, [k for k in allk if kind[k] == 'road'], km, cand),
           'straight_tr': greedy(Ftr, Ptr, [k for k in allk if kind[k] == 'straight'], km, cand),
           'plan_plus': greedy(Ftr, Ptr, pool + [k for k in allk if kind[k] == 'straight'], km, cand),
           'oracle': greedy(Fte, Pte, pool, km, cand)}
    # hot-spot: training burnt cells crossed per km (no cut logic)
    pk, pf = Ftr.pairs(cand, np.array(pool, np.int64))
    cross = np.zeros(len(tab))
    for k, f in zip(pk, pf):
        cl = cand['cells'][cand['ptr'][k]:cand['ptr'][k + 1]]; r = cl // L['W'] - Ftr.r0[f]; c = cl % L['W'] - Ftr.c0[f]
        ok = (r >= 0) & (r < Ftr.H[f]) & (c >= 0) & (c < Ftr.W[f])
        cross[k] += Ftr.D[Ftr.off[f] + r[ok] * Ftr.W[f] + c[ok]].sum()
    order = sorted(pool, key=lambda k: -cross[k] / km[k]); used = set(); hs = []; t = 0
    for k in order:
        if t >= max(BUDGETS): break
        cl = cand['cells'][cand['ptr'][k]:cand['ptr'][k + 1]]
        if np.isin(cl, list(used)).mean() > 0.2: continue
        hs.append((k, cross[k] / km[k])); used.update(cl.tolist()); t += km[k]
    sel['hotspot'] = hs
    R['sel'] = {m: [k for k, _ in v] for m, v in sel.items()}
    # test (and train) value per fire for each method and budget
    V, VT, KM = {}, {}, {}
    for m, v in R['sel'].items():
        for b in BUDGETS:
            ln, t = prefix(v, km, b); V[(m, b)] = Fte.value(Pte, ln); VT[(m, b)] = Ftr.value(Ptr, ln).sum(); KM[(m, b)] = t
    for m, kk in (('rand_forest', 'random'), ('rand_road', 'road'), ('rand_beat', 'beat')):
        ids = np.nonzero(kind == kk)[0]
        if kk != 'random': ids = ids[np.abs(km[ids] - 2.0) < 0.3]
        for b in BUDGETS:
            acc = np.zeros(len(Fte.idx)); acct = 0.0; kmt = 0.0; nd = 200
            for d in range(nd):
                ln, t = prefix(list(RNG.permutation(ids)), km, b)
                acc += Fte.value(Pte, ln); acct += Ftr.value(Ptr, ln).sum(); kmt += t
            V[(m, b)] = acc / nd; VT[(m, b)] = acct / nd; KM[(m, b)] = kmt / nd
    R['V'], R['VT'], R['KM'] = V, VT, KM
    # stop-chance range for the plan at 20 km
    ln, _ = prefix(R['sel']['plan'], km, 20)
    R['p_range'] = {p: (Fte.value(Pte, ln, p).sum(), Ftr.value(Ptr, ln, p).sum()) for p in (C.P_RANGE[0], C.P_STOP, C.P_RANGE[1])}
    # conservative variant: every front its own start (test, plan and baselines at 20 km)
    Ffr = Fires(L, Fte.idx, 'fronts')
    need = set(ln) | set(prefix(R['sel']['road_only'], km, 20)[0]) | set(prefix(R['sel']['plan_plus'], km, 20)[0]) | set(prefix(R['sel']['straight_tr'], km, 20)[0]) | set(prefix(R['sel']['plan_stable'], km, 20)[0]) | set(prefix(R['sel']['hotspot'], km, 20)[0])
    Pfr = Ffr.protect(cand, np.array(sorted(need), np.int64), 1)
    R['fronts20'] = {m: Ffr.value(Pfr, prefix(R['sel'][m], km, 20)[0]).sum() for m in ('plan', 'plan_stable', 'plan_plus', 'straight_tr', 'road_only', 'hotspot')}
    # single-line benefit, train vs test, over the pool (stability of where lines pay)
    btr = np.array([sum(c.size for _, c in Ptr.get(k, [])) for k in pool]) / km[pool]
    bte = np.array([sum(c.size for _, c in Pte.get(k, [])) for k in pool]) / km[pool]
    R['rank_rho'] = float(spearmanr(btr, bte).correlation) if btr.std() > 0 and bte.std() > 0 else np.nan
    top = np.argsort(-btr)[:max(1, len(pool) // 100)]
    R['top1pct_test_vs_all'] = (bte[top].mean(), bte.mean())
    R['frac_cand_any_test'] = float((bte > 0).mean())
    # chosen lines with their cells for maps / geojson
    lines = {}
    for m in ('plan', 'plan_stable', 'plan_plus', 'road_only', 'oracle'):
        for k, g in sel[m]:
            lines[k] = dict(kind=kind[k], km=km[k], cells=cand['cells'][cand['ptr'][k]:cand['ptr'][k + 1]].copy())
    R['lines'] = lines; R['gain_train'] = {m: v for m, v in sel.items()}
    R['test_line_ha'] = {k: Fte.value(Pte, [k]).sum() for k in R['sel']['plan']}
    R['train_line_ha'] = {k: Ftr.value(Ptr, [k]).sum() for k in R['sel']['plan']}
    R['test_line_years'] = {k: pd.Series(Fte.value(Pte, [k])).groupby(Fte.year).sum().to_dict() for k in R['sel']['plan']}
    R['grid'] = dict(x0=L['x0'], y1=L['y1'], W=L['W'], H=L['H'])
    pickle.dump(R, open(C.SC + f'sel_{key}.pkl', 'wb'))
    b = 20
    print(key, 'done', round(time.time() - t00), 's | test ha/km @20:', {m: round(V[(m, b)].sum() / max(KM[(m, b)], 1e-9), 2) for m in
          ('plan', 'plan_stable', 'plan_plus', 'road_only', 'straight_tr', 'hotspot', 'rand_forest', 'rand_road', 'rand_beat', 'oracle')}, 'rho', round(R['rank_rho'], 3), flush=True)


if __name__ == '__main__':
    keys = sys.argv[1:] or sorted(p.split('cand_')[1][:-4] for p in glob.glob(C.SC + 'cand_*.pkl'))
    for k in keys: main(k)
