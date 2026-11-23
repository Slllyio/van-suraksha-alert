"""Step 7: scores of the held-out predictions. AUC, PR-AUC (average precision), Brier, reliability, with 95% bootstrap ranges
over fires; the officials' view (top N alerts per day statewide); per-division results.
Out: out/metrics.csv, out/reliability.csv, out/officials_topN.csv, out/division_v1.csv"""
import glob
import numpy as np, pandas as pd
from sklearn.metrics import roc_auc_score, average_precision_score
SC = '/tmp/claude-0/-home-user/be9b8f54-cc26-52cb-bdbb-9c8008a24baf/scratchpad/r21_big'
OUT = '/mnt/project-files/ratapani/fsi/scouting/code/big_fire_chance/out'
A = pd.read_parquet(f'{SC}/ds.parquet')
P = pd.concat([pd.read_parquet(f) for f in glob.glob(f'{SC}/preds_*.parquet')])
P['set'] = np.where(P.split == 'forward', 'forward', 'loso')
P = P.merge(A[['alert', 'fire', 'season', 'Division', 't0', 'n1'] + [c for c in A if c.startswith('y') or c.startswith('cross')]], on='alert')
P.loc[P.set == 'forward', 'set'] = 'fwd' + P.season.astype(str)
rng = np.random.default_rng(1); NB = 200
def boot(y, p, fire, fn):
    """95% range over fires: resample fires with replacement; alerts of a fire share its weight."""
    u, inv = np.unique(fire, return_inverse=True); out = []
    for _ in range(NB):
        w = np.bincount(rng.integers(0, len(u), len(u)), minlength=len(u))[inv]
        out.append(fn(y, p, w))
    return np.percentile(out, [2.5, 97.5])
AUC = lambda y, p, w: roc_auc_score(y, p, sample_weight=w)
AP = lambda y, p, w: average_precision_score(y, p, sample_weight=w)
rows, rel = [], []
for (tgt, ver, model, st), g in P.groupby(['target', 'ver', 'model', 'set']):
    y = g[f'y{tgt}']; ok = y.notna(); g = g[ok]; y = y[ok].values.astype(int); p = g.p.values.astype(float)
    if len(g) == 0 or y.sum() < 5: continue
    r = dict(target=tgt, ver=ver, model=model, set=st, alerts=len(g), big=int(y.sum()), base=y.mean(),
             auc=roc_auc_score(y, p), prauc=average_precision_score(y, p), brier=np.mean((p - y) ** 2), mean_said=p.mean())
    if model in ('dots', 'logit', 'lgbm') and tgt in ('V200', 'S200', 'V50', 'S50', 'V500', 'S500'):
        lo, hi = boot(y, p, g.fire.values, AUC); r['auc_lo'], r['auc_hi'] = lo, hi
        lo, hi = boot(y, p, g.fire.values, AP); r['prauc_lo'], r['prauc_hi'] = lo, hi
    rows.append(r)
    b = pd.cut(p, [-.001, .01, .02, .05, .1, .2, .35, .5, 1.0])
    t = pd.DataFrame(dict(b=b, p=p, y=y)).groupby('b', observed=True).agg(alerts=('y', 'size'), said=('p', 'mean'), happened=('y', 'mean')).reset_index()
    t['target'], t['ver'], t['model'], t['set'] = tgt, ver, model, st; t['b'] = t.b.astype(str); rel.append(t)
M = pd.DataFrame(rows); M.to_csv(f'{OUT}/metrics.csv', index=False, float_format='%.4f')
pd.concat(rel).to_csv(f'{OUT}/reliability.csv', index=False, float_format='%.4f')
print(M[M.target.isin(['V200', 'S200'])].round(3).to_string())
# paired AUC gain over the dots flag (bootstrap over fires)
gain = []
for (tgt, ver, st), g in P[P.model.isin(['dots', 'lgbm', 'logit'])].groupby(['target', 'ver', 'set']):
    W = g.pivot_table(index=['alert', 'fire'], columns='model', values='p').reset_index().merge(A[['alert', f'y{tgt}']], on='alert')
    W = W[W[f'y{tgt}'].notna()]; y = W[f'y{tgt}'].values.astype(int)
    if y.sum() < 5: continue
    for mdl in ('logit', 'lgbm'):
        d0 = roc_auc_score(y, W[mdl]) - roc_auc_score(y, W.dots)
        both = np.c_[W[mdl].values, W.dots.values]
        lo, hi = boot(y, both, W.fire.values, lambda yy, pp, w: roc_auc_score(yy, pp[:, 0], sample_weight=w) - roc_auc_score(yy, pp[:, 1], sample_weight=w))
        gain.append(dict(target=tgt, ver=ver, set=st, model=mdl, auc_gain_over_dots=d0, lo=lo, hi=hi))
