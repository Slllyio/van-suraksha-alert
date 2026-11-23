"""Step 6: tests on the per-look heat per burning area (step 5), comparing looks INSIDE the same fire (fire, season,
weather-of-the-week and scar quality are then shared).
 A. Same look, two satellites ~50 min apart: do they agree on the look's heat per area?
 B. Same fire, different looks: does a look whose new ground has more canopy / litter give more heat per area?
    Fire-demeaned rank correlations, and a model with fires held out, against within-fire-shuffled ground.
 C. What does move it: time of day, night, pixel size, window length, area.
Out: results/look_tests.json
"""
import json
import numpy as np, pandas as pd
from scipy.stats import spearmanr
from sklearn.linear_model import LinearRegression
from h0_lib import RES

R = pd.read_csv(f'{RES}/look_fuel.csv', parse_dates=['t'])
R = R[(R.area_ha > 0) & (R.fuel_tha > 0)].copy()
R['lf'] = np.log(R.fuel_tha); R['l_area'] = np.log(R.area_ha); R['l_H'] = np.log(R.window_fire_h); R['l_pix'] = np.log(R.pix_km2)
R['day'] = (R.night < .5).astype(int)
out = {'rows': len(R), 'fires': R.fire.nunique(), 'looks': R.groupby(['fire', 'look']).ngroups,
       'fuel_tha_median': round(R.fuel_tha.median(), 2), 'fuel_tha_iqr': R.fuel_tha.quantile([.25, .75]).round(2).tolist()}
# A
pa = []
for (f, k), g in R.groupby(['fire', 'look']):
    g = g.sort_values('t')
    if g.sensor.nunique() >= 2: pa.append((g.lf.iloc[0], g.lf.iloc[1], g.l_pix.iloc[1] - g.l_pix.iloc[0]))
pa = np.array(pa)
out['A_same_look_two_sats'] = dict(n=len(pa), rho=round(spearmanr(pa[:, 0], pa[:, 1])[0], 3), typical_factor=round(float(np.exp(np.median(np.abs(pa[:, 0] - pa[:, 1])))), 2))
print('A', out['A_same_look_two_sats'])
# look-level table: one value per look = mean of its passes' log fuel
Lk = R.groupby(['fire', 'look']).agg(lf=('lf', 'mean'), l_area=('l_area', 'first'), l_H=('l_H', 'first'), l_pix=('l_pix', 'mean'), day=('day', 'mean'),
                                     ist=('ist_hour', 'mean'), near=('near600', 'first'), canopy=('canopy', 'first'), litter=('litter', 'first'),
                                     grass=('grass', 'first'), teak=('teak', 'first'), slope=('slope', 'first'), tree=('tree', 'first')).reset_index()
Lk = Lk[Lk.groupby('fire').look.transform('size') >= 3].dropna()
dm = lambda c: Lk[c] - Lk.groupby('fire')[c].transform('mean')
B = []
for c in ['canopy', 'litter', 'grass', 'teak', 'slope', 'tree', 'l_area', 'l_H', 'l_pix', 'day', 'near']:
    B.append(dict(var=c, rho_within_fire=round(spearmanr(dm(c), dm('lf'))[0], 3)))
B = pd.DataFrame(B); print('B within-fire rank corr with log heat per area (%d looks, %d fires)' % (len(Lk), Lk.fire.nunique())); print(B.to_string(index=False))
out['B_within_fire'] = B.to_dict('records'); out['B_n_looks'] = len(Lk); out['B_n_fires'] = int(Lk.fire.nunique())
# held-out fires, within-fire model
ctrl = ['l_area', 'l_H', 'l_pix', 'day', 'near']; ground = ['canopy', 'litter', 'grass', 'teak', 'slope', 'tree']
Z = Lk.copy()
for c in ctrl + ground + ['lf']: Z[c] = dm(c)
fires = Z.fire.unique(); rng = np.random.default_rng(0); fold = dict(zip(fires, rng.integers(0, 10, len(fires))))
Z['fold'] = Z.fire.map(fold)
def cv(Z, feats):
    pred = np.zeros(len(Z))
    for k in range(10):
        tr, te = Z.fold != k, Z.fold == k
        pred[te.values] = LinearRegression().fit(Z.loc[tr, feats], Z.loc[tr, 'lf']).predict(Z.loc[te, feats])
    return 1 - ((Z.lf - pred) ** 2).sum() / (Z.lf ** 2).sum()
r_ctrl, r_all = cv(Z, ctrl), cv(Z, ctrl + ground)
sh = []
for s in range(20):
    Z2 = Z.copy(); Z2[ground] = Z2.groupby('fire')[ground].transform(lambda x: x.sample(frac=1, random_state=s).values)
    sh.append(cv(Z2, ctrl + ground))
out['B_heldout_r2_within_fire'] = {'controls (area, window, pixel, day, near)': round(r_ctrl, 3), '+ ground': round(r_all, 3),
                                   '+ ground shuffled inside fire': round(float(np.mean(sh)), 3)}
print('B held-out share of within-fire spread explained:', out['B_heldout_r2_within_fire'])
# tercile table: looks with more canopy than the fire's average
Lk['canopy_rel'] = dm('canopy'); Lk['lf_rel'] = dm('lf')
t = Lk.groupby(pd.qcut(Lk.canopy_rel, 3, labels=['less canopy than fire average', 'about average', 'more canopy than average'])).agg(
    looks=('lf', 'size'), canopy_diff=('canopy_rel', 'median'), heat_per_area_vs_fire=('lf_rel', lambda s: np.exp(s.median())))
print(t.round(2)); out['B_canopy_terciles'] = t.round(3).reset_index().astype(str).to_dict('records')
# C time of day
R['hour_band'] = pd.cut(R.ist_hour, [0, 6, 12, 18, 24], labels=['00-06 IST', '06-12', '12-18', '18-24'])
t = R.groupby('hour_band', observed=True).agg(rows=('lf', 'size'), fuel_median=('fuel_tha', 'median'), frp_median=('frp', 'median'))
print(t.round(2)); out['C_by_hour'] = t.round(3).reset_index().astype(str).to_dict('records')
json.dump(out, open(f'{RES}/look_tests.json', 'w'), indent=1, default=float)
