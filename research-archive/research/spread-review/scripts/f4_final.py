"""Final 12/24/48 h 'chance this cell burns' models on all seasons 2017-26 (arrival-map labels), each with the isotonic
calibration learnt from the held-out-season predictions. Out: forecast_burn/model_y{12,24,48}.txt + iso_y*.pkl"""
import pandas as pd, numpy as np, sys, pickle, lightgbm as lgb
from sklearn.isotonic import IsotonicRegression
D = pd.read_parquet(sys.argv[1]); OUT = '/mnt/project-files/research/spread-review/forecast_burn/'
F = ['d_all', 'd_last', 'd_first', 'd_old', 'n_old500', 'proj', 'perp', 'mom_len', 'n_seen', 'n_last', 'looks_seen', 'frp_last', 'frp_max',
     'h_since_first', 'h_since_last', 'silent', 'next_night', 'doy', 'elev_rel', 'slope', 'wc']
P = pd.read_parquet(OUT + 'preds.parquet')
for y in ('y12', 'y24', 'y48'):
    m = lgb.LGBMClassifier(n_estimators=400, learning_rate=0.05, num_leaves=63, min_child_samples=200, subsample=0.8, subsample_freq=1,
                           colsample_bytree=0.8, verbose=-1).fit(D[F], D[y], sample_weight=D.w)
    m.booster_.save_model(OUT + f'model_{y}.txt')
    iso = IsotonicRegression(out_of_bounds='clip', y_min=0, y_max=1).fit(P['full_' + y], P[y], sample_weight=P.w)
    pickle.dump(iso, open(OUT + f'iso_{y}.pkl', 'wb'))
print('saved')
