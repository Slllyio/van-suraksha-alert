"""B step 6: figures for squares_v3_per_fire.md.
fig_b1_pooling.png   how much a fire's own pairs say: noise SD of its factor vs pairs, against the between-fire SD; shrinkage
fig_b2_line.png      hot-line length (30 m) vs VIIRS block arrangement; growth predicted vs blend-map growth
fig_b4_forecast.png  forecast tests: same / class / per-fire speeds against the baselines"""
import sys, os, json
import numpy as np, pandas as pd
import matplotlib; matplotlib.use('Agg'); import matplotlib.pyplot as plt
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from b_lib import *
r1 = json.load(open(f'{OUT}/b1_hier.json'))
F = pd.read_parquet(f'{SC}/fires_post.parquet')
tau = r1['class']['tau_split_half']; lo, hi = [np.sqrt(max(x, 0)) for x in r1['class']['tau2_split_half_ci']]
fig, ax = plt.subplots(1, 2, figsize=(12, 4.6))
nb = pd.cut(F.n, [0, 1, 2, 4, 8, 16, 32, 64, 1e6]); g = np.sqrt(F.s2e).groupby(nb, observed=True)
x = np.arange(len(g)); med = g.median().values; q1 = g.quantile(.25).values; q3 = g.quantile(.75).values
ax[0].bar(x, med, color='#7a9cc6', label='noise SD of one fire\'s factor (median, IQR)'); ax[0].errorbar(x, med, [med - q1, q3 - med], fmt='none', ecolor='k', lw=1)
ax[0].axhspan(lo, hi, color='#d9534f', alpha=.2); ax[0].axhline(tau, color='#d9534f', lw=2, label=f'real between-fire SD {tau:.2f} (CI {lo:.2f}-{hi:.2f})')
cnt = F.n.groupby(nb, observed=True).size().values
ax[0].set_xticks(x); ax[0].set_xticklabels([f'{str(k).replace("(", "").replace("]", "").replace(", ", "-").replace(".0", "").replace("-1000000", "+")}\n{c:,} fires' for k, c in zip(g.median().index, cnt)], fontsize=8)
ax[0].set_yscale('log'); ax[0].set_ylabel('SD of the fire factor (1 = class mean)'); ax[0].set_xlabel('pairs of looks per fire (all MP)')
ax[0].legend(fontsize=8); ax[0].set_title('A fire needs ~30+ pairs before its own data beat the class mean')
s = F[F.n >= 4].sample(min(6000, (F.n >= 4).sum()), random_state=0)
ax[1].scatter(s.f_hat.clip(-8, 10), s.f_post, s=4, c=np.log10(s.n), cmap='viridis', alpha=.5)
ax[1].axhline(1, color='k', lw=.5); ax[1].plot([-8, 10], [-8, 10], 'k:', lw=.5)
ax[1].set_xlabel("fire's own estimate of its factor (clipped)"); ax[1].set_ylabel('after partial pooling'); ax[1].set_ylim(-.5, 4)
ax[1].set_title('Shrinkage: most fires are pulled to the class mean (colour = log10 pairs)')
plt.tight_layout(); plt.savefig(f'{OUT}/fig_b1_pooling.png', dpi=110); plt.close()

