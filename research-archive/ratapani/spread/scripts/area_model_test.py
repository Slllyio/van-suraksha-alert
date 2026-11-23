"""How much area to add per forecast (Akkshay Oct 19 07:20Z "what to do for burn scar prediction that's important").
Gap analysis said size is the big lever (0.44 -> 0.51 with the right size). Unseen 818 fires, same truth and nearest-first placement as the
0.477 rule; only the AREA added outside the 265 m blocks changes.
  rule    : 24.1 ha x active fronts
  oracle  : the true burnt area outside blocks (ceiling for any area model)
  q50..q90: LightGBM quantile of the extra area, leave-one-season-out, from what is known at the look
  python3 area_model_test.py
"""
import sys, pickle, json, numpy as np, pandas as pd, lightgbm as lgb
from scipy.spatial import cKDTree
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components
sys.path.insert(0, '/mnt/project-files/research/fire-continuity/scripts'); import c0_lib as C
X0, Y0 = 737300.0, 2560500.0; MED = 24.1; LINK = 750.0
I = pd.read_parquet('/tmp/claude-0/unseen/u_issues.parquet'); M = pickle.load(open('/tmp/claude-0/unseen/u_maps.pkl', 'rb'))
A = pd.read_csv('/mnt/project-files/research/big-fires/results/fire_alerts.csv', parse_dates=['t']); A = A[A.sat != 'modis']
so = lambda a, b: 2 * (a & b).sum() / max(a.sum() + b.sum(), 1)
def clusters(xy):
    if len(xy) == 1: return np.zeros(1, int)
    p = np.array(list(cKDTree(xy).query_pairs(LINK)))
    if len(p) == 0: return np.arange(len(xy))
    return connected_components(coo_matrix((np.ones(len(p)), (p[:, 0], p[:, 1])), shape=(len(xy), len(xy))), directed=False)[1]
rows, CACHE = [], {}
for fire, g in I.groupby('fire'):
    mp = M[fire]; r0, r1, c0, c1 = mp['box']; Tg = mp['Tg'].ravel(); dom = mp['dom'].ravel()
    rr, cc = np.mgrid[r0:r1, c0:c1]; P = np.c_[(X0 + (cc + .5) * 20).ravel(), (Y0 - (rr + .5) * 20).ravel()]
    d = C.viirs_looks(A[A.fire == fire]).reset_index(drop=True)
    for it in g.itertuples():
        kn = d[d.lk <= it.k].reset_index(drop=True); xy = kn[['x', 'y']].values; lab = clusters(xy); tk = kn.t.max(); last = kn[kn.lk == it.k]
        act = set(lab[(kn.lk >= it.k - 1).values]); truth = dom & (Tg <= it.th + 24)
        dd = cKDTree(xy).query(P)[0].astype(np.float32); foot = dd <= 265
        order = np.argsort(np.where(foot, -1, dd), kind='stable')
        CACHE[(fire, it.k)] = (order, int(foot.sum()), np.cumsum(truth[order]), int(truth.sum()))
        ext = (xy.max(0) - xy.min(0)); prev = kn[kn.lk == it.k - 1]
        rows.append(dict(fire=fire, k=it.k, season=tk.year, doy=tk.dayofyear, hour=tk.hour, n_dots=len(xy), n_last=len(last), n_prev=len(prev),
                         n_fronts=len(set(lab)), n_act=len(act), age_h=(tk - kn.t.min()).total_seconds() / 3600,
                         gap_h=(tk - prev.t.max()).total_seconds() / 3600 if len(prev) else -1, frp_last=last.frp.sum(), frp_max=last.frp.max(),
                         frp_all=kn.frp.sum(), ext_x=ext[0], ext_y=ext[1], foot_ha=foot.sum() * .04, day=int((last.daynight == 'D').any()),
                         sats_last=last.sat.nunique(), extra_true_ha=(truth & ~foot).sum() * .04))
