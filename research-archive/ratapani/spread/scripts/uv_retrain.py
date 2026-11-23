"""Does training on ALL fires (not just the 146 big ones) fix the unseen-fire results? (Oct 17)
Same features and settings as mf_eval.py; each season held out in turn; trained on big + unseen multi-look + one-look fires.
Scored separately on each group, next to the frozen big-fire models. Also saves per-season models (models_all/growth24_<season>.txt) so
the forecast tool can be re-scored with a model that never saw the season.
  python3 uv_retrain.py
"""
import json, os, numpy as np, pandas as pd, lightgbm as lgb
from sklearn.metrics import roc_auc_score
U = '/tmp/claude-0/unseen'; OUTM = f'{U}/models_all'; os.makedirs(OUTM, exist_ok=True)
FE = ['age_h', 'n_dots', 'n_dots_last', 'n_dots_last2', 'frp_last', 'frp_all', 'night', 'extent_m', 'foot_ha', 'forest_share', 'grass_share',
      'n_fronts', 'n_active', 'fire_dots', 'doy', 'th', 'k', 'kind_c']
parts = [('big146', '/tmp/claude-0/fronts/mf'), ('unseen_multi', f'{U}/u'), ('unseen_one', f'{U}/o')]
R = pd.concat([pd.read_parquet(f'{p}_fronts.parquet').assign(group=g) for g, p in parts], ignore_index=True)
R = R[R.active].copy(); R['kind_c'] = R.kind.map({'first': 0, 'continuing': 1, 'separate': 2, 'independent': 3, 'old': 4}); R['y'] = np.log1p(R.new24_ha)
P = dict(objective='regression_l1', learning_rate=.05, num_leaves=7, min_data_in_leaf=20, feature_fraction=.8, verbose=-1, seed=0)
for tag, train_groups in [('all', ['big146', 'unseen_multi', 'unseen_one']), ('big', ['big146'])]:
    R[f'pred_{tag}'] = np.nan; R[f'pstop_{tag}'] = np.nan
    for s in sorted(R.season.unique()):
        tr = R[(R.season != s) & R.group.isin(train_groups)]; te = R.season == s
        m = lgb.train(P, lgb.Dataset(tr[FE], tr.y), 300); c = lgb.train(dict(P, objective='binary'), lgb.Dataset(tr[FE], (tr.new24_ha < 2).astype(int)), 200)
        R.loc[te, f'pred_{tag}'] = np.expm1(m.predict(R.loc[te, FE])); R.loc[te, f'pstop_{tag}'] = c.predict(R.loc[te, FE])
        if tag == 'all':
            m.save_model(f'{OUTM}/growth24_{s}.txt'); c.save_model(f'{OUTM}/stop24_{s}.txt')
w2 = lambda p, t: float((np.abs(np.log(np.clip(p, .5, None) / np.clip(t, .5, None))) <= np.log(2)).mean())
res = {}
for g, x in R.groupby('group'):
    y = (x.new24_ha < 2).astype(int); o = dict(rows=len(x), fires=int(x.fire.nunique()), share_stopped=float(y.mean()), median_true_ha=float(x.new24_ha.median()))
    for tag in ['big', 'all']:
        o[f'within2x_{tag}'] = w2(x[f'pred_{tag}'], x.new24_ha)
        o[f'bias_{tag}'] = float(np.exp(np.median(np.log1p(x[f'pred_{tag}']) - np.log1p(x.new24_ha))))
        if 0 < y.sum() < len(y):
            o[f'stop_auc_{tag}'] = float(roc_auc_score(y, x[f'pstop_{tag}']))
        o[f'stop_said_{tag}'] = float(x[f'pstop_{tag}'].mean())
    o['within2x_median_all'] = w2(np.full(len(x), R.new24_ha.median()), x.new24_ha)
    res[g] = o
x = R; x['bin'] = pd.cut(x.pstop_all, [0, .2, .4, .6, .8, 1.0], include_lowest=True)
res['calibration_all_model'] = [dict(bin=str(b), n=len(z), said=round(float(z.pstop_all.mean()), 2), happened=round(float((z.new24_ha < 2).mean()), 2))
                                for b, z in x.groupby('bin', observed=True)]
R.drop(columns='bin').to_parquet(f'{U}/retrain_rows.parquet')
json.dump(res, open(f'{U}/retrain.json', 'w'), indent=1); print(json.dumps(res, indent=1))
