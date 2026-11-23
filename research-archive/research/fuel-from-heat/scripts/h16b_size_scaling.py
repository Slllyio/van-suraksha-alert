"""Why heat per hectare falls with scar size: total corrected energy vs scar area (log-log slope; 1 = energy grows in
step with burnt ground). Also how the slope differs for scars below/above 50 ha. Out: results/size_scaling.json"""
import json, numpy as np, pandas as pd
import statsmodels.formula.api as smf
from h0_lib import RES
R = pd.read_csv(f'{RES}/corrected_fire_fuel.csv')
R['area'] = R.n_pix * 0.04; R['E'] = R.fuel_corr * R.area      # proportional to energy
R['lE'], R['lA'] = np.log(R.E), np.log(R.area)
out = {}
m = smf.ols('lE ~ lA + C(month) + n_pass', R).fit(); out['slope_all'] = [round(m.params.lA, 3), m.conf_int().loc['lA'].round(3).tolist()]
for lab, d in [('scar < 50 ha', R[R.area < 50]), ('scar >= 50 ha', R[R.area >= 50])]:
    m = smf.ols('lE ~ lA + C(month) + n_pass', d).fit(); out[f'slope {lab}'] = [round(m.params.lA, 3), m.conf_int().loc['lA'].round(3).tolist(), len(d)]
t = R.groupby(pd.qcut(R.area, 5)).agg(fires=('fire', 'size'), tha=('fuel_corr', 'median'), passes=('n_pass', 'median')).round(2)
out['by_size'] = t.reset_index().astype(str).to_dict('records'); print(out); print(t)
json.dump(out, open(f'{RES}/size_scaling.json', 'w'), indent=1)
