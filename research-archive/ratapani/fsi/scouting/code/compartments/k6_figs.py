"""Part B figures (conference paper) and Part A figures. Every number drawn here is read from round-25/26/27 outputs.
Run: python k6_figs.py [names...]   Out: scouting/conference/figs/*.png (and copies used by repeat_patch_compartments.md in out/)"""
import pickle, glob, json, sys, shutil
import numpy as np, pandas as pd, geopandas as gpd, shapely
import matplotlib; matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.colors import ListedColormap, BoundaryNorm
from matplotlib.lines import Line2D
from matplotlib.patches import Patch as MPatch
import k0 as K

FIG = K.CONF + 'figs/'
R26 = '/mnt/project-files/ratapani/fsi/scouting/code/repeat_patch_lines/out/'
R25 = '/mnt/project-files/ratapani/fsi/scouting/code/fire_lines/out/'
DIVS = '/mnt/project-files/fire-alert-scars/mp/out/mp_divisions.geojson'
plt.rcParams.update({'font.size': 9, 'axes.titlesize': 10, 'axes.spines.top': False, 'axes.spines.right': False, 'savefig.dpi': 200,
                     'font.family': 'DejaVu Sans'})
COL = dict(comp='#1b6ca8', rand='#9db4c8', randkm='#c7d7e6', entry='#d98c1f', ring='#7a5195', corridor='#2e8b57')
NAME = dict(comp='Compartment cuts', rand='Random cuts (same patches, same n)', randkm='Random cuts (same patches, same km)', entry='Entry-side lines (r26)', ring='Perimeter ring', corridor='Corridor lines (r25)')


def divs():
    D = gpd.read_file(DIVS).to_crs(32643); D['key'] = D.Division.map(K.slug); return D


def save(fig, name):
    fig.savefig(FIG + name, bbox_inches='tight'); plt.close(fig); print('saved', name, flush=True)


def fig_mp_map():
    Z = np.load(K.SC + 'mosaic.npz'); CA = Z['cnt_all'].astype(float); x0, y1, res = float(Z['x0']), float(Z['y1']), float(Z['res'])
    k = 5  # 600 m blocks
    H, W = CA.shape; Hb, Wb = H // k, W // k
    A = CA[:Hb * k, :Wb * k].reshape(Hb, k, Wb, k)
    forest = (A >= 0).sum((1, 3)); s = np.where(A >= 0, A, 0).sum((1, 3))
    mean = np.where(forest >= 5, s / np.maximum(forest, 1), np.nan)
    k2 = 10; H2, W2 = H // k2, W // k2; A2 = CA[:H2 * k2, :W2 * k2].reshape(H2, k2, W2, k2)
    f2 = (A2 >= 0).sum((1, 3)); rep = (A2 >= 5).sum((1, 3)); share5 = np.where(f2 >= 10, rep / np.maximum(f2, 1), np.nan)
    ext2 = [x0, x0 + W2 * k2 * res, y1 - H2 * k2 * res, y1]
    ext = [x0, x0 + Wb * k * res, y1 - Hb * k * res, y1]
    D = divs()
    fig, ax = plt.subplots(1, 2, figsize=(11, 4.4))
    cm = plt.get_cmap('YlOrRd')
    im = ax[0].imshow(mean, extent=ext, cmap=cm, vmin=0, vmax=3, interpolation='nearest')
    D.boundary.plot(ax=ax[0], color='0.35', lw=0.3)
    ax[0].set_title('a. Mean seasons burnt per forest cell, 2017-25', fontsize=9)
    plt.colorbar(im, ax=ax[0], shrink=0.7, label='seasons burnt (600 m block mean)')
    cm2 = ListedColormap(['#f2f2f2', '#fdd49e', '#fc8d59', '#d7301f', '#7f0000'])
    nb = BoundaryNorm([0, 0.0001, 0.05, 0.15, 0.3, 1.01], 5)
    im2 = ax[1].imshow(share5, cmap=cm2, norm=nb, interpolation='nearest', extent=ext2)
    D.boundary.plot(ax=ax[1], color='0.35', lw=0.3)
    cb = plt.colorbar(im2, ax=ax[1], shrink=0.7, ticks=[0, 0.05, 0.15, 0.3, 1.0]); cb.set_label('share of forest')
    ax[1].set_title('b. Forest burnt in >= 5 of 9 seasons (1.2 km blocks)', fontsize=9)
    for a in ax:
        a.set_xlabel(''); a.set_ylabel(''); a.plot([ext[0] + 30e3, ext[0] + 130e3], [ext[2] + 30e3] * 2, 'k-', lw=2); a.text(ext[0] + 80e3, ext[2] + 40e3, '100 km', ha='center', fontsize=7)
        a.set_xticks([]); a.set_yticks([]); a.set_xlim(ext[0], ext[1]); a.set_ylim(ext[2], ext[3]); a.set_aspect('equal')
        for s_ in a.spines.values(): s_.set_visible(False)
    core = D[D.key.isin(K.CORE)]
    for _, r in core.iterrows():
        c = r.geometry.representative_point(); ax[1].annotate(r.Division.split(' (')[0].replace('_', ' ').replace('Kanha Tiger Reserve', 'Kanha').replace('Madhav National Park', 'Madhav')
                                                               .replace('SANJAY DUBRI', 'Sanjay-Dubri').replace('PTR MP', 'Pench').replace('Obedullahganj', 'Ratapani'),
                                                               (c.x, c.y), fontsize=6, ha='center', color='navy')
    save(fig, 'fig01_mp_repeat_map.png')


