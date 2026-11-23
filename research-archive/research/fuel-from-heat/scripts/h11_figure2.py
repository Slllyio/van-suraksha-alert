"""Second method picture: figures/place_memory.png"""
import json, matplotlib; matplotlib.use('Agg'); import matplotlib.pyplot as plt
from h0_lib import RES, HERE
P = json.load(open(f'{RES}/place_tests.json')); F = json.load(open(f'{RES}/first_heat.json'))
fig, ax = plt.subplots(1, 3, figsize=(15, 4.2))
q = P['T1_quintile_halfB_factor']
ax[0].bar(range(5), [100 * (x - 1) for x in q], color='tab:red'); ax[0].axhline(0, color='k', lw=.8)
ax[0].set_xticks(range(5), ['coolest\nfifth', '2', '3', '4', 'hottest\nfifth']); ax[0].set_ylim(-20, 20)
ax[0].set_xlabel('500 m places ranked by heat in some years'); ax[0].set_ylabel('% hotter than pass average, OTHER years')
ax[0].set_title('1. Hot places are barely hot again\nin other years (+2%)', fontsize=10)
c = P['T2_heat_vs_burnt_1_season_ago']; lab = ['1 season', '2 seasons', '3+ seasons', 'not since 2017']
val = [0] + [100 * (c[k][0] - 1) for k in lab[1:]]; err = [[0] + [100 * (c[k][0] - c[k][1][0]) for k in lab[1:]], [0] + [100 * (c[k][1][1] - c[k][0]) for k in lab[1:]]]
ax[1].bar(range(4), val, yerr=err, color='tab:orange', capsize=4); ax[1].axhline(0, color='k', lw=.8); ax[1].set_ylim(-20, 20)
ax[1].set_xticks(range(4), ['burnt last\nseason', '2 seasons\nago', '3+ seasons\nago', 'not since\n2017'])
ax[1].set_ylabel('% heat vs "burnt last season", same place'); ax[1].set_title('2. No fuel reset: heat is the same\nhowever long since the last burn', fontsize=10)
b = F['by_quintile']
ax[2].bar(range(5), [float(r['scar_ha_median']) for r in b], color='tab:blue')
ax[2].set_xticks(range(5), ['coolest\nfifth', '2', '3', '4', 'hottest\nfifth']); ax[2].set_xlabel('first-pass heat vs rest of that pass')
ax[2].set_ylabel('final scar, median ha'); ax[2].set_title('3. A hot first detection does mean\na bigger fire (2x)', fontsize=10)
fig.tight_layout(); fig.savefig(f'{HERE}/figures/place_memory.png', dpi=110)
