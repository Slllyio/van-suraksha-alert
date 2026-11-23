"""Pattern detection with ML on the spread tables (Akkshay 20:41Z "detect pattern and apply ml, think deeply").

Design.
  Targets that are as clean as the data allows: the fire's front speed fitted through all passes (b12), weighted by how
  sure the fit is; and, for direction, which of 8 sectors the next new burning falls in (sectors_ml).
  Honest testing: every model is trained without the season it is scored on (8-10 seasons). Baselines: "same speed for
  all fires" and "keep going the same way". Small gradient-boosted trees (shallow, few leaves) and, as a readable
  cross-check, a logistic model for direction. Pattern read-out: permutation importance (how much the held-out score
  drops when a column is scrambled) and one-way partial effects (how the prediction moves along one column).
Out: results/ml/patterns.json, figures/4_ml_patterns.png
"""
import json
import numpy as np, pandas as pd, lightgbm as lgb
from scipy.stats import spearmanr
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import make_pipeline
import matplotlib; matplotlib.use('Agg'); import matplotlib.pyplot as plt
D = '/mnt/project-files/research/big-fires/results/ml'; FG = '/mnt/project-files/research/big-fires/figures'
FR = pd.read_csv(f'{D}/fires_ml.csv'); SE = pd.read_csv(f'{D}/sectors_ml.csv'); rng = np.random.default_rng(0)
P = dict(n_estimators=300, learning_rate=0.03, num_leaves=6, min_child_samples=25, subsample=0.8, subsample_freq=1, colsample_bytree=0.8, reg_lambda=5, verbose=-1)
out = {}

# ================= 1. SPEED =================
d = FR.dropna(subset=['front_all_speed_m_per_h']).copy()
d = d[(d.front_all_ci_width < 150)]            # fits that actually pin the speed (median CI width 38 on big fires)
d['y'] = np.log(np.clip(d.front_all_speed_m_per_h, 3, 300))
d['w'] = 1 / np.clip(d.front_all_ci_width, 10, 150)
X_SPEED = {'terrain': ['elev_mean', 'elev_relief', 'slope_mean', 'slope_share_gt5', 'slope_first'],
           'fuel/canopy/history': ['canopy_mean', 'teak_mean', 'litter_v3_mean', 'grass_v3_mean', 'burn_prior_mean', 'wc_tree', 'wc_shrub', 'wc_grass'],
           'weather/date': ['wx_tmax_c', 'wx_rh', 'wx_wind_ms', 'wx_soil_water', 'wx_rain7_mm', 'wx_rain30_mm', 'doy_start'],
           'people/access': ['d_building_first_m', 'hamlets_4km_first', 'd_road_first_m', 'depth_in_forest_first_m'],
           'first-look alerts': ['first_frp_sum', 'first_frp_max', 'first_ti4_mean', 'first_ti4_minus_ti5', 'first_n_det', 'first_look_night', 'first_look_hour_ist'],
           'fire so far (size/detections)': ['n_det_viirs', 'n_looks', 'all_frp_sum', 'all_frp_max', 'night_det_share']}
ALL = sum(X_SPEED.values(), [])
def loso_reg(cols, dd):
    pr = np.full(len(dd), np.nan)
    for s in dd.season.unique():
        tr, te = (dd.season != s).values, (dd.season == s).values
        m = lgb.LGBMRegressor(**P).fit(dd.loc[tr, cols], dd.loc[tr, 'y'], sample_weight=dd.loc[tr, 'w']); pr[te] = m.predict(dd.loc[te, cols])
    return pr
base = np.array([np.average(d.loc[d.season != s, 'y'], weights=d.loc[d.season != s, 'w']) for s in d.season])
def score(pr, dd):
    e = np.average(np.abs(dd.y - pr), weights=dd.w); return e
e0 = score(base, d)
res = {'baseline: same speed for every fire': dict(weighted_abs_log_error=round(e0, 3))}
for name, cols in list(X_SPEED.items()) + [('all columns', ALL)]:
    pr = loso_reg(cols, d); e = score(pr, d)
    res[name] = dict(weighted_abs_log_error=round(e, 3), better_than_baseline_pct=round(100 * (1 - e / e0), 1), spearman=round(spearmanr(pr, d.y)[0], 3))
# permutation importance of the all-columns model (held-out, LOSO)
pr_all = loso_reg(ALL, d); e_all = score(pr_all, d); imp = {}
for c in ALL:
    dd = d.copy(); dd[c] = rng.permutation(dd[c].values); imp[c] = round(score(loso_reg(ALL, dd), d) - e_all, 4)