def fig_repeat_stats():
    T = json.load(open(R26 + 'tables.json'))
    obs = np.array(T['hist']['all MP']); ind = np.array(T['hist_indep']['all MP'])
    fig, ax = plt.subplots(1, 2, figsize=(10, 3.4))
    x = np.arange(1, 10)
    ax[0].bar(x - 0.2, obs[1:] / obs[1:].sum() * 100, 0.4, label='observed', color='#c0392b')
    ax[0].bar(x + 0.2, ind[1:] / ind[1:].sum() * 100, 0.4, label='if seasons burnt independently', color='0.7')
    ax[0].set_yscale('log'); ax[0].set_xlabel('seasons burnt, 2017-25 (120 m forest cells burnt at least once)'); ax[0].set_ylabel('% of cells (log)')
    ax[0].legend(frameon=False, fontsize=8); ax[0].set_title('a. Burnt ground keeps burning')
    s1 = {r['set']: r for r in T['step1'] if r['grp'] == 'all MP'}
    yrs = [str(y) for y in K.ALL]
    for s, c, lab in (('tr3', '#1b6ca8', '>= 3 of 5 seasons 2017-21 (4.8% of forest)'), ('tr4', '#7a5195', '>= 4 of 5 (1.2%)'), ('tr5', '#d98c1f', '5 of 5 (0.16%)')):
        ax[1].plot(K.ALL, [s1[s][y] for y in yrs], 'o-', color=c, label=lab, ms=3)
    ax[1].axvspan(2021.5, 2025.5, color='0.92', zorder=0); ax[1].text(2023.5, 40, 'held out', ha='center', fontsize=8)
    ax[1].set_ylabel('% of season\'s burnt forest inside patches'); ax[1].set_title('b. Patches defined on 2017-21')
    ax[1].legend(frameon=False, fontsize=7, loc='upper left'); ax[1].set_ylim(0, 66)
    save(fig, 'fig02_repeat_stats.png')


