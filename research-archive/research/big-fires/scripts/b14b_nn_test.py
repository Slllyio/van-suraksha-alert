"""Part 2 of b14: models on the widened tables. Neural net vs trees vs logistic vs rules, season held out.
Out: results/ml/all_fires_nn.json, figures/5_all_fires_nn.png"""
import json, warnings
import numpy as np, pandas as pd, lightgbm as lgb
from scipy.stats import spearmanr
from sklearn.neural_network import MLPClassifier, MLPRegressor
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import make_pipeline
from sklearn.exceptions import ConvergenceWarning
import matplotlib; matplotlib.use('Agg'); import matplotlib.pyplot as plt
warnings.filterwarnings('ignore', category=ConvergenceWarning)
D = '/mnt/project-files/research/big-fires/results/ml'; FG = '/mnt/project-files/research/big-fires/figures'; rng = np.random.default_rng(0)
SE = pd.read_csv(f'{D}/all_fires_sectors.csv'); SP = pd.read_csv(f'{D}/all_fires_speed.csv'); out = {}
P = dict(n_estimators=300, learning_rate=0.03, num_leaves=6, min_child_samples=25, subsample=0.8, subsample_freq=1, colsample_bytree=0.8, reg_lambda=5, verbose=-1)
def mlp_c(): return make_pipeline(StandardScaler(), MLPClassifier(hidden_layer_sizes=(32, 32), alpha=1e-2, early_stopping=True, max_iter=300, random_state=0))
def mlp_r(): return make_pipeline(StandardScaler(), MLPRegressor(hidden_layer_sizes=(32, 32), alpha=1e-2, early_stopping=True, max_iter=500, random_state=0))
def logit(): return make_pipeline(StandardScaler(), LogisticRegression(C=0.3, max_iter=500))

# ================= DIRECTION =================
SE = SE[SE.groupby(['fire', 'k']).target_main.transform('sum') == 1].copy(); SE['gid'] = SE.fire.astype(str) + '_' + SE.k.astype(str)
REL = ['elev_diff', 'slope', 'canopy', 'teak', 'litter_v3', 'grass_v3', 'burn_prior', 'wc_tree', 'wc_open', 'wc_nonfuel', 'burned_this_season_before', 'own_fire_already', 'd_building', 'd_road']
for c in REL: SE[f'{c}_rel'] = SE[c] - SE.groupby('gid')[c].transform('mean')
SE['cos_prev0'] = SE.cos_prev.fillna(0); SE['has_prev'] = SE.cos_prev.notna().astype(int); SE['cos_first0'] = SE.cos_from_first.fillna(0)
SE['cos_wind0'] = SE.cos_wind.fillna(0); SE['wind_x_cos'] = SE.cos_wind0 * SE.wind_ms.fillna(0); SE['night_x_prev'] = SE.night * SE.cos_prev0
SE['cos_upslope'] = SE.cos_upslope.fillna(0)
HIST = ['cos_prev0', 'has_prev', 'cos_first0']
GROUND = [f'{c}_rel' for c in REL] + ['cos_upslope', 'cos_wind0', 'wind_x_cos', 'night', 'gap_h', 'night_x_prev']
ALL = HIST + GROUND
def topk(score, df):
    df = df.assign(_s=score); rank = df.groupby('gid')._s.rank(ascending=False, method='first')
    best = df.loc[rank == 1].set_index('gid').sector; tru = df.loc[df.target_main == 1].set_index('gid').sector
    dd = (best - tru.reindex(best.index)) % 8
    return round(float((dd == 0).mean()), 3), round(float(dd.isin([0, 1, 7]).mean()), 3)
def loso(cols, make, df):
    pr = np.full(len(df), np.nan); X = df[cols].fillna(0)
    for s in df.season.unique():
        tr, te = (df.season != s).values, (df.season == s).values
        m = make().fit(X[tr], df.target_main[tr]); pr[te] = m.predict_proba(X[te])[:, 1]
    return pr
gbm = lambda: lgb.LGBMClassifier(**P)
dres = {'random': dict(top1=0.125, within_1=0.375)}
for nm, s in [('keep going the same way', SE.cos_prev0), ('away from the first detection', SE.cos_first0), ('uphill', SE.cos_upslope), ('downwind', SE.cos_wind0)]:
    t1, w1 = topk(s.values + rng.normal(0, 1e-6, len(SE)), SE); dres[nm] = dict(top1=t1, within_1=w1)
