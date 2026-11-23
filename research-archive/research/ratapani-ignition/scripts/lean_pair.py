"""Custom pairwise loss on pairs straddling rank 5 (coordinator full-read list, item 2).
Reuses lean_plus.py's data build (exec of everything before its config loop) and its
score_pred/run. Objective: within each (season, date, real beat) query with >= 1
positive, at every boosting round rank cells by the current score and take only the
pairs where exactly one of (positive, negative) sits in the top 5; pairwise logistic
loss on those pairs. Then rank-average with the plain classifier.
Usage: python3 lean_pair.py OUTDIR  (reads lean_plus's data paths)
"""
import sys, os, json, numpy as np, pandas as pd, lightgbm as lgb
src = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'lean_plus.py')).read()
src = src[:src.index('for cfg in CONFIGS:')]
sys.argv = [sys.argv[0], sys.argv[1], 'none']
exec(compile(src, 'lean_plus.py', 'exec'))
OUT = sys.argv[1]; K = int(os.environ.get('PAIR_K', 5))

def pair_objective(qid):
    # qid: int array aligned with the training rows (sorted by qid)
    def obj(preds, ds):
        y = ds.get_label().astype(bool)
        s = pd.Series(preds)
        r = s.groupby(qid).rank('first', ascending=False).values
        top = r <= K
        df = pd.DataFrame({'q': qid, 'i': np.arange(len(y)), 'pos': y, 'top': top})
        A = df[df.pos & ~df.top][['q', 'i']].merge(df[~df.pos & df.top][['q', 'i']], on='q', suffixes=('_p', '_n'))
        B = df[df.pos & df.top][['q', 'i']].merge(df[~df.pos & ~df.top][['q', 'i']], on='q', suffixes=('_p', '_n'))
        P = pd.concat([A, B]); ip = P.i_p.values; ineg = P.i_n.values
        d = preds[ip] - preds[ineg]; sig = 1.0 / (1.0 + np.exp(d))  # = sigmoid(-d) = dL/d(-d)
        g = np.zeros(len(y)); h = np.zeros(len(y))
        np.add.at(g, ip, -sig); np.add.at(g, ineg, sig)
        hh = sig * (1 - sig) + 1e-6
        np.add.at(h, ip, hh); np.add.at(h, ineg, hh)
        return g, h
    return obj

def fit_pair(tr_seasons, te_seasons, feat):
    set_prior(tr_seasons)
    tr = X.season.isin(tr_seasons).values; te = X.season.isin(te_seasons).values
    q = X.loc[tr, ['season', 'date', 'beat', 'pos']].copy(); q['qid'] = pd.factorize(pd.MultiIndex.from_frame(q[['season', 'date', 'beat']]))[0]
    haspos = q.groupby('qid').pos.transform('max').values > 0
    sub = q[haspos].sort_values('qid'); idx = sub.index.values
    ds = lgb.Dataset(X.loc[idx, feat], label=X.pos.values[idx].astype(int), free_raw_data=False)
    params = dict(objective=pair_objective(sub.qid.values), learning_rate=0.05, num_leaves=31, min_data_in_leaf=50,
                  bagging_fraction=0.8, bagging_freq=1, feature_fraction=0.7, num_threads=4, verbose=-1)
    bst = lgb.train(params, ds, num_boost_round=300)
    return bst.predict(X.loc[te, feat]), te, bst

def run_pair(name, feat):
    P = np.full(len(X), np.nan)
    for Y in range(2017, 2025):
        p, te, _ = fit_pair([s for s in range(2017, 2025) if s != Y], [Y], feat); P[te] = p
        print(' fold', Y, 'done', flush=True)
    X[name] = P
    p, te, _ = fit_pair(list(range(2017, 2025)), [2025, 2026], feat); X.loc[te, name] = p
    res[name] = {'loso': score_pred(name, range(2017, 2025)), 'test': score_pred(name, [2025, 2026])}
    print(name, 'LOSO', res[name]['loso']['real94_recall@5'], 'TEST', res[name]['test']['real94_recall@5'], flush=True)
    json.dump(res, open(os.path.join(OUT, 'lean_pair_results.json'), 'w'), indent=1)

run('base', BASE)
run_pair('pair5_base', BASE)
m = X[['season', 'date', 'beat']]
X['rankavg_pair5'] = X['base'].groupby([m.season, m.date, m.beat]).rank(pct=True) + X['pair5_base'].groupby([m.season, m.date, m.beat]).rank(pct=True)
res['rankavg_pair5'] = {'loso': score_pred('rankavg_pair5', range(2017, 2025)), 'test': score_pred('rankavg_pair5', [2025, 2026])}
print('rankavg_pair5', res['rankavg_pair5']['loso']['real94_recall@5'], res['rankavg_pair5']['test']['real94_recall@5'], flush=True)
json.dump(res, open(os.path.join(OUT, 'lean_pair_results.json'), 'w'), indent=1)
X[['season', 'date', 'cell_id', 'base', 'pair5_base', 'rankavg_pair5']].to_parquet(os.path.join(OUT, 'lean_pair_pred.parquet'))
print('LEAN_PAIR_DONE', flush=True)