def fig_entries():
    T = json.load(open(R26 + 'tables.json'))['entries']
    S = pd.read_parquet(K.SC26 + 'patches_tr3.parquet'); s3 = S[S.n_entered >= 3]
    fig, ax = plt.subplots(1, 2, figsize=(10, 3.4))
    labs = [('core 2017-21', 'tr3|core|def'), ('core 2022-25', 'tr3|core|test'), ('rest 2017-21', 'tr3|rest|def'), ('rest 2022-25', 'tr3|rest|test')]
    cats = [('started inside', lambda r: r['inside'], '#c0392b'), ('edge (<400 m)', lambda r: r['entered'] - r['entered_from_out'], '#f39c12'),
            ('from >=400 m outside', lambda r: r['entered_from_out'], '#2e86c1'), ('not connected', lambda r: r['unreached'], '0.75')]
    left = np.zeros(len(labs))
    for nm, f, c in cats:
        v = np.array([f(T[k]) for _, k in labs]); ax[0].barh(range(len(labs)), v, left=left, color=c, label=nm); left += v
    ax[0].set_yticks(range(len(labs))); ax[0].set_yticklabels([l for l, _ in labs]); ax[0].invert_yaxis()
    ax[0].set_xlabel('% of patch-seasons (main fire)'); ax[0].legend(frameon=False, fontsize=7, ncol=2, loc='lower center', bbox_to_anchor=(0.5, -0.38))
    ax[0].set_title('a. Where the main fire of each patch-season started')
    ax[1].scatter(s3.chance_share, s3.mode_share + np.random.default_rng(1).normal(0, 0.006, len(s3)), s=5, alpha=0.35, color='#2e86c1')
    ax[1].plot([0.3, 1], [0.3, 1], 'k--', lw=0.8)
    ax[1].set_xlabel('top-segment share expected by chance'); ax[1].set_ylabel('observed top-segment share')
    ax[1].set_title(f'b. Entry side vs chance ({len(s3)} patches, >= 3 entries)')
    save(fig, 'fig03_entries.png')


def _tab():
    return json.load(open(K.OUT + 'tables.json'))


def fig_strategies():
    ST = pd.read_csv(K.OUT + 'strategy_table.csv'); ST = ST[ST.p == 0.35]
    fig, ax = plt.subplots(1, 2, figsize=(10.5, 3.6))
    Bs = list(K.BUDGETS); x = np.arange(len(Bs)); wd = 0.14
    for j, (w, ttl) in enumerate((('patch', 'a. Repeat-patch forest saved'), ('forest', 'b. All forest saved'))):
        for i, s in enumerate(('comp', 'randkm', 'rand', 'entry', 'ring', 'corridor')):
            d = ST[ST.strategy == s].set_index('budget').reindex(Bs)
            v = d[f'{w}_ha_km_yr'].values; lo = d[f'{w}_lo'].values; hi = d[f'{w}_hi'].values
            ax[j].bar(x + (i - 2.5) * wd, v, wd, color=COL[s], label=NAME[s])
            ax[j].errorbar(x + (i - 2.5) * wd, v, yerr=[v - lo, hi - v], fmt='none', ecolor='k', lw=0.7, capsize=1.5)
        ax[j].set_xticks(x); ax[j].set_xticklabels([f'{b} km' for b in Bs]); ax[j].set_title(ttl)
        ax[j].set_ylabel('ha saved per km of line per year\n(held out 2022-25, stop chance 0.35)')
        ax[j].set_xlabel('statewide line budget (ranked on 2017-21)')
    ax[0].legend(frameon=False, fontsize=7, loc='upper right')
    save(fig, 'fig06_strategies.png')


def fig_budget():
    T = _tab(); cv = pd.DataFrame(T['alloc_curve']); ST = pd.read_csv(K.OUT + 'strategy_table.csv'); ST = ST[ST.p == 0.35]
    fig, ax = plt.subplots(1, 2, figsize=(10.5, 3.6))
    cv = cv[cv.budget <= 3000]
    ax[0].plot(cv.km, cv.train_patch, '-', color=COL['comp'], label='compartments, in-sample (2017-21)')
    ax[0].plot(cv.km, cv.test_patch_indep, '--', color=COL['comp'], label='compartments, held out (2022-25)')
    for s in ('comp', 'randkm', 'entry', 'ring', 'corridor'):
        d = ST[ST.strategy == s]
        ax[0].errorbar(d.km, d.patch_ha_yr, yerr=[d.patch_ha_yr - d.patch_lo * d.km, d.patch_hi * d.km - d.patch_ha_yr], fmt='o', color=COL[s], ms=4, lw=0.8,
                       label=NAME[s] + ' (held out)' if s != 'comp' else 'compartments, held out, joint scoring')
    ax[0].set_yscale('log'); ax[0].set_ylim(30, 1e5); ax[0].set_xlabel('km of line, statewide'); ax[0].set_ylabel('repeat-patch forest saved, ha per year (log)'); ax[0].set_title('a. Benefit vs budget')
    ax[0].legend(frameon=False, fontsize=6.5, loc='lower right')
    ax[1].plot(cv.km, cv.lam, '-', color=COL['comp'])
    ax[1].set_yscale('log'); ax[1].set_xlabel('km of line, statewide'); ax[1].set_ylabel('marginal ha / km / yr (in-sample, 2017-21)')
    ax[1].set_title('b. Marginal return of the last cut taken (lambda)')
    for B in K.BUDGETS:
        l = cv[cv.budget == B].lam.iloc[0]; ax[1].plot([B], [l], 'o', color='k', ms=3); ax[1].annotate(f'{B} km: {l:.2f}', (B, l), fontsize=7, xytext=(4, 4), textcoords='offset points')
    save(fig, 'fig07_budget.png')