preds = {}
for nm, cols, mk in [('history only, logistic', HIST, logit), ('ground only (terrain/fuel/people/wind), trees', GROUND, gbm), ('everything, logistic', ALL, logit),
                     ('everything, trees', ALL, gbm), ('everything, neural net (2x32)', ALL, mlp_c), ('ground only, neural net', GROUND, mlp_c)]:
    preds[nm] = loso(cols, mk, SE); t1, w1 = topk(preds[nm], SE); dres[nm] = dict(top1=t1, within_1=w1)
# subsets of the same held-out predictions
subs = {}
for nm, mask in [('big fires (old set)', SE.big == 1), ('small fires (not big)', SE.big == 0), ('steps seen by VIIRS', SE.sensor.isin(['S-NPP', 'NOAA-20', 'NOAA-21'])),
                 ('steps seen by MODIS', SE.sensor.str.contains('MODIS')), ('steps seen by Sentinel-2/Landsat', SE.sensor.isin(['Sentinel-2', 'Landsat'])),
                 ('gap under 3 h', SE.gap_h < 3), ('gap 3-18 h', (SE.gap_h >= 3) & (SE.gap_h < 18)), ('gap 18 h or more', SE.gap_h >= 18), ('seasons 2025-26', SE.season >= 2025)]:
    sub = SE[mask]; row = dict(steps=int(sub.gid.nunique()))
    for mn in ['everything, trees', 'everything, neural net (2x32)']:
        row[mn] = topk(preds[mn][mask.values], sub)[0]
    row['keep going the same way'] = topk(sub.cos_prev0.values + rng.normal(0, 1e-6, len(sub)), sub)[0]
    subs[nm] = row
# calibration of the neural net and the trees
cal = {}
for mn in ['everything, trees', 'everything, neural net (2x32)']:
    df = SE.assign(_p=preds[mn]); df['_pn'] = df._p / df.groupby('gid')._p.transform('sum'); top = df.loc[df.groupby('gid')._pn.idxmax()]
    top['bin'] = pd.cut(top._pn, [0, .15, .2, .25, .3, .4, 1]); cal[mn] = top.groupby('bin', observed=True).agg(n=('target_main', 'size'), predicted=('_pn', 'mean'), right=('target_main', 'mean')).round(3).reset_index().astype(str).to_dict('records')
# learning curve: does more data help? train on a random share of fires (other seasons), test season out
curve = {}
fires = SE.fire.unique()
for share in [0.1, 0.25, 0.5, 1.0]:
    keep = set(rng.choice(fires, int(len(fires) * share), replace=False)); r = {}
    for mn, mk in [('trees', gbm), ('neural net', mlp_c)]:
        pr = np.full(len(SE), np.nan); X = SE[ALL].fillna(0)
        for s in SE.season.unique():
            tr = ((SE.season != s) & SE.fire.isin(keep)).values; te = (SE.season == s).values
            m = mk().fit(X[tr], SE.target_main[tr]); pr[te] = m.predict_proba(X[te])[:, 1]
        r[mn] = topk(pr, SE)[0]
    curve[f'{int(share*100)}% of fires'] = r
lm = logit().fit(SE[ALL].fillna(0), SE.target_main)
coef = dict(sorted({c: round(v, 3) for c, v in zip(ALL, lm[-1].coef_[0])}.items(), key=lambda kv: -abs(kv[1])))
out['direction'] = dict(n_steps=int(SE.gid.nunique()), n_fires=int(SE.fire.nunique()), results=dres, subsets=subs, calibration=cal, learning_curve=curve, logistic_coefficients_standardised=coef)
print(json.dumps(out['direction'], indent=1))

# ================= SPEED =================
d = SP[(SP.ci_width < 150)].copy(); d['y'] = np.log(np.clip(d.speed_m_per_h, 3, 300)); d['w'] = 1 / np.clip(d.ci_width, 10, 150)
XS = {'terrain': ['elev', 'slope', 'relief'], 'fuel/canopy/history': ['canopy', 'teak', 'litter_v3', 'grass_v3', 'burn_prior', 'wc_tree'],
      'weather/date': ['wx_tmax_c', 'wx_rh', 'wx_wind_ms', 'wx_soil_water', 'wx_rain7_mm', 'wx_rain30_mm', 'doy'], 'people': ['d_building', 'd_road'],
      'fire so far': ['n_det', 'n_passes', 'n_sensors', 'frp_sum', 'night_share']}
