"""Crown blocking measured through VIEWING ANGLE (Akkshay 17 Oct 07:48Z: "apply your fullest brain").

WHY THIS DESIGN. A surface fire under trees is seen through the gaps in the crowns. Light (here 3.7 um infrared) that
travels a slant path through a crown layer is cut as exp(-k x crown density x path length), and the path length through
the layer is 1/cos(view zenith) = sec(theta) (Beer-Lambert, the same law used for canopy gap fraction / LAI).
So IF crowns hide the fire, the hiding must GROW as the satellite looks more sideways. Nothing else in the question
depends on the viewing angle: fuel load, litter, grass, site moisture, background temperature of the place are the same
whether the satellite looks straight down or sideways. That makes angle the clean, fuel-free handle on blocking
(the leaf-fall test could not separate "leaf left the crown" from "leaf became litter").

VIEW ANGLE. VIIRS I-band along-track pixel size grows with the slant range R to the ground (375 m at nadir).
R = 829 km x track/375 m; scan angle alpha from the triangle earth-centre / satellite / pixel; view zenith theta at the
ground: sin(theta) = (Re + h)/Re x sin(alpha). Range here: theta 0 to ~68 deg, sec(theta) 1 to ~2.7.
CROWN DENSITY OVERHEAD. leafy = canopy cover x share of leaves still on the trees that day (per-pixel Sentinel-2 leaf
fall, h12). bare = canopy cover (stems and branches, always there).

TESTS
 A. Same fire, two VIIRS satellites 20-100 min apart, different angles (fuel identical by construction):
    change in log summed FRP (allowing for the burning clock) ~ change in sec(theta) x [1, leafy, canopy].
    Open-ground fires give the baseline angle effect (bigger pixels, detection limit); the extra drop under leafy
    crowns is blocking.
 B. All detections, compared within their own satellite pass (relative heat from h9), view angle varying between passes:
    relative heat ~ leafy + canopy + (leafy + canopy) x (sec(theta) - 1).
    The x(sec-1) terms = blocking that grows with path length; the plain terms = everything else (fuel, litter,
    background, crown at nadir).
 Readings: FRP, I4 (3.7 um, unsaturated), I5 (11 um).
Out: results/det_geom.csv, results/view_angle_tests.json, figures/view_angle.png
"""
import json, os
import numpy as np, pandas as pd, rasterio
import statsmodels.formula.api as smf
from h0_lib import RES, ROOT, HERE, layers, r_clock

RE, HS = 6371.0, 829.0
def view_zenith(track_m):
    R = HS * np.clip(np.asarray(track_m, float) / 375.0, 1, None)
    ca = ((RE + HS) ** 2 + R ** 2 - RE ** 2) / (2 * R * (RE + HS))
    a = np.arccos(np.clip(ca, -1, 1))
    return np.degrees(np.arcsin(np.clip((RE + HS) / RE * np.sin(a), 0, 1)))