imp = dict(sorted(imp.items(), key=lambda kv: -kv[1]))
single = {c: round(spearmanr(d[c], d.y, nan_policy='omit')[0], 3) for c in ALL}
out['speed'] = dict(n_fires=len(d), n_big=int(d.big.sum()), target='log front speed (all passes fit), weighted by 1/CI width', results=res,
                    permutation_importance_top=dict(list(imp.items())[:10]), single_column_spearman_top=dict(sorted(single.items(), key=lambda kv: -abs(kv[1]))[:10]))
print('SPEED', json.dumps(out['speed'], indent=1))

# ================= 2. DIRECTION =================
SE = SE[SE.groupby(['fire', 'k']).target_main.transform('sum') == 1].copy(); SE['gid'] = SE.fire.astype(str) + '_' + SE.k.astype(str)
# within-step relative columns: a sector matters compared with the other 7 of the same step
REL = ['elev_diff', 'slope', 'canopy', 'teak', 'litter_v3', 'grass_v3', 'burn_prior', 'wc_tree', 'wc_open', 'wc_nonfuel', 'burned_this_season_before', 'own_fire_already', 'd_building', 'd_road']
for c in REL: SE[f'{c}_rel'] = SE[c] - SE.groupby('gid')[c].transform('mean')
SE['cos_prev0'] = SE.cos_prev.fillna(0); SE['has_prev'] = SE.cos_prev.notna().astype(int); SE['cos_first0'] = SE.cos_from_first.fillna(0)
SE['cos_wind0'] = SE.cos_wind.fillna(0); SE['wind_x_cos'] = SE.cos_wind0 * SE.wind_ms.fillna(0)
SE['night_x_prev'] = SE.night * SE.cos_prev0
X_DIR = {'history (same way, away from start)': ['cos_prev0', 'has_prev', 'cos_first0'],
         'terrain': ['elev_diff_rel', 'slope_rel', 'cos_upslope'],
         'fuel/canopy': ['canopy_rel', 'teak_rel', 'litter_v3_rel', 'grass_v3_rel', 'wc_tree_rel', 'wc_open_rel', 'wc_nonfuel_rel'],
         'already burnt (this season, own fire)': ['burned_this_season_before_rel', 'own_fire_already_rel', 'burn_prior_rel'],
         'people': ['d_building_rel', 'd_road_rel'], 'wind': ['cos_wind0', 'wind_x_cos'], 'timing': ['night', 'gap_h', 'night_x_prev']}
ALLD = sum(X_DIR.values(), [])
def topk(score):
    SE['_s'] = score; rank = SE.groupby('gid')._s.rank(ascending=False, method='first')
    best = SE.loc[rank == 1].set_index('gid').sector; tru = SE.loc[SE.target_main == 1].set_index('gid').sector
    dd_ = (best - tru.reindex(best.index)) % 8
    return round(float((dd_ == 0).mean()), 3), round(float(dd_.isin([0, 1, 7]).mean()), 3)
def loso_cls(cols, model='gbm', sub=None):
    pr = np.full(len(SE), np.nan)
    for s in SE.season.unique():
        tr, te = (SE.season != s).values, (SE.season == s).values
        if model == 'gbm': m = lgb.LGBMClassifier(**P).fit(SE.loc[tr, cols], SE.loc[tr, 'target_main'])
        else: m = make_pipeline(StandardScaler(), LogisticRegression(C=0.3, max_iter=500)).fit(SE.loc[tr, cols].fillna(0), SE.loc[tr, 'target_main'])
        pr[te] = m.predict_proba(SE.loc[te, cols].fillna(0) if model != 'gbm' else SE.loc[te, cols])[:, 1]
    return pr
dres = {'random': dict(top1=0.125, within_1_sector=0.375)}
for nm, s in [('keep going the same way', SE.cos_prev0 + rng.normal(0, 1e-6, len(SE))), ('away from the first detection', SE.cos_first0 + rng.normal(0, 1e-6, len(SE)))]:
    t1, w1 = topk(s.values); dres[nm] = dict(top1=t1, within_1_sector=w1)
for name, cols in list(X_DIR.items()) + [('everything but history', [c for c in ALLD if c not in X_DIR['history (same way, away from start)']]), ('everything (trees)', ALLD)]:
    t1, w1 = topk(loso_cls(cols)); dres[name] = dict(top1=t1, within_1_sector=w1)
