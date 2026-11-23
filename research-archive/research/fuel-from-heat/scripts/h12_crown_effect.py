"""Crown effect on the infrared readings (Akkshay 17 Oct 07:37Z: "see concretely the infrared channels' effect from
crowns and how much it is").

PROBLEM: closed forest shows less heat from space than open ground. Two stories:
  (a) CROWNS BLOCK: leaves above a ground fire absorb / hide part of its infrared before it reaches the satellite.
  (b) DIFFERENT FIRE / GROUND: open grassy ground really burns hotter, or its warmer background shifts the readings.
TEST that separates them: teak and other deciduous crowns drop their leaves Dec-Apr. The SAME closed-canopy ground has
leafy crowns in January and bare branches in April. If crowns block, the closed-vs-open gap must shrink as the leaves
fall. If it is the fire or ground itself, the gap stays the same all season.

MEASURE: each reading of a detection is compared with the other detections of the SAME satellite pass (same minute,
sensor, weather), allowing for pixel size and the burnt share of the square (as in h9). Then, inside each pass:
   reading ~ canopy_bare_part + leafy_crown_now
   leafy_crown_now = canopy cover x (1 - share of leaves already fallen on that date, per pixel, Sentinel-2,
                     fuel-map leaf_fall_fraction_10m.tif, interpolated between month ends; 0 by Nov end, 100% after Apr)
   canopy_bare_part = canopy cover (branches, trunks, site: always there)
The leafy_crown_now coefficient = the crown blocking effect, with the site held by the canopy term.
Readings: FRP, I4 (3.7 um, unsaturated only), I5 (11 um), I4-I5. Day and night separately (night: no sun-heated
background, so a background story should vanish at night; blocking should not).
Out: results/crown_tests.json, figures/crown_effect.png
"""
import json
import numpy as np, pandas as pd, rasterio
import statsmodels.formula.api as smf
from h0_lib import RES, ROOT, HERE

v = pd.read_csv(f'{RES}/place_det.csv', parse_dates=['t'])
v = v[v.t.dt.month.isin([1, 2, 3, 4, 5])].copy()
with rasterio.open(f'{ROOT}/fuel-map/ratapani/leaf_fall_fraction_10m.tif') as r:
    LF = r.read().astype(float); T = r.transform; nd = r.nodata