f = f'{RES}/det_geom.csv'
if not os.path.exists(f):
    v = pd.read_csv(f'{RES}/viirs_det.csv', parse_dates=['t'])
    L = layers()
    with rasterio.open(f'{ROOT}/fuel-map/ratapani/leaf_fall_fraction_10m.tif') as r:
        LF = r.read().astype(float); T = r.transform; nd = r.nodata
    if nd is not None: LF[LF == nd] = np.nan
    H, W = LF.shape[1:]; xa = np.array([-31, 0, 31, 59, 90, 120, 151])
    can, fal = [], []
    for rr in v.itertuples():
        hx, hy = rr.scan_m / 2, rr.track_m / 2
        c0, c1 = max(int((rr.x - hx - T.c) // 10), 0), min(int((rr.x + hx - T.c) // 10) + 1, W)
        r0, r1 = max(int((T.f - rr.y - hy) // 10), 0), min(int((T.f - rr.y + hy) // 10) + 1, H)
        if c1 <= c0 or r1 <= r0: can.append(np.nan); fal.append(np.nan); continue
        can.append(np.nanmean(L['canopy'][r0 // 2 + 100:(r1 + 1) // 2 + 100, c0 // 2 + 100:(c1 + 1) // 2 + 100]) / 100)
        row = np.nanmean(LF[:, r0:r1, c0:c1].reshape(5, -1), axis=1)
        m = rr.t.month; d = rr.t.dayofyear if m <= 6 else rr.t.dayofyear - 365 - (rr.t.is_leap_year)
        if m in (7, 8, 9, 10): fal.append(np.nan)               # monsoon / leaf-on: outside the season
        else: fal.append(np.interp(d, xa, np.r_[0, row, 100]) / 100 if np.isfinite(row).all() else np.nan)
    v['canopy01'] = can; v['fallen'] = fal
    v['leafy'] = v.canopy01 * (1 - v.fallen)
    v['theta'] = view_zenith(v.track_m); v['sec'] = 1 / np.cos(np.radians(v.theta))
    v[['t', 'sensor', 'x', 'y', 'fire', 'frp', 'track_m', 'scan_m', 'theta', 'sec', 'canopy01', 'fallen', 'leafy']].to_csv(f, index=False)
G = pd.read_csv(f, parse_dates=['t'])
out = {'theta_quartiles': G.theta.quantile([.05, .25, .5, .75, .95]).round(1).tolist(), 'sec_max': round(G.sec.max(), 2)}
print(out)

# ---------- TEST A: same fire, two satellites ----------
F = G.dropna(subset=['fire', 'leafy']).copy(); F['fire'] = F.fire.astype(int)
P = F.groupby(['fire', 'sensor', 't']).apply(lambda g: pd.Series(dict(frp=g.frp.sum(), n=len(g), sec=np.average(g.sec, weights=g.frp),
                                                                       leafy=g.leafy.mean(), can=g.canopy01.mean())), include_groups=False).reset_index()
P = P.sort_values(['fire', 't']); rows = []
for fire, g in P.groupby('fire'):
    g = g.reset_index(drop=True)
    for i in range(len(g) - 1):
        a, b = g.iloc[i], g.iloc[i + 1]; dt = (b.t - a.t).total_seconds() / 60
        if a.sensor != b.sensor and 20 <= dt <= 100:
            rows.append(dict(fire=fire, y=np.log(b.frp / a.frp) - np.log(r_clock(b.t)[0] / r_clock(a.t)[0]), dsec=b.sec - a.sec,
                             leafy=(a.leafy + b.leafy) / 2, can=(a.can + b.can) / 2, pair=f'{a.sensor}>{b.sensor}'))
Q = pd.DataFrame(rows)
mA = smf.ols('y ~ C(pair) + dsec + dsec:leafy + dsec:can', Q).fit(cov_type='cluster', cov_kwds={'groups': Q.fire})
out['A'] = dict(pairs=len(Q), fires=int(Q.fire.nunique()), dsec_sd=round(Q.dsec.std(), 3),
                coef={k: [round(mA.params[k], 3), mA.conf_int().loc[k].round(3).tolist()] for k in ['dsec', 'dsec:leafy', 'dsec:can']})
# simple DiD table: pairs where the 2nd look is more oblique by > 0.3 sec vs less oblique, open vs leafy-closed
Q['grp'] = np.select([Q.can < .25, (Q.can >= .5) & (Q.leafy >= .2)], ['open ground', 'closed, leafy crowns'], 'other')
Q['dir'] = np.select([Q.dsec > .3, Q.dsec < -.3], ['2nd look more sideways', '2nd look more straight-down'], 'similar')
tA = Q[(Q.grp != 'other') & (Q.dir != 'similar')].groupby(['grp', 'dir']).y.agg(['size', 'mean']).reset_index()
tA['frp_factor'] = np.exp(tA['mean']).round(3)
print('A', out['A']); print(tA)
out['A_table'] = tA.drop(columns='mean').to_dict('records')

# ---------- TEST B: all detections, within pass ----------
D = pd.read_csv(f'{RES}/place_det.csv', parse_dates=['t'])
D = D.merge(G[['t', 'sensor', 'x', 'y', 'sec', 'theta', 'leafy', 'canopy01']], on=['t', 'sensor', 'x', 'y'], how='left').dropna(subset=['leafy', 'sec'])
D['i4'] = D.bright_ti4.where(~D.sat_i4.astype(bool)); D['i5'] = D.bright_ti5
for c in ['leafy', 'canopy01', 'i4', 'i5', 'lpix', 'burnt_now']:
    D[c + '_d'] = D[c] - D.groupby('pass')[c].transform('mean')
D['s1'] = D.sec - 1
D['night'] = (D.daynight == 'N').astype(int)
resB = {}
for y in ['rel', 'i4_d', 'i5_d']:
    for nm, d in [('all', D), ('day', D[D.night == 0]), ('night', D[D.night == 1])]:
        d = d.dropna(subset=[y])
        extra = '' if y == 'rel' else ' + lpix_d + burnt_now_d'
        m = smf.ols(f'{y} ~ leafy_d + canopy01_d + leafy_d:s1 + canopy01_d:s1{extra} - 1', d).fit(cov_type='cluster', cov_kwds={'groups': pd.factorize(d['pass'])[0]})
        resB[f'{y}|{nm}'] = {k: [round(m.params[k], 3), m.conf_int().loc[k].round(3).tolist()] for k in ['leafy_d', 'canopy01_d', 'leafy_d:s1', 'canopy01_d:s1']}
        resB[f'{y}|{nm}']['n'] = int(m.nobs)
for k, r in resB.items(): print('B', k, r)
out['B'] = resB
# what share of FRP is hidden for a closed (80%) stand, leafy (half leaves on) vs bare, at nadir and at the swath edge
b = resB['rel|all']
def hidden(leafy, can, sec):
    lg = b['leafy_d'][0] * leafy + b['canopy01_d'][0] * can + (b['leafy_d:s1'][0] * leafy + b['canopy01_d:s1'][0] * can) * (sec - 1)
    return round(float(1 - np.exp(lg)), 3)
out['B_hidden_share'] = {f'{lab}, {pos}': hidden(l, .8, s) for lab, l in [('closed 80%, half leaves on', .4), ('closed 80%, bare', 0.0), ('closed 80%, full leaf', .8)]
                         for pos, s in [('nadir', 1.0), ('mid swath (sec 1.4)', 1.4), ('edge (sec 2.3)', 2.3)]}
print(out['B_hidden_share'])
json.dump(out, open(f'{RES}/view_angle_tests.json', 'w'), indent=1, default=float)

import matplotlib; matplotlib.use('Agg'); import matplotlib.pyplot as plt
fig, ax = plt.subplots(1, 2, figsize=(12, 4.2))
D['sb'] = pd.cut(D.sec, [1, 1.15, 1.4, 1.8, 3], labels=['straight down\n(<30 deg)', '30-45 deg', '45-56 deg', 'sideways\n(>56 deg)'])
D['cg'] = np.select([D.canopy01 < .25, (D.canopy01 >= .5) & (D.leafy >= .2), (D.canopy01 >= .5) & (D.leafy < .1)],
                    ['open ground', 'closed, leafy crowns', 'closed, bare crowns'], 'other')
tb = D[D.cg != 'other'].groupby(['sb', 'cg'], observed=True).rel.mean().unstack()
gap_leafy = 100 * (np.exp(tb['closed, leafy crowns'] - tb['open ground']) - 1)
gap_bare = 100 * (np.exp(tb['closed, bare crowns'] - tb['open ground']) - 1)
x = np.arange(len(tb))
ax[0].bar(x - .2, gap_leafy, .4, label='closed, leafy crowns', color='tab:green'); ax[0].bar(x + .2, gap_bare, .4, label='closed, bare crowns', color='tab:brown')
ax[0].axhline(0, color='k', lw=.8); ax[0].set_xticks(x, tb.index.astype(str)); ax[0].set_ylabel('FRP vs open-ground fires in the same pass (%)')
ax[0].set_xlabel('satellite viewing angle'); ax[0].legend(fontsize=8); ax[0].set_title('Closed-forest heat deficit by viewing angle', fontsize=10)
lab = list(out['B_hidden_share'].keys()); vals = [100 * out['B_hidden_share'][k] for k in lab]
ax[1].barh(range(len(lab)), vals, color=['tab:green'] * 3 + ['tab:brown'] * 3 + ['darkgreen'] * 3); ax[1].set_yticks(range(len(lab)), lab, fontsize=8)
ax[1].axvline(0, color='k', lw=.8); ax[1].set_xlabel('% of fire heat hidden from the satellite (model B)'); ax[1].invert_yaxis()
ax[1].set_title('Fitted crown hiding', fontsize=10)
fig.tight_layout(); fig.savefig(f'{HERE}/figures/view_angle.png', dpi=110)
pd.DataFrame({'leafy_gap_pct': gap_leafy.round(1), 'bare_gap_pct': gap_bare.round(1), 'n_leafy': D[D.cg == 'closed, leafy crowns'].groupby('sb', observed=True).size(),
              'n_open': D[D.cg == 'open ground'].groupby('sb', observed=True).size()}).to_csv(f'{RES}/view_angle_table.csv')
print(pd.read_csv(f'{RES}/view_angle_table.csv'))
