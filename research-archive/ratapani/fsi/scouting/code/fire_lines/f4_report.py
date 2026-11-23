"""Step 4. Tables, bootstrap CIs (resampling whole test fires), maps and the geojson of top lines.
Out: out/summary_tables.json, out/division_table.csv, out/fig_*.png (the geojson is written by f5_final.py)."""
import pickle, glob, json
import numpy as np, pandas as pd, shapely, geopandas as gpd
import matplotlib; matplotlib.use('Agg'); import matplotlib.pyplot as plt
import common as C

B = (10, 20, 50); RNG = np.random.default_rng(11); NB = 1000
METH = ['plan', 'plan_stable', 'plan_plus', 'road_only', 'straight_tr', 'hotspot', 'rand_forest', 'rand_road', 'rand_beat', 'oracle']
BASE = ['road_only', 'straight_tr', 'hotspot', 'rand_forest', 'rand_road', 'rand_beat']


def load():
    R = {}
    for p in sorted(glob.glob(C.SC + 'sel_*.pkl')):
        r = pickle.load(open(p, 'rb')); R[r['key']] = r
    return R


def boot(group, m, b, ref=None):
    """group: list of R. ha/km on test (sum over divisions) with CI from resampling fires within each division;
    with ref, the difference m - ref in ha/km (paired: same resampled fires)."""
    est, diff = [], []
    km = sum(r['KM'][(m, b)] for r in group); kmr = sum(r['KM'][(ref, b)] for r in group) if ref else 1
    pt = sum(r['V'][(m, b)].sum() for r in group) / km
    pr = (sum(r['V'][(ref, b)].sum() for r in group) / kmr) if ref else None
    for _ in range(NB):
        s, sr = 0.0, 0.0
        for r in group:
            n = len(r['test_fire_ha'])
            if n == 0: continue
            i = RNG.integers(0, n, n); s += r['V'][(m, b)][i].sum()
            if ref: sr += r['V'][(ref, b)][i].sum()
        est.append(s / km); diff.append(s / km - sr / kmr if ref else 0)
    lo, hi = np.percentile(est, [2.5, 97.5]); dlo, dhi = np.percentile(diff, [2.5, 97.5])
    return dict(est=pt, lo=lo, hi=hi, diff=(pt - pr) if ref else None, dlo=dlo, dhi=dhi, p_le0=float(np.mean(np.array(diff) <= 0)) if ref else None)


def chain_line(cells, g):
    r, c = cells // g['W'], cells % g['W']
    x = g['x0'] + (c + .5) * C.RES; y = g['y1'] - (r + .5) * C.RES
    lon, lat = C.TB.transform(x, y)
    return shapely.simplify(shapely.LineString(np.c_[lon, lat]), 0.0002)


