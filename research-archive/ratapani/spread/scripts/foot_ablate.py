"""Which ingredients give the learned footprint its gain over the circle? Feature-group ablation on the 80 m lattice rows:
4 folds of two seasons each, 250 rounds; per-fire Sorensen at the true positive count on the held-out lattice rows (a proxy for
the 20 m score) and per-fire AUC. Usage: foot_ablate.py rows.parquet[,..] out.json"""
import numpy as np, pandas as pd, sys, json, time, lightgbm as lgb
from sklearn.metrics import roc_auc_score
from footprint import FEATS
d = pd.concat([pd.read_parquet(f) for f in sys.argv[1].split(',')], ignore_index=True)
FOLDS = [(2017, 2018), (2019, 2020), (2021, 2022), (2023, 2024)]
G = {'distance': ['d_near', 'd_cent'],
     'fire level': ['n_first', 'frp_sum', 'frp_max', 'night', 'doy', 'ext_first', 'ws0', 'rh0', 'm1_0', 'temp0'],
     'physics arrival': ['t_phys', 'reach'],
     'pixel statics': ['wc', 'elev', 'slope', 'd_road', 'd_nonveg', 'd_built', 'd_prev', 'nburn_hist', 'last_burn', 'rf1', 'lf', 'forest'],
     'deltas vs detection': ['dd_road', 'dd_nonveg', 'dd_built', 'dd_prev', 'delev', 'drf1', 'dlf'],
     'dryness (lean)': ['lean', 'dlean'],
     'wind & front relations': ['rel_w0', 'rel_w24', 'rel_front']}
SETS = {'full': FEATS, 'distance only': G['distance'], 'distance + fire level': G['distance'] + G['fire level'],
        'distance + fire + physics': G['distance'] + G['fire level'] + G['physics arrival'],
        'distance + fire + statics + deltas': G['distance'] + G['fire level'] + G['pixel statics'] + G['deltas vs detection'],
        'distance + fire + statics + deltas + dryness': G['distance'] + G['fire level'] + G['pixel statics'] + G['deltas vs detection'] + G['dryness (lean)'],
        'full minus wind & front': [f for f in FEATS if f not in G['wind & front relations']],
        'full minus dryness': [f for f in FEATS if f not in G['dryness (lean)']],
        'full minus physics': [f for f in FEATS if f not in G['physics arrival']]}
params = dict(objective='binary', learning_rate=0.06, num_leaves=63, min_child_samples=300, feature_fraction=0.8, bagging_fraction=0.7, bagging_freq=1, lambda_l2=5.0, num_threads=3, verbose=-1)
def fire_scores(df, p):
    out = []
    for e, g in df.groupby('event'):
        y = g.y.values.astype(bool); n = int(y.sum())
        if n == 0 or n == len(y): continue
        pp = p[g.index.values]; sel = np.zeros(len(y), bool); sel[np.argpartition(-pp, n - 1)[:n]] = True
        out.append((2 * (sel & y).sum() / (sel.sum() + n), roc_auc_score(y, pp)))
    return np.array(out)
res = {}; tt = time.time()
idx = pd.Series(np.arange(len(d)), index=d.index)
# circle baseline on the same rows
c = fire_scores(d, -d.d_near.values); res['circle'] = dict(sorensen=round(float(c[:, 0].mean()), 4), auc=round(float(c[:, 1].mean()), 4), n_fires=int(len(c)))
print('circle', res['circle'], flush=True)
for name, feats in SETS.items():
    p = np.zeros(len(d))
    for hold in FOLDS:
        tr = d[~d.season.isin(hold)]; te = d[d.season.isin(hold)]
        m = lgb.train(params, lgb.Dataset(tr[feats], tr.y, categorical_feature=['wc'] if 'wc' in feats else []), num_boost_round=250)
        p[te.index.values] = m.predict(te[feats])
    s = fire_scores(d, p); res[name] = dict(sorensen=round(float(s[:, 0].mean()), 4), auc=round(float(s[:, 1].mean()), 4), n_fires=int(len(s)), n_feats=len(feats))
    print(name, res[name], f'{time.time() - tt:.0f}s', flush=True)
    json.dump(res, open(sys.argv[2], 'w'), indent=1)