pr_log = loso_cls(ALLD, 'logit'); t1, w1 = topk(pr_log); dres['everything (logistic, readable)'] = dict(top1=t1, within_1_sector=w1)
pr_dir = loso_cls(ALLD); SE['_p'] = pr_dir
# big fires only, and 2025-26 forward
for nm, mask in [('everything (trees), big fires only', SE.big == 1), ('everything (trees), seasons 2025-26 only', SE.season >= 2025)]:
    sub = SE[mask].copy(); SEfull = SE; SE = sub; t1, w1 = topk(sub._p.values); dres[nm] = dict(top1=t1, within_1_sector=w1, steps=int(sub.gid.nunique())); SE = SEfull
# calibration: predicted share of the chosen sector vs how often it is right
SE['_pn'] = SE._p / SE.groupby('gid')._p.transform('sum'); top = SE.loc[SE.groupby('gid')._pn.idxmax()]
top['bin'] = pd.cut(top._pn, [0, .2, .3, .4, .6, 1]); cal = top.groupby('bin', observed=True).agg(n=('target_main', 'size'), predicted=('_pn', 'mean'), right=('target_main', 'mean')).round(3)
# permutation importance (drop in top-1 when a column is scrambled within the test)
base_t1 = dres['everything (trees)']['top1']; dimp = {}
for c in ALLD:
    sv = SE[c].copy(); SE[c] = rng.permutation(SE[c].values); dimp[c] = round(base_t1 - topk(loso_cls(ALLD))[0], 3); SE[c] = sv
dimp = dict(sorted(dimp.items(), key=lambda kv: -kv[1]))
# readable coefficients from the logistic model on all data (standardised)
lm = make_pipeline(StandardScaler(), LogisticRegression(C=0.3, max_iter=500)).fit(SE[ALLD].fillna(0), SE.target_main)
coef = dict(sorted({c: round(v, 3) for c, v in zip(ALLD, lm[-1].coef_[0])}.items(), key=lambda kv: -abs(kv[1])))
# simple rule check: chosen sector is the highest / most canopy / least burnt among 8?
rules = {}
for nm, col, hi in [('went to the highest ground', 'elev_diff', True), ('went to the most canopy', 'canopy', True), ('went to the least already-burnt this season', 'burned_this_season_before', False), ('went to ground burnt most often in earlier seasons', 'burn_prior', True),
                    ('went to the farthest from buildings', 'd_building', True), ('went to the most litter (v3)', 'litter_v3', True), ('went downwind-most', 'cos_wind0', True)]:
    r = SE.groupby('gid')[col].rank(ascending=not hi, method='average'); rules[nm] = dict(mean_rank_of_chosen_sector_1best_8worst=round(float(r[SE.target_main == 1].mean()), 2), random=4.5)
out['direction'] = dict(n_steps=int(SE.gid.nunique()), results=dres, calibration=cal.reset_index().astype(str).to_dict('records'), permutation_importance=dimp,
                        logistic_coefficients_standardised=coef, rank_rules=rules)
print('DIRECTION', json.dumps(out['direction'], indent=1))
json.dump(out, open(f'{D}/patterns.json', 'w'), indent=1)

# ---- figure
fig, axs = plt.subplots(1, 3, figsize=(17, 5))
ax = axs[0]; names = list(res.keys()); vals = [res[k].get('better_than_baseline_pct', 0) for k in names]
ax.barh(names, vals, color=['0.5'] + ['C0'] * (len(names) - 1)); ax.axvline(0, color='k'); ax.set_xlabel('% better than "same speed for every fire" (held-out seasons)')
ax.set_title(f'Speed: what predicts it? ({len(d)} fires)'); ax.tick_params(labelsize=8)
ax = axs[1]; names = [k for k in dres if 'only' not in k]; vals = [dres[k]['top1'] * 100 for k in names]
ax.barh(names, vals, color=['0.5', '0.5', '0.5'] + ['C1'] * (len(names) - 3)); ax.axvline(12.5, color='k', ls=':'); ax.set_xlabel('right sector out of 8, % (random 12.5)')
ax.set_title(f'Direction: which columns help? ({SE.gid.nunique()} steps)'); ax.tick_params(labelsize=8)
ax = axs[2]; items = list(coef.items())[:12]
ax.barh([k for k, _ in items][::-1], [v for _, v in items][::-1], color=['C2' if v > 0 else 'C3' for _, v in items][::-1]); ax.axvline(0, color='k')
ax.set_xlabel('effect on "fire goes this way" (standardised logistic weight)'); ax.set_title('Direction: the pattern, in one readable model'); ax.tick_params(labelsize=8)
plt.tight_layout(); plt.savefig(f'{FG}/4_ml_patterns.png', dpi=110); plt.close()
