"""Calibrated chance that a fire VIIRS has stopped seeing is still burning.

Truth: every Sentinel-2 / Landsat scene (cloud < 30%) over a fire between its first VIIRS dot and 72 h after its
last one, taken when the latest VIIRS pass before the scene did NOT see the fire ('dark'). Burning = a 30 m hot
pixel within 1 km of the fire's dots so far. Inputs use only what was known before the scene (no future dots).
Held out by season (train on the other seasons). -> results/still_burning.json, results/still_burning_rows.csv
"""
import json, numpy as np, pandas as pd, lightgbm as lgb
from scipy.spatial import cKDTree
from sklearn.metrics import roc_auc_score, brier_score_loss
from sklearn.linear_model import LogisticRegression
from pyproj import Transformer

ROOT = '/mnt/project-files'
OUT = f'{ROOT}/research/fire-continuity'
R = f'{ROOT}/ratapani/fsi/scouting/code/squares_v2/tracking/results/'

S = pd.read_csv(R + 'mask_fire_pass_summary.csv', parse_dates=['t_pass']).sort_values(['fire', 't_pass']).reset_index(drop=True)
S['pid'] = np.arange(len(S))
A = pd.read_csv(f'{ROOT}/research/big-fires/results/fire_alerts.csv', parse_dates=['t'])
A = A[A.sat.str.startswith('viirs') & A.fire.isin(S.fire.unique())].copy()
A['sensor'] = A.sat.map({'viirs-snpp': 'S-NPP', 'viirs-jpss1': 'NOAA-20', 'viirs-noaa21': 'NOAA-21'})
M = A.merge(S[['fire', 'sensor', 't_pass', 'pid']], on=['fire', 'sensor'])
M = M[(M.t >= M.t_pass - pd.Timedelta('1min')) & (M.t <= M.t_pass + pd.Timedelta('7min'))]
M = M.sort_values('t').drop_duplicates(['latitude', 'longitude', 't'])
S['n_alert'] = S.pid.map(M.groupby('pid').size()).fillna(0).astype(int)
S['frp_max'] = S.pid.map(M.groupby('pid').frp.max())
S['day'] = (S.t_pass.dt.hour + S.t_pass.dt.minute / 60).between(4, 12)
nf = S.n_front.clip(lower=1)
S['clear'] = (S.n_alert == 0) & (S.n_front > 0) & (S.n_clear / nf >= 0.8)
S['blind'] = (S.n_alert == 0) & ((S.n_front == 0) | ((S.n_cloud + S.n_noinfo + S.n_missing) / nf >= 0.5))

SC = pd.read_csv(f'{OUT}/results/s2ls_scenes.csv')
SC['t'] = pd.to_datetime(SC.t, utc=True, format='mixed').dt.tz_localize(None)
SC = SC[SC.cloud < 30].copy()
bb = np.array([json.loads(b) for b in SC.bbox])
SC['lon0'], SC['lat0'], SC['lon1'], SC['lat1'] = bb.T
AF = pd.read_csv(f'{ROOT}/fire-alert-scars/out/af/af_pixels_clean.csv')
AF['x'], AF['y'] = Transformer.from_crs(4326, 32643, always_xy=True).transform(AF.lon.values, AF.lat.values)
AFt = {s: cKDTree(g[['x', 'y']].values) for s, g in AF.groupby('scene')}

rows = []
for fire, fa in M.groupby('fire'):
    fp = S[S.fire == fire]
    lo, la = fa.longitude.mean(), fa.latitude.mean()
    t_first, t_last = fa.t.min(), fa.t.max()
    sc = SC[(SC.t > t_first) & (SC.t < t_last + pd.Timedelta('72h')) & (SC.lon0 < lo) & (SC.lon1 > lo) & (SC.lat0 < la) & (SC.lat1 > la)]
    for s in sc.itertuples():
        before = fp[fp.t_pass < s.t]
        seen = before[before.n_alert > 0]
        if len(seen) == 0 or before.n_alert.values[-1] > 0:
            continue                                   # not dark: the latest pass saw it
        last = seen.iloc[-1]
        miss = before[before.t_pass > last.t_pass]
        dots = fa[fa.t < s.t]
        d24 = dots[dots.t > s.t - pd.Timedelta('24h')]
        pts = dots[['x', 'y']].values
        hot = bool(s.scene in AFt and (AFt[s.scene].query_ball_point(pts, 1000, return_length=True) > 0).any())
        rows.append(dict(fire=fire, scene=s.scene, season=s.t.year, hot=hot,
                         h_dark=(s.t - last.t_pass) / pd.Timedelta('1h'),
                         n_miss=len(miss), n_miss_clear=int(miss.clear.sum()), n_miss_blind=int(miss.blind.sum()),
                         n_miss_day_clear=int((miss.clear & miss.day).sum()),
                         miss_vza=float(miss.vza_med.mean()),
                         last_frp=float(last.frp_max), last_n=int(last.n_alert), last_day=bool(last.day),
                         dots_24h=len(d24), frp24=float(d24.frp.sum()), dots_all=len(dots),
                         age_h=(s.t - t_first) / pd.Timedelta('1h'), doy=s.t.dayofyear, cloud=s.cloud,
                         sensor=s.sensor))