ALLS = sum(XS.values(), [])
def loso_r(cols, mk, dd):
    pr = np.full(len(dd), np.nan); X = dd[cols].fillna(dd[cols].median())
    for s in dd.season.unique():
        tr, te = (dd.season != s).values, (dd.season == s).values
        if mk is mlp_r: m = mk().fit(X[tr], dd.y[tr])
        else: m = lgb.LGBMRegressor(**P).fit(X[tr], dd.y[tr], sample_weight=dd.w[tr])
        pr[te] = m.predict(X[te])
    return pr
base = np.array([np.average(d.loc[d.season != s, 'y'], weights=d.loc[d.season != s, 'w']) for s in d.season])
sc = lambda pr: float(np.average(np.abs(d.y - pr), weights=d.w)); e0 = sc(base)
sres = {'baseline: same speed for every fire': dict(error=round(e0, 3))}
for nm, cols in list(XS.items()) + [('all columns', ALLS)]:
    pr = loso_r(cols, 'gbm', d); sres[f'{nm}, trees'] = dict(error=round(sc(pr), 3), better_pct=round(100 * (1 - sc(pr) / e0), 1), spearman=round(spearmanr(pr, d.y)[0], 3))
pr = loso_r(ALLS, mlp_r, d); sres['all columns, neural net (2x32)'] = dict(error=round(sc(pr), 3), better_pct=round(100 * (1 - sc(pr) / e0), 1), spearman=round(spearmanr(pr, d.y)[0], 3))
single = {c: round(spearmanr(d[c], d.y, nan_policy='omit')[0], 3) for c in ALLS}
out['speed'] = dict(n_fires=len(d), n_big=int(d.big.sum()), median_speed_m_per_h=round(float(d.speed_m_per_h.median()), 1), median_speed_big=round(float(d[d.big == 1].speed_m_per_h.median()), 1),
                    median_speed_small=round(float(d[d.big == 0].speed_m_per_h.median()), 1), results=sres, single_column_spearman_top=dict(sorted(single.items(), key=lambda kv: -abs(kv[1]))[:10]))
print(json.dumps(out['speed'], indent=1))
json.dump(out, open(f'{D}/all_fires_nn.json', 'w'), indent=1)

fig, axs = plt.subplots(1, 3, figsize=(17, 5))
ax = axs[0]; names = list(dres.keys()); vals = [dres[k]['top1'] * 100 for k in names]
ax.barh(names, vals, color=['0.5'] * 5 + ['C1'] * (len(names) - 5)); ax.axvline(12.5, color='k', ls=':'); ax.set_xlabel('right sector out of 8, % (random 12.5)')
ax.set_title(f'Direction, all fires with 3+ passes ({SE.gid.nunique()} steps, {SE.fire.nunique()} fires)'); ax.tick_params(labelsize=8)
ax = axs[1]; names = list(curve.keys())
ax.plot(names, [curve[k]['trees'] * 100 for k in names], 'o-', label='trees'); ax.plot(names, [curve[k]['neural net'] * 100 for k in names], 's-', label='neural net')
ax.axhline(dres['keep going the same way']['top1'] * 100, color='0.5', ls='--', label='keep going the same way'); ax.axhline(12.5, color='k', ls=':', label='random')
ax.set_ylabel('right sector, %'); ax.set_title('Does more data help? (share of fires used to train)'); ax.legend(fontsize=8)
ax = axs[2]; names = list(sres.keys()); vals = [sres[k].get('better_pct', 0) for k in names]
ax.barh(names, vals, color=['0.5'] + ['C0'] * (len(names) - 2) + ['C2']); ax.axvline(0, color='k'); ax.set_xlabel('% better than "same speed for every fire"')
ax.set_title(f'Speed ({len(d)} fires)'); ax.tick_params(labelsize=8)
plt.tight_layout(); plt.savefig(f'{FG}/5_all_fires_nn.png', dpi=110); plt.close()
