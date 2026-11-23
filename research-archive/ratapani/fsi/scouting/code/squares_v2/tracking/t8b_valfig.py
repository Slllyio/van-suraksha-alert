"""Validation figure: photos (accuracy, AUC; held-out odd seasons), hot pixels (ranking AUC by gap to the nearest VIIRS
pass), and the synthetic recovery test. Reads results/*.json. Out: results/fig_validation.png"""
import json, os
import numpy as np, pandas as pd
import matplotlib; matplotlib.use('Agg'); import matplotlib.pyplot as plt
OUT = '/mnt/project-files/ratapani/fsi/scouting/code/squares_v2/tracking/results'
J = lambda f: json.load(open(f'{OUT}/{f}'))
fig, axs = plt.subplots(1, 3, figsize=(14, 4.2))
ph = {'front model': J('t6_photos_final.json'), 'grid map': J('t6_photos_grid12.json')}
if os.path.exists(f'{OUT}/t6_photos_ring.json'): ph['grid map + edge ring'] = J('t6_photos_ring.json')
labs, acc, auc = [], [], []
g = ph['grid map']['odd_seasons']
for m, lab in [('blend', 'blend (continuity)'), ('nearest', 'nearest look'), ('linear', 'linear (nat.-neighbour type)'), ('idw2', 'weighted mean p=2')]:
    labs.append(lab); acc.append(g[m]['acc']); auc.append(g[m]['auc'])
for k, r in ph.items():
    labs.append(k); acc.append(r['odd_seasons']['inversion']['acc']); auc.append(r['odd_seasons']['inversion']['auc'])
y = np.arange(len(labs)); ax = axs[0]
ax.barh(y - .2, acc, .4, label='pixel accuracy', color='#4c78a8'); ax.barh(y + .2, auc, .4, label='AUC (burn-time ranking)', color='#f58518')
ax.set_yticks(y); ax.set_yticklabels(labs, fontsize=8); ax.set_xlim(.6, .9); ax.legend(fontsize=7, loc='lower right')
ax.set_title(f"Mid-fire photos, held-out odd seasons (n={g['n']})", fontsize=9)
hp = J('t7_hotpix_grid12.json') if os.path.exists(f'{OUT}/t7_hotpix_grid12.json') else J('t7_hotpix_final.json')
ax = axs[1]; ms = ['inversion', 'kernel', 'pass_centres']; cl = ['#54a24b', '#e45756', '#9d755d']
for i, (k, lab) in enumerate([('gap_le_3h', 'nearest VIIRS pass <= 3 h away'), ('gap_gt_3h', '> 3 h away')]):
    v = [hp[k][f'auc_{m}'] for m in ms]
    ax.bar(np.arange(3) + i * 4, v, color=cl)
    ax.text(1 + i * 4, .8, f"{lab}\n(n={hp[k]['n']})", ha='center', fontsize=7)
ax.set_xticks([0, 1, 2, 4, 5, 6]); ax.set_xticklabels(['inversion', 'dot kernel', 'pass pixel\ncentres'] * 2, fontsize=7); ax.set_ylim(.5, .85)
ax.set_title('S2/Landsat hot pixels: which 40 m cells burn at the scene minute (AUC)', fontsize=9)
sm = J('t3_sim_summary.json'); ax = axs[2]
ks = [('start_nearest', 'nearest flag'), ('blend', 'blend (IDW p4)'), ('inv_firms', 'inversion, FIRMS points'), ('inv_mask', 'inversion, full fire mask')]
ax.bar(range(4), [sm[f'mae_{k}'] for k, _ in ks], color=['#9d755d', '#e45756', '#54a24b', '#4c78a8'])
ax.set_xticks(range(4)); ax.set_xticklabels([l for _, l in ks], fontsize=7, rotation=15); ax.set_ylabel('mean |arrival error| (h)')
ax.set_title(f"Synthetic fires with known truth (n={sm['fires']})", fontsize=9)
plt.tight_layout(); plt.savefig(f'{OUT}/fig_validation.png', dpi=115); print('saved')
