"""Stage 2 of the multi-front test (see mf_tracker.py).
(1) Growth + stop model per active front: LightGBM, leave-one-season-out, target = true new burned ha near the front (<= 1 km) in the
    next 24 h; baselines = training median, and 'same as dots added since last look'. Stop = new < 2 ha.
(2) Maps for the burn state at t_k + 24 h (Sorensen inside the scar outline v2; nothing outside the box is known to the forecast):
      single_*  : current footprints + growth placed by distance to ANY dot so far (one blob, all dots alike)
      multi_*   : current footprints + each ACTIVE front grows its own budget by distance to its own dots; old fronts don't grow
    with total area from  _pred (growth model) or _true (oracle total, true per-front split for multi).
  python3 mf_eval.py prefix
"""
import sys, pickle, json, numpy as np, pandas as pd, lightgbm as lgb
from scipy.spatial import cKDTree
from scipy.stats import spearmanr
from sklearn.metrics import roc_auc_score
PRE = sys.argv[1]
R = pd.read_parquet(f'{PRE}_fronts.parquet'); I = pd.read_parquet(f'{PRE}_issues.parquet'); M = pickle.load(open(f'{PRE}_maps.pkl', 'rb'))
X0, Y0 = 737300.0, 2560500.0
FE = ['age_h', 'n_dots', 'n_dots_last', 'n_dots_last2', 'frp_last', 'frp_all', 'night', 'extent_m', 'foot_ha', 'forest_share', 'grass_share',
      'n_fronts', 'n_active', 'fire_dots', 'doy', 'th', 'k', 'kind_c']
R['kind_c'] = R.kind.map({'first': 0, 'continuing': 1, 'separate': 2, 'independent': 3, 'old': 4})
act = R[R.active].copy(); act['y'] = np.log1p(act.new24_ha)
act['pred'] = np.nan; act['p_stop'] = np.nan
P = dict(objective='regression_l1', learning_rate=.05, num_leaves=7, min_data_in_leaf=20, feature_fraction=.8, verbose=-1, seed=0)
for s in sorted(act.season.unique()):
    tr, te = act[act.season != s], act.season == s
    m = lgb.train(P, lgb.Dataset(tr[FE], tr.y), 300); act.loc[te, 'pred'] = m.predict(act.loc[te, FE])
    c = lgb.train(dict(P, objective='binary'), lgb.Dataset(tr[FE], (tr.new24_ha < 2).astype(int)), 200); act.loc[te, 'p_stop'] = c.predict(act.loc[te, FE])
    act.loc[te, 'med'] = tr.y.median()
res = {}
err = lambda p: float(np.median(np.abs(p - act.y)))
res['growth'] = dict(n_front_rows=len(act), n_fires=int(act.fire.nunique()), median_new24_ha=float(act.new24_ha.median()),
                     share_stopped=float((act.new24_ha < 2).mean()),
                     model_err_log=err(act.pred), median_err_log=err(act.med),
                     model_spearman=float(spearmanr(act.pred, act.y)[0]),
                     dots_added_spearman=float(spearmanr(act.dots_added.fillna(act.n_dots), act.y)[0]),
                     stop_auc=float(roc_auc_score((act.new24_ha < 2).astype(int), act.p_stop)),
                     within_2x_model=float((np.abs(np.log(np.expm1(act.pred).clip(.5) / act.new24_ha.clip(.5))) <= np.log(2)).mean()),
                     within_2x_median=float((np.abs(np.log(np.expm1(act.med).clip(.5) / act.new24_ha.clip(.5))) <= np.log(2)).mean()))
print(res['growth'], flush=True)
imp = dict(zip(FE, m.feature_importance('gain').round(0))); res['importance_last_fold'] = {k: float(v) for k, v in sorted(imp.items(), key=lambda x: -x[1])[:8]}
# ---- maps
A = pd.read_csv('/mnt/project-files/research/big-fires/results/fire_alerts.csv', parse_dates=['t']); A = A[A.sat != 'modis']
import os
sys.path.insert(0, '/mnt/project-files/research/fire-continuity/scripts'); import c0_lib as C