R = pd.DataFrame(rows); F = [c for c in R.columns if c not in ('fire', 'k', 'season', 'extra_true_ha')]
print('issues', len(R), 'median true extra ha', R.extra_true_ha.median(), 'rule extra', (R.n_act * MED).median(), flush=True)
QS = [.5, .6, .7, .8, .9]; y = np.log1p(R.extra_true_ha)
for q in QS: R[f'q{int(q*100)}'] = 0.0
R['mean'] = 0.0
for Y in R.season.unique():
    tr, te = R.season != Y, R.season == Y
    for q in QS:
        m = lgb.LGBMRegressor(objective='quantile', alpha=q, n_estimators=300, learning_rate=.03, num_leaves=15, min_child_samples=30, verbose=-1).fit(R.loc[tr, F], y[tr])
        R.loc[te, f'q{int(q*100)}'] = np.expm1(m.predict(R.loc[te, F])).clip(0)
    m = lgb.LGBMRegressor(n_estimators=300, learning_rate=.03, num_leaves=15, min_child_samples=30, verbose=-1).fit(R.loc[tr, F], y[tr])
    R.loc[te, 'mean'] = np.expm1(m.predict(R.loc[te, F])).clip(0)
def score(ha, key):
    order, nf, ct, T = CACHE[key]; n = min(int(nf + ha / .04), len(order))
    hit = ct[n - 1] if n > 0 else 0; return 2 * hit / max(n + T, 1)
V = ['rule', 'oracle', 'mean'] + [f'q{int(q*100)}' for q in QS]
for i, r in R.iterrows():
    key = (r.fire, r.k); R.at[i, 's_rule'] = score(MED * r.n_act, key); R.at[i, 's_oracle'] = score(r.extra_true_ha, key)
    for v in V[2:]: R.at[i, f's_{v}'] = score(r[v], key)
# best constant multiplier of the rule, fitted on other seasons (fair simple baseline)
for Y in R.season.unique():
    tr = R.season != Y; best = max([.5, .75, 1, 1.5, 2, 3, 4], key=lambda c: np.mean([score(MED * r.n_act * c, (r.fire, r.k)) for r in R[tr].itertuples()]))
    for i in R.index[R.season == Y]: R.at[i, 's_rule_scaled'] = score(MED * R.at[i, 'n_act'] * best, (R.at[i, 'fire'], R.at[i, 'k']))
R.to_csv('/tmp/claude-0/unseen/area_model.csv', index=False)
rng = np.random.default_rng(0); fm = R.groupby('fire')[[c for c in R.columns if c.startswith('s_')]].mean()
res = dict(issues=len(R), fires=int(R.fire.nunique()), overlap_mean_by_fire=fm.mean().round(4).to_dict(), overlap_median_issue=R[[c for c in R.columns if c.startswith('s_')]].median().round(4).to_dict())
best = max([c for c in fm.columns if c not in ('s_oracle', 's_rule')], key=lambda c: fm[c].mean()); res['best'] = best
for c in [best, 's_rule_scaled', 's_oracle']:
    dl = (fm[c] - fm.s_rule).values
    res[f'{c}_minus_rule_ci'] = [round(float(np.percentile([dl[rng.integers(0, len(dl), len(dl))].mean() for _ in range(2000)], q)), 4) for q in (2.5, 97.5)]
    res[f'{c}_better/worse'] = [int((dl > .005).sum()), int((dl < -.005).sum())]
from scipy.stats import spearmanr
res['area_rank_corr'] = {v: round(float(spearmanr(R[v] if v != 'rule' else R.n_act, R.extra_true_ha).correlation), 3) for v in ['rule', 'mean', 'q50', 'q70']}
res['median_ha'] = {v: round(float((R[v] if v != 'rule' else R.n_act * MED).median()), 1) for v in ['rule', 'mean', 'q50', 'q70', 'q90']} | {'true': round(float(R.extra_true_ha.median()), 1)}
json.dump(res, open('/tmp/claude-0/unseen/area_model.json', 'w'), indent=1); print(json.dumps(res, indent=1))
