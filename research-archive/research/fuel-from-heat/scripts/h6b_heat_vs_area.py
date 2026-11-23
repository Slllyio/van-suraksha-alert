"""Step 6b: does a look's heat follow how much ground the map says was burning then? Within each big fire,
log(FRP / clock) vs log(area burning per fire-hour) for the same look. Slope 1 = heat tracks burning area exactly
(then heat per area is a clean per-ground number); slope 0 = heat ignores it. Day passes only, to keep the clock out.
Also the night/day FRP ratio, against the burning clock's night/day ratio (clock from MODIS detection counts).
Out: results/heat_vs_area.json"""
import json, numpy as np, pandas as pd
from scipy.stats import spearmanr
import statsmodels.api as sm
from h0_lib import RES
R = pd.read_csv(f'{RES}/look_fuel.csv', parse_dates=['t']); R = R[R.area_ha > 0]
R['li'] = np.log(R.frp / R.clock_r); R['la'] = np.log(R.area_ha / R.window_fire_h)
out = {}
for name, S in [('day passes', R[R.night < .5]), ('all passes', R)]:
    S = S[S.groupby('fire').look.transform('nunique') >= 3].copy()
    a = S.li - S.groupby('fire').li.transform('mean'); b = S.la - S.groupby('fire').la.transform('mean')
    m = sm.OLS(a, b).fit(cov_type='cluster', cov_kwds={'groups': S.fire})
    out[name] = dict(n=len(S), rho=round(spearmanr(a, b)[0], 3), slope=round(m.params.iloc[0], 3), ci=m.conf_int().iloc[0].round(3).tolist())
d = R.groupby(R.night >= .5).frp.median(); c = R.groupby(R.night >= .5).clock_r.median()
out['night_over_day_frp_median'] = round(d[True] / d[False], 3); out['night_over_day_clock'] = round(c[True] / c[False], 3)
print(out); json.dump(out, open(f'{RES}/heat_vs_area.json', 'w'), indent=1, default=float)