D = pd.DataFrame(rows)
D.to_csv(f'{OUT}/results/still_burning_rows.csv', index=False)
print(D.shape, 'burning share', D.hot.mean().round(3), 'fires', D.fire.nunique())

FEAT = ['h_dark', 'n_miss', 'n_miss_clear', 'n_miss_blind', 'n_miss_day_clear', 'miss_vza', 'last_frp', 'last_n',
        'last_day', 'dots_24h', 'frp24', 'dots_all', 'age_h', 'doy', 'cloud']
D['last_day'] = D.last_day.astype(int)
P = {'hours_only': np.zeros(len(D)), 'logit': np.zeros(len(D)), 'gbm': np.zeros(len(D))}
for se in sorted(D.season.unique()):
    tr, te = D.season != se, D.season == se
    if te.sum() == 0:
        continue
    X = D[FEAT]
    m1 = LogisticRegression(max_iter=1000).fit(np.log1p(D.loc[tr, ['h_dark']]), D.hot[tr])
    P['hours_only'][te] = m1.predict_proba(np.log1p(D.loc[te, ['h_dark']]))[:, 1]
    Z = X.copy(); Z[['h_dark', 'last_frp', 'frp24', 'dots_24h', 'dots_all', 'age_h']] = np.log1p(Z[['h_dark', 'last_frp', 'frp24', 'dots_24h', 'dots_all', 'age_h']])
    Z = Z.fillna(Z.median())
    mu, sd = Z[tr].mean(), Z[tr].std() + 1e-9
    m2 = LogisticRegression(max_iter=2000, C=0.3).fit((Z[tr] - mu) / sd, D.hot[tr])
    P['logit'][te] = m2.predict_proba((Z[te] - mu) / sd)[:, 1]
    m3 = lgb.LGBMClassifier(n_estimators=200, learning_rate=0.03, num_leaves=7, min_child_samples=30,
                            subsample=0.8, subsample_freq=1, colsample_bytree=0.8, verbose=-1).fit(X[tr], D.hot[tr])
    P['gbm'][te] = m3.predict_proba(X[te])[:, 1]

rng = np.random.default_rng(0)
fires = D.fire.unique()
idx = {f: np.where(D.fire.values == f)[0] for f in fires}
res = dict(n_scenes=len(D), n_fires=int(D.fire.nunique()), burning_share=round(float(D.hot.mean()), 3),
           seasons=D.season.value_counts().sort_index().to_dict(), models={})
for k, p in P.items():
    bs = []
    for _ in range(500):
        ii = np.concatenate([idx[f] for f in rng.choice(fires, len(fires))])
        bs.append(roc_auc_score(D.hot.values[ii], p[ii]))
    res['models'][k] = dict(auc=round(roc_auc_score(D.hot, p), 3), lo=round(float(np.percentile(bs, 2.5)), 3),
                            hi=round(float(np.percentile(bs, 97.5)), 3), brier=round(brier_score_loss(D.hot, p), 4))
res['brier_constant'] = round(brier_score_loss(D.hot, np.full(len(D), D.hot.mean())), 4)
best = max(res['models'], key=lambda k: res['models'][k]['auc'])
D['p'] = P[best]
cal = D.groupby(pd.cut(D.p, [0, .2, .35, .5, .65, .8, 1]), observed=True).agg(n=('hot', 'size'), said=('p', 'mean'), real=('hot', 'mean')).round(3)
cal.index = cal.index.astype(str)
res['best'] = best
res['calibration'] = cal.reset_index().to_dict('records')
# plain table by hours dark x last heat
D['hb'] = pd.cut(D.h_dark, [0, 6, 12, 24, 48, 200])
D['fb'] = pd.cut(D.last_frp, [0, 3, 8, 1000], labels=['weak <3 MW', 'mid 3-8', 'strong >8'])
t = D.pivot_table(index='hb', columns='fb', values='hot', aggfunc=['mean', 'size'], observed=True).round(2)
res['table_hours_x_heat'] = {str(i): {f'{a}|{b}': v for (a, b), v in r.items()} for i, r in t.iterrows()}
t2 = D.groupby('hb', observed=True).hot.agg(['size', 'mean']).round(3)
t2.index = t2.index.astype(str)
res['by_hours_dark'] = t2.reset_index().to_dict('records')
res['by_last_day'] = D.groupby('last_day').hot.agg(['size', 'mean']).round(3).reset_index().to_dict('records')
m = lgb.LGBMClassifier(n_estimators=200, learning_rate=0.03, num_leaves=7, min_child_samples=30, verbose=-1).fit(D[FEAT], D.hot)
res['gbm_importance_gain'] = dict(sorted(zip(FEAT, m.booster_.feature_importance('gain').round(0).tolist()), key=lambda x: -x[1]))
json.dump(res, open(f'{OUT}/results/still_burning.json', 'w'), indent=1, default=str)
print(json.dumps(res, indent=1, default=str))
