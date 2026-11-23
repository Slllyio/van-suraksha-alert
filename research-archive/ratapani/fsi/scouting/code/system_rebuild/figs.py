"""Figures 2, 3 and 5 for the note."""
import pandas as pd, numpy as np, json, os
import matplotlib; matplotlib.use('Agg'); import matplotlib.pyplot as plt
import common as C
O = C.OUT
def fig2():
    c = pd.read_csv(O + 'compare_held_sub.csv').set_index('variant'); m = pd.read_csv(O + 'matched_held_sub.csv').drop_duplicates('variant', keep='last').set_index('variant')
    L = [('L1a_looks', '1a look counts', c), ('L1b_fpfeat', '1b footprint features', c), ('L1b_fplabel', '1b footprint labels', c), ('L1c_offsets', '1c sensor offsets', c),
         ('L1c_dedup', '1c drop duplicates', c), ('L1c_droplow', '1c drop low confidence', c), ('L1c_conf', '1c high-conf counts', c), ('L1c_frp', '1c FRP', c),
         ('L1d_histnorm', '1d history per-season norm', c), ('L1d_histsnpp', '1d history S-NPP only', c),
         ('L2_terrain', '2 terrain*', m), ('L2_lc', '2 land cover / edge*', m), ('L2_access', '2 roads / villages*', m), ('L2_static', '2 all GIS*', m),
         ('L3_obsw2', '3 obs-aware weights (+looks)*', m), ('L3_newhead', '3 new-fire head*', m), ('C_static_newhead', 'GIS + new-fire head*', m), ('C_static_looks_newhead', 'GIS + looks + new head*', m)]
    fig, ax = plt.subplots(1, 2, figsize=(12, 7), sharey=True); y = np.arange(len(L))[::-1]
    for k, (col, ttl) in enumerate((('all', 'all fires'), ('new', 'brand-new fires'))):
        for i, (v, lab, T) in zip(y, L):
            r = T.loc[v]; d, lo, hi = r[f'd_{col}'], r[f'd_{col}_lo'], r[f'd_{col}_hi']
            ax[k].errorbar(d, i, xerr=[[d - lo], [hi - d]], fmt='o', color='C2' if lo > 0 else ('C3' if hi < 0 else 'grey'))
        ax[k].axvline(0, color='k', lw=.8); ax[k].axvspan(-.7, .7, color='grey', alpha=.12); ax[k].set_title(f'change in strict catch, {ttl} (points)')
    ax[0].set_yticks(y); ax[0].set_yticklabels([l for _, l, _ in L]); fig.suptitle('Each change vs baseline B0, 10 divisions, held-out 2022-24 (95% paired bootstrap by fire; grey band = seed noise; * = at matched ground share)')
    plt.tight_layout(); plt.savefig(O + 'fig2_changes.png', dpi=110)
def fig3():
    g = pd.read_csv(O + 'importance_groups_L2_static.csv'); g.columns = ['grp', 'share']
    fig, ax = plt.subplots(figsize=(6, 3.5)); ax.barh(g.grp[::-1], 100 * g.share[::-1]); ax.set_xlabel('% of total gain'); ax.set_title('What the model uses (B0 + GIS, gain importance)')
    plt.tight_layout(); plt.savefig(O + 'fig3_importance.png', dpi=110)


def fig5():
    rows = []
    for per, lab in (('held', 'held-out 2022-24'), ('fwd', 'forward 2025-26')):
        m = pd.read_csv(O + f'matched_{per}_sub.csv').drop_duplicates('variant', keep='last').set_index('variant')
        for v, nm in (('B0', 'before (B0)'), ('C_static_newhead', 'after (GIS + new-fire head)')):
            n = json.load(open(O + f'results/{v}_{per}_sub.json'))
            rows.append(dict(period=lab, model=nm, all_10pct=n['all'], new_10pct=n['new'], beats_10pct=n['beats'], ground_10pct=n['ground'],
                             all_matched=m.loc[v, 'all'], new_matched=m.loc[v, 'new'], beats_matched=m.loc[v, 'beats'], ground_matched=m.loc[v, 'ground']))
    T = pd.DataFrame(rows).round(1); T.to_csv(O + 'before_after.csv', index=False); print(T.to_string())
    fig, ax = plt.subplots(1, 2, figsize=(11, 4))
    for k, per in enumerate(('held-out 2022-24', 'forward 2025-26')):
        t = T[T.period == per]; x = np.arange(3); w = .38
        for j, (_, r) in enumerate(t.iterrows()):
            vals = [r.all_matched, r.new_matched, r.beats_matched]
            ax[k].bar(x + (j - .5) * w, vals, w, label=r.model)
            for xi, val in zip(x + (j - .5) * w, vals): ax[k].text(xi, val + 1, f'{val:.1f}', ha='center', fontsize=8)
        ax[k].set_xticks(x); ax[k].set_xticklabels(['all fires', 'brand-new fires', 'beat episodes']); ax[k].set_ylim(0, 100); ax[k].set_title(f'{per}, same ground ({t.ground_matched.iloc[0]:.1f}%)')
    ax[0].set_ylabel('% caught 1-2 days before (strict)'); ax[0].legend(loc='lower right', fontsize=8); plt.tight_layout(); plt.savefig(O + 'fig5_before_after.png', dpi=110)


if __name__ == '__main__':
    fig2(); fig3(); fig5()
