"""Feature-group ablation of the learned restart's next-pass head on the training lattice rows (held-out seasons):
AUC and the share of next-pass pixels captured at the persistence count. -> data/lr_ablation.json"""
import numpy as np, pandas as pd, glob, json, lightgbm as lgb
from sklearn.metrics import roc_auc_score
from foot_restart import FEATS, STAT
D = '/tmp/claude-0/spread/data'
d = pd.concat([pd.read_parquet(f) for f in sorted(glob.glob(f'{D}/lr_rows_[0-3].parquet'))], ignore_index=True)
d = d[d.y_next >= 0].sample(frac=0.5, random_state=0).reset_index(drop=True)
groups = {'all features': [], 'no weather': ['ws', 'rh', 'm1', 'temp', 'rel_w'], 'no momentum/axis': ['rel_mom', 'mom_len', 'rel_last_axis', 'rel_all_axis', 'run_so_far'],
          'no landscape': [f for f in STAT if f not in ('lean', 'forest')] + ['dd_road', 'dd_nonveg', 'dd_built', 'dd_prev', 'delev', 'drf1', 'dlf'],
          'no dryness': ['lean', 'dlean', 'forest'], 'no FRP/time': ['frp_last', 'frp_all', 'night_last', 'doy', 'elapsed_h', 'k', 'n_prev', 'n_last', 'ext_all'],
          'distances and lead only': [f for f in FEATS if f not in ('d_all', 'd_last', 'd_first', 'd_cent_all', 'd_cent_last', 'lead_h')]}
params = dict(objective='binary', learning_rate=0.08, num_leaves=63, min_child_samples=300, feature_fraction=0.8, bagging_fraction=0.7, bagging_freq=1, lambda_l2=5.0, num_threads=2, verbose=-1)
out = {}
for g, drop in groups.items():
    feats = [f for f in FEATS if f not in drop]; p = np.zeros(len(d))
    for s in range(2017, 2025):
        tr, te = d.season != s, d.season == s
        m = lgb.train(params, lgb.Dataset(d.loc[tr, feats], d.loc[tr, 'y_next'], categorical_feature=['wc'] if 'wc' in feats else []), num_boost_round=200)
        p[te.values] = m.predict(d.loc[te, feats])
    d['p'] = p; cap = pers = pos = 0
    for (e, k), q in d.groupby(['event', 'step']):
        n_p = int((q.d_all <= 475).sum()); npos = int(q.y_next.sum())
        if npos == 0 or n_p == 0:
            continue
        top = q.nlargest(n_p, 'p'); cap += int(top.y_next.sum()); pers += int(q.loc[q.d_all <= 475, 'y_next'].sum()); pos += npos
    out[g] = dict(auc=round(roc_auc_score(d.y_next, p), 4), captured_at_persistence_count=round(cap / pos, 4), persistence=round(pers / pos, 4), n_feats=len(feats))
    print(g, out[g], flush=True)
json.dump(out, open(f'{D}/lr_ablation.json', 'w'), indent=1)
