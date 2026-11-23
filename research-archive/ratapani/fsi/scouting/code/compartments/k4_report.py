"""Step 4. Tables for repeat_patch_compartments.md and the conference paper: statewide and per-division held-out results with
bootstrap ranges (test fires resampled within each division, 1,000 times; all strategies scored on the same fires, so differences
are paired), the allocation curve, n* distribution, cut kinds, top patches, and where the saved hectares come from.
Out: out/tables.json, out/strategy_table.csv, out/division_table.csv, out/top_tested_patches.csv"""
import pickle, glob, json
import numpy as np, pandas as pd
import k0 as K

NB = 1000; RNG = np.random.default_rng(27)
STRATS = ('comp', 'rand', 'randkm', 'entry', 'ring', 'corridor')
WH = {'patch': 0, 'forest': 1, 'ground': 2}


def load():
    S = {}
    for f in sorted(glob.glob(K.SC + 'score_*.pkl')):
        r = pickle.load(open(f, 'rb')); S[r['key']] = r
    return S


def per_fire(r, s, B, per, p):
    """per-fire saved (n, 3) for strategy s at budget B; rand = mean of 5 draws; None -> zeros."""
    n = r['n_test'] if per == 'test' else r['n_train']
    if s in ('rand', 'randkm'):
        arr = [r['res'][(s, B, d)] for d in range(5)]
        v = [a[(per, p)] if a is not None else np.zeros((n, 3), np.float32) for a in arr]
        km = np.mean([a['km'] if a is not None else 0.0 for a in arr])
        return np.mean(v, 0), km
    a = r['res'][(s, B, 0)]
    return (a[(per, p)], a['km']) if a is not None else (np.zeros((n, 3), np.float32), 0.0)


def stat(S, keys, s, B, p, per='test'):
    ny = len(K.TEST) if per == 'test' else len(K.TRAIN)
    V = [per_fire(S[k], s, B, per, p) for k in keys]
    km = sum(v[1] for v in V); tot = sum(v[0].sum(0) for v in V)
    return V, km, tot / ny


def boot(S, keys, fn):
    out = []
    for _ in range(NB):
        I = {k: RNG.integers(0, S[k]['n_test'], S[k]['n_test']) for k in keys}
        out.append(fn(I))
    return np.percentile(np.array(out), [2.5, 97.5], axis=0)