if nd is not None: LF[LF == nd] = np.nan
H, W = LF.shape[1:]
lf = []
for rr in v.itertuples():
    hx, hy = rr.scan_m / 2, rr.track_m / 2
    c0, c1 = max(int((rr.x - hx - T.c) // 10), 0), min(int((rr.x + hx - T.c) // 10) + 1, W)
    r0, r1 = max(int((T.f - rr.y - hy) // 10), 0), min(int((T.f - rr.y + hy) // 10) + 1, H)
    lf.append(np.nanmean(LF[:, r0:r1, c0:c1].reshape(5, -1), axis=1) if (c1 > c0 and r1 > r0) else np.full(5, np.nan))
lf = np.array(lf)  # month-end fallen share for Dec, Jan, Feb, Mar, Apr (0-100)
# interpolate to the date: anchors at month ends (Nov 30 = 0, Dec 31, Jan 31, Feb 28, Mar 31, Apr 30), 100 after
doy = v.t.dt.dayofyear.values.astype(float)            # Jan-May only
xa = np.array([-31, 0, 31, 59, 90, 120, 151])           # Nov30, Dec31, Jan31, Feb28, Mar31, Apr30, May31 (day of year)
fallen = np.array([np.interp(d, xa, np.r_[0, row, 100]) if np.isfinite(row).all() else np.nan for d, row in zip(doy, lf)]) / 100
v['fallen'] = fallen
v = v.dropna(subset=['fallen', 'canopy'])
v['can'] = v.canopy / 100                         # 0-1
v['leafy'] = v.can * (1 - v.fallen)               # leafy crown cover now, 0-1
v['i4'] = v.bright_ti4.where(~v.sat_i4.astype(bool)); v['i5'] = v.bright_ti5; v['i45'] = v.i4 - v.i5
v['lfrp'] = np.log(v.frp)
v['night'] = (v.daynight == 'N').astype(int)
out = {'detections': len(v), 'leafy_mean_by_month': v.groupby(v.t.dt.month).leafy.mean().round(3).to_dict(),
       'fallen_median_by_month': v.groupby(v.t.dt.month).fallen.median().round(3).to_dict()}
print(out)
res = {}
for name, d in [('day', v[v.night == 0]), ('night', v[v.night == 1])]:
    d = d[d.groupby('pass').frp.transform('size') >= 3].copy()
    for c in ['lfrp', 'i4', 'i5', 'i45', 'lpix', 'burnt_now', 'can', 'leafy']:
        d[c + '_d'] = d[c] - d.groupby('pass')[c].transform('mean')
    for y in ['lfrp', 'i4', 'i5', 'i45']:
        dd = d.dropna(subset=[y + '_d'])
        m = smf.ols(f'{y}_d ~ lpix_d + burnt_now_d + can_d + leafy_d - 1', dd).fit(cov_type='cluster', cov_kwds={'groups': pd.factorize(dd['pass'])[0]})
        res[f'{name}|{y}'] = dict(n=int(m.nobs), passes=int(dd['pass'].nunique()),
                                  leafy=round(m.params.leafy_d, 4), leafy_ci=m.conf_int().loc['leafy_d'].round(4).tolist(), leafy_p=round(m.pvalues.leafy_d, 4),
                                  canopy=round(m.params.can_d, 4), canopy_ci=m.conf_int().loc['can_d'].round(4).tolist())
out['models'] = res
for k, r in res.items(): print(k, r)
# plain-number version for FRP: full closed canopy (cover 1) leafy vs bare, and vs open ground
for name in ['day', 'night']:
    r = res[f'{name}|lfrp']
    out[f'{name}_frp_factor_full_leafy_crown'] = [round(float(np.exp(r['leafy'])), 3), [round(float(np.exp(x)), 3) for x in r['leafy_ci']]]
    out[f'{name}_frp_factor_closed_bare_vs_open'] = round(float(np.exp(r['canopy'])), 3)
    out[f'{name}_frp_factor_closed_leafy_vs_open'] = round(float(np.exp(r['canopy'] + r['leafy'])), 3)
# simple table: within-pass FRP gap closed (>=60%) vs open (<20%) by month
v['grp'] = np.select([v.can >= .6, v.can < .2], ['closed', 'open'], 'mid')
for c in ['lfrp', 'lpix']:
    v[c + '_d'] = v[c] - v.groupby('pass')[c].transform('mean')
v = v[v.groupby('pass').frp.transform('size') >= 3]
v['adj'] = v.lfrp_d - v.lpix_d
tab = v[v.grp != 'mid'].groupby([v.t.dt.month, 'grp']).adj.agg(['mean', 'size']).unstack()
gap = (np.exp(tab['mean']['closed'] - tab['mean']['open'])).round(3)
leaf = v[v.grp == 'closed'].groupby(v.t.dt.month).fallen.median()
T2 = pd.DataFrame({'closed_vs_open_FRP': gap, 'n_closed': tab['size']['closed'], 'n_open': tab['size']['open'],
                   'leaves_fallen_closed': leaf.round(2)})
print(T2); out['month_table'] = T2.reset_index().to_dict('records')
json.dump(out, open(f'{RES}/crown_tests.json', 'w'), indent=1, default=float)

import matplotlib; matplotlib.use('Agg'); import matplotlib.pyplot as plt
fig, ax = plt.subplots(1, 2, figsize=(11, 4))
mm = T2.index.values
ax[0].bar(mm, 100 * (T2.closed_vs_open_FRP - 1), color='tab:green'); ax[0].axhline(0, color='k', lw=.8)
ax[0].set_xticks(mm, ['Jan', 'Feb', 'Mar', 'Apr', 'May'][:len(mm)])
for x, l in zip(mm, T2.leaves_fallen_closed): ax[0].text(x, 2, f'{int(100 * l)}%\nfallen', ha='center', fontsize=8)
ax[0].set_ylabel('FRP under closed canopy vs open ground (%)'); ax[0].set_title('Same pass: closed-forest fires vs open-ground fires', fontsize=10)
labs = ['FRP', 'I4 3.7um', 'I5 11um', 'I4-I5']
for i, nm in enumerate(['day', 'night']):
    vals = [(np.exp(res[f'{nm}|lfrp']['leafy']) - 1) * 100] + [res[f'{nm}|{y}']['leafy'] for y in ['i4', 'i5', 'i45']]
    ax[1].bar(np.arange(4) + (i - .5) * .38, vals, .38, label=nm)
ax[1].axhline(0, color='k', lw=.8); ax[1].set_xticks(range(4), ['FRP (%)', 'I4 (K)', 'I5 (K)', 'I4-I5 (K)'])
ax[1].set_title('Effect of full leafy crowns overhead\n(vs the same canopy with bare branches)', fontsize=10); ax[1].legend()
fig.tight_layout(); fig.savefig(f'{HERE}/figures/crown_effect.png', dpi=110)