def main():
    R = load(); core = [r for k, r in R.items() if k in C.CORE]; rest = [r for k, r in R.items() if k not in C.CORE]
    out = {}
    # per-division table
    rows = []
    for k, r in R.items():
        for b in B:
            row = dict(key=k, division=r['div'], set='core' if k in C.CORE else 'rest_of_mp', budget_km=b, km=round(r['KM'][('plan', b)], 1),
                       train_years='-'.join(map(str, (r['tr_years'][0], r['tr_years'][-1]))), test_years='-'.join(map(str, (r['te_years'][0], r['te_years'][-1]))),
                       n_test_fires=r['n_test'], test_burnt_ha=round(r['test_ha']),
                       train_ha_per_km=round(r['VT'][('plan', b)] / r['KM'][('plan', b)] / len(r['tr_years']), 2))
            for m in METH: row[m] = round(r['V'][(m, b)].sum() / max(r['KM'][(m, b)], 1e-9) / len(r['te_years']), 2)
            row['plan_pct_test_ha'] = round(100 * r['V'][('plan', b)].sum() / r['test_ha'], 2)
            bs = boot([r], 'plan', b, 'rand_forest'); row['plan_lo'] = round(bs['lo'] / len(r['te_years']), 2); row['plan_hi'] = round(bs['hi'] / len(r['te_years']), 2)
            bb = max(BASE, key=lambda m: r['V'][(m, b)].sum() / max(r['KM'][(m, b)], 1e-9)); row['best_baseline'] = bb
            d = boot([r], 'plan', b, bb); row['plan_minus_best_lo'] = round(d['dlo'] / len(r['te_years']), 2); row['plan_minus_best_hi'] = round(d['dhi'] / len(r['te_years']), 2)
            rows.append(row)
        print(k, 'table done', flush=True)
    T = pd.DataFrame(rows); T.to_csv(C.OUT + 'division_table.csv', index=False)
    # pooled (per year of test: divide by number of test seasons, all core divisions have 4)
    for nm, grp in (('core', core), ('rest_of_mp', rest)):
        if not grp: continue
        ny = np.mean([len(r['te_years']) for r in grp])
        out[nm] = {}
        for b in B:
            d = {}
            for m in METH:
                km = sum(r['KM'][(m, b)] for r in grp)
                d[m] = dict(ha_per_km_yr=sum(r['V'][(m, b)].sum() for r in grp) / km / ny, km=km)
            bp = boot(grp, 'plan', b); d['plan'].update(lo=bp['lo'] / ny, hi=bp['hi'] / ny)
            for m in BASE:
                x = boot(grp, 'plan', b, m); d[m].update(plan_minus=x['diff'] / ny, dlo=x['dlo'] / ny, dhi=x['dhi'] / ny, p_le0=x['p_le0'])
            d['pct_test_ha_plan'] = 100 * sum(r['V'][('plan', b)].sum() for r in grp) / sum(r['test_ha'] for r in grp)
            d['pct_test_ha_oracle'] = 100 * sum(r['V'][('oracle', b)].sum() for r in grp) / sum(r['test_ha'] for r in grp)
            d['train_ha_per_km_yr_plan'] = sum(r['VT'][('plan', b)] for r in grp) / sum(r['KM'][('plan', b)] for r in grp) / np.mean([len(r['tr_years']) for r in grp])
            out[nm][b] = d
        # by test year, plan vs random forest lines at 20 km
        yy = {}
        for y in C.TEST:
            s = {m: sum(r['V'][(m, 20)][r['test_year'] == y].sum() for r in grp if y in r['te_years']) /
                 max(sum(r['KM'][(m, 20)] for r in grp if y in r['te_years']), 1e-9) for m in ('plan', 'rand_forest', 'road_only', 'hotspot', 'oracle')}
            yy[y] = s
        out[nm]['by_year'] = yy
        out[nm]['p_range'] = {str(p): sum(r['p_range'][p][0] for r in grp) / sum(r['KM'][('plan', 20)] for r in grp) / ny for p in grp[0]['p_range']}
        out[nm]['fronts20'] = {m: sum(r['fronts20'][m] for r in grp) / sum(r['KM'][(m, 20)] for r in grp) / ny for m in ('plan', 'plan_stable', 'plan_plus', 'straight_tr', 'road_only', 'hotspot')}
        out[nm]['rank_rho'] = {r['key']: r['rank_rho'] for r in grp}
        out[nm]['top1pct'] = {r['key']: r['top1pct_test_vs_all'] for r in grp}
        kinds = []
        for r in grp:
            t = 0.0
            for k in r['sel']['plan']:
                t += r['lines'][k]['km']
                if t > 22: break
                kinds.append(r['lines'][k]['kind'])
        out[nm]['kinds20'] = pd.Series(kinds).value_counts().to_dict()
        out[nm]['n_div'] = len(grp); out[nm]['test_ha'] = sum(r['test_ha'] for r in grp); out[nm]['n_test_fires'] = sum(r['n_test'] for r in grp)
    json.dump(out, open(C.OUT + 'summary_tables.json', 'w'), indent=1, default=float)
    figs(R, out)


