"""Summary picture of the photo test + share of each big fire's outline that lies within 600 m walk of a detection.
Out: figures/photo_test.png, results/big_fire_coverage.csv"""
import sys, os, json, numpy as np, pandas as pd, matplotlib
matplotlib.use('Agg'); import matplotlib.pyplot as plt
sys.argv = [sys.argv[0], '{"p":4,"clock":true}']
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import c3_maps as C
R = f'{C.HERE}/results'
S = pd.read_csv(f'{R}/photo_summary.csv', index_col=0)
show = [('base', 'Spread review map\n(nearest earlier dot + 15 m/h)'), ('joint_clock', 'One speed through\nall passes'),
        ('front_walk_edge_clock', 'Front walking\nlook to look'), ('terr_up+3', 'Same + uphill\nfaster'),
        ('terr_open+0.7', 'Same + open\nground faster'), ('nn', 'Time of the\nnearest look'), ('chosen', 'BLEND (chosen,\nseasons held out)')]
fig, ax = plt.subplots(figsize=(10, 4.2))
x = np.arange(len(show)); w = .38
a = [S.loc[m, 'acc_all'] * 100 for m, _ in show]; b = [S.loc[m, 'acc_both_sides'] * 100 for m, _ in show]
ax.bar(x - w / 2, a, w, label='all 340 photos', color='#7a8ca8'); ax.bar(x + w / 2, b, w, label='171 photos with a look before AND after', color='#d9822b')
for i in range(len(show)): ax.text(x[i] - w / 2, a[i] + .5, f'{a[i]:.0f}', ha='center', fontsize=8); ax.text(x[i] + w / 2, b[i] + .5, f'{b[i]:.0f}', ha='center', fontsize=8)
ax.set_xticks(x, [l for _, l in show], fontsize=8); ax.set_ylim(50, 92); ax.set_ylabel('% of 20 m pixels right\n(burned yet or not, at photo time)')
ax.legend(fontsize=8, loc='upper left'); ax.spines[['top', 'right']].set_visible(False)
ax.set_title('Mid-fire Sentinel-2/Landsat photos: which growth map gets "burned by now" right?', fontsize=10)
fig.tight_layout(); fig.savefig(f'{C.HERE}/figures/photo_test.png', dpi=110)
rows = []
for fire in C.L.fire:
    d, t0, box, tr, dom, Tg, W, vs = C.build(fire)
    dm = box.dmin[dom]; rows.append(dict(fire=fire, area_ha=dom.sum() * .04, share_within_600m=float((dm <= 600).mean()), n_looks=d.lk.nunique()))
X = pd.DataFrame(rows); X.to_csv(f'{R}/big_fire_coverage.csv', index=False); print(X.describe().round(2))
