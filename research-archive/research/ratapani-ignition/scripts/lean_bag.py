"""Negative-bagged LightGBM ensemble (small_data_models.md item 4): all positives + negatives at 2.5%,
5 seeds rank-averaged; variant sampling negatives only from beat-days that have a positive (case-control within query).
Usage: python3 lean_bag.py OUTDIR
"""
import sys, os, json, numpy as np, pandas as pd, lightgbm as lgb
src = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'lean_plus.py')).read()
src = src[:src.index('for cfg in CONFIGS:')]
sys.argv = [sys.argv[0], sys.argv[1], 'none']
exec(compile(src, 'lean_plus.py', 'exec'))
OUT = sys.argv[1]
q = pd.factorize(pd.MultiIndex.from_frame(X[['season', 'date', 'beat']]))[0]; X['qid'] = q
X['q_haspos'] = X.groupby('qid').pos.transform('max').values
def fit_bag(tr_seasons, te_seasons, feat, rate, within, seeds=5):
    set_prior(tr_seasons)
    tr = X.season.isin(tr_seasons).values; te = X.season.isin(te_seasons).values; pos = X.pos.values
    out = np.zeros(te.sum())
    for s in range(seeds):
        rs = np.random.default_rng(100 + s)
        negok = tr & ~pos & (rs.random(len(X)) < rate)
        if within: negok &= X.q_haspos.values
        keep = (tr & pos) | negok
        gb = lgb.LGBMClassifier(n_estimators=300, learning_rate=0.05, num_leaves=31, min_child_samples=50, subsample=0.8, subsample_freq=1, colsample_bytree=0.7, n_jobs=4, verbose=-1, random_state=s)
        gb.fit(X.loc[keep, feat], pos[keep])
        p = gb.predict_proba(X.loc[te, feat])[:, 1]
        m = X.loc[te, ['season', 'date', 'beat']]
        out += pd.Series(p).groupby([m.season.values, m.date.values, m.beat.values]).rank(pct=True).values
    return out / seeds, te
def run_bag(name, rate, within):
    P = np.full(len(X), np.nan)
    for Y in range(2017, 2025):
        p, te = fit_bag([s for s in range(2017, 2025) if s != Y], [Y], BASE, rate, within); P[te] = p
    X[name] = P
    p, te = fit_bag(list(range(2017, 2025)), [2025, 2026], BASE, rate, within); X.loc[te, name] = p
    res[name] = {'loso': score_pred(name, range(2017, 2025)), 'test': score_pred(name, [2025, 2026])}
    print(name, 'LOSO', res[name]['loso']['real94_recall@5'], 'TEST', res[name]['test']['real94_recall@5'], flush=True)
    json.dump(res, open(os.path.join(OUT, 'lean_bag_results.json'), 'w'), indent=1)
run('base', BASE)
run_bag('bag025', 0.025, False)
run_bag('bag025_within', 0.025, True)
run_bag('bag10', 0.10, False)
print('LEAN_BAG_DONE', flush=True)
