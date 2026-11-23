"""Compact tables + figure for the unseen-fire validation (uv_apply.py outputs, frozen big-fire models vs per-season all-fire models)."""
import json, numpy as np, pandas as pd, matplotlib; matplotlib.use('Agg'); import matplotlib.pyplot as plt
from sklearn.metrics import roc_auc_score
U, T = '/tmp/claude-0/unseen/u', '/tmp/claude-0/fronts/mf'
Fz = pd.read_csv('/mnt/project-files/research/big-fires/results/fires.csv').set_index('fire')
w2 = lambda p, t: float((np.abs(np.log(np.clip(p, .5, None) / np.clip(t, .5, None))) <= np.log(2)).mean())
rng = np.random.default_rng(0)
def ci(I, a, b):
    f = I.groupby('fire')[[a, b]].mean(); d = (f[a] - f[b]).values
    v = [d[rng.integers(0, len(d), len(d))].mean() for _ in range(1000)]; return [round(np.percentile(v, 2.5), 3), round(np.percentile(v, 97.5), 3)]
out = {}
for name, pre in [('unseen', U), ('train146', T)]:
    for mt, tag in [('frozen_big', ''), ('all_fires_loso', '_loso')]:
        F = pd.read_csv(f'{pre}_apply{tag}_fronts.csv'); I = pd.read_csv(f'{pre}_apply{tag}_issues.csv'); y = (F.true_ha < 2).astype(int)
        I['size'] = pd.cut(Fz.area_ha.reindex(I.fire).values, [0, 50, 100, 200, 1e9], labels=['<50', '50-100', '100-200', '>200'])
        o = dict(front_rows=len(F), issues=len(I), fires=int(I.fire.nunique()), within2x=w2(F.pred_ha, F.true_ha),
                 bias=float(np.exp(np.median(np.log1p(F.pred_ha) - np.log1p(F.true_ha)))), stop_auc=float(roc_auc_score(y, F.p_stop)),
                 stop_said=float(F.p_stop.mean()), stop_happened=float(y.mean()),
                 sor_tool=float(I.sor_tool.median()), sor_foot=float(I.sor_foot.median()), sor_blob_same_area=float(I.sor_blob_same_area.median()),
                 sor_blob_median=float(I.sor_blob_median.median()), forecast_over_true_area=float(np.median(I.fc_ha / I.truth_ha.clip(1))),
                 ci_tool_minus_foot=ci(I, 'sor_tool', 'sor_foot'), ci_tool_minus_blob_median=ci(I, 'sor_tool', 'sor_blob_median'),
                 ci_tool_minus_blob_same_area=ci(I, 'sor_tool', 'sor_blob_same_area'),
                 by_size={str(k): dict(n=len(x), tool=round(float(x.sor_tool.median()), 3), foot=round(float(x.sor_foot.median()), 3),
                                       blob_median=round(float(x.sor_blob_median.median()), 3)) for k, x in I.groupby('size', observed=True)})
        F['bin'] = pd.cut(F.p_stop, [0, .2, .4, .6, .8, 1], include_lowest=True)
        o['calib'] = [(round(float(x.p_stop.mean()), 2), round(float((x.true_ha < 2).mean()), 2), len(x)) for _, x in F.groupby('bin', observed=True)]
        out[f'{name}/{mt}'] = o
json.dump(out, open('/tmp/claude-0/unseen/summary.json', 'w'), indent=1); print(json.dumps(out, indent=1))
fig, ax = plt.subplots(1, 2, figsize=(11, 4.4))
for key, c, lab in [('unseen/frozen_big', '#c0392b', 'trained on 146 big fires'), ('unseen/all_fires_loso', '#2471a3', 'trained on all fires (season held out)')]:
    cb = np.array(out[key]['calib']); ax[0].plot(cb[:, 0], cb[:, 1], 'o-', color=c, label=lab)
ax[0].plot([0, 1], [0, 1], 'k:', lw=1); ax[0].set_xlabel('chance the front stops, as forecast'); ax[0].set_ylabel('share that really stopped')
ax[0].set_title('Unseen fires: are the stop chances honest?'); ax[0].legend(fontsize=8)
sz = ['<50', '50-100', '100-200', '>200']; xx = np.arange(4)
for i, (k, lab, c) in enumerate([('foot', 'dots only', '#999'), ('blob_median', 'dots + same growth for all', '#e59866'), ('tool', 'forecast tool (all-fire model)', '#2471a3')]):
    ax[1].bar(xx + (i - 1) * .27, [out['unseen/all_fires_loso']['by_size'][s][k] for s in sz], .27, color=c, label=lab)
ax[1].set_xticks(xx, [s + ' ha' for s in sz]); ax[1].set_xlabel('final scar size'); ax[1].set_ylabel('24 h overlap with real burn (median)')
ax[1].set_title('Unseen fires: 24 h map overlap'); ax[1].legend(fontsize=8); ax[1].set_ylim(0, .7)
plt.tight_layout(); plt.savefig('/tmp/claude-0/unseen/unseen_validation.png', dpi=130)
