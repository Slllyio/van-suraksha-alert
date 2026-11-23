"""Check of the censoring result: is the fall of leafy-crown detections with angle just a date effect? Logit inside each
month (month fixed effects) and by year, leafy-closed vs bare-closed detections. Also day vs night (VIIRS night passes
~19-21 UTC). Out: results/view_angle_month_check.json"""
import json, numpy as np, pandas as pd
import statsmodels.formula.api as smf
from h0_lib import RES
D = pd.read_csv(f'{RES}/det_geom.csv', parse_dates=['t']).dropna(subset=['leafy'])
D = D[(D.canopy01 >= .5) & ((D.leafy >= .2) | (D.leafy < .1))].copy()
D['y'] = (D.leafy >= .2).astype(int); D['month'] = D.t.dt.month; D['year'] = D.t.dt.year
D['night'] = D.t.dt.hour.between(17, 23).astype(int)
out = {}
m = smf.logit('y ~ sec + C(month) + C(year)', D).fit(disp=0)
out['leafy_vs_bare_per_sec_month_year_FE'] = [round(m.params.sec, 3), m.conf_int().loc['sec'].round(3).tolist(), int(m.nobs)]
for nm, d in [('day', D[D.night == 0]), ('night', D[D.night == 1])]:
    m = smf.logit('y ~ sec + C(month) + C(year)', d).fit(disp=0)
    out[f'{nm}'] = [round(m.params.sec, 3), m.conf_int().loc['sec'].round(3).tolist(), int(m.nobs)]
# angle distribution by month (is angle related to month?)
out['median_sec_by_month'] = D.groupby('month').sec.median().round(3).to_dict()
# within-month table for Feb and Mar
for mo in [1, 2, 3]:
    d = D[D.month == mo]; d = d.assign(sb=pd.cut(d.sec, [0.99, 1.15, 1.4, 1.8, 3], labels=['<30', '30-45', '45-56', '>56']))
    out[f'leafy_share_by_angle_month{mo}'] = d.groupby('sb', observed=True).y.agg(['mean', 'size']).round(3).reset_index().astype(str).to_dict('records')
print(json.dumps(out, indent=1, default=float)); json.dump(out, open(f'{RES}/view_angle_month_check.json', 'w'), indent=1, default=float)
