"""Why do some fronts run farther? Stage 2: how much of the difference each factor explains.
Target: log(1 + ha newly burned within 1 km of the front in the next 24 h).
1. Where the variation sits: between fires / between looks of one fire / between fronts of the same fire at the same look.
2. WITHIN the same fire and look (groups with >= 2 active fronts): weather, season and fire-wide suppression are the same for every
   front, so only local factors can explain the difference. Features and target are centred within each group. Each factor group
   is scored on seasons held out (fit on the others): share of the front-to-front difference explained (R2). Baseline: the same
   with the factor values shuffled among the fronts of each group (30 repeats; the 95% top of that range is the 'chance' bar).
   Run on all fronts and on connected fronts only (separate/independent starts removed: they are new ignitions, not spread).
3. BETWEEN looks/fires: total growth of the fire in the next 24 h vs that day's weather (ERA5-Land), against the fire's own state.
Out: results/front_drivers.json, figures/front_drivers.png"""
import json, numpy as np, pandas as pd, matplotlib
import lightgbm as lgb
matplotlib.use('Agg'); import matplotlib.pyplot as plt
from scipy.stats import spearmanr
R = '/mnt/project-files'; HERE = f'{R}/research/fire-continuity'
X = pd.read_parquet(f'{HERE}/results/front_features.parquet')
X['y'] = np.log1p(X.new24_ha); X['frp_last'] = np.log1p(X.frp_last); X['separate'] = X.kind.isin(['separate', 'independent']).astype(float)
X['fuel'] = X.fuel.fillna(X.fuel.median()); X['village_km'] = X.village_km.fillna(X.village_km.median())
X['grp'] = X.fire.astype(str) + '_' + X.k.astype(str)
GROUPS = {'fire activity (dots, heat, age of front)': ['n_dots_last', 'frp_last', 'n_dots', 'age_h', 'separate'],
          'room to grow (unburned ground around it)': ['avail_ha'],
          'tree cover / grass / crops / fuel map': ['tree', 'grass', 'crop', 'fuel'],
          'terrain (slope, uphill, ridge/valley)': ['slope', 'uphill', 'local_height'],
          'burn history (earlier this season, past years)': ['burned_earlier', 'prior_burns'],
          'people (roads, villages)': ['road', 'village_km'],
          'downwind side of the fire': ['downwind']}
GROUPS['all local factors (no fire activity)'] = sum([v for k, v in GROUPS.items() if not k.startswith('fire activity')], [])
GROUPS['everything'] = sum([v for k, v in GROUPS.items() if k not in ('all local factors (no fire activity)',)], [])
rng = np.random.default_rng(0)

def centre(D, cols):
    return D[cols] - D.groupby('grp')[cols].transform('mean')

def cv_r2(D, cols, model, shuffle=False):
    D = D.copy()
    if shuffle:
        for c in cols: D[c] = D.groupby('grp')[c].transform(lambda s: s.sample(frac=1, random_state=int(rng.integers(1e9))).values)
    Xc = centre(D, cols).fillna(0).values; yc = (D.y - D.groupby('grp').y.transform('mean')).values
    pred = np.zeros(len(D))
    for s in D.season.unique():
        tr, te = (D.season != s).values, (D.season == s).values
        if model == 'linear':
            b = np.linalg.lstsq(np.c_[Xc[tr], np.ones(tr.sum())], yc[tr], rcond=None)[0]; pred[te] = np.c_[Xc[te], np.ones(te.sum())] @ b
        else:
            m = lgb.LGBMRegressor(n_estimators=150, learning_rate=.05, num_leaves=6, min_child_samples=30, subsample=.8, subsample_freq=1, verbose=-1)
            m.fit(Xc[tr], yc[tr]); pred[te] = m.predict(Xc[te])
    return 1 - ((yc - pred) ** 2).sum() / (yc ** 2).sum()

