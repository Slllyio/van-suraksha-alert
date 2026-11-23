"""Picture for the growth patterns (c6). Out: figures/patterns.png"""
import json, numpy as np, pandas as pd, matplotlib
matplotlib.use('Agg'); import matplotlib.pyplot as plt
H = '/mnt/project-files/research/fire-continuity'
X = pd.read_csv(f'{H}/results/patterns_fires.csv'); L = pd.read_csv(f'{H}/results/patterns_looks.csv'); P = json.load(open(f'{H}/results/patterns.json'))
fig, ax = plt.subplots(1, 3, figsize=(13, 4))
# a: how the outline fills
first = X[['fire', 'first_look_share']].rename(columns={'first_look_share': 'share'}).assign(th=0.0)
A = pd.concat([first, L[['fire', 'share', 'th']]]).sort_values(['fire', 'th']); A['cum'] = A.groupby('fire').share.cumsum()
hrs = np.arange(0, 121, 6); curves = np.array([[g.cum[g.th <= h].max() if (g.th <= h).any() else 0 for h in hrs] for _, g in A.groupby('fire')])
for q, a_ in [(25, .25), (50, 1), (75, .25)]:
    ax[0].plot(hrs, np.percentile(curves, q, 0) * 100, color='#c0392b', lw=2 if q == 50 else 1, alpha=a_ if q != 50 else 1)
ax[0].fill_between(hrs, np.percentile(curves, 25, 0) * 100, np.percentile(curves, 75, 0) * 100, color='#c0392b', alpha=.12)
ax[0].set_xlabel('hours after first VIIRS look'); ax[0].set_ylabel('% of final outline burned'); ax[0].set_title('a. How a big fire fills its outline\n(median and middle half of 146 fires)', fontsize=10)
ax[0].set_xticks(range(0, 121, 24))
# b: edges
e = P['edges']; items = [('tree', 'tree cover'), ('grass_shrub', 'grass / shrub'), ('crop_built', 'crop / built')]
x = np.arange(len(items)); w = .38
ax[1].bar(x - w / 2, [e[k]['inside_mean'] * 100 for k, _ in items], w, label='just inside the edge', color='#555')
ax[1].bar(x + w / 2, [e[k]['outside_mean'] * 100 for k, _ in items], w, label='just outside the edge', color='#e39b3a')
ax[1].set_xticks(x, [l for _, l in items]); ax[1].set_ylabel('% of ground (40-200 m from edge)'); ax[1].legend(fontsize=8)
ax[1].set_title('b. Where big fires stop: cover thins out\n(146 fires; outside has fewer trees in 79%)', fontsize=10)
# c: terrain along the growth vs rotated
t = P['terrain_along_growth']; items = [('elev', 'height'), ('local_height', 'ridge vs valley'), ('slope', 'steepness'), ('tree', 'tree cover')]
x = np.arange(len(items))
ax[2].bar(x - w / 2, [t[k]['share_positive'] * 100 for k, _ in items], w, label='real growth maps', color='#2c6fbb')
ax[2].bar(x + w / 2, [t[k]['null_share_positive'] * 100 for k, _ in items], w, label='same maps turned round (chance)', color='#bbb')
ax[2].axhline(50, color='k', lw=.6, ls=':'); ax[2].set_ylim(30, 70); ax[2].set_xticks(x, [l for _, l in items], fontsize=9)
ax[2].set_ylabel('% of fires where later-burned ground\nis higher / steeper / more wooded'); ax[2].legend(fontsize=8)
ax[2].set_title('c. Inside the outline, terrain does not\norder which ground burns first', fontsize=10)
for a in ax: a.spines[['top', 'right']].set_visible(False)
fig.tight_layout(); fig.savefig(f'{H}/figures/patterns.png', dpi=110)