pd.DataFrame(gain).to_csv(f'{OUT}/auc_gain_over_dots.csv', index=False, float_format='%.4f'); print(pd.DataFrame(gain).round(3).to_string())
# ---------------- officials' view ----------------
off = []
for (tgt, ver, model, st), g in P[P.target.isin(['V200', 'S200', 'V500', 'S500', 'V50', 'S50'])].groupby(['target', 'ver', 'model', 'set']):
    thr = int(tgt[1:]); k = tgt[0]
    issue_h = 0.0 if ver == 'v1' else 15.0
    g = g.copy(); g['day'] = (g.t0 + pd.Timedelta(hours=issue_h)).dt.normalize()
    lab = g[f'y{tgt}']; bigf = g[lab == 1].groupby('fire').agg(cross=(f'cross{k}{thr}', 'min'))
    if len(bigf) < 5: continue
    for N in (5, 10, 20, 50):
        caught_runs, lead_runs, prec_runs = [], [], []
        for seed in range(10 if model == 'dots' else 1):
            j = g.p.values + np.random.default_rng(seed).random(len(g)) * 1e-6
            g['r'] = pd.Series(j, index=g.index).groupby(g.day).rank(ascending=False, method='first')
            top = g[g.r <= N]
            cf = set(top.fire[top[f'y{tgt}'] == 1])
            c = bigf.index.isin(cf); caught_runs.append(c.mean())
            lead = bigf.cross[c] - issue_h; lead_runs.append(lead)
            prec_runs.append(top[f'y{tgt}'].mean())
        lead = pd.concat(lead_runs)
        off.append(dict(target=tgt, ver=ver, model=model, set=st, N=N, days=g.day.nunique(), alerts_per_day=len(g) / g.day.nunique(),
                        big_fires=len(bigf), caught=np.mean(caught_runs), caught_before_cross=np.mean([((l > 0).sum()) / len(bigf) for l in lead_runs]),
                        lead_median_h=lead[lead > 0].median(), lead_p25_h=lead[lead > 0].quantile(.25), lead_p75_h=lead[lead > 0].quantile(.75),
                        already_past_at_issue=(bigf.cross <= issue_h).mean(), flagged_that_became_big=np.nanmean(prec_runs)))
O = pd.DataFrame(off); O.to_csv(f'{OUT}/officials_topN.csv', index=False, float_format='%.3f')
print(O[(O.target.isin(['V200', 'S200']))].round(3).to_string())
# ---------------- per division (LOSO pooled, v1) ----------------
dv = []
for (tgt, model), g in P[(P.set == 'loso') & (P.ver == 'v1') & P.target.isin(['V200', 'S200']) & P.model.isin(['dots', 'lgbm'])].groupby(['target', 'model']):
    for d, h in g.groupby('Division'):
        y = h[f'y{tgt}']; ok = y.notna(); y = y[ok]; p = h.p[ok]
        if y.sum() < 5 or (1 - y).sum() < 5: continue
        dv.append(dict(target=tgt, model=model, Division=d, alerts=len(y), big=int(y.sum()), base=y.mean(), said=p.mean(), auc=roc_auc_score(y, p)))
D = pd.DataFrame(dv); D.to_csv(f'{OUT}/division_v1.csv', index=False, float_format='%.3f')
W = D.pivot_table(index=['target', 'Division'], columns='model', values='auc').reset_index()
print(W.groupby('target')[['dots', 'lgbm']].describe().T.round(3))
