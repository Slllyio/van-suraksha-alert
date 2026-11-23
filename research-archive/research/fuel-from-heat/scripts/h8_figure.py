"""Step 8: one summary picture (figures/fuel_from_heat.png)."""
import json, numpy as np, pandas as pd, matplotlib
matplotlib.use('Agg'); import matplotlib.pyplot as plt
from h0_lib import RES, HERE
R = pd.read_csv(f'{RES}/fire_fuel.csv').merge(pd.read_csv(f'{RES}/fire_cov.csv'), on='fire')
D = R[(R.n_pass >= 2) & R.month.between(2, 6)]
fig, ax = plt.subplots(1, 4, figsize=(17, 4.2))
# 1 canopy
b = pd.cut(D.canopy, [0, 20, 40, 60, 100]); g = D.groupby(b, observed=True)
x = np.arange(len(g)); ax[0].bar(x - .2, g.fuel_tha.median(), .4, label='from heat (FRP energy / scar area)', color='tab:red')
ax[0].bar(x + .2, g.litter.median() + g.grass.median(), .4, label='fuel map v3 (litter + grass)', color='tab:green')
ax[0].set_xticks(x, ['0-20', '20-40', '40-60', '60+']); ax[0].set_xlabel('canopy cover under the scar (%)'); ax[0].set_ylabel('t/ha')
ax[0].set_title('1. Heat says the same fuel everywhere;\nthe map says more under canopy', fontsize=10); ax[0].legend(fontsize=8)
# 2 month
g = D.groupby('month'); g = g.filter(lambda s: len(s) >= 20).groupby('month')
ax[1].bar(g.fuel_tha.median().index, g.fuel_tha.median(), color='tab:red'); ax[1].set_xticks([2, 3, 4, 5], ['Feb', 'Mar', 'Apr', 'May'])
ax[1].set_ylabel('t/ha burnt (from heat)'); ax[1].set_title('2. It rises through the season\n(drier fuel burns more completely)', fontsize=10)
# 3 size
b = pd.qcut(D.scar_ha, 5); g = D.groupby(b, observed=True)
ax[2].plot([f'{int(i.left)}-{int(i.right)}' for i in g.fuel_tha.median().index], g.fuel_tha.median(), 'o-', color='tab:red')
ax[2].set_xlabel('scar size (ha)'); ax[2].set_ylabel('t/ha burnt (from heat)'); ax[2].tick_params(axis='x', labelsize=7)
ax[2].set_title('3. Small scars look "heavy", big ones "light":\nfire size, not fuel', fontsize=10)
# 4 two satellites
J = json.load(open(f'{RES}/cluster_tests2.json'))['two_sat']
v = pd.read_csv(f'{RES}/clusters.csv', parse_dates=['t']).dropna(subset=['fire'])
v['pass'] = v.sensor + v.t.dt.strftime('%Y%m%d%H%M')
P = v.groupby(['fire', 'pass']).agg(t=('t', 'first'), s=('sensor', 'first'), n=('frp', 'size'), frp=('frp', 'sum')).reset_index().sort_values(['fire', 't'])
rows = []
for f, gg in P.groupby('fire'):
    gg = gg.reset_index(drop=True)
    for i in range(len(gg) - 1):
        dt = (gg.t[i + 1] - gg.t[i]).total_seconds() / 60
        if gg.s[i] != gg.s[i + 1] and 20 <= dt <= 100: rows.append((gg.n[i + 1] / gg.n[i], gg.frp[i + 1] / gg.frp[i]))
Q = pd.DataFrame(rows, columns=['nr', 'fr'])
lab = Q.nr.apply(lambda r: '1/3 or less' if r <= 1 / 3 else 'about 1/2' if r < .8 else 'same' if r <= 1.25 else 'about 2x' if r < 3 else '3x or more')
order = ['1/3 or less', 'about 1/2', 'same', 'about 2x', '3x or more']
m = Q.groupby(lab).fr.median().reindex(order)
ax[3].bar(range(5), m.values, color='tab:blue'); ax[3].set_yscale('log'); ax[3].set_xticks(range(5), order, fontsize=8)
ax[3].axhline(1, color='k', lw=.8); ax[3].set_xlabel('pixels lit by 2nd satellite vs 1st (same fire, ~50 min later)')
ax[3].set_ylabel('summed FRP, 2nd / 1st'); ax[3].set_title('4. Summed FRP follows how many pixels\nthe satellite lights up', fontsize=10)
fig.tight_layout(); fig.savefig(f'{HERE}/figures/fuel_from_heat.png', dpi=110)