out = {}
# 1. where the variation sits (all active fronts)
y = X.y; tot = ((y - y.mean()) ** 2).sum()
fire_m = X.groupby('fire').y.transform('mean'); grp_m = X.groupby('grp').y.transform('mean')
out['variance_split'] = dict(between_fires=round(float(((fire_m - y.mean()) ** 2).sum() / tot), 3),
                             between_looks_same_fire=round(float(((grp_m - fire_m) ** 2).sum() / tot), 3),
                             between_fronts_same_look=round(float(((y - grp_m) ** 2).sum() / tot), 3), n_fronts=len(X))
# 2. within same fire and look
res = {}
for setname, D in [('all fronts', X), ('connected fronts only', X[X.separate == 0])]:
    D = D[D.groupby('grp').grp.transform('size') >= 2].copy()
    r = dict(n_fronts=len(D), n_groups=int(D.grp.nunique()))
    for gname, cols in GROUPS.items():
        cols = [c for c in cols if c in D]
        e = {}
        for model in ['linear', 'trees']:
            real = cv_r2(D, cols, model); sh = [cv_r2(D, cols, model, shuffle=True) for _ in range(30 if model == 'linear' else 10)]
            e[model] = dict(r2=round(float(real), 3), chance_95=round(float(np.quantile(sh, .95)), 3))
        r[gname] = e
    # single factors: within-group Spearman, fire bootstrap
    one = {}
    cols = sorted(set(sum(GROUPS.values(), [])))
    C_ = centre(D, cols); yc = D.y - D.groupby('grp').y.transform('mean')
    fires = D.fire.values; uf = np.unique(fires)
    for c in cols:
        ok = C_[c].notna().values
        rho = spearmanr(C_[c][ok], yc[ok])[0]; bs = []
        for _ in range(300):
            sel = rng.choice(uf, len(uf)); m = np.concatenate([np.where((fires == f) & ok)[0] for f in sel])
            bs.append(spearmanr(C_[c].values[m], yc.values[m])[0])
        one[c] = [round(float(rho), 3), round(float(np.nanquantile(bs, .025)), 3), round(float(np.nanquantile(bs, .975)), 3)]
    r['single_factor_rho_95'] = one
    res[setname] = r
out['within_same_fire_and_look'] = res
# 3. between looks/fires: weather vs fire state
W = pd.read_csv(f'{R}/ratapani/ee/era5land_daily.csv', parse_dates=['time']); W['date'] = W.time.dt.normalize()
W['tmax'] = W.temperature_2m_max - 273.15; W['wind'] = np.hypot(W.u_component_of_wind_10m, W.v_component_of_wind_10m)
td, tt = W.dewpoint_temperature_2m - 273.15, W.temperature_2m - 273.15
W['rh'] = 100 * np.exp(17.625 * td / (243.04 + td)) / np.exp(17.625 * tt / (243.04 + tt))
W['rain7'] = W.total_precipitation_sum.rolling(7).sum() * 1000; W['soil'] = W.volumetric_soil_water_layer_1
I = X.groupby('grp').agg(fire=('fire', 'first'), season=('season', 'first'), date=('date', 'first'), y=('new24_ha', 'sum'),
                          dots_last=('n_dots_last', 'sum'), frp=('frp_last', 'sum'), age=('th', 'first'), fronts=('front', 'size'),
                          avail=('avail_ha', 'sum'), hour=('hour_ist', 'first')).reset_index()
I['y'] = np.log1p(I.y); I = I.merge(W[['date', 'tmax', 'wind', 'rh', 'rain7', 'soil']], on='date', how='left')
I['doy'] = pd.to_datetime(I.date).dt.dayofyear; I['night'] = ((I.hour < 6) | (I.hour >= 18)).astype(float)
BG = {'weather that day (temp, humidity, wind, rain, soil water)': ['tmax', 'rh', 'wind', 'rain7', 'soil'],
      'date in season': ['doy'], 'night or afternoon look': ['night'],
      'fire activity (dots, heat, hours burning, fronts, room)': ['dots_last', 'frp', 'age', 'fronts', 'avail'],
      'everything': ['tmax', 'rh', 'wind', 'rain7', 'soil', 'doy', 'night', 'dots_last', 'frp', 'age', 'fronts', 'avail']}
