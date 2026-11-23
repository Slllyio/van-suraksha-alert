"""Step 13. Why does burnt ground protect 0.05x in some divisions and 0.7x in others? Per-division re-burn ratio (2-12 wk after
the burn, deep inside the scar) with bootstrap CI, split by the month the ground burnt (15-28 Feb / Mar / Apr-Jun), against the
division's forest types, leaf-fall timing, fire density, fire size, scar detection (code/mp_types/out/division_types_final.csv).
Hypothesis to test: sal sheds late (half its leaf fall after 7 Feb), so ground burnt in February gets fresh litter and can burn again.
Out: out/cb13_division.csv (per division), out/cb13_corr.csv (correlations), out/cb13_groups.csv (by dominant type)."""
import os, sys
import numpy as np, pandas as pd
from scipy import stats
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cb0 as B
from cb2_ratios import smr, NA

D = pd.read_parquet(B.OUT + 'cb1_classes.parquet'); M = D[D.set == 'main']
age_of = {2 + a * 3 + m: B.AGE_LAB[a] for a in range(NA) for m in range(3)}
mon_of = {2 + a * 3 + m: B.MON_LAB[m] for a in range(NA) for m in range(3) if B.AGE_LAB[a] in ('2-4 wk', '4-6 wk', '6-8 wk', '8-12 wk')}
pool = {k: '2-12 wk' for k in mon_of}
R = smr(M, 0, pool, nboot=300, by='key'); R['key'] = R.g.str.split('|').str[0]; R = R.drop(columns='g').rename(columns={'ratio': 'ratio_2_12wk', 'lo': 'lo', 'hi': 'hi'})
RM = smr(M, 0, mon_of, nboot=200, by='key'); RM['key'] = RM.g.str.split('|').str[0]; RM['mon'] = RM.g.str.split('|').str[1]
pv = RM.pivot(index='key', columns='mon', values='ratio').rename(columns={'15-28 Feb': 'ratio_feb_burn', 'Mar': 'ratio_mar_burn', 'Apr-Jun': 'ratio_apr_burn'})
pe = RM.pivot(index='key', columns='mon', values='expected').rename(columns={'15-28 Feb': 'exp_feb', 'Mar': 'exp_mar', 'Apr-Jun': 'exp_apr'})
T = pd.read_csv('/mnt/project-files/ratapani/fsi/scouting/code/mp_types/out/division_types_final.csv')
X = R.merge(pv, left_on='key', right_index=True, how='left').merge(pe, left_on='key', right_index=True, how='left').merge(T, left_on='key', right_on='Division', how='left')
# mean fire size and burnt share per division from the scar panel
Q = pd.read_parquet(B.OUT + 'cb3_squares.parquet'); q = Q.groupby('key').agg(forest_ha=('forest_ha', 'sum'), ha=('ha_late', 'sum')); q = q.assign(forest_ha=q.forest_ha / 9, burnt_pct=100 * q.ha / q.forest_ha)
S = pd.read_csv(B.OUT + 'cb3_sizes.csv').groupby('key').agg(fire_med_ha=('ha', 'median'), fire_p90_ha=('ha', lambda s: s.quantile(.9)))
X = X.merge(q[['burnt_pct']], left_on='key', right_index=True, how='left').merge(S, left_on='key', right_index=True, how='left')
X = X.sort_values('ratio_2_12wk'); X.to_csv(B.OUT + 'cb13_division.csv', index=False)
W = X[X.expected >= 20].copy(); print('divisions with expected >= 20:', len(W))
print(W[['key', 'pts', 'expected', 'ratio_2_12wk', 'lo', 'hi', 'ratio_feb_burn', 'ratio_mar_burn', 'ratio_apr_burn', 'dominant', 'sal', 'teak', 'leaf_d50', 'leaf_f_15feb', 'pts_per_100km2_yr', 'scar_found_fire', 'fire_med_ha', 'burnt_pct']].round(3).to_string(index=False))
cov = ['sal', 'teak', 'dry_mixed', 'moist_mixed', 'degraded', 'bamboo', 'north_dry', 'leaf_d50', 'leaf_f_15feb', 'leaf_ndvi_dry', 'pts_per_100km2_yr', 'repeat_burn_share', 'frp_med', 'night_share', 'scar_found_fire', 'fire_med_ha', 'fire_p90_ha', 'burnt_pct', 'doy_med', 'share_before_15feb', 'forest_km2']
rows = []
for c in cov:
    v = W[[c, 'ratio_2_12wk']].dropna()
    if len(v) < 10: continue
    rho, p = stats.spearmanr(v[c], v.ratio_2_12wk); rows.append(dict(covariate=c, n=len(v), spearman=rho, p=p))
C = pd.DataFrame(rows).sort_values('p'); C.to_csv(B.OUT + 'cb13_corr.csv', index=False); print(C.round(3).to_string(index=False))
# by dominant type, pooled points / expected (weighted) and median of division ratios
g = W.groupby('dominant').apply(lambda d: pd.Series(dict(divisions=len(d), pooled_ratio=d.pts.sum() / d.expected.sum(), median_ratio=d.ratio_2_12wk.median(),
                                                        feb_burn_pooled=d.pts.sum() * 0 + (RM[(RM.key.isin(d.key)) & (RM.mon == '15-28 Feb')].pts.sum() / max(RM[(RM.key.isin(d.key)) & (RM.mon == '15-28 Feb')].expected.sum(), 1e-9)),
                                                        mar_burn_pooled=RM[(RM.key.isin(d.key)) & (RM.mon == 'Mar')].pts.sum() / max(RM[(RM.key.isin(d.key)) & (RM.mon == 'Mar')].expected.sum(), 1e-9),
                                                        apr_burn_pooled=RM[(RM.key.isin(d.key)) & (RM.mon == 'Apr-Jun')].pts.sum() / max(RM[(RM.key.isin(d.key)) & (RM.mon == 'Apr-Jun')].expected.sum(), 1e-9)))).reset_index()
g.to_csv(B.OUT + 'cb13_groups.csv', index=False); print(g.round(3).to_string(index=False))
# sal share split: ratio of Feb-burnt ground in sal-heavy (>=30%) vs sal-poor divisions
for lab, m in (('sal >= 30%', W.sal >= 0.3), ('sal < 10%', W.sal < 0.1)):
    d = W[m]; ks = d.key
    for mon in B.MON_LAB:
        r = RM[(RM.key.isin(ks)) & (RM.mon == mon)]; print(lab, mon, 'divisions', len(d), 'ratio', round(r.pts.sum() / max(r.expected.sum(), 1e-9), 3), 'expected', round(r.expected.sum()))
