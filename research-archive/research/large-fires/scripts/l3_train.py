"""Step 3. Train the models on the square-day samples (negatives at 1%, weight 100).
Period 'held': train 2018-21, test 2022-24. 'fwd': train 2018-24, test 2025.
  ALL   : today's kind of list - target any VIIRS fire point in the square in the next 2 days; round-22 inputs (B0 + static GIS).
  ALLS  : the same target, plus the new scar-history inputs (separates "new inputs" from "new target").
  BIG   : target = first look of a 200 forest ha+ scar fire in the square in the next 2 days; all inputs.
  B100  : same, 100 ha+.   B500: same, 500 ha+.
  START : target = first look of any scar fire; SIZE: among those starts, chance it reaches 200 ha (two-stage = START x SIZE).
Out: scratch models_<period>.pkl."""
import sys, pickle, numpy as np, pandas as pd, lightgbm as lgb
import lf_common as L
SCAR = ['bf_all_r0', 'bf_all_r3', 'bf_big_r0', 'bf_big_r3', 'bf_big_r7', 'bf_b500_r3', 'bst_r7', 'n_scar_yrs']
META = ['y_any', 'lsz', 'w', 'ui', 'season', 'doy']
P_ALL = dict(objective='binary', learning_rate=0.06, num_leaves=127, min_data_in_leaf=400, feature_fraction=0.8, bagging_fraction=0.8,
             bagging_freq=1, lambda_l2=1.0, verbose=-1, num_threads=4, max_cat_to_onehot=4, cat_smooth=20)
P_BIG = dict(P_ALL, learning_rate=0.03, num_leaves=31, min_data_in_leaf=200, lambda_l2=10.0, feature_fraction=0.7)
TR = {'held': range(2018, 2022), 'fwd': range(2018, 2025)}


def fit(D, y, feats, params, n, w=None):
    ds = lgb.Dataset(D[feats].values.astype(np.float32), y.astype(np.float32), weight=D.w.values if w is None else w, feature_name=feats,
                     categorical_feature=['div'], free_raw_data=True)
    m = lgb.train(params, ds, n); m._feats = feats; return m


def main(period):
    D = pd.concat([pd.read_parquet(L.SC + f'samp_{y}.parquet') for y in TR[period]], ignore_index=True)
    allf = [c for c in D.columns if c not in META]; base = [c for c in allf if c not in SCAR]
    print(period, len(D), 'feats', len(allf), flush=True)
    M = {}
    M['ALL'] = fit(D, D.y_any.values, base, P_ALL, 350); print('ALL', flush=True)
    M['ALLS'] = fit(D, D.y_any.values, allf, P_ALL, 350); print('ALLS', flush=True)
    for nm, th in (('BIG', 200), ('B100', 100), ('B500', 500)):
        M[nm] = fit(D, (D.lsz >= th).values, allf, P_BIG, 500); print(nm, int((D.lsz >= th).sum()), flush=True)
    M['START'] = fit(D, (D.lsz > 0).values, allf, P_BIG, 500)
    S = D[D.lsz > 0]
    M['SIZE'] = fit(S, (S.lsz >= 200).values, allf, P_BIG, 400, w=np.ones(len(S), np.float32)); print('SIZE', len(S), flush=True)
    pickle.dump({k: (m.model_to_string(), m._feats) for k, m in M.items()}, open(L.SC + f'models_{period}.pkl', 'wb'))
    imp = {k: pd.Series(m.feature_importance('gain'), index=m._feats).sort_values(ascending=False) for k, m in M.items()}
    pd.DataFrame({k: (v / v.sum()).round(4) for k, v in imp.items()}).to_csv(L.OUT + f'importance_{period}.csv')


if __name__ == '__main__':
    main(sys.argv[1])
