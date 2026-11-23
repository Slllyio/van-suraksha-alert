"""Figures for README: example big fires, direction persistence, photo test."""
import pickle, json, glob
import numpy as np, pandas as pd
import matplotlib; matplotlib.use('Agg'); import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle
R = '/mnt/project-files/research/big-fires/results'; FG = '/mnt/project-files/research/big-fires/figures'
F = pd.read_csv(f'{R}/fires.csv'); A = pd.read_csv(f'{R}/fire_alerts.csv', parse_dates=['t']); S = pickle.load(open(f'{R}/fire_scars.pkl', 'rb'))
F['big'] = (F.area_ha >= 200) & (F.n_looks >= 4) & (F.n_viirs >= 10) & ~F.still_at_edge
Sh = pd.read_csv(f'{R}/fire_shape.csv')

# 1. six example big fires: scar outline + every block coloured by hours since first detection
ex = Sh[Sh.big].sort_values('n_looks', ascending=False)
pick = list(ex.fire.iloc[[0, 3, 8, 15, 25, 40]])
fig, axs = plt.subplots(2, 3, figsize=(15, 10))
for ax, fid in zip(axs.flat, pick):
    poly = S[fid]; a = A[A.fire == fid].sort_values('t'); t0 = a.t.min()
    for g in getattr(poly, 'geoms', [poly]):
        x, y = g.exterior.xy; ax.fill(x, y, color='0.85', ec='k', lw=0.8)
    hrs = (a.t - t0).dt.total_seconds() / 3600; cm = plt.cm.plasma
    for r, hh in zip(a.itertuples(), hrs):
        w = (r.scan if np.isfinite(r.scan) else (1 if r.sat == 'modis' else .375)) * 1000
        ht = (r.track if np.isfinite(r.track) else (1 if r.sat == 'modis' else .375)) * 1000
        ax.add_patch(Rectangle((r.x - w / 2, r.y - ht / 2), w, ht, fc='none', ec=cm(min(hh / max(hrs.max(), 1), 1)),
                               lw=1.6 if r.sat != 'modis' else 0.8, ls='-' if r.sat != 'modis' else '--'))
    looks = a[a.sat != 'modis'].groupby('look').agg(t=('t', 'median'), x=('x', 'mean'), y=('y', 'mean')).sort_values('t')
    ax.plot(looks.x, looks.y, '-o', color='k', ms=3, lw=1)
    ax.plot(looks.x.iloc[0], looks.y.iloc[0], 'g*', ms=16)
    f = F[F.fire == fid].iloc[0]
    ax.set_title(f'{f.date0}: {f.area_ha:.0f} ha, {f.n_viirs} VIIRS + {f.n_modis} MODIS,\n{f.n_looks} looks over {f.hours:.0f} h', fontsize=10)
    ax.set_aspect('equal'); ax.set_xticks([]); ax.set_yticks([])
sm = plt.cm.ScalarMappable(cmap='plasma'); sm.set_array([0, 1])
fig.colorbar(sm, ax=axs, shrink=0.6, label='time: first look (dark) to last look (yellow)')
fig.suptitle('Big fires: grey = burn scar (v2), boxes = real detection blocks (solid VIIRS 375 m, dashed MODIS 1 km),\n'
             'black line = centre of each look, green star = first look', fontsize=12)
plt.savefig(f'{FG}/1_example_fires.png', dpi=110, bbox_inches='tight'); plt.close()

# 2. direction persistence
G = json.load(open(f'{R}/growth_summary.json'))
fig, ax = plt.subplots(figsize=(7, 4))
labs = ['big fires', 'smaller fires']; vals = [G['big']['next_look']['within90'], G['smaller']['next_look']['within90']]
vals45 = [G['big']['next_look']['within45'], G['smaller']['next_look']['within45']]
x = np.arange(2); ax.bar(x - 0.2, vals45, 0.4, label='within 45 deg (random 25%)'); ax.bar(x + 0.2, vals, 0.4, label='within 90 deg (random 50%)')
ax.axhline(0.25, color='C0', ls=':'); ax.axhline(0.5, color='C1', ls=':')
for i in range(2): ax.text(x[i] - 0.2, vals45[i] + .01, f'{vals45[i]:.0%}', ha='center'); ax.text(x[i] + 0.2, vals[i] + .01, f'{vals[i]:.0%}', ha='center')
ax.set_xticks(x, labs); ax.set_ylim(0, 1); ax.set_ylabel('share of looks')
ax.set_title('Does new burning go the same way as at the previous look?'); ax.legend(loc='upper right', fontsize=8)
plt.savefig(f'{FG}/2_direction_persistence.png', dpi=110, bbox_inches='tight'); plt.close()

# 3. photo test
P = json.load(open(f'{R}/photo_summary.json')); Q = json.load(open(f'{R}/photo_fields_summary.json'))
m = P['all|all fires']['mean_auc']
names = {'points': 'closest VIIRS dot', 'viirs_blocks': 'closest VIIRS block', 'all_blocks': 'closest block, all sensors',
         'recent_blocks': 'blocks, older count less', 'kernel': 'many dots nearby', 'kernel_frp': 'many dots, FRP-weighted'}
extra = {'w_dz': 'many dots, two-channel area', 'w_conf': 'many dots, confidence', 'w_night': 'many dots, night x1.5'}
lab = [names[k] for k in names] + list(extra.values()); val = [m[k] for k in names] + [Q['mean_auc'][k] for k in extra]
o = np.argsort(val)
fig, ax = plt.subplots(figsize=(8, 5)); ax.barh(np.array(lab)[o], np.array(val)[o], color=['C2' if 'many dots' == l else 'C0' for l in np.array(lab)[o]])
for i, v in enumerate(np.array(val)[o]): ax.text(v + 0.003, i, f'{v:.3f}', va='center')
ax.set_xlim(0.5, 0.85); ax.axvline(0.5, color='k')
ax.set_xlabel('score on mid-fire photos (AUC: 0.5 = guessing, 1 = perfect)')
ax.set_title(f'Which way of reading the detections finds the ground burned by photo time?\n{P["all|all fires"]["photos"]} photos, 2017-24')
plt.savefig(f'{FG}/3_photo_test.png', dpi=110, bbox_inches='tight'); plt.close()
print('ok', pick)
