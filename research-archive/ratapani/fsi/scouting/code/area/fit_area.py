"""Fit area-from-VIIRS-points models with leave-one-season-out CV; report error by size class."""
import sys, numpy as np, pandas as pd, lightgbm as lgb
from scipy.stats import spearmanr
D = '/tmp/claude-0/-home-user/be9b8f54-cc26-52cb-bdbb-9c8008a24baf/scratchpad/r12_area_code/'
F = pd.read_parquet(D + (sys.argv[1] if len(sys.argv) > 1 else 'features_750.parquet'))
TARGET = sys.argv[2] if len(sys.argv) > 2 else 'scar_ha'
F = F[(F.month <= 6)].copy()
F['season'] = F.year
ok = ~F.edge & ~F.grew_large
print('rows', len(F), 'scored (no chip edge, not grew_into_large)', ok.sum())
y = np.log(F[TARGET].values)
bins = [0, 10, 30, 100, 300, 1e9]; labs = ['<10', '10-30', '30-100', '100-300', '>=300']
F['cls'] = pd.cut(F[TARGET], bins, labels=labs, right=False)


def report(pred_ha, name, mask=ok):
    t = F[TARGET].values[mask]; p = pred_ha[mask]; lr = np.log2(p / t)
    out = {'model': name, 'n': mask.sum(), 'spearman': spearmanr(p, t)[0],
           'med_abs_log2': np.median(np.abs(lr)), 'within_x2': np.mean(np.abs(lr) <= 1),
           'MAE_ha': np.mean(np.abs(p - t)), 'bias_med_ratio': 2 ** np.median(lr)}
    for c in labs:
        m = (F.cls.values[mask] == c)
        if m.sum() == 0: continue
        out[f'{c}:n'] = m.sum()
        out[f'{c}:x2'] = np.mean(np.abs(lr[m]) <= 1)
        out[f'{c}:ratio'] = 2 ** np.median(lr[m])
        out[f'{c}:MAE'] = np.mean(np.abs(p[m] - t[m]))
    return out


res = []
# null: training-season median
seasons = sorted(F.season.unique())


def loyo(fitpred):
    pred = np.full(len(F), np.nan)
    for s in seasons:
        te = (F.season == s).values; tr = ~te & ok.values
        pred[te] = fitpred(tr, te)
    return np.exp(pred)


res.append(report(loyo(lambda tr, te: np.full(te.sum(), np.median(y[tr]))), 'null: train median'))
for pre in ['d0_', 'd1_', 'all_']:
    for f in ['hull_ha', 'concave_ha', 'fp_union_ha']:
        res.append(report(F[pre + f].values, f'raw {pre}{f} (no fit)'))
    for f in ['n', 'frp_sum', 'fp_union_ha', 'hull_ha']:
        x = np.log(F[pre + f].values + 0.1)
        def fp(tr, te, x=x):
            b = np.polyfit(x[tr], y[tr], 1); return np.polyval(b, x[te])
        res.append(report(loyo(fp), f'powerlaw {pre}{f}'))
    cols = [c for c in F.columns if c.startswith(pre)] + ['month']
    X = F[cols].values
    def gb(tr, te, X=X):
        m = lgb.LGBMRegressor(n_estimators=300, learning_rate=0.03, num_leaves=15, min_child_samples=40,
                              subsample=0.8, subsample_freq=1, colsample_bytree=0.8, verbose=-1)
        m.fit(X[tr], y[tr]); return m.predict(X[te])
    res.append(report(loyo(gb), f'LightGBM {pre}* + month'))

R = pd.DataFrame(res)
pd.set_option('display.width', 250)
print(R[['model', 'n', 'spearman', 'med_abs_log2', 'within_x2', 'MAE_ha', 'bias_med_ratio']].round(3).to_string())
cls_cols = ['model'] + [c for c in R.columns if ':' in c and (c.endswith('x2') or c.endswith('ratio') or c.endswith(':n'))]
print(R[cls_cols].round(2).to_string())
R.to_csv(D + f'results_{TARGET}.csv', index=False)

# quantile intervals for d0 LightGBM: 80% coverage by class
cols = [c for c in F.columns if c.startswith('d0_')] + ['month']; X = F[cols].values
lo = np.full(len(F), np.nan); hi = lo.copy(); md = lo.copy()
for s in seasons:
    te = (F.season == s).values; tr = ~te & ok.values
    for a, arr in [(0.1, lo), (0.5, md), (0.9, hi)]:
        m = lgb.LGBMRegressor(objective='quantile', alpha=a, n_estimators=300, learning_rate=0.03, num_leaves=15,
                              min_child_samples=40, verbose=-1)
        m.fit(X[tr], y[tr]); arr[te] = m.predict(X[te])
cov = (y >= lo) & (y <= hi)
print('d0 quantile 10-90% coverage overall', cov[ok].mean().round(3), 'median width factor', np.exp(np.median(hi - lo)[()]).round(2))
for c in labs:
    m = ok.values & (F.cls.values == c)
    print(c, 'n', m.sum(), 'cov', cov[m].mean().round(3), 'median pred', np.exp(np.median(md[m])).round(1))
# by month
for mo in range(1, 7):
    m = ok.values & (F.month.values == mo)
    print('month', mo, 'n', m.sum(), 'median true', np.median(F[TARGET].values[m]).round(1))
