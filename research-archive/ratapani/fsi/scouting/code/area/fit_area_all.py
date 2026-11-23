"""Variant: train/score on all scars (chip-edge areas are lower bounds); LOYO. Size-class errors and
day-0 classification of large fires (>=100 ha) and small (<10 ha)."""
import numpy as np, pandas as pd, lightgbm as lgb
from scipy.stats import spearmanr
from sklearn.metrics import roc_auc_score
D = '/tmp/claude-0/-home-user/be9b8f54-cc26-52cb-bdbb-9c8008a24baf/scratchpad/r12_area_code/'
F = pd.read_parquet(D + 'features_750.parquet'); F = F[(F.month <= 6) & ~F.grew_large].reset_index(drop=True)
y = np.log(F.scar_ha.values); seasons = sorted(F.year.unique())
bins = [0, 10, 30, 100, 300, 1e9]; labs = ['<10', '10-30', '30-100', '100-300', '>=300']
cls = pd.cut(F.scar_ha, bins, labels=labs, right=False).values
print('n', len(F), 'edge', F.edge.sum())
P = lambda: lgb.LGBMRegressor(n_estimators=300, learning_rate=0.03, num_leaves=15, min_child_samples=40,
                               subsample=0.8, subsample_freq=1, colsample_bytree=0.8, verbose=-1)
C = lambda: lgb.LGBMClassifier(n_estimators=300, learning_rate=0.03, num_leaves=15, min_child_samples=40, verbose=-1)
for pre in ['d0_', 'all_']:
    cols = [c for c in F.columns if c.startswith(pre)] + ['month']; X = F[cols].values
    pr = np.full(len(F), np.nan); pbig = pr.copy(); psmall = pr.copy(); pl = pr.copy()
    xl = np.log(F[pre + 'fp_union_ha'].values)
    for s in seasons:
        te = (F.year == s).values; tr = ~te
        pr[te] = P().fit(X[tr], y[tr]).predict(X[te])
        b = np.polyfit(xl[tr], y[tr], 1); pl[te] = np.polyval(b, xl[te])
        pbig[te] = C().fit(X[tr], F.scar_ha.values[tr] >= 100).predict_proba(X[te])[:, 1]
        psmall[te] = C().fit(X[tr], F.scar_ha.values[tr] < 10).predict_proba(X[te])[:, 1]
    for name, p in [('LightGBM', pr), ('power law on footprint union', pl)]:
        lr = (p - y) / np.log(2)
        print(f'{pre} {name}: spearman {spearmanr(p, y)[0]:.3f} within x2 {np.mean(np.abs(lr) <= 1):.3f} '
              f'med|log2| {np.median(np.abs(lr)):.2f}')
        for c in labs:
            m = cls == c
            print(f'   {c:8s} n={m.sum():5d} within x2 {np.mean(np.abs(lr[m]) <= 1):.2f} median pred/true {2 ** np.median(lr[m]):.2f}'
                  f' MAE {np.mean(np.abs(np.exp(p[m]) - F.scar_ha.values[m])):.1f} ha')
    print(f'{pre} AUC big>=100ha {roc_auc_score(F.scar_ha >= 100, pbig):.3f} (base rate {np.mean(F.scar_ha >= 100):.3f}); '
          f'AUC small<10ha {roc_auc_score(F.scar_ha < 10, psmall):.3f} (base {np.mean(F.scar_ha < 10):.3f})')
    # precision at top 10% of pbig
    k = int(0.1 * len(F)); top = np.argsort(-pbig)[:k]
    print(f'   top10% by p(big): {np.mean(F.scar_ha.values[top] >= 100):.3f} are >=100 ha')
    # single-pixel events
    m1 = F[pre + 'n'].values == 1
    print(f'   single-detection fires: n={m1.sum()} median scar {np.median(F.scar_ha.values[m1]):.1f} ha, IQR '
          f'{np.percentile(F.scar_ha.values[m1], 25):.1f}-{np.percentile(F.scar_ha.values[m1], 75):.1f}')
# area per detection, by n
F['nb'] = pd.cut(F.all_n, [0, 1, 2, 4, 8, 16, 1000])
print(F.groupby('nb', observed=True).agg(n=('scar_ha', 'size'), med_scar=('scar_ha', 'median'),
      med_union=('all_fp_union_ha', 'median'), med_frp=('all_frp_sum', 'median'),
      ha_per_det=('scar_ha', lambda s: np.median(s / F.loc[s.index, 'all_n']))).round(1).to_string())
F['ha_per_MJs'] = F.scar_ha / F.all_frp_sum
print('median scar ha per MW of summed FRP', F.ha_per_MJs.median().round(2), 'by month', F.groupby('month').ha_per_MJs.median().round(2).to_dict())
