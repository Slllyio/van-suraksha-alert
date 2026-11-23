"""Quick honest test on the ML tables: do terrain, fuel, weather or the alert fields predict spread rate and direction?
Every model is trained without the season it is tested on (leave one season out), and compared with a simple baseline.
Out: results/ml/ml_test.json, printed tables.
"""
import json
import numpy as np, pandas as pd, lightgbm as lgb
from scipy.stats import spearmanr
D = '/mnt/project-files/research/big-fires/results/ml'
FR = pd.read_csv(f'{D}/fires_ml.csv'); SE = pd.read_csv(f'{D}/sectors_ml.csv')
out = {}
P = dict(n_estimators=200, learning_rate=0.03, num_leaves=8, min_child_samples=20, subsample=0.8, subsample_freq=1, colsample_bytree=0.8, verbose=-1)

# ---- 1. rate (fire level)
TER = ['elev_mean', 'elev_relief', 'slope_mean', 'slope_share_gt5', 'slope_first']
FUEL = ['canopy_mean', 'teak_mean', 'litter_v3_mean', 'grass_v3_mean', 'fuel_total_v3_mean', 'burn_count_mean', 'wc_tree', 'wc_shrub', 'wc_grass', 'wc_crop']
WX = ['wx_tmax_c', 'wx_rh', 'wx_wind_ms', 'wx_soil_water', 'wx_rain7_mm', 'wx_rain30_mm', 'doy_start']
PEOPLE = ['d_building_first_m', 'hamlets_4km_first', 'd_road_first_m', 'depth_in_forest_first_m']
FIRST = ['first_frp_sum', 'first_frp_max', 'first_ti4_mean', 'first_ti4_minus_ti5', 'first_n_det', 'first_look_night', 'first_dozier_p_median']
d = FR.dropna(subset=['rate_median_m_per_h']).copy(); d['y'] = np.log(d.rate_median_m_per_h)
def loso_reg(cols):
    pr = np.full(len(d), np.nan)
    for s in d.season.unique():
        tr, te = d.season != s, d.season == s
        m = lgb.LGBMRegressor(**P).fit(d.loc[tr, cols], d.loc[tr, 'y']); pr[te.values] = m.predict(d.loc[te, cols])
    return pr
base = np.array([d.loc[d.season != s, 'y'].median() for s in d.season]); err0 = np.abs(d.y - base)
res = {'baseline (median of other seasons)': dict(mae_log=round(err0.mean(), 3))}
for name, cols in [('terrain', TER), ('fuel+canopy+burn history', FUEL), ('weather+date', WX), ('people/roads', PEOPLE),
                   ('first-look alert fields', FIRST), ('all', TER + FUEL + WX + PEOPLE + FIRST)]:
    pr = loso_reg(cols); e = np.abs(d.y - pr)
    res[name] = dict(mae_log=round(e.mean(), 3), better_than_baseline_pct=round(100 * (1 - e.mean() / err0.mean()), 1),
                     spearman_pred_vs_true=round(spearmanr(pr, d.y)[0], 3))
out['rate'] = dict(n_fires=len(d), results=res,
                   single_feature_spearman={c: round(spearmanr(d[c], d.y, nan_policy='omit')[0], 3) for c in TER + FUEL + WX + PEOPLE + FIRST})
print('RATE', json.dumps(out['rate']['results'], indent=1))
sf = pd.Series(out['rate']['single_feature_spearman']).sort_values(key=np.abs, ascending=False); print(sf.head(8))

# ---- 2. direction (step x 8 sectors): which sector gets the new burning?
SE = SE[SE.groupby(['fire', 'k']).target_main.transform('sum') == 1].copy()
SE['gid'] = SE.fire.astype(str) + '_' + SE.k.astype(str)
SEC_T = ['elev_diff', 'slope', 'cos_upslope']
SEC_F = ['canopy', 'teak', 'litter_v3', 'grass_v3', 'fuel_total_v3', 'burn_count', 'wc_tree', 'wc_open', 'wc_nonfuel']
SEC_B = ['burned_this_season_before', 'own_fire_already']
SEC_P = ['d_building', 'd_road']
SEC_W = ['cos_wind']
SEC_H = ['cos_prev', 'cos_from_first']
def topk(score):
    SE['_s'] = score
    rank = SE.groupby('gid')._s.rank(ascending=False, method='first')
    hit1 = SE[(rank == 1)].target_main.mean()
    # within one sector either side of the chosen one
    best = SE.loc[rank == 1, ['gid', 'sector']].set_index('gid').sector
    tru = SE.loc[SE.target_main == 1, ['gid', 'sector']].set_index('gid').sector
    dd = ((best - tru.reindex(best.index)) % 8); within1 = dd.isin([0, 1, 7]).mean()
    return round(hit1, 3), round(within1, 3)
def loso_cls(cols):
    pr = np.full(len(SE), np.nan)
    for s in SE.season.unique():
        tr, te = SE.season != s, SE.season == s
        m = lgb.LGBMClassifier(**P).fit(SE.loc[tr, cols], SE.loc[tr, 'target_main']); pr[te.values] = m.predict_proba(SE.loc[te, cols])[:, 1]
    return pr
rng = np.random.default_rng(0)
dres = {'random': dict(top1=0.125, within_1_sector=0.375)}
simple = {'same way as last step': SE.cos_prev.fillna(0) + rng.normal(0, 1e-6, len(SE)),
          'away from first detection': SE.cos_from_first.fillna(0) + rng.normal(0, 1e-6, len(SE)),
          'uphill': SE.elev_diff, 'downhill': -SE.elev_diff, 'most canopy': SE.canopy, 'most litter (v3)': SE.litter_v3,
          'most grass (v3)': SE.grass_v3, 'least burned already this season': -SE.burned_this_season_before.fillna(0),
          'away from own burnt ground': -SE.own_fire_already, 'downwind': SE.cos_wind.fillna(0), 'away from buildings': SE.d_building.fillna(0)}
for k, s in simple.items():
    t1, w1 = topk(s.values); dres[k] = dict(top1=t1, within_1_sector=w1)
for name, cols in [('model: terrain', SEC_T), ('model: fuel+canopy', SEC_F), ('model: terrain+fuel+burnt+people+wind', SEC_T + SEC_F + SEC_B + SEC_P + SEC_W),
                   ('model: history only (last step, from first)', SEC_H), ('model: history + everything', SEC_H + SEC_T + SEC_F + SEC_B + SEC_P + SEC_W)]:
    t1, w1 = topk(loso_cls(cols)); dres[name] = dict(top1=t1, within_1_sector=w1)
for big in [1]:
    pass
out['direction'] = dict(n_steps=int(SE.gid.nunique()), results=dres)
print('DIRECTION', json.dumps(dres, indent=1))
# big fires only, main models
sub = SE.big == 1
json.dump(out, open(f'{D}/ml_test.json', 'w'), indent=1)
