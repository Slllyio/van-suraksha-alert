"""Picture for the viewing-angle result: figures/view_angle.png"""
import json, numpy as np, pandas as pd, matplotlib
matplotlib.use('Agg'); import matplotlib.pyplot as plt
from h0_lib import RES, HERE
M = json.load(open(f'{RES}/view_angle_month_check.json')); C = json.load(open(f'{RES}/view_angle_checks.json')); P = json.load(open(f'{RES}/power.json'))
fig, ax = plt.subplots(1, 3, figsize=(16, 4.3))
t = pd.DataFrame(M['leafy_share_by_angle_month3']); s = t['mean'].astype(float)
odds = s / (1 - s); rel = odds / odds.iloc[0]
ax[0].bar(range(4), 100 * rel, color='tab:green'); ax[0].axhline(100, color='k', lw=.8)
for i, (a, n) in enumerate(zip(rel, t['size'])): ax[0].text(i, 100 * a + 2, f'{100 * a:.0f}%\n(n={n})', ha='center', fontsize=8)
ax[0].set_xticks(range(4), ['straight down\n<30 deg', '30-45', '45-56', 'sideways\n>56 deg']); ax[0].set_ylim(0, 125)
ax[0].set_ylabel('fires under LEAFY crowns detected,\nrelative to bare-crowned forest (%)'); ax[0].set_xlabel('satellite viewing angle (March, closed forest)')
ax[0].set_title('1. Leafy crowns hide fires from detection\nwhen the satellite looks sideways', fontsize=10)
lab = ['open ground', 'closed, leafy crowns', 'closed, bare crowns']
sl = [C['A_slope_open'], C['A_slope_leafy_closed'], C['A_slope_bare_closed']]
ax[1].bar(range(3), [100 * (np.exp(x) - 1) for x in sl], color=['tab:orange', 'tab:green', 'tab:brown']); ax[1].axhline(0, color='k', lw=.8)
ax[1].set_xticks(range(3), lab, fontsize=9); ax[1].set_ylabel('% change in fire FRP per +1 unit of slant path\n(e.g. straight down -> 60 deg)')
ax[1].set_title('2. Same fire, two satellites 50 min apart:\nlooking sideways loses more heat under trees', fontsize=10)
ks = [k for k in P if k.startswith('expected')]
vals = [P['observed_rho']] + [P[k][0] for k in ks]; lo = [0] + [P[k][0] - P[k][1][0] for k in ks]; hi = [0] + [P[k][1][1] - P[k][0] for k in ks]
names = ['OBSERVED', 'map fully right\n(generous noise)', 'map half right\n(generous noise)', 'map fully right\n(sat. noise)', 'map half right\n(sat. noise)']
ax[2].bar(range(5), vals, yerr=[lo, hi], color=['tab:red'] + ['grey'] * 4, capsize=3); ax[2].axhline(0, color='k', lw=.8)
ax[2].set_xticks(range(5), names, fontsize=7); ax[2].set_ylabel('rank corr: heat per ha vs fuel map')
ax[2].set_title('3. Power check: if the map were right,\nheat should follow it at 0.19-0.26', fontsize=10)
fig.tight_layout(); fig.savefig(f'{HERE}/figures/view_angle.png', dpi=110)
