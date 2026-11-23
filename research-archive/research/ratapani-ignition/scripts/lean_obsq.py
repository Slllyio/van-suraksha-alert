"""Observation-quality variants of the lean model (coordinator full-read list, PAWS-style).
Under the shared rule a burn dated to a long gap between clear images becomes many positive
cell-days, most of them not within 2 days of the real fire. Variants:
  eqburn : positive weight 1/(positive days of that burn) so every burn counts once
  tight5 : train only on positives whose window is <= 5 days (negatives unchanged)
  ens    : rank-average of models trained with window cut-offs 4, 8 and none
Usage: python3 lean_obsq.py OUTDIR
"""
import sys, os, json, numpy as np, pandas as pd, lightgbm as lgb
src = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'lean_plus.py')).read()
src = src[:src.index('for cfg in CONFIGS:')]
sys.argv = [sys.argv[0], sys.argv[1], 'none']
exec(compile(src, 'lean_plus.py', 'exec'))
OUT = sys.argv[1]
wl = bw[['season', 'cell_id', 'window_start', 'window_end']].copy(); wl['wlen'] = (wl.window_end - wl.window_start).dt.days
X = X.merge(wl[['season', 'cell_id', 'wlen']], on=['season', 'cell_id'], how='left')
npd = X[X.pos].groupby(['season', 'cell_id']).size().rename('npd'); X = X.join(npd, on=['season', 'cell_id'])
print('positive window length quantiles', X.loc[X.pos, 'wlen'].quantile([.25, .5, .75, .9]).tolist(), flush=True)

def fit_w(tr_seasons, te_seasons, feat, mode, cut=None):
    set_prior(tr_seasons)
    tr = X.season.isin(tr_seasons).values; te = X.season.isin(te_seasons).values
    rs = np.random.default_rng(0); pos = X.pos.values
    keep = tr & (pos | (rs.random(len(X)) < 0.25))
    if cut is not None: keep &= ~(pos & (X.wlen.values > cut))
    wt = np.where(pos[keep], 1.0, 4.0)
    if mode == 'eqburn':
        w = 1.0 / X.npd.values[keep]; w = np.where(pos[keep], w / w[pos[keep]].mean(), 4.0); wt = w
    gb = lgb.LGBMClassifier(n_estimators=300, learning_rate=0.05, num_leaves=31, min_child_samples=100, subsample=0.8, subsample_freq=1, colsample_bytree=0.7, n_jobs=4, verbose=-1)
    gb.fit(X.loc[keep, feat], pos[keep], sample_weight=wt)
    return gb.predict_proba(X.loc[te, feat])[:, 1], te

def run_w(name, mode, cut=None):
    P = np.full(len(X), np.nan)
    for Y in range(2017, 2025):
        p, te = fit_w([s for s in range(2017, 2025) if s != Y], [Y], BASE, mode, cut); P[te] = p
    X[name] = P
    p, te = fit_w(list(range(2017, 2025)), [2025, 2026], BASE, mode, cut); X.loc[te, name] = p
    res[name] = {'loso': score_pred(name, range(2017, 2025)), 'test': score_pred(name, [2025, 2026])}
    print(name, 'LOSO', res[name]['loso']['real94_recall@5'], 'TEST', res[name]['test']['real94_recall@5'], flush=True)
    json.dump(res, open(os.path.join(OUT, 'lean_obsq_results.json'), 'w'), indent=1)

run_w('base', 'plain')
run_w('eqburn', 'eqburn')
run_w('tight5', 'plain', cut=5)
run_w('cut4', 'plain', cut=4); run_w('cut8', 'plain', cut=8)
m = X[['season', 'date', 'beat']]
X['ens'] = sum(X[c].groupby([m.season, m.date, m.beat]).rank(pct=True) for c in ('base', 'cut4', 'cut8'))
res['ens'] = {'loso': score_pred('ens', range(2017, 2025)), 'test': score_pred('ens', [2025, 2026])}
print('ens', res['ens']['loso']['real94_recall@5'], res['ens']['test']['real94_recall@5'], flush=True)
json.dump(res, open(os.path.join(OUT, 'lean_obsq_results.json'), 'w'), indent=1)
print('LEAN_OBSQ_DONE', flush=True)
