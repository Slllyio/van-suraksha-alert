"""Step 4: is per-fire 'fuel burnt per hectare' (energy / scar area, step 3) a fuel signal?
 A. Repeatability: S-NPP-only vs NOAA-20-only estimate of the same fire.
 B. What it follows: rank correlations with sensor geometry, fire size, timing, weather, and the ground (canopy, litter...).
 C. Does the ground add anything once sensor/size/timing/weather are known? Linear model on log fuel, seasons held out.
 D. Physical expectations if it measured fuel: more under more canopy / litter, more later in the season (litter piles up
    Feb->Apr), less where the ground burnt the season before.
Out: results/fire_tests.json
"""
import json
import numpy as np, pandas as pd
from scipy.stats import spearmanr
from sklearn.linear_model import LinearRegression
from h0_lib import RES

R = pd.read_csv(f'{RES}/fire_fuel.csv')[['fire', 'scar_ha', 'n_pass', 'n_det', 'pix_km2', 'night_share', 'hours', 'fuel_tha', 'fuel_tha_short',
                                         'fuel_tha_long', 'fuel_tha_snpp', 'fuel_tha_n20', 'n_pass_snpp', 'n_pass_n20']]
C = pd.read_csv(f'{RES}/fire_cov.csv')
D = R.merge(C, on='fire')
D = D[(D.n_pass >= 2) & (D.month.between(2, 6))].copy()     # fire season, >= 2 VIIRS passes
D['lf'] = np.log(D.fuel_tha)
out = {'n_fires': len(D), 'fuel_tha_median': round(D.fuel_tha.median(), 2), 'fuel_tha_iqr': D.fuel_tha.quantile([.25, .75]).round(2).tolist(),
       'end_assumption_range': [round(D.fuel_tha_short.median(), 2), round(D.fuel_tha_long.median(), 2)]}
print(out)
# A
for k in [1, 2]:
    a = D[(D.n_pass_snpp >= k) & (D.n_pass_n20 >= k)]
    rho = spearmanr(a.fuel_tha_snpp, a.fuel_tha_n20)[0]
    out[f'A_snpp_vs_n20_min{k}'] = dict(n=len(a), rho=round(rho, 3), median_ratio=round(np.median(a.fuel_tha_snpp / a.fuel_tha_n20), 2))
    print('A repeatability (>=%d pass each): fires %d rank corr %.2f' % (k, len(a), rho))
# shared-size part: both divide by the same area. Repeatability of energy alone, and with area taken out
a = D[(D.n_pass_snpp >= 2) & (D.n_pass_n20 >= 2)].copy()
ra = np.log(a.fuel_tha_snpp) - np.polyval(np.polyfit(np.log(a.scar_ha), np.log(a.fuel_tha_snpp), 1), np.log(a.scar_ha))
rb = np.log(a.fuel_tha_n20) - np.polyval(np.polyfit(np.log(a.scar_ha), np.log(a.fuel_tha_n20), 1), np.log(a.scar_ha))
out['A_after_removing_size'] = round(spearmanr(ra, rb)[0], 3)
print('A after removing scar size from both:', out['A_after_removing_size'])
# B
cols = {'pix_km2': 'pixel size (swath position)', 'night_share': 'share of night detections', 'n_pass': 'number of passes',
        'scar_ha': 'scar size', 'hours': 'fire duration', 'doy': 'day of year', 'tmax': 'max temperature', 'rh': 'humidity',
        'wind': 'wind', 'rain30': 'rain last 30 days', 'canopy': 'canopy %', 'litter': 'litter map v3', 'grass': 'grass map v3',
        'teak': 'teak probability', 'slope': 'slope', 'tree': 'WorldCover tree share', 'burnt_last_season': 'burnt the season before'}
B = []
for k, lab in cols.items():
    ok = D[[k, 'fuel_tha']].dropna()
    B.append(dict(var=lab, n=len(ok), rho=round(spearmanr(ok[k], ok.fuel_tha)[0], 3)))
B = pd.DataFrame(B); print(B.to_string(index=False)); out['B'] = B.to_dict('records')
# C
D['l_area'] = np.log(D.scar_ha); D['l_pix'] = np.log(D.pix_km2); D['l_npass'] = np.log(D.n_pass); D['l_hours'] = np.log1p(D.hours)
base = ['l_area', 'l_pix', 'night_share', 'l_npass', 'l_hours', 'doy']
wx = ['tmax', 'rh', 'wind', 'rain30']
ground = ['canopy', 'litter', 'grass', 'teak', 'slope', 'burnt_last_season']
E = D.dropna(subset=base + wx + ground).copy()
def cv(feats):
    pred = np.zeros(len(E))
    for s in E.season.unique():
        tr, te = E.season != s, E.season == s
        pred[te.values] = LinearRegression().fit(E.loc[tr, feats], E.loc[tr, 'lf']).predict(E.loc[te, feats])
    return 1 - ((E.lf - pred) ** 2).sum() / ((E.lf - E.lf.mean()) ** 2).sum()
C_ = {'sensor + size + timing': cv(base), '+ weather': cv(base + wx), '+ ground': cv(base + wx + ground), 'ground only': cv(ground),
      'canopy only': cv(['canopy']), 'sensor+size+timing+canopy': cv(base + ['canopy'])}
rng = np.random.default_rng(0); sh = []
for _ in range(20):
    E2 = E.copy(); E2[ground] = E2[ground].values[rng.permutation(len(E2))]
    E_bak = E; E = E2; sh.append(cv(base + wx + ground)); E = E_bak
C_['+ ground shuffled (baseline)'] = float(np.mean(sh))
C_ = {k: round(float(v), 3) for k, v in C_.items()}
print('C share of fire-to-fire spread explained, seasons held out (n=%d):' % len(E), C_); out['C_r2_heldout'] = C_; out['C_n'] = len(E)
m = LinearRegression().fit((E[base + wx + ground] - E[base + wx + ground].mean()) / E[base + wx + ground].std(), E.lf)
out['C_std_coefs'] = dict(zip(base + wx + ground, np.round(m.coef_, 3)))
print('standardised effects on log fuel:', out['C_std_coefs'])
# D: litter within canopy bands; doy within season; burnt-last-season
D['cb'] = pd.qcut(D.canopy, 5, labels=False)
w = [spearmanr(g.litter, g.fuel_tha)[0] for _, g in D.dropna(subset=['litter']).groupby('cb')]
out['D_litter_within_canopy_band_rho'] = np.round(w, 3).tolist()
t = D.groupby(pd.cut(D.canopy, [0, 20, 40, 60, 100])).agg(fires=('fuel_tha', 'size'), fuel_median=('fuel_tha', 'median'), map_litter=('litter', 'median'))
t2 = D.groupby('month').agg(fires=('fuel_tha', 'size'), fuel_median=('fuel_tha', 'median'), pix_km2=('pix_km2', 'median'), scar_ha=('scar_ha', 'median'))
t3 = D.groupby(pd.cut(D.burnt_last_season, [-.01, .05, .3, 1])).agg(fires=('fuel_tha', 'size'), fuel_median=('fuel_tha', 'median'))
print(t.round(2)); print(t2.round(2)); print(t3.round(2))
out['D_by_canopy'] = t.round(3).reset_index().astype(str).to_dict('records'); out['D_by_month'] = t2.round(3).reset_index().to_dict('records')
out['D_by_burnt_last'] = t3.round(3).reset_index().astype(str).to_dict('records')
json.dump(out, open(f'{RES}/fire_tests.json', 'w'), indent=1, default=float)