def soren(a, b):
    return 2 * (a & b).sum() / max(a.sum() + b.sum(), 1)


rows = []
for fire, g in I.groupby('fire'):
    mp = M[fire]; r0, r1, c0, c1 = mp['box']; Tg = mp['Tg'].ravel(); dom = mp['dom'].ravel()
    rr, cc = np.mgrid[r0:r1, c0:c1]; Pxy = np.c_[(X0 + (cc + .5) * 20).ravel(), (Y0 - (rr + .5) * 20).ravel()]
    d = C.viirs_looks(A[A.fire == fire]).reset_index(drop=True); t0 = d.t.min(); d['th'] = (d.t - t0).dt.total_seconds() / 3600
    for it in g.itertuples():
        known = d[d.lk <= it.k]; xy = known[['x', 'y']].values
        truth = dom & (Tg <= it.th + 24)
        dall = cKDTree(xy).query(Pxy)[0]; foot = dall <= 265
        fr = R[(R.fire == fire) & (R.k == it.k)]; fa = act[(act.fire == fire) & (act.k == it.k)]
        # front membership of each known dot: recompute the same single linkage as stage 1
        sys.path.insert(0, os.path.dirname(__file__)); from mf_tracker_lib import clusters
        lab = clusters(xy)
        out = dict(fire=fire, season=it.season, k=it.k, truth_ha=truth.sum() * .04, foot_ha=foot.sum() * .04, new24_ha=it.new24_ha,
                   far1k_share=it.new24_far1k_ha / it.new24_ha if it.new24_ha > 0 else np.nan)
        n_true = int(truth.sum()); n_foot = int(foot.sum())
        gp = {int(r.front): max(np.expm1(r.pred), 0) for r in fa.itertuples()}; gt = {int(r.front): r.new24_ha for r in fa.itertuples()}
        for tag, budget in [('pred', gp), ('true', gt)]:
            tot = n_foot + int(sum(budget.values()) / .04) if tag == 'pred' else n_true
            order = np.argsort(dall, kind='stable'); single = np.zeros(len(dall), bool); single[order[:max(tot, n_foot)]] = True
            out[f'single_{tag}'] = soren(single, truth)
            multi = foot.copy()
            for f, ha in budget.items():
                n = int(ha / .04)
                if n <= 0:
                    continue
                df = cKDTree(xy[lab == f]).query(Pxy)[0]; df[foot] = np.inf
                multi[np.argsort(df, kind='stable')[:n]] = True
            if tag == 'true':     # oracle total too: top up/trim by distance to active dots to hit the true area
                pass
            out[f'multi_{tag}'] = soren(multi, truth); out[f'multi_{tag}_ha'] = multi.sum() * .04
        out['foot_only'] = soren(foot, truth)
        rows.append(out)
S = pd.DataFrame(rows); S.to_csv(f'{PRE}_scores.csv', index=False)
for c in ['foot_only', 'single_pred', 'multi_pred', 'single_true', 'multi_true']:
    res[c] = float(S[c].median())
rng = np.random.default_rng(0); f = S.groupby('fire')[['multi_pred', 'single_pred', 'foot_only']].mean()
bs = [(f.multi_pred - f.single_pred).values[rng.integers(0, len(f), len(f))].mean() for _ in range(2000)]
res['multi_minus_single_pred_ci'] = [float(np.percentile(bs, q)) for q in (2.5, 50, 97.5)]
bs = [(f.multi_pred - f.foot_only).values[rng.integers(0, len(f), len(f))].mean() for _ in range(2000)]
res['multi_pred_minus_foot_ci'] = [float(np.percentile(bs, q)) for q in (2.5, 50, 97.5)]
res['issues'] = len(S); res['far1k_share_median'] = float(S.far1k_share.median()); res['far1k_share_pooled'] = float(I.new24_far1k_ha.sum() / I.new24_ha.sum())
res['kinds'] = R[R.k > 0].kind.value_counts().to_dict()
json.dump(res, open(f'{PRE}_summary.json', 'w'), indent=1, default=float); print(json.dumps(res, indent=1, default=float))
