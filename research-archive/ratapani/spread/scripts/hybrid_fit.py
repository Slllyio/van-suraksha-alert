"""Learned spread correction: LightGBM on physics arrival time + geometry + fuel + weather.
Train 2017-21, test 2022-24. Score = Sorensen with the scar when picking scar-area pixels."""
import numpy as np, pandas as pd, lightgbm as lgb, glob, json
cols = ['label', 'w', 'event', 'season', 'dist', 't_phys', 'wind_al', 'dz', 'slope', 'wc', 'burnable', 'nb_dist', 'bfrac',
        'burned_prev', 'n_det', 'doy', 'rh_min', 'm1_min', 'ws_mean', 'scar_px']
d = pd.concat([pd.read_parquet(f, columns=cols) for f in sorted(glob.glob('/tmp/claude-0/spread/data/hyb_[0-9].parquet'))])
d['t_phys'] = np.minimum(d.t_phys, 5000.0)
d['burnable'] = d.burnable.astype(int); d['burned_prev'] = d.burned_prev.astype(int)
tr, te = d[d.season <= 2021], d[d.season >= 2022]
print(len(d), 'rows;', d.event.nunique(), 'events; train', tr.event.nunique(), 'test', te.event.nunique())
rng = np.random.default_rng(0)
sub = tr[(tr.label == 1) | (rng.random(len(tr)) < 0.3)]
wsub = np.where(sub.label == 1, 1.0, sub.w / 0.3)
FEATS = {
    'distance only': ['dist'],
    'physics time only': ['t_phys'],
    'distance + physics time': ['dist', 't_phys'],
    'all (physics + geometry + fuel + weather)': ['dist', 't_phys', 'wind_al', 'dz', 'slope', 'wc', 'burnable', 'nb_dist', 'bfrac',
                                                  'burned_prev', 'n_det', 'doy', 'rh_min', 'm1_min', 'ws_mean'],
    'all without wind': ['dist', 't_phys', 'dz', 'slope', 'wc', 'burnable', 'nb_dist', 'bfrac', 'burned_prev', 'n_det', 'doy', 'rh_min', 'm1_min'],
}
def sorensen(g, score):
    # pick the scar-area worth of (weighted) pixels with the highest score
    o = np.argsort(-score); w = g.w.values[o]; y = g.label.values[o]
    n = g.scar_px.iloc[0]; k = np.searchsorted(np.cumsum(w), n)
    hit = y[:k + 1].sum()
    return 2 * hit / (n + n)
res = {}
for name, f in FEATS.items():
    m = lgb.LGBMClassifier(n_estimators=300, learning_rate=0.05, num_leaves=63, min_child_samples=200, subsample=0.8,
                           subsample_freq=1, colsample_bytree=0.9, verbose=-1)
    if f == ['dist']:
        p = -te.dist.values
    elif f == ['t_phys']:
        p = -te.t_phys.values
    else:
        m.fit(sub[f], sub.label, sample_weight=wsub); p = m.predict_proba(te[f])[:, 1]
        if name.startswith('all ('):
            imp = pd.Series(m.booster_.feature_importance('gain'), index=f).sort_values(ascending=False)
            res['importance'] = (imp / imp.sum()).round(3).to_dict()
    t = te.assign(p=p)
    s = t.groupby('event').apply(lambda g: sorensen(g, g.p.values), include_groups=False)
    res[name] = round(float(s.mean()), 3)
    print(f'{name:45s} test Sorensen {s.mean():.3f}  (events {len(s)})', flush=True)
json.dump(res, open('/tmp/claude-0/spread/data/hybrid_results.json', 'w'), indent=1)
print(res.get('importance'))
