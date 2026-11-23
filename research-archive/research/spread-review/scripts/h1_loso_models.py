"""Season-held-out models (2017-24) for the photo test: arrival-label rows and raw-dot rows, horizons 12 and 24 h.
Out: <scratch>/loso_models/{arr,raw}_{y12,y24}_{season}.txt"""
import pandas as pd, lightgbm as lgb, sys, os
S = sys.argv[1]; O = S + '/loso_models/'; os.makedirs(O, exist_ok=True)
F = ['d_all', 'd_last', 'd_first', 'd_old', 'n_old500', 'proj', 'perp', 'mom_len', 'n_seen', 'n_last', 'looks_seen', 'frp_last', 'frp_max',
     'h_since_first', 'h_since_last', 'silent', 'next_night', 'doy', 'elev_rel', 'slope', 'wc']
for tag, fn in (('arr', 'rows_arrival.parquet'), ('raw', 'rows.parquet')):
    D = pd.read_parquet(S + '/' + fn, columns=F + ['yr', 'w', 'y12', 'y24']); D = D[D.yr <= 2024]
    for y in ('y12', 'y24'):
        for s in range(2017, 2025):
            if os.path.exists(O + f'{tag}_{y}_{s}.txt'): continue
            tr = D[D.yr != s].sample(frac=0.35, random_state=s)  # lighter than the final models (35% of rows, 200 trees) to keep run time sane
            m = lgb.LGBMClassifier(n_estimators=200, learning_rate=0.09, num_leaves=63, min_child_samples=200, subsample=0.8, subsample_freq=1,
                                   colsample_bytree=0.8, verbose=-1).fit(tr[F], tr[y], sample_weight=tr.w / 0.35)
            m.booster_.save_model(O + f'{tag}_{y}_{s}.txt'); print(tag, y, s, flush=True)