def main():
    S = load(); keys = sorted(S); A = pickle.load(open(K.SC + 'alloc.pkl', 'rb'))
    T = {}
    burnt_forest_yr = sum(S[k]['test_forest_ha'].sum() for k in keys) / len(K.TEST)
    burnt_ground_yr = sum(S[k]['test_ha'].sum() for k in keys) / len(K.TEST)
    T['test_burnt_forest_ha_yr'] = burnt_forest_yr; T['test_burnt_ha_yr'] = burnt_ground_yr
    T['n_test_fires'] = int(sum(S[k]['n_test'] for k in keys)); T['n_train_fires'] = int(sum(S[k]['n_train'] for k in keys)); T['n_div'] = len(keys)
    rows = []
    cache = {}
    for B in K.BUDGETS:
        for p in K.PS:
            for s in STRATS:
                V, km, tot = stat(S, keys, s, B, p); cache[(s, B, p)] = (V, km)
                Vt, kmt, tott = stat(S, keys, s, B, p, 'train')
                if km == 0: continue
                ny = len(K.TEST)
                lohi = boot(S, keys, lambda I: sum(v[0][I[k]].sum(0) for v, k in zip(V, keys)) / km / ny)
                row = dict(budget=B, p=p, strategy=s, km=round(km, 1))
                for w, i in WH.items():
                    row[f'{w}_ha_km_yr'] = round(tot[i] / km, 3); row[f'{w}_lo'] = round(lohi[0][i], 3); row[f'{w}_hi'] = round(lohi[1][i], 3)
                    row[f'{w}_train_ha_km_yr'] = round(tott[i] / max(kmt, 1e-9), 3); row[f'{w}_ha_yr'] = round(tot[i], 1)
                row['pct_burnt_forest'] = round(100 * tot[1] / burnt_forest_yr, 4); row['pct_burnt_forest_patchonly'] = round(100 * tot[0] / burnt_forest_yr, 4)
                rows.append(row)
            # paired differences per km: comp minus each other strategy
            for s in STRATS[1:]:
                (Vc, kc), (Vo, ko) = cache[('comp', B, p)], cache[(s, B, p)]
                if ko == 0: continue
                ny = len(K.TEST)
                f = lambda I: sum(v[0][I[k]].sum(0) for v, k in zip(Vc, keys)) / kc / ny - sum(v[0][I[k]].sum(0) for v, k in zip(Vo, keys)) / ko / ny
                est = f({k: np.arange(S[k]['n_test']) for k in keys}); lohi = boot(S, keys, f)
                rows.append(dict(budget=B, p=p, strategy=f'comp_minus_{s}', **{f'{w}_ha_km_yr': round(est[i], 3) for w, i in WH.items()},
                                 **{f'{w}_lo': round(lohi[0][i], 3) for w, i in WH.items()}, **{f'{w}_hi': round(lohi[1][i], 3) for w, i in WH.items()}))
    ST = pd.DataFrame(rows); ST.to_csv(K.OUT + 'strategy_table.csv', index=False); T['strategy'] = ST.to_dict('records')
    print(ST[(ST.p == 0.35)][['budget', 'strategy', 'km', 'patch_ha_km_yr', 'patch_lo', 'patch_hi', 'forest_ha_km_yr', 'forest_lo', 'forest_hi', 'patch_train_ha_km_yr', 'pct_burnt_forest']].to_string(), flush=True)
    # conservative start rule (every new front its own start), 500 km, p 0.35
    fr = []
    for st in STRATS:
        V = []
        for k in keys:
            F = S[k]['fronts']
            if st in ('rand', 'randkm'):
                a = [F.get((st, 500, d)) for d in range(5)]
                v = np.mean([x[0] if x is not None else np.zeros((S[k]['n_test'], 3), np.float32) for x in a], 0); km = np.mean([x[1] if x is not None else 0 for x in a])
            else:
                x = F.get((st, 500, 0)); v, km = (x if x is not None else (np.zeros((S[k]['n_test'], 3), np.float32), 0.0))
            V.append((v, km))
        km = sum(v[1] for v in V); tot = sum(v[0].sum(0) for v in V) / len(K.TEST)
        lohi = boot(S, keys, lambda I: sum(v[0][I[k]].sum(0) for v, k in zip(V, keys)) / km / len(K.TEST))
        main_ = [r for r in rows if r['budget'] == 500 and r['p'] == 0.35 and r['strategy'] == st][0]
        fr.append(dict(strategy=st, km=round(km, 1), patch_ha_km_yr=round(tot[0] / km, 3), patch_lo=round(lohi[0][0], 3), patch_hi=round(lohi[1][0], 3),
                       forest_ha_km_yr=round(tot[1] / km, 3), forest_lo=round(lohi[0][1], 3), forest_hi=round(lohi[1][1], 3),
                       patch_ratio_to_main=round(tot[0] / km / main_['patch_ha_km_yr'], 3), forest_ratio_to_main=round(tot[1] / km / main_['forest_ha_km_yr'], 3)))
    T['fronts_500'] = fr; print(pd.DataFrame(fr).to_string(), flush=True)
    # by year (500 km, p 0.35): comp vs corridor, patch and forest
    by = []
    for s in STRATS:
        V, km = cache[(s, 500, 0.35)]
        for y in K.TEST:
            t = sum(v[0][S[k]['test_year'] == y].sum(0) for v, k in zip(V, keys))
            by.append(dict(strategy=s, year=y, patch_ha_km=round(t[0] / km, 3), forest_ha_km=round(t[1] / km, 3)))
    T['by_year_500'] = by
    # allocation curve and n*
    cv = A['curve']; T['alloc_curve'] = cv.round(3).to_dict('records')
    P = A['P']; ns = {}
    for B in K.BUDGETS:
        n = np.array(list(A[('comp', B)].values())) + 1
        ns[B] = dict(patches=len(n), nstar_median=float(np.median(n)), nstar_p90=float(np.percentile(n, 90)), nstar_max=int(n.max()), share_n2=round(float((n == 2).mean()), 3),
                     cuts=int((n - 1).sum()), lam=float(cv[cv.budget == B].lam.iloc[0]))
    T['nstar'] = ns
    # patches with any cut available, mean curve shape (first cut vs later cuts)
    allp = pd.DataFrame([dict(key=k, patch=p, ncut=len(d['km']), g1=d['g'][0] / d['km'][0], km=d['km'].sum(), g=d['g'].sum(), t=d['test_cum'][-1]) for (k, p), d in P.items()])
    T['patches_with_cuts'] = dict(n=len(allp), cuts_median=float(allp.ncut.median()), first_cut_ha_km_yr_median=round(float(allp.g1.median()), 3))
    T['n_patches_tr3'] = int(pd.read_csv(K.SC26 + 'patch_stats.csv').query("set == 'tr3'").n_patches.sum())
    # cut kinds
    kc = {}
    for f in sorted(glob.glob(K.SC + 'cuts_tr3_*.pkl')):
        R = pickle.load(open(f, 'rb')); key = R['key']
        for r in R['patches']:
            n = A[('comp', 500)].get((key, r['patch']), 0)
            for i, s in enumerate(r['seq']):
                kc.setdefault('all', {}).setdefault(s['kind'], 0); kc['all'][s['kind']] += 1
                if i < n: kc.setdefault('500', {}).setdefault(s['kind'], 0); kc['500'][s['kind']] += 1
    T['kinds'] = kc
    # where the saved patch hectares come from (500 km, p 0.35): test fires that started inside a 2017-21 patch vs not
    E = pd.read_parquet(K.SC26 + 'entries_tr3.parquet'); E = E[E.year.isin(K.TEST)]
    ins = set(zip(E[E.status == 'inside'].key, E[E.status == 'inside'].fi))
    src = {'inside': np.zeros(3), 'other': np.zeros(3)}
    for k in keys:
        L = pickle.load(open(K.SC26 + f'fires_{k}.pkl', 'rb')); yrs = np.array([f['year'] for f in L['fires']]); idx = np.nonzero(np.isin(yrs, K.TEST))[0]
        v, _ = per_fire(S[k], 'comp', 500, 'test', 0.35)
        m = np.array([(k, int(i)) in ins for i in idx])
        if len(m): src['inside'] += v[m].sum(0); src['other'] += v[~m].sum(0)
    T['saved_by_start'] = {a: (b / len(K.TEST)).round(2).tolist() for a, b in src.items()}
    T['test_fires_started_inside_a_patch'] = len(ins)
    # per division (500 km, p 0.35)
    dr = []
    for k in keys:
        r = S[k]; row = dict(key=k, division=r['div'], set='core' if k in K.CORE else 'rest', test_fires=r['n_test'], test_burnt_forest_ha_yr=round(r['test_forest_ha'].sum() / len(K.TEST)))
        ncomp = {p: n for (kk, p), n in A[('comp', 500)].items() if kk == k}
        row['patches_cut'] = len(ncomp); row['cuts'] = sum(ncomp.values())
        for s in STRATS:
            v, km = per_fire(r, s, 500, 'test', 0.35); row[f'{s}_km'] = round(km, 1)
            row[f'{s}_patch'] = round(v[:, 0].sum() / max(km, 1e-9) / len(K.TEST), 3) if km else np.nan
            row[f'{s}_forest'] = round(v[:, 1].sum() / max(km, 1e-9) / len(K.TEST), 3) if km else np.nan
            if s == 'comp' and km:
                lohi = boot(S, [k], lambda I: v[I[k]].sum(0) / km / len(K.TEST)); row['comp_patch_lo'], row['comp_patch_hi'] = round(lohi[0][0], 3), round(lohi[1][0], 3)
                row['comp_patch_ha_yr'] = round(v[:, 0].sum() / len(K.TEST), 2); row['comp_forest_ha_yr'] = round(v[:, 1].sum() / len(K.TEST), 2)
                vt, _ = per_fire(r, s, 500, 'train', 0.35); row['comp_patch_train'] = round(vt[:, 0].sum() / km / len(K.TRAIN), 3)
                row['comp_pct_burnt_forest'] = round(100 * v[:, 1].sum() / max(r['test_forest_ha'].sum(), 1e-9), 3)
        dr.append(row)
    DD = pd.DataFrame(dr).sort_values('comp_km', ascending=False); DD.to_csv(K.OUT + 'division_table.csv', index=False)
    T['division_wins'] = {s: int((DD.comp_patch > DD[f'{s}_patch']).sum()) for s in STRATS[1:]}
    T['division_with_cuts'] = int((DD.comp_km > 0).sum())
    # top tested patches at 500 km: ranked by 2017-21 benefit (what a planner sees), with 2022-25 outcome
    rows = []
    for (k, p), n in A[('comp', 500)].items():
        d = P[(k, p)]
        rows.append(dict(key=k, patch=p, nstar=n + 1, km=round(d['km'][:n].sum(), 2), train_ha_yr=round(d['g'][:n].sum(), 2), test_ha_yr=round(float(d['test_cum'][n - 1]), 2),
                         fires_2017_21=d['n_fires'], fires_2022_25=d['n_fires_test']))
    TP = pd.DataFrame(rows).sort_values('train_ha_yr', ascending=False)
    # locations
    loc = {}
    for f in sorted(glob.glob(K.SC + 'cuts_tr3_*.pkl')):
        R = pickle.load(open(f, 'rb'))
        for r in R['patches']:
            if (R['key'], r['patch']) not in A[('comp', 500)]: continue
            r0, r1, c0, c1 = r['box']; pm = (r['comp_final'] != 0) | r['line_final']; rr, cc = np.nonzero(pm)
            lo, la = K.C25.TB.transform(R['x0'] + (cc.mean() + c0 + .5) * K.RES, R['y1'] - (rr.mean() + r0 + .5) * K.RES)
            loc[(R['key'], r['patch'])] = (round(float(lo), 4), round(float(la), 4), round(r['n_patch_cells'] * K.CELL_HA), R['div'])
    TP['lon'] = [loc[(k, p)][0] for k, p in zip(TP.key, TP.patch)]; TP['lat'] = [loc[(k, p)][1] for k, p in zip(TP.key, TP.patch)]
    TP['patch_ha'] = [loc[(k, p)][2] for k, p in zip(TP.key, TP.patch)]; TP['division'] = [loc[(k, p)][3] for k, p in zip(TP.key, TP.patch)]
    TP.to_csv(K.OUT + 'top_tested_patches.csv', index=False)
    T['top_tested'] = dict(n=len(TP), share_zero_test=round(float((TP.test_ha_yr <= 0.005).mean()), 3), top20_train=round(TP.head(20).train_ha_yr.sum(), 1), top20_test=round(TP.head(20).test_ha_yr.sum(), 1))
    json.dump(T, open(K.OUT + 'tables.json', 'w'), indent=1, default=float)
    print(json.dumps({k: T[k] for k in ('nstar', 'kinds', 'saved_by_start', 'division_wins', 'top_tested', 'patches_with_cuts')}, default=float, indent=0), flush=True)


if __name__ == '__main__':
    main()