def fig_divisions():
    DT = pd.read_csv(K.OUT + 'division_table.csv'); DT = DT[DT.comp_km > 0].sort_values('comp_km', ascending=False).head(30)
    fig, ax = plt.subplots(figsize=(10.5, 4.2))
    x = np.arange(len(DT)); wd = 0.27
    for i, s in enumerate(('comp', 'randkm', 'corridor')):
        ax.bar(x + (i - 1) * wd, DT[f'{s}_patch'], wd, color=COL[s], label=NAME[s])
    ax.errorbar(x - wd, DT.comp_patch, yerr=[DT.comp_patch - DT.comp_patch_lo, DT.comp_patch_hi - DT.comp_patch], fmt='none', ecolor='k', lw=0.6, capsize=1)
    ax.set_xticks(x); ax.set_xticklabels([d.replace('_', ' ')[:18] for d in DT.division], rotation=70, ha='right', fontsize=7)
    ax.set_ylabel('repeat-patch forest saved\nha / km / yr (2022-25)'); ax.legend(frameon=False, fontsize=7)
    ax.set_title('30 divisions with the most compartment km at the 500 km statewide budget')
    save(fig, 'fig08_divisions.png')


def fig_division_map():
    D = divs(); DT = pd.read_csv(K.OUT + 'division_table.csv'); PS = pd.read_csv(K.SC26 + 'patch_stats.csv'); PS = PS[PS.set == 'tr3']
    PS['held'] = 100 * PS[[f'inpatch_{y}' for y in K.TEST]].sum(1) / PS[[f'burnt_{y}' for y in K.TEST]].sum(1)
    D = D.merge(PS[['key', 'held']], on='key', how='left').merge(DT[['key', 'comp_km', 'comp_patch_ha_yr']], on='key', how='left')
    fig, ax = plt.subplots(1, 2, figsize=(11, 4.3))
    D.plot(column='held', ax=ax[0], cmap='OrRd', legend=True, vmin=0, vmax=40, edgecolor='0.4', lw=0.3, missing_kwds=dict(color='0.9'),
           legend_kwds=dict(shrink=0.7, label='% of 2022-25 burnt forest inside 2017-21 patches'))
    ax[0].set_title('a. Held-out share of burning in repeat patches', fontsize=9)
    D['kmc'] = D.comp_km.fillna(0)
    D.plot(column='kmc', ax=ax[1], cmap='Blues', legend=True, edgecolor='0.4', lw=0.3, legend_kwds=dict(shrink=0.7, label='km of compartment cuts (500 km statewide)'))
    ax[1].set_title('b. Where the 500 km budget goes', fontsize=9)
    for a in ax: a.set_axis_off()
    save(fig, 'fig04_division_maps.png')