def cv_between(D, cols, shuffle=False):
    D = D.copy()
    if shuffle: D[cols] = D[cols].sample(frac=1, random_state=int(rng.integers(1e9))).values
    pred = np.zeros(len(D))
    for s in D.season.unique():
        tr, te = D.season != s, D.season == s
        m = lgb.LGBMRegressor(n_estimators=150, learning_rate=.05, num_leaves=6, min_child_samples=30, subsample=.8, subsample_freq=1, verbose=-1)
        m.fit(D.loc[tr, cols], D.y[tr]); pred[te.values] = m.predict(D.loc[te, cols])
    return 1 - ((D.y - pred) ** 2).sum() / ((D.y - D.y.mean()) ** 2).sum()
bt = {}
for gname, cols in BG.items():
    real = cv_between(I, cols); sh = [cv_between(I, cols, True) for _ in range(10)]
    bt[gname] = dict(r2=round(float(real), 3), chance_95=round(float(np.quantile(sh, .95)), 3))
bt['single_rho'] = {c: round(float(spearmanr(I[c], I.y, nan_policy='omit')[0]), 3) for c in BG['everything']}
bt['n_looks'] = len(I)
out['between_looks_and_fires'] = bt
print(json.dumps(out, indent=1)); json.dump(out, open(f'{HERE}/results/front_drivers.json', 'w'), indent=1)

# picture: share of front-to-front difference explained (connected fronts, trees), vs chance
r = out['within_same_fire_and_look']['connected fronts only']
names = [g for g in GROUPS]
fig, ax = plt.subplots(1, 2, figsize=(15, 5.2), gridspec_kw=dict(width_ratios=[1.6, 1]))
vals = [max(r[g]['trees']['r2'], r[g]['linear']['r2']) * 100 for g in names]; ch = [max(r[g]['trees']['chance_95'], r[g]['linear']['chance_95']) * 100 for g in names]
yy = np.arange(len(names))[::-1]
ax[0].barh(yy, vals, color=['#c0392b' if v > c else '#999' for v, c in zip(vals, ch)])
ax[0].scatter(ch, yy, marker='|', s=250, color='k', label='chance (shuffled, 95% top)')
ax[0].set_yticks(yy, names, fontsize=9); ax[0].axvline(0, color='k', lw=.6)
ax[0].set_xlabel('% of the difference between fronts of the same fire explained\n(seasons held out; red = beats chance; below 0 = worse than no model)')
ax[0].set_title(f"A. Same fire, same moment: why one front runs farther\n({r['n_fronts']} connected fronts in {r['n_groups']} look-groups)", fontsize=10); ax[0].legend(fontsize=8, loc='lower right')
b = out['between_looks_and_fires']; bn = [g for g in BG]
bv = [b[g]['r2'] * 100 for g in bn]; bc = [b[g]['chance_95'] * 100 for g in bn]; yb = np.arange(len(bn))[::-1]
ax[1].barh(yb, bv, color=['#2c6fbb' if v > c else '#999' for v, c in zip(bv, bc)]); ax[1].scatter(bc, yb, marker='|', s=250, color='k')
ax[1].set_yticks(yb, bn, fontsize=9); ax[1].axvline(0, color='k', lw=.6)
ax[1].set_xlabel('% of the difference in whole-fire growth\nexplained (seasons held out)'); ax[1].set_title(f"B. Between fires and days\n({b['n_looks']} looks)", fontsize=10)
for a in ax: a.spines[['top', 'right']].set_visible(False)
fig.tight_layout(); fig.savefig(f'{HERE}/figures/front_drivers.png', dpi=110)
