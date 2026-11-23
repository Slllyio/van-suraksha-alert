"""Checks on h13. (1) Same-fire pairs, one crown variable at a time, and the difference-in-differences with fire-
bootstrap ranges. (2) Censoring: bigger oblique pixels need a stronger fire to trigger a detection, so weakened
(blocked) fires under leafy crowns should drop OUT of the detections at oblique angles: their share of detections
should fall with angle. Out: results/view_angle_checks.json"""
import json, numpy as np, pandas as pd
import statsmodels.formula.api as smf
from h0_lib import RES, r_clock
G = pd.read_csv(f'{RES}/det_geom.csv', parse_dates=['t'])
out = {}
F = G.dropna(subset=['fire', 'leafy']).copy(); F['fire'] = F.fire.astype(int)
P = F.groupby(['fire', 'sensor', 't']).apply(lambda g: pd.Series(dict(frp=g.frp.sum(), sec=np.average(g.sec, weights=g.frp),
                                                                       leafy=g.leafy.mean(), can=g.canopy01.mean())), include_groups=False).reset_index().sort_values(['fire', 't'])
rows = []
for fire, g in P.groupby('fire'):
    g = g.reset_index(drop=True)
    for i in range(len(g) - 1):
        a, b = g.iloc[i], g.iloc[i + 1]; dt = (b.t - a.t).total_seconds() / 60
        if a.sensor != b.sensor and 20 <= dt <= 100:
            rows.append(dict(fire=fire, y=np.log(b.frp / a.frp) - np.log(r_clock(b.t)[0] / r_clock(a.t)[0]), dsec=b.sec - a.sec,
                             leafy=(a.leafy + b.leafy) / 2, can=(a.can + b.can) / 2, pair=f'{a.sensor}>{b.sensor}'))
Q = pd.DataFrame(rows)
for term in ['leafy', 'can']:
    m = smf.ols(f'y ~ C(pair) + dsec + dsec:{term}', Q).fit(cov_type='cluster', cov_kwds={'groups': Q.fire})
    out[f'A_single_{term}'] = [round(m.params[f'dsec:{term}'], 3), m.conf_int().loc[f'dsec:{term}'].round(3).tolist()]
# DiD: slope of y on dsec, leafy-closed minus open, fire bootstrap
op = Q[Q.can < .25]; lc = Q[(Q.can >= .5) & (Q.leafy >= .2)]; bc = Q[(Q.can >= .5) & (Q.leafy < .1)]
slope = lambda d: np.polyfit(d.dsec, d.y, 1)[0]
rng = np.random.default_rng(0)
def boot(d1, d0):
    f1, f0 = d1.fire.unique(), d0.fire.unique(); r = []
    for _ in range(500):
        s1 = d1.set_index('fire').loc[rng.choice(f1, len(f1))].reset_index(); s0 = d0.set_index('fire').loc[rng.choice(f0, len(f0))].reset_index()
        r.append(slope(s1) - slope(s0))
    return np.percentile(r, [2.5, 97.5]).round(3).tolist()
out['A_slope_open'] = round(slope(op), 3); out['A_slope_leafy_closed'] = round(slope(lc), 3); out['A_slope_bare_closed'] = round(slope(bc), 3)
out['A_extra_slope_leafy_vs_open'] = [round(slope(lc) - slope(op), 3), boot(lc, op)]
out['A_extra_slope_bare_vs_open'] = [round(slope(bc) - slope(op), 3), boot(bc, op)]
out['A_n'] = dict(open=len(op), leafy_closed=len(lc), bare_closed=len(bc))
print({k: v for k, v in out.items() if k.startswith('A')})
# (2) composition of detections by angle
D = G.dropna(subset=['leafy']).copy()
D['grp'] = np.select([D.canopy01 < .25, (D.canopy01 >= .5) & (D.leafy >= .2), (D.canopy01 >= .5) & (D.leafy < .1)], ['open', 'closed_leafy', 'closed_bare'], 'other')
D['sb'] = pd.cut(D.sec, [0.99, 1.15, 1.4, 1.8, 3], labels=['<30 deg', '30-45', '45-56', '>56 deg'])
D['night'] = D.t.dt.hour.between(17, 23) | D.t.dt.hour.between(0, 1)   # VIIRS night passes ~19-21 UTC
comp = pd.crosstab(D.sb, D.grp, normalize='index').round(4)
print(comp); out['composition_by_angle'] = comp.reset_index().astype(str).to_dict('records')
# leafy-closed share relative to bare-closed share (both closed forest; only the leaves differ)
r = (comp['closed_leafy'] / comp['closed_bare']).round(3); out['leafy_over_bare_by_angle'] = r.astype(float).to_dict()
print('leafy-closed / bare-closed detections by angle:', r.to_dict())
m = smf.logit('y ~ sec', D[D.grp.isin(['closed_leafy', 'open'])].assign(y=lambda d: (d.grp == 'closed_leafy').astype(int))).fit(disp=0)
out['logit_leafy_vs_open_per_sec'] = [round(m.params.sec, 3), m.conf_int().loc['sec'].round(3).tolist()]
m = smf.logit('y ~ sec', D[D.grp.isin(['closed_leafy', 'closed_bare'])].assign(y=lambda d: (d.grp == 'closed_leafy').astype(int))).fit(disp=0)
out['logit_leafy_vs_bare_per_sec'] = [round(m.params.sec, 3), m.conf_int().loc['sec'].round(3).tolist()]
print(out['logit_leafy_vs_open_per_sec'], out['logit_leafy_vs_bare_per_sec'])
json.dump(out, open(f'{RES}/view_angle_checks.json', 'w'), indent=1, default=float)
