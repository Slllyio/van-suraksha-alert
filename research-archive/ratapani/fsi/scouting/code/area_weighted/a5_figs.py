"""Figures and small tables for area_weighted_list.md.
fig1_concentration.png: share of burnt ha held by the biggest x% of fires (scar truth), held-out 2022-24 and forward 2025.
fig2_catch_by_size.png: the current list's catch rate by fire size class.
fig3_tradeoff.png: change in % burnt ha caught vs change in % fires caught, each ranking at matched ground, with 95% CIs.
Out: out/fig*.png, out/catch_by_size_{period}.csv, out/concentration.csv."""
import numpy as np, pandas as pd
import matplotlib; matplotlib.use('Agg'); import matplotlib.pyplot as plt
import aw_common as A
ev = pd.read_parquet(A.S24 + 'events.parquet'); ev = ev[ev.valid]
PER = {'held': 'held-out 2022-24', 'fwd': 'forward 2025'}

# fig 1
fig, ax = plt.subplots(figsize=(5.2, 4.2)); rows = []
for per, lab in PER.items():
    for src, ls in (('scar', '-'), ('best', '--')):
        g = ev[ev.season.isin(A.TEST[per])]
        a = g.scar_ha[g.scar_status == 'scar'].values if src == 'scar' else g.area_ha.values
        a = np.sort(a)[::-1]; c = np.r_[0, a.cumsum() / a.sum()]; x = np.linspace(0, 100, len(c))
        ax.plot(x, 100 * c, ls, label=f'{lab}, {"scar" if src == "scar" else "scar or VIIRS"}')
        n = len(a)
        rows.append(dict(period=per, truth=src, fires=n, median_ha=np.median(a), top1=100 * a[:max(1, n // 100)].sum() / a.sum(),
                         top10=100 * a[:n // 10].sum() / a.sum(), top20=100 * a[:n // 5].sum() / a.sum(), big_share_fires=100 * (a >= A.BIG).mean(),
                         big_share_ha=100 * a[a >= A.BIG].sum() / a.sum()))
ax.plot([0, 100], [0, 100], 'k:', lw=0.8); ax.set_xlabel('biggest fires (% of fires)'); ax.set_ylabel('% of burnt ha'); ax.set_xlim(0, 100); ax.set_ylim(0, 100)
ax.set_title('A few big fires burn most of the forest'); ax.legend(fontsize=7, loc='lower right'); ax.grid(alpha=.3); plt.tight_layout(); plt.savefig(A.OUT + 'fig1_concentration.png', dpi=110)
pd.DataFrame(rows).round(1).to_csv(A.OUT + 'concentration.csv', index=False)

# fig 2
bins = [0, 10, 50, 200, 500, 1e9]; labs = ['<10', '10-50', '50-200', '200-500', '500+']
fig, ax = plt.subplots(figsize=(5.6, 3.8)); wd = 0.38
for k, (per, lab) in enumerate(PER.items()):
    h = pd.read_parquet(A.S24 + f'hits_{per}.parquet'); h = h[h.ranking == 'P (current)'].merge(ev[ev.season.isin(A.TEST[per])], on=['division', 'ev'])
    s = h[h.area_src == 'scar'].copy(); s['cls'] = pd.cut(s.area_ha, bins, labels=labs, right=False)
    t = s.groupby('cls', observed=False).agg(fires=('hit', 'size'), caught=('hit', 'mean'), ha=('area_ha', 'sum')); t['caught'] *= 100
    t.to_csv(A.OUT + f'catch_by_size_{per}.csv')
    ax.bar(np.arange(5) + (k - 0.5) * wd, t.caught.values, wd, label=lab)
    for i, (v, n) in enumerate(zip(t.caught.values, t.fires.values)): ax.text(i + (k - 0.5) * wd, v + 1, f'n={n}', ha='center', fontsize=6)
ax.set_xticks(range(5)); ax.set_xticklabels(labs); ax.set_xlabel('scar size (ha)'); ax.set_ylabel('% caught by the current list'); ax.set_ylim(0, 100)
ax.set_title('Current list: catch rate by fire size (scar truth)'); ax.legend(fontsize=8); ax.grid(axis='y', alpha=.3); plt.tight_layout(); plt.savefig(A.OUT + 'fig2_catch_by_size.png', dpi=110)

# fig 3
fig, axs = plt.subplots(1, 2, figsize=(10, 4.2), sharey=True)
for ax, (per, lab) in zip(axs, PER.items()):
    T = pd.read_csv(A.OUT + f'rank_{per}.csv'); T = T[~T.ranking.isin(['P (current)', 'E'])]  # size-only ranking is far off the chart (-22 to -24 fires, -10 to -13 ha); see table
    for _, r in T.iterrows():
        ax.errorbar(r.d_fires, r.d_ha_scar, xerr=[[r.d_fires - r.d_fires_lo], [r.d_fires_hi - r.d_fires]], yerr=[[r.d_ha_scar - r.d_ha_scar_lo], [r.d_ha_scar_hi - r.d_ha_scar]], fmt='o', ms=4, lw=0.8)
        ax.annotate(r.ranking.replace('P1E', 'P·E^'), (r.d_fires, r.d_ha_scar), fontsize=7, xytext=(4, -10 if r.ranking.startswith('pool') else 4), textcoords='offset points')
    ax.axhline(0, color='k', lw=0.6); ax.axvline(0, color='k', lw=0.6); ax.grid(alpha=.3)
    ax.set_xlabel('change in % fires caught (points)'); ax.set_title(f'{lab}, same ground as the current list')
axs[0].set_ylabel('change in % burnt ha caught (scar truth, points)'); plt.tight_layout(); plt.savefig(A.OUT + 'fig3_tradeoff.png', dpi=110)
print('ok')