def figs(R, out):
    # Fig 1: pooled core ha/km/yr by method at 10/20/50 km
    for nm in [n for n in ('core', 'rest_of_mp') if n in out]:
        fig, ax = plt.subplots(figsize=(8, 4.2))
        lab = {'plan': 'plan (chosen 2017-21)', 'plan_stable': 'plan, lines useful in 2+ seasons', 'plan_plus': 'plan + straight lines', 'road_only': 'roads only (chosen)', 'straight_tr': 'straight lines (chosen)', 'hotspot': 'most-burnt ground',
               'rand_forest': 'random in forest', 'rand_road': 'random road bits', 'rand_beat': 'random beat edges', 'oracle': 'ceiling (chosen on test)'}
        w = 0.09
        for i, m in enumerate(METH):
            v = [out[nm][b][m]['ha_per_km_yr'] for b in B]
            ax.bar(np.arange(3) + (i - 4.5) * w, v, w, label=lab[m], color=plt.cm.tab10(i), alpha=.5 if m == 'oracle' else 1)
            if m == 'plan':
                lo = [out[nm][b]['plan']['lo'] for b in B]; hi = [out[nm][b]['plan']['hi'] for b in B]
                ax.errorbar(np.arange(3) + (i - 4.5) * w, v, yerr=[np.array(v) - lo, np.array(hi) - v], fmt='none', ecolor='k', lw=1)
        ax.set_xticks(range(3)); ax.set_xticklabels([f'{b} km per division' for b in B]); ax.set_ylabel('ha saved per km per year, 2022-25')
        ax.set_title(f'Held-out test ({nm.replace("_", " ")}): expected burnt ha saved per km of new line, stop chance {C.P_STOP}')
        ax.legend(fontsize=7, ncol=2); fig.tight_layout(); fig.savefig(C.OUT + f'fig_test_{nm}.png', dpi=130); plt.close(fig)
    # Fig 2: maps of training spread flow + plan lines for four core divisions
    keys = [k for k in ('Obedullahganj', 'Noradehi', 'Panna_TR', 'Satpura_TR') if k in R]
    fig, axs = plt.subplots(2, 2, figsize=(11, 10))
    for ax, k in zip(axs.ravel(), keys):
        r = R[k]; Ly = np.load(C.SC + f'layers_{k}.npz'); F = Ly['flow']; ins = Ly['inside']; fo = Ly['forest']
        from scipy.ndimage import gaussian_filter
        F = gaussian_filter(F, 2.0); img = np.where(ins, np.log10(1 + F), np.nan)
        Lf = pickle.load(open(C.SC + f'fires_{k}.pkl', 'rb')); TB = np.zeros_like(F, dtype=bool)
        for fr in Lf['fires']:
            if fr['year'] in r['te_years']:
                M = np.unpackbits(fr['M'])[:fr['shape'][0] * fr['shape'][1]].reshape(fr['shape']).astype(bool)
                TB[fr['r0']:fr['r0'] + M.shape[0], fr['c0']:fr['c0'] + M.shape[1]] |= M
        ax.imshow(np.where(ins & fo, 0.2, np.where(ins, 0.05, np.nan)), cmap='Greens', vmin=0, vmax=1, interpolation='nearest')
        ax.imshow(np.where(F > 1, img, np.nan), cmap='magma_r', vmin=0, vmax=3, interpolation='nearest')
        ax.contour(TB.astype(float), levels=[.5], colors='royalblue', linewidths=.4)
        t = 0
        for kk in r['sel']['plan']:
            ln = r['lines'][kk]; t += ln['km']
            if t > 20.5: break
            cl = ln['cells']; ax.plot(cl % r['grid']['W'], cl // r['grid']['W'], '-', color='cyan', lw=2.2)
        rr, cc = np.nonzero(ins)
        ax.set_xlim(cc.min() - 10, cc.max() + 10); ax.set_ylim(rr.max() + 10, rr.min() - 10); ax.set_xticks([]); ax.set_yticks([])
        ax.set_title(f"{r['div']}: spread flow 2017-21 + first ~20 km of plan", fontsize=9)
    fig.suptitle('Orange-dark = ground that 2017-21 fires burned through to reach more forest (spread flow, ha downstream, log). Blue outlines = 2022-25 test burns. Cyan = lines chosen on 2017-21.', fontsize=9)
    fig.tight_layout(); fig.savefig(C.OUT + 'fig_maps_core.png', dpi=120); plt.close(fig)
    # Fig 3: per-division plan vs best baseline at 20 km
    T = pd.read_csv(C.OUT + 'division_table.csv'); T = T[T.budget_km == 20].sort_values('plan')
    fig, ax = plt.subplots(figsize=(8, max(4, .18 * len(T))))
    y = np.arange(len(T))
    ax.barh(y - .2, T.plan, .4, label='plan (chosen 2017-21)', color='C0')
    ax.barh(y + .2, T[['road_only', 'straight_tr', 'hotspot', 'rand_forest', 'rand_road', 'rand_beat']].max(axis=1), .4, label='best of 6 baselines (picked after seeing the test)', color='C7')
    ax.set_yticks(y); ax.set_yticklabels([d[:22] + (' *' if s == 'core' else '') for d, s in zip(T.division, T.set)], fontsize=6)
    ax.set_xlabel('test ha saved per km per year (20 km per division)'); ax.legend(fontsize=8); ax.set_title('* = complete scar set (tiger reserves, Ratapani)', fontsize=8)
    fig.tight_layout(); fig.savefig(C.OUT + 'fig_divisions.png', dpi=130); plt.close(fig)


if __name__ == '__main__':
    main()
