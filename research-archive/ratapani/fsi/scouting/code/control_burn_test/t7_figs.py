"""t7: figures + the Ratapani scar-shape mixture estimate (share of flagged 15-28 Feb scars that look like Jan-14 Feb flagged scars
by the strip index; bootstrap by event). Figures to out/fig*.png"""
import numpy as np, pandas as pd, matplotlib
matplotlib.use('Agg'); import matplotlib.pyplot as plt
S = '/tmp/claude-0/-home-user/be9b8f54-cc26-52cb-bdbb-9c8008a24baf/scratchpad/'
O = '/mnt/project-files/ratapani/fsi/scouting/code/control_burn_test/out/'
plt.rcParams.update({'font.size': 9})
# fig1 per season
P = pd.read_csv(O + 'heldout_by_season.csv'); D = pd.read_csv(O + 'season_density.csv')
dc = D[D.rule == 'current rule'].set_index('season')
fig, ax = plt.subplots(figsize=(7, 3.2))
x = P.season.values
ax.errorbar(x - 0.15, P.precision, yerr=[P.precision - P.prec_lo, P.prec_hi - P.precision], fmt='o', color='0.6', label='background = all Mar-May (r15 method)')
ax.errorbar(x + 0.15, dc.precision[x], yerr=[dc.precision[x] - dc.lo[x], dc.hi[x] - dc.precision[x]], fmt='o', color='C3', label='background matched on fire density')
ax.axhline(0.69, ls=':', color='0.4'); ax.text(2013.6, 0.71, 'r15 claim 64-73%', fontsize=8, color='0.3')
ax.axvspan(2025.5, 2026.5, color='C0', alpha=0.08); ax.text(2025.6, 0.05, 'forward', fontsize=8, color='C0')
ax.set_ylim(0, 1); ax.set_xticks(x); ax.set_ylabel('est. precision, 15-28 Feb'); ax.set_title('Current rule, each season scored on its own (95% CI by fire)')
ax.legend(fontsize=7, loc='lower right'); fig.tight_layout(); fig.savefig(O + 'fig1_season_precision.png', dpi=130)
# fig2 fortnight plain vs matched incl June placebo
M = pd.read_csv(O + 'density_matched.csv'); m = M[M.rule == 'current rule']
wins = ['1 Jan', '2 1-14 Feb', '3 15-28 Feb', '4 1-15 Mar', '6 Jun']; lab = ['Jan', '1-14 Feb', '15-28 Feb', '1-15 Mar', 'Jun\n(placebo)']
fig, ax = plt.subplots(figsize=(6, 3))
for k, (bg, col) in enumerate([('plain (as r15)', '0.6'), ('density-matched', 'C3')]):
    q = m[m.background == bg].set_index('window').loc[wins]
    xx = np.arange(len(wins)) + (k - 0.5) * 0.3
    ax.bar(xx, q.precision, 0.3, color=col, label=bg)
    ax.errorbar(xx, q.precision, yerr=[q.precision - q.season_lo, q.season_hi - q.precision], fmt='none', color='k', lw=0.8)
ax.set_xticks(range(len(wins))); ax.set_xticklabels(lab); ax.axhline(0, color='k', lw=0.5)
ax.set_ylabel('share of flagged points\nabove wildfire background'); ax.set_title('Excess estimate by fortnight (bars: 95% CI over seasons)')
ax.legend(fontsize=7); fig.tight_layout(); fig.savefig(O + 'fig2_fortnight_placebo.png', dpi=130)
# fig3 rules: control caught vs precision, late Feb, density matched
q = M[(M.window == '3 15-28 Feb') & (M.background == 'density-matched')]
fig, ax = plt.subplots(figsize=(5, 3.2))
for i, r in q.iterrows():
    ax.errorbar(r.est_control_caught, r.precision, yerr=[[r.precision - r.fire_lo], [r.fire_hi - r.precision]], fmt='o')
    ax.annotate(r.rule, (r.est_control_caught, r.precision), fontsize=7, xytext=(4, 4), textcoords='offset points')
ax.set_xlabel('est. control-burn points caught, 15-28 Feb, 2014-26'); ax.set_ylabel('est. precision (density-matched)')
ax.set_ylim(0.3, 0.7); ax.set_xlim(0, 5000); ax.set_title('Held-out rules, 15-28 Feb'); fig.tight_layout(); fig.savefig(O + 'fig3_rules.png', dpi=130)
# fig4 scars Ratapani
T = pd.read_csv(O + 'scar_shape_by_class.csv'); r = T[T.set == 'Ratapani v2'].copy()
order = [('Jan-14 Feb', True), ('Jan-14 Feb', False), ('15-28 Feb', True), ('15-28 Feb', False), ('16 Mar-May', True), ('16 Mar-May', False)]
r = r.set_index(['window', 'flagged']).loc[order]
lbl = [f"{w}\n{'flagged' if f else 'not flagged'}" for w, f in order]
fig, axs = plt.subplots(1, 2, figsize=(8, 3))
axs[0].bar(range(6), r.strip_share, color=['C3', 'C1', 'C3', 'C1', 'C3', 'C1']); axs[0].set_xticks(range(6)); axs[0].set_xticklabels(lbl, fontsize=6)
axs[0].set_title('Ratapani: strip-like scars (<25% of area\nleft after 30 m inward buffer)'); axs[0].set_ylabel('share of scars')
xx = np.arange(6)
axs[1].bar(xx - 0.2, r.beat30, 0.2, label='beat boundary', color='C0'); axs[1].bar(xx, r.beat30_decoy, 0.2, label='beat, decoy moved 2-4 km', color='C0', alpha=0.4)
axs[1].bar(xx + 0.2, r.road30, 0.2, label='road', color='C2'); axs[1].bar(xx + 0.4, r.road30_decoy, 0.2, label='road, decoy', color='C2', alpha=0.4)
axs[1].set_xticks(xx + 0.1); axs[1].set_xticklabels(lbl, fontsize=6); axs[1].set_title('Share of scar outline within 30 m of a line'); axs[1].legend(fontsize=6)
fig.tight_layout(); fig.savefig(O + 'fig4_scars.png', dpi=130)
# mixture estimate
E = pd.read_parquet(S + 'r21_cb/scar_shapes.parquet'); E = E[(E.set == 'R') & E.area_ha.notna() & (E.flag_cur == True)]
E['strip'] = E.core30 < 0.25
wmap = {'1 Jan': 'J', '2 1-14 Feb': 'J', '3 15-28 Feb': 'L', '5 16 Mar-May': 'B'}; E['w'] = E.fn.map(wmap); E = E[E.w.notna()]
rng = np.random.default_rng(5); est = []
def pi(df):
    s = df.groupby('w').strip.mean(); return (s['L'] - s['B']) / (s['J'] - s['B'])
for _ in range(1000):
    est.append(pi(pd.concat([g.iloc[rng.integers(0, len(g), len(g))] for _, g in E.groupby('w')])))
print('Ratapani strip mixture: share of flagged late-Feb scars that are Jan-like', round(pi(E), 3), np.percentile(est, [2.5, 97.5]).round(3), E.w.value_counts().to_dict())
pd.DataFrame({'estimate': [pi(E)], 'lo': [np.percentile(est, 2.5)], 'hi': [np.percentile(est, 97.5)]}).to_csv(O + 'scar_mixture_ratapani.csv', index=False)