X = pd.read_csv(f'{OUT}/b2_linelength_pairs.csv'); V = X[(X.kind == 'viirs') & X.gap_h.between(1.5, 4)]
I = pd.read_csv(f'{OUT}/b3_intervals.csv'); r3 = json.load(open(f'{OUT}/b3_growth.json')); r2 = json.load(open(f'{OUT}/b2_linelength.json'))
fig, ax = plt.subplots(1, 2, figsize=(12, 4.6))
ax[0].loglog(V.extent, V.hot_len, '.', alpha=.35, ms=5)
bins = np.quantile(V.extent, np.linspace(0, 1, 9)); mid = V.groupby(pd.cut(V.extent, bins, include_lowest=True), observed=True).agg(x=('extent', 'median'), y=('hot_len', 'median'))
ax[0].plot(mid.x, mid.y, 'r-o', label='median per bin')
a, b = r2['calibration']['all']; xx = np.geomspace(V.extent.min(), V.extent.max()); ax[0].plot(xx, np.exp(a) * xx ** b, 'k--', label=f'fit L = {np.exp(a):.2f} x extent^{b:.2f}')
row = pd.read_csv(f'{OUT}/b2_linelength.csv').set_index(['set', 'predictor']).loc[('viirs_day', 'extent')]
ax[0].set_xlabel('extent of one VIIRS pass\'s blocks on the fire (m)'); ax[0].set_ylabel('30 m hot-line length 2-3 h earlier (m)')
ax[0].set_title(f"Line length from blocks: held-out R2 {row.heldout_r2} ({row.r2_ci})", fontsize=10); ax[0].legend(fontsize=8)
d = I[I.obs_blend >= 0]
ax[1].loglog(d.pred_class * r3['obs_blend']['pred_class']['k_median'] + 1e-2, d.obs_blend + 1, '.', alpha=.3, ms=4)
lim = [0.1, 3e3]; ax[1].plot(lim, lim, 'k:', lw=.8); ax[1].set_xlim(lim); ax[1].set_ylim(1, 3e3)
ax[1].set_xlabel('predicted growth: k x line length x class speed x clock hours (ha)'); ax[1].set_ylabel('blend-map growth between looks + 1 (ha)')
ax[1].set_title(f"Growth between looks: rho {r3['obs_blend']['pred_class']['rho']} (per-fire speed {r3['obs_blend']['pred_fire']['rho']})", fontsize=10)
plt.tight_layout(); plt.savefig(f'{OUT}/fig_b2_line.png', dpi=110); plt.close()

r4 = json.load(open(f'{OUT}/b4_forecast.json'))
fig, ax = plt.subplots(1, 3, figsize=(15, 4.4))
a = r4['a_photos']['scores']; ms = ['persistence', 'kernel', 'tail15', 'same', 'class', 'fire', 'ring600', 'blend_all_looks']
lab = ['persist.', 'dot kernel', 'blend tail\n15 m/h', 'same\nspeed', 'class\nspeed', 'per-fire\nspeed', '600 m\nring', 'blend, all\nlooks*']
cols = ['#999'] * 3 + ['#5b8bd0', '#2a5caa', '#d9534f', '#999', '#ccc']
ax[0].bar(range(len(ms)), [a[m]['acc'] * 100 for m in ms], color=cols); ax[0].set_xticks(range(len(ms))); ax[0].set_xticklabels(lab, fontsize=7.5)
ax[0].set_ylim(60, 85); ax[0].set_ylabel('pixel accuracy, %'); ax[0].set_title(f"(a) burned by the morning photo ({r4['a_photos']['photos']} photos)\n* reconstruction, not a forecast", fontsize=9)
if 'b_nextpass' in r4:
    b = r4['b_nextpass']; ms = ['fixed', 'same', 'class', 'fire', 'kernel', 'ring600']
    lab = ['fixed\nreach', 'same\nspeed', 'class\nspeed', 'per-fire\nspeed', 'dot kernel\n(same area)', f"600 m ring\n({b['mean_area_ha']['ring600']:.0f} ha)"]
    cols = ['#999', '#5b8bd0', '#2a5caa', '#d9534f', '#999', '#ccc']
    ax[1].bar(range(len(ms)), [b['capture_new'][m] * 100 for m in ms], color=cols); ax[1].set_xticks(range(len(ms))); ax[1].set_xticklabels(lab, fontsize=7.5)
    ax[1].set_ylabel('NEW next-pass points caught, %'); ax[1].set_title(f"(b) next VIIRS pass, equal mean reach {b['mean_reach_m']:.0f} m\n({b['forecasts']} forecasts)", fontsize=9)
c = r4['c_final']; ms = ['ring 600 m', 'dot kernel 400 m', 'ring + line x same speed', 'ring + line x class speed', 'ring + line x per-fire speed']
lab = ['600 m\nring', 'dot kernel', '+ line x\nsame', '+ line x\nclass', '+ line x\nper-fire']
ax[2].bar(range(len(ms)), [c[m]['heldout_r2_log'] for m in ms], color=['#999', '#999', '#5b8bd0', '#2a5caa', '#d9534f']); ax[2].set_xticks(range(len(ms))); ax[2].set_xticklabels(lab, fontsize=7.5)
ax[2].set_ylim(.25, .4); ax[2].set_ylabel('held-out R2, log final scar area'); ax[2].set_title(f"(c) final scar size from the first 24 h ({c['fires']} fires)", fontsize=9)
plt.tight_layout(); plt.savefig(f'{OUT}/fig_b4_forecast.png', dpi=110); plt.close()
print('ok')
