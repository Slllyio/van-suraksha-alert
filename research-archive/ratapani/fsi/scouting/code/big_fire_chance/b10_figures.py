"""Figures: fig1 reliability (held-out), fig2 officials' top-N capture, fig3 per-division AUC, fig4 skill by item group."""
import numpy as np, pandas as pd
import matplotlib, matplotlib.ticker; matplotlib.use('Agg'); import matplotlib.pyplot as plt
OUT = '/mnt/project-files/ratapani/fsi/scouting/code/big_fire_chance/out'
R = pd.read_csv(f'{OUT}/reliability.csv'); O = pd.read_csv(f'{OUT}/officials_topN.csv'); D = pd.read_csv(f'{OUT}/division_v1.csv'); AB = pd.read_csv(f'{OUT}/ablation.csv')
fig, ax = plt.subplots(1, 2, figsize=(10, 4.3))
for k, tgt in enumerate(['S200', 'V200']):
    a = ax[k]; a.plot([0, .8], [0, .8], 'k:', lw=1)
    for (mdl, ver, st), sty in {('dots', 'v1', 'loso'): ('o-', 'gray'), ('lgbm', 'v1', 'loso'): ('o-', 'tab:blue'), ('lgbm', 'v1', 'fwd2025'): ('s--', 'tab:blue'),
                                ('lgbm', 'v2', 'loso'): ('o-', 'tab:red'), ('lgbm', 'v2', 'fwd2025'): ('s--', 'tab:red')}.items():
        g = R[(R.target == tgt) & (R.model == mdl) & (R.ver == ver) & (R.set == st) & (R.alerts >= 30)]
        a.plot(g.said, g.happened, sty[0], color=sty[1], ms=4, label=f"{'dot flag' if mdl == 'dots' else 'model ' + ver}, {'held-out seasons 2017-24' if st == 'loso' else 'forward 2025'}")
    a.set_xlabel('chance said at the alert'); a.set_ylabel('share that became 200 ha+')
    a.set_title(('Scar truth' if tgt[0] == 'S' else 'VIIRS-footprint truth') + ', 200 ha', fontsize=10); a.set_xlim(0, .8); a.set_ylim(0, .9)
ax[0].legend(fontsize=7, loc='upper left'); fig.tight_layout(); fig.savefig(f'{OUT}/fig1_reliability.png', dpi=110)
fig, ax = plt.subplots(1, 2, figsize=(10, 4.3))
for k, tgt in enumerate(['S200', 'V200']):
    a = ax[k]
    for (mdl, ver), c in {('dots', 'v1'): 'gray', ('lgbm', 'v1'): 'tab:blue', ('lgbm', 'v2'): 'tab:red'}.items():
        g = O[(O.target == tgt) & (O.model == mdl) & (O.ver == ver) & (O.set == 'loso')]
        a.plot(g.N, g.caught * 100, 'o-', color=c, label=f"{'dot flag' if mdl == 'dots' else 'model ' + ver}: flagged")
        a.plot(g.N, g.caught_before_cross * 100, 'o:', color=c, label=f"... flagged before it passed 200 ha")
    a.set_xscale('log'); a.xaxis.set_minor_formatter(matplotlib.ticker.NullFormatter()); a.set_xticks([5, 10, 20, 50], ['5', '10', '20', '50']); a.set_xlabel('alerts watched per day, statewide (top N)')
    a.set_ylabel('% of 200 ha+ fires'); a.set_ylim(0, 80)
    a.set_title(('Scar truth' if tgt[0] == 'S' else 'VIIRS-footprint truth') + ', held-out seasons 2017-24', fontsize=10)
ax[1].legend(fontsize=7); fig.tight_layout(); fig.savefig(f'{OUT}/fig2_officials_topN.png', dpi=110)
W = D[D.target == 'V200'].pivot_table(index='Division', columns='model', values='auc').dropna().sort_values('lgbm')
B = D[(D.target == 'V200') & (D.model == 'lgbm')].set_index('Division')
fig, a = plt.subplots(figsize=(10, 4.2)); x = np.arange(len(W))
a.bar(x, W.lgbm, color='tab:blue', label='model v1'); a.plot(x, W.dots, 'k.', label='dot flag')
a.axhline(0.5, color='gray', lw=0.8); a.set_xticks(x, W.index, rotation=90, fontsize=6); a.set_ylim(0.3, 1); a.set_ylabel('AUC, held-out seasons')
a.set_title('Per division, VIIRS-footprint truth 200 ha, 2017-24 held out (divisions with 5+ big fires)', fontsize=10); a.legend(fontsize=8)
fig.tight_layout(); fig.savefig(f'{OUT}/fig3_divisions.png', dpi=110)
fig, a = plt.subplots(figsize=(8, 3.8))
for tgt, c in (('S200', 'tab:green'), ('V200', 'tab:purple')):
    g = AB[(AB.target == tgt) & (AB.set == 'loso 2017-24') & ~AB.config.str.startswith('all minus')]
    a.plot(range(len(g)), g.auc, 'o-', color=c, label=('scar' if tgt[0] == 'S' else 'VIIRS') + ' truth, held-out 2017-24')
    g = AB[(AB.target == tgt) & (AB.set == 'fwd2025-26') & ~AB.config.str.startswith('all minus')]
    a.plot(range(len(g)), g.auc, 's--', color=c, label=('scar' if tgt[0] == 'S' else 'VIIRS') + ' truth, forward 2025-26')
a.set_xticks(range(len(g)), [s.replace('+ ', '+') for s in g.config], fontsize=8, rotation=15); a.set_ylabel('AUC (logistic)'); a.legend(fontsize=7)
a.set_title('Skill added item group by item group (first look only)', fontsize=10); fig.tight_layout(); fig.savefig(f'{OUT}/fig4_item_groups.png', dpi=110)
