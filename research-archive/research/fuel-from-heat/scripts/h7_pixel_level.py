"""Step 7: one detection at a time, compared only with other detections of the SAME satellite pass over the SAME fire
(same sensor, minute, weather, fire): does a pixel sitting over more canopy / litter give more FRP or brighter channels?
Per detection: footprint box (scan x track) intersected with the fire's final scar on the 20 m grid ->
   scar_share (how much of the box burnt at some point), canopy / litter / grass / teak / slope over the burnt part.
Signals: log FRP, bright_ti4 (3.7 um, dropped when saturated >= 367 K), bright_ti5 (11 um), ti4 - ti5,
   two-channel (Dozier) fire temperature and burning fraction (background = 10th percentile of ti5 in the pass, rough).
Also the per-fire level: median of each signal per fire vs the ground under the scar (rank corr), and vs the
per-fire heat per hectare from step 3.
Out: results/pixel_tests.json, results/pixel_det.csv
"""
import json, pickle
import numpy as np, pandas as pd
from scipy.stats import spearmanr
from scipy.optimize import brentq
from h0_lib import RES, SCRATCH, X0, Y0, NR, NC, layers

L = layers(); pix = pickle.load(open(f'{SCRATCH}/fire_pix.pkl', 'rb'))
v = pd.read_csv(f'{RES}/clusters.csv', parse_dates=['t']).dropna(subset=['fire']); v['fire'] = v.fire.astype(int)
v['pass'] = v.sensor + v.t.dt.strftime('%Y%m%d%H%M')
# scar mask lookup per fire as a set of flat indices
recs = []
for fire, g in v.groupby('fire'):
    rr, cc = pix.get(fire, (np.array([], int), np.array([], int)))
    flat = set((rr * NC + cc).tolist())
    for r in g.itertuples():
        c0, c1 = int((r.x - r.scan_m / 2 - X0) // 20), int((r.x + r.scan_m / 2 - X0) // 20)
        r0, r1 = int((Y0 - r.y - r.track_m / 2) // 20), int((Y0 - r.y + r.track_m / 2) // 20)
        R_, C_ = np.mgrid[max(r0, 0):min(r1 + 1, NR), max(c0, 0):min(c1 + 1, NC)]
        R_, C_ = R_.ravel(), C_.ravel(); inside = np.array([(a * NC + b) in flat for a, b in zip(R_, C_)], bool)
        rec = dict(idx=r.Index, scar_share=inside.mean() if len(inside) else np.nan, canopy_box=np.nanmean(L['canopy'][R_, C_]))
        for k in ['canopy', 'litter', 'grass', 'teak', 'slope']:
            rec[k] = np.nanmean(L[k][R_[inside], C_[inside]]) if inside.any() else np.nan
        recs.append(rec)
X = pd.DataFrame(recs).set_index('idx'); v = v.join(X)
# Dozier two-channel split
h, c, k = 6.626e-34, 2.998e8, 1.381e-23
pl = lambda lam, T: 2 * h * c ** 2 / lam ** 5 / (np.exp(h * c / (lam * k * T)) - 1)
L4, L5 = 3.74e-6, 11.45e-6
allv = pd.read_csv(f'{RES}/viirs_det.csv', parse_dates=['t']); allv['pass'] = allv.sensor + allv.t.dt.strftime('%Y%m%d%H%M')
tb = allv.groupby('pass').bright_ti5.quantile(.1); v['Tb'] = v['pass'].map(tb)
def dz(T4, T5, Tb):
    if T4 >= 366.9 or T5 <= Tb + .05: return np.nan, np.nan
    r4, r5, b4, b5 = pl(L4, T4), pl(L5, T5), pl(L4, Tb), pl(L5, Tb)
    f = lambda Tf: (r5 - b5) / (pl(L5, Tf) - b5) * pl(L4, Tf) + (1 - (r5 - b5) / (pl(L5, Tf) - b5)) * b4 - r4
    try: Tf = brentq(f, 400, 2500)
    except ValueError: return np.nan, np.nan
    return (r5 - b5) / (pl(L5, Tf) - b5), Tf
z = [dz(a, b, t) for a, b, t in zip(v.bright_ti4, v.bright_ti5, v.Tb)]
v['dz_p'] = [a for a, _ in z]; v['dz_Tf'] = [b for _, b in z]
v['l_frp'] = np.log(v.frp); v['ti4'] = v.bright_ti4.where(~v.sat_i4); v['ti5'] = v.bright_ti5; v['ti4_5'] = v.ti4 - v.ti5
v['l_dzp'] = np.log(v.dz_p)
v.to_csv(f'{RES}/pixel_det.csv', index=False)
out = {'detections': len(v), 'i4_saturated_share': round(v.sat_i4.mean(), 3), 'dozier_solvable_share': round(v.dz_p.notna().mean(), 3),
       'day_share': round((v.daynight == 'D').mean(), 3)}
print(out)
sig = ['l_frp', 'ti4', 'ti5', 'ti4_5', 'dz_Tf', 'l_dzp']
grd = ['scar_share', 'canopy', 'litter', 'grass', 'teak', 'slope', 'canopy_box']
W = v[v.groupby(['fire', 'pass']).frp.transform('size') >= 2].copy()
rows = []
for s in sig:
    for gname in grd:
        ok = W[[s, gname, 'fire', 'pass']].dropna()
        ok = ok[ok.groupby(['fire', 'pass'])[s].transform('size') >= 2]
        a = ok[s] - ok.groupby(['fire', 'pass'])[s].transform('mean'); b = ok[gname] - ok.groupby(['fire', 'pass'])[gname].transform('mean')
        rows.append(dict(signal=s, ground=gname, n=len(ok), rho_within_pass=round(spearmanr(a, b)[0], 3)))
T = pd.DataFrame(rows).pivot(index='ground', columns='signal', values='rho_within_pass')[sig]
print('within the same pass of the same fire: rank corr (detections in passes with >=2 over the fire: %d)' % len(W)); print(T)
out['within_pass_rho'] = T.reset_index().to_dict('records')
# litter holding canopy fixed (within pass): residual of litter on canopy
ok = W[['l_frp', 'litter', 'canopy', 'scar_share', 'fire', 'pass']].dropna()
for col in ['l_frp', 'litter', 'canopy', 'scar_share']: ok[col] = ok[col] - ok.groupby(['fire', 'pass'])[col].transform('mean')
import statsmodels.api as sm
m = sm.OLS(ok.l_frp, sm.add_constant(ok[['scar_share', 'canopy', 'litter']])).fit(cov_type='cluster', cov_kwds={'groups': pd.factorize(ok['pass'])[0]})
out['within_pass_ols'] = dict(coef=m.params.round(4).to_dict(), p=m.pvalues.round(4).to_dict(), n=int(m.nobs),
                              note='log FRP per unit: scar_share 0-1, canopy %, litter t/ha; errors clustered by pass')
print(out['within_pass_ols'])
# per-fire level
fu = pd.read_csv(f'{RES}/fire_fuel.csv')[['fire', 'fuel_tha', 'n_pass']]
cv_ = pd.read_csv(f'{RES}/fire_cov.csv')[['fire', 'canopy', 'litter', 'grass', 'doy']]
Fm = v[v.daynight == 'D'].groupby('fire')[sig].median().reset_index().merge(fu, on='fire').merge(cv_, on='fire')
rows = []
for s in sig:
    for gname in ['canopy', 'litter', 'grass', 'doy', 'fuel_tha']:
        ok = Fm[[s, gname]].dropna(); rows.append(dict(signal=s, vs=gname, rho=round(spearmanr(ok[s], ok[gname])[0], 3), n=len(ok)))
T2 = pd.DataFrame(rows).pivot(index='vs', columns='signal', values='rho')[sig]
print('per fire (day detections, median per fire):'); print(T2); out['per_fire_rho'] = T2.reset_index().to_dict('records')
json.dump(out, open(f'{RES}/pixel_tests.json', 'w'), indent=1, default=float)