def fig_examples():
    A = pickle.load(open(K.SC + 'alloc.pkl', 'rb')); TP = pd.read_csv(K.OUT + 'top_tested_patches.csv')
    from k3_final import compartments
    picks = []
    t = TP.sort_values('test_ha_yr', ascending=False).iloc[0]; picks.append((t.key, t.patch, 'best held-out result'))
    o = TP[TP.key.isin(K.CORE) & ~((TP.key == t.key) & (TP.patch == t.patch))].sort_values('train_ha_yr', ascending=False)
    if len(o): picks.append((o.iloc[0].key, o.iloc[0].patch, 'top-ranked other core patch'))
    z = TP[(TP.test_ha_yr <= 0.01) & ~TP.key.isin([p[0] for p in picks])].sort_values('train_ha_yr', ascending=False).iloc[0]; picks.append((z.key, z.patch, 'high 2017-21 value, nothing saved 2022-25'))
    b = TP[(TP.nstar >= 4) & ~TP.set_index(['key', 'patch']).index.isin([(p[0], p[1]) for p in picks])].sort_values('patch_ha', ascending=False).iloc[0]; picks.append((b.key, b.patch, 'large patch, several cuts'))
    S3 = pd.read_parquet(K.SC26 + 'patches_tr3.parquet'); RG = pickle.load(open(K.SC26 + 'rings_tr3.pkl', 'rb'))
    fig, axs = plt.subplots(2, 2, figsize=(10, 9.5))
    for ax, (key, p, ttl) in zip(axs.ravel(), picks):
        R = pickle.load(open(K.SC + f'cuts_tr3_{key}.pkl', 'rb')); rec = [r for r in R['patches'] if r['patch'] == p][0]; W = R['W']
        n = A[('comp', 500)][(key, p)]
        r0, r1, c0, c1 = rec['box']; m = 12; R0, C0 = max(r0 - m, 0), max(c0 - m, 0); R1, C1 = min(r1 + m, R['H']), min(c1 + m, W)
        L = pickle.load(open(K.SC26 + f'fires_{key}.pkl', 'rb'))
        burn = np.zeros((R1 - R0, C1 - C0)); starts = []
        for f in L['fires']:
            if f['year'] not in K.TEST: continue
            h, w = f['shape']
            if f['r0'] > R1 or f['r0'] + h < R0 or f['c0'] > C1 or f['c0'] + w < C0: continue
            M = np.unpackbits(f['M'])[:h * w].reshape(h, w).astype(bool)
            a0, b0 = max(f['r0'], R0), max(f['c0'], C0); a1, b1 = min(f['r0'] + h, R1), min(f['c0'] + w, C1)
            if a1 <= a0 or b1 <= b0: continue
            sub = M[a0 - f['r0']:a1 - f['r0'], b0 - f['c0']:b1 - f['c0']]
            if not sub.any(): continue
            burn[a0 - R0:a1 - R0, b0 - C0:b1 - C0] += sub
            dc = f['dotc'] if len(f['dotc']) else f['ign']
            rr, cc = dc // w + f['r0'] - R0, dc % w + f['c0'] - C0; ok = (rr >= 0) & (rr < R1 - R0) & (cc >= 0) & (cc < C1 - C0)
            if ok.any(): starts.append((cc[ok].mean() + C0, rr[ok].mean() + R0))
        ax.imshow(np.ma.masked_equal(burn, 0), cmap='Greys', vmin=0, vmax=5, alpha=0.6, extent=[C0 - .5, C1 - .5, R1 - .5, R0 - .5])
        _, lab = compartments(rec, [s['cells'] for s in rec['seq'][:n]], W, R['x0'], R['y1'])
        lab = np.ma.masked_equal(lab, 0)
        ax.imshow(lab % 8, cmap='Pastel2', alpha=0.55, extent=[c0 - .5, c1 - .5, r1 - .5, r0 - .5], interpolation='nearest')
        pm = (rec['comp_final'] != 0) | rec['line_final']
        ax.contour(np.arange(c0, c1), np.arange(r0, r1), pm.astype(float), [0.5], colors='k', linewidths=0.8)
        for s in rec['seq'][:n]:
            ax.plot(s['cells'] % W, s['cells'] // W, '-', color=COL['comp'], lw=2.2)
        s3 = S3[(S3.key == key) & (S3.patch == p)]
        if len(s3) and bool(s3.consistent.iloc[0]):
            ring, seg = RG['rings'][key][p]; e = ring[seg == int(s3.mode_seg.iloc[0])]
            ax.plot(e % W, e // W, 's', color=COL['entry'], ms=1.5)
        if starts:
            st = np.array(starts); ax.plot(st[:, 0], st[:, 1], 'x', color='#c0392b', ms=5, mew=1.2)
        ax.set_xlim(C0, C1); ax.set_ylim(R1, R0); ax.set_aspect('equal'); ax.set_xticks([]); ax.set_yticks([])
        for sp in ax.spines.values(): sp.set_visible(False)
        d = TP[(TP.key == key) & (TP.patch == p)].iloc[0]
        ax.set_title(f"{R['div'].split(' (')[0].replace('_', ' ')} patch {p}\n{ttl}\nn*={n + 1}, {d.km:.1f} km of cuts, patch saved 2017-21 {d.train_ha_yr:.1f}\nvs 2022-25 {d.test_ha_yr:.1f} ha/yr", fontsize=8.5)
        ax.plot([C0 + 2, C0 + 2 + 1000 / K.RES], [R1 - 3] * 2, 'k-', lw=2); ax.text(C0 + 2 + 500 / K.RES, R1 - 5, '1 km', ha='center', fontsize=6.5)
    h = [MPatch(color='0.6', alpha=0.6, label='2022-25 burnt (darker = more seasons)'), Line2D([], [], color=COL['comp'], lw=2.2, label='compartment cut (chosen 2017-21)'),
         Line2D([], [], color=COL['entry'], marker='s', ls='', ms=3, label='entry-side line (r26), if any'), Line2D([], [], color='#c0392b', marker='x', ls='', label='2022-25 fire start'),
         Line2D([], [], color='k', lw=0.8, label='repeat patch (>= 3 of 5, 2017-21)')]
    fig.legend(handles=h, loc='lower center', ncol=3, frameon=False, fontsize=8, bbox_to_anchor=(0.5, -0.03))
    save(fig, 'fig05_examples.png')


def fig_ncurve():
    A = pickle.load(open(K.SC + 'alloc.pkl', 'rb')); P = A['P']; T = _tab()
    fig, ax = plt.subplots(1, 2, figsize=(10.5, 3.4))
    big = sorted(P.items(), key=lambda kv: -kv[1]['g'].sum())[:12]
    for (k, p), d in big:
        ax[0].plot(np.r_[1, np.arange(2, len(d['g']) + 2)], np.r_[0, np.cumsum(d['g'])], '-', lw=0.9, color=COL['comp'], alpha=0.7)
        ax[0].plot(np.r_[1, np.arange(2, len(d['g']) + 2)], np.r_[0, d['test_cum'][:len(d['g'])]], ':', lw=0.9, color='#c0392b', alpha=0.7)
    ax[0].plot([], [], '-', color=COL['comp'], label='2017-21 (chosen on)'); ax[0].plot([], [], ':', color='#c0392b', label='2022-25 (held out)')
    ax[0].set_xlabel('n compartments'); ax[0].set_ylabel('patch forest saved, ha/yr'); ax[0].legend(frameon=False, fontsize=7)
    ax[0].set_title('a. Benefit vs n, the 12 patches with most in-sample benefit')
    for B, c in zip(K.BUDGETS, ('#c6dbef', '#6baed6', '#2171b5', '#08306b')):
        n = np.array(list(A[('comp', B)].values())) + 1
        v = np.bincount(np.minimum(n, 12), minlength=13)[2:]
        ax[1].plot(np.arange(2, 13), v, 'o-', color=c, ms=3, label=f'{B} km ({len(n)} patches)')
    ax[1].set_xlabel('n* (12 = 12 or more)'); ax[1].set_ylabel('patches'); ax[1].set_yscale('log'); ax[1].legend(frameon=False, fontsize=7)
    ax[1].set_title('b. n* chosen by the statewide allocation')
    save(fig, 'fig09_ncurve.png')


def fig_copy_r25():
    shutil.copy(R25 + 'fig_maps_core.png', FIG + 'fig10_r25_corridor_maps.png'); print('copied r25 map')


if __name__ == '__main__':
    names = sys.argv[1:]
    for n, f in list(globals().items()):
        if n.startswith('fig_') and (not names or n in names): f()
