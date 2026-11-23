"""Step 3. Statewide allocation (greedy knapsack on each patch's upper concave hull, as round 27) and held-out 2022-25 totals for
every (patch set, objective) variant at p = 0.35 / 0.70 / 1.0, on a budget grid up to the km available. 95% ranges by resampling
test fires within divisions (1,000 draws) for the p = 0.35 patch-forest value.
Run: python m3_score.py            Out: out/m3_curve_<pset>_<obj>.csv, out/m3_div_<pset>_<obj>_<B>.csv, scratch r28/alloc_<pset>_<obj>.pkl"""
import pickle, glob, os, sys
import numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import m0 as M
sys.path.insert(0, '/mnt/project-files/ratapani/fsi/scouting/code/compartments/')
from k2_score import hull, take   # noqa: E402

GRID = np.r_[np.arange(50, 1000, 50), np.arange(1000, 5001, 250), np.arange(6000, 20001, 1000)]


def run(pset, obj, nboot=1000):
    files = sorted(glob.glob(M.SC + f'cuts_{pset}_{obj}_*.pkl'))
    if not files: return
    P = {}; items = []; div = {}; ntest = {}; tfh = {}; tyear = {}
    for fn in files:
        R = pickle.load(open(fn, 'rb')); key = R['key']
        if not R['patches']: continue
        div[key] = R['div']; ntest[key] = R['n_test']; tfh[key] = R['test_forest_ha']; tyear[key] = R['test_year']
        for r in R['patches']:
            if not r['seq']: continue
            km = np.array([s['km'] for s in r['seq']]); g = np.array([s['g'] for s in r['seq']])
            sy = np.array([s['sy'] for s in r['seq']])      # cumulative per train year
            P[(key, r['patch'])] = dict(km=km, g=g, sy=sy, test_cum=r['test_cum'], test_fire=r['test_fire'], fids=r['test_fids'], ha=R['patch_ha'][r['patch']])
            for o, (i, j, k_, v) in enumerate(hull(km, g)): items.append(((key, r['patch']), o, k_, v, j))
    segj = {(it[0], it[1]): it[4] for it in items}
    tot_test = sum(tfh.values()) / len(M.TEST)
    rng = np.random.default_rng(0)
    boot_idx = {k: rng.integers(0, ntest[k], size=(nboot, ntest[k])) for k in ntest}   # same draws for every budget (paired)
    curve = []; alloc = {}; divrows = []
    kmax = sum(it[2] for it in items)
    for B in sorted(set(GRID.tolist()) | set(M.BUDGETS)):
        if B > kmax + 500: break
        got, tot = take([it[:4] for it in items], B)
        last = {}
        for ow, od, k_, v in got: last[ow] = max(last.get(ow, -1), od)
        nstar = {ow: segj[(ow, od)] for ow, od in last.items()}
        row = dict(budget=B, km=tot, patches=len(nstar), cuts=sum(nstar.values()), lam=min((v / k_ for _, _, k_, v in got), default=np.nan))
        tc = sum(P[ow]['test_cum'][n - 1] for ow, n in nstar.items()) if nstar else np.zeros((3, 3))
        tr_sy = sum(P[ow]['sy'][n - 1] for ow, n in nstar.items()) if nstar else np.zeros(5)
        for j, pp in enumerate(M.PS):
            for m, name in enumerate(('patch', 'forest', 'ground')):
                row[f'test_{name}_p{int(pp*100)}'] = tc[j, m]
            row[f'pct_forest_p{int(pp*100)}'] = 100 * tc[j, 1] / tot_test
        row['train_patch_mean'] = tr_sy.mean(); row['train_patch_min'] = tr_sy.min(); row['train_patch_median'] = np.median(tr_sy)
        # per-fire values (p = 0.35, patch forest) for bootstrap and by-year
        fv = {k: np.zeros(ntest[k]) for k in ntest}
        for ow, n in nstar.items():
            fv[ow[0]][P[ow]['fids']] += P[ow]['test_fire'][n - 1]
        row['test_patch_p35_check'] = sum(v.sum() for v in fv.values()) / len(M.TEST)
        for y in M.TEST: row[f'test_patch_{y}'] = sum(fv[k][tyear[k] == y].sum() for k in fv)
        if nstar and tot > 0:
            bs = np.zeros(nboot)
            for k, v in fv.items():
                if v.any(): bs += v[boot_idx[k]].sum(1)
            bs /= len(M.TEST) * tot
            row['perkm_p35'] = row['test_patch_p35'] / tot; row['perkm_lo'] = np.percentile(bs, 2.5); row['perkm_hi'] = np.percentile(bs, 97.5)
            row['perkm_forest_p35'] = row['test_forest_p35'] / tot; row['perkm_forest_p70'] = row['test_forest_p70'] / tot
            # cuts that saved anything held out
            saved = [P[ow]['test_fire'][n - 1].sum() > 0 for ow, n in nstar.items()]
            row['share_patches_saving'] = float(np.mean(saved))
        curve.append(row); alloc[B] = nstar
        if B in M.BUDGETS:
            for k in div:
                ps = {ow: n for ow, n in nstar.items() if ow[0] == k}
                if not ps: continue
                kmd = sum(P[ow]['km'][:n].sum() for ow, n in ps.items())
                tcd = sum(P[ow]['test_cum'][n - 1] for ow, n in ps.items())
                divrows.append(dict(budget=B, key=k, div=div[k], patches=len(ps), cuts=sum(ps.values()), km=kmd,
                                    patch_p35=tcd[0, 0], forest_p35=tcd[0, 1], forest_p70=tcd[1, 1], perkm_patch_p35=tcd[0, 0] / kmd, perkm_forest_p70=tcd[1, 1] / kmd,
                                    pct_div_burnt_p70=100 * tcd[1, 1] / (tfh[k] / len(M.TEST)), train_mean=sum(P[ow]['sy'][n - 1].mean() for ow, n in ps.items())))
    C = pd.DataFrame(curve); C.to_csv(M.OUT + f'm3_curve_{pset}_{obj}.csv', index=False)
    pd.DataFrame(divrows).to_csv(M.OUT + f'm3_div_{pset}_{obj}.csv', index=False)
    pickle.dump(dict(alloc=alloc, tot_test=tot_test, kmax=kmax), open(M.SC + f'alloc_{pset}_{obj}.pkl', 'wb'))
    cols = ['budget', 'km', 'patches', 'cuts', 'perkm_p35', 'perkm_lo', 'perkm_hi', 'perkm_forest_p35', 'perkm_forest_p70', 'pct_forest_p35', 'pct_forest_p70', 'pct_forest_p100', 'train_patch_mean', 'share_patches_saving']
    print(pset, obj, 'km available', round(kmax), 'test forest ha/yr', round(tot_test))
    print(C[C.budget.isin(M.BUDGETS)][[c for c in cols if c in C]].round(2).to_string(index=False), flush=True)


if __name__ == '__main__':
    todo = [(a.split('_')[0], a.split('_')[1]) for a in sys.argv[1:]] or [(p, o) for p in M.PSETS for o in M.OBJS]
    for pset, obj in todo: run(pset, obj)
