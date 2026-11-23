"""Last round on the Jan-Feb department-burn capture (20 Oct). Four questions, all from files already made:
 A. Targeting: does the department burn the ground that burns most later? (pre-15 Feb clusters inside repeat patches vs not;
    within-division repeat rate of burnt vs unburnt patches; share of department burning that lands in any repeat patch
    against the share of later wildfire that does)
 B. Spillover: does a department burn in a patch lower fire in neighbouring patches (within 2 km) that season?
    Two-way FE on patch-seasons (patch + division-season), own burn and neighbour burn together.
 C. Habit: once a patch is burnt early, how often is it burnt early again next season?
 D. Money vs activity: CAMPA 2025-26 fire-line and watcher budget per division against captured pre-15 Feb burning 2023-26.
Out: out/d6_targeting.csv, d6_spillover.csv, d6_habit.csv, d6_budget_vs_activity.csv"""
import os, numpy as np, pandas as pd, geopandas as gpd
from scipy.stats import spearmanr, mannwhitneyu
S = '/mnt/project-files/ratapani/fsi/scouting/'; HERE = os.path.dirname(os.path.abspath(__file__)); OUT = HERE + '/out/'
P = gpd.read_file(S + 'code/joint_plan/out/j1_patches.geojson').to_crs(32643)
P['patchid'] = P.key + '_' + P.patch.astype(str)
C = pd.read_csv(OUT + 'viirs_clusters_jan_feb.csv'); C = C[C.pre15 & C.season.between(2017, 2026)]
G = gpd.GeoDataFrame(C, geometry=gpd.points_from_xy(C.lon, C.lat), crs=4326).to_crs(32643)
J = gpd.sjoin(G, P[['patchid', 'geometry']], how='left', predicate='within')
J = J[~J.index.duplicated()]
in_patch = J.patchid.notna()
# later wildfire points (15 Feb - 15 Jun, type 0, 2017-26) inside patches, for the same share
V = pd.read_parquet(S + 'code/mp_types/out/viirs_vtm.parquet', columns=['latitude', 'longitude', 'season', 'doy', 'type'])
V = V[(V.type == 0) & V.season.between(2017, 2026) & (V.doy >= 46) & (V.doy <= 166)]
GV = gpd.GeoDataFrame(V, geometry=gpd.points_from_xy(V.longitude, V.latitude), crs=4326).to_crs(32643)
JV = gpd.sjoin(GV, P[['patchid', 'geometry']], how='left', predicate='within'); JV = JV[~JV.index.duplicated()]
rows = [dict(item='pre-15 Feb burn clusters inside a repeat patch', share=in_patch.mean(), n=len(J)),
        dict(item='later wildfire points (15 Feb-15 Jun) inside a repeat patch', share=JV.patchid.notna().mean(), n=len(JV)),
        dict(item='control-like clusters inside a repeat patch', share=in_patch[J.flag.values].mean(), n=int(J.flag.sum()))]
# within-division: patches the department burnt early (any pre-15 Feb cluster 2017-26) vs never, repeat rate 2017-25 and plan benefit
pb = J[in_patch].groupby('patchid').season.nunique().rename('seasons_burnt')
Q = P.merge(pb, left_on='patchid', right_index=True, how='left').fillna({'seasons_burnt': 0})
Q['burnt'] = Q.seasons_burnt > 0
def within(col):
    d = Q[[col, 'key', 'burnt']].dropna(); d['pct'] = d.groupby('key')[col].rank(pct=True)
    a, b = d[d.burnt].pct, d[~d.burnt].pct
    return dict(measure=col, burnt_patches=len(a), mean_pct_rank_burnt=a.mean(), mean_pct_rank_never=b.mean(), p=mannwhitneyu(a, b).pvalue)
T = pd.DataFrame([within(c) for c in ('burnt_share_per_season_2017_25', 'burnt_share_per_season_2022_25', 'benefit_per_100ha', 'forest_ha')])
print(pd.DataFrame(rows).round(3).to_string(index=False)); print(T.round(3).to_string(index=False))
pd.concat([pd.DataFrame(rows), T], axis=0).to_csv(OUT + 'd6_targeting.csv', index=False)
# how many of the first-programme patches a division burns are its own top ones: share of burnt patches in top quartile of repeat rate
Q['top_q'] = Q.groupby('key').burnt_share_per_season_2017_25.rank(pct=True) > 0.75
print('burnt patches in own division top quartile of repeat rate:', round(Q[Q.burnt].top_q.mean(), 3), 'never-burnt:', round(Q[~Q.burnt].top_q.mean(), 3))

# B. spillover ------------------------------------------------------------------------------------------------
N = pd.read_csv(S + 'code/newq/out/n7_patch_seasons.csv'); N['patchid'] = N.key + '_' + N.patch.astype(str)
N['own'] = (N.early_clusters > 0).astype(int)          # calibrated on Ratapani: every pre-15 Feb cluster counts as department
cent = P.set_index('patchid').geometry.centroid
from scipy.spatial import cKDTree
ids = cent.index.values; xy = np.c_[cent.x.values, cent.y.values]; tree = cKDTree(xy)
pairs = tree.query_pairs(2000.0, output_type='ndarray')
nb = {}
for a, b in pairs: nb.setdefault(ids[a], []).append(ids[b]); nb.setdefault(ids[b], []).append(ids[a])
own = N.set_index(['patchid', 'season']).own
N['nb_burnt'] = [int(any(own.get((q, s), 0) for q in nb.get(p, []))) for p, s in zip(N.patchid, N.season)]
N['has_nb'] = N.patchid.map(lambda p: len(nb.get(p, [])) > 0).astype(int)
def twfe(df, cols):
    d = df.copy(); d['ds'] = d.key + '_' + d.season.astype(str); y = d.late_share.values.astype(float); X = d[cols].values.astype(float); w = d.forest_ha.values
    for _ in range(30):
        for col in ('ds', 'patchid'):
            g = d[col].values; m = pd.DataFrame(np.c_[y, X]).groupby(g).transform('mean').values; y = y - m[:, 0]; X = X - m[:, 1:]
    Xw = X * w[:, None]; return np.linalg.lstsq(Xw.T @ X, Xw.T @ y, rcond=None)[0]
M = N[N.has_nb == 1]
b = twfe(M, ['own', 'nb_burnt']); rng = np.random.default_rng(0); keys = M.key.unique(); bs = []
for _ in range(100):
    pick = rng.choice(keys, len(keys)); bs.append(twfe(pd.concat([M[M.key == k] for k in pick]), ['own', 'nb_burnt']))
bs = np.array(bs); base = M.late_share.mean()
R = pd.DataFrame(dict(term=['own patch burnt early', 'a neighbour patch (<2 km) burnt early'], patch_seasons=[int(M.own.sum()), int(M.nb_burnt.sum())],
                      effect_points=b, ci_lo=np.percentile(bs, 2.5, axis=0), ci_hi=np.percentile(bs, 97.5, axis=0), relative=b / base, base_later_burnt_share=base))
print(R.round(4).to_string(index=False)); R.to_csv(OUT + 'd6_spillover.csv', index=False)

# C. habit ----------------------------------------------------------------------------------------------------
W = J[in_patch].groupby(['patchid', 'season']).size().unstack(fill_value=0) > 0
yrs = sorted(W.columns); hab = []
for y in yrs[:-1]:
    a = W[y]; nxt = W[y + 1] if y + 1 in W.columns else None
    if nxt is None: continue
    hab.append(dict(season=y, burnt=int(a.sum()), burnt_again_next=float(nxt[a].mean()), base_next=float(nxt[~a].mean())))
H = pd.DataFrame(hab); print(H.round(3).to_string(index=False)); H.to_csv(OUT + 'd6_habit.csv', index=False)
cnt = W.sum(axis=1); print('patches burnt early in 1/2/3+ seasons of 2017-26:', (cnt == 1).sum(), (cnt == 2).sum(), (cnt >= 3).sum())

# D. money vs activity ----------------------------------------------------------------------------------------
B8 = pd.read_csv(S + 'code/newq/out/n8_budget_vs_burning.csv').dropna(subset=['key'])
D = pd.read_csv(OUT + 'jan_feb_by_division_season.csv'); D = D[D.season.between(2023, 2026)]
act = D.groupby('Division').agg(pre15_clusters_yr=('pre15_clusters', 'mean'), control_like_yr=('control_like', 'mean')).reset_index().rename(columns={'Division': 'key'})
X = B8.merge(act, on='key', how='inner')
out = []
for a in ('lakh', 'watchers_lakh', 'watchers_n'):
    for b in ('pre15_clusters_yr', 'control_like_yr', 'burnt_forest_ha_yr'):
        r, p = spearmanr(X[a], X[b]); out.append(dict(budget=a, against=b, spearman=r, p=p, divisions=len(X)))
X['lakh_per_cluster'] = X.lakh / X.pre15_clusters_yr.clip(lower=1)
print(pd.DataFrame(out).round(3).to_string(index=False))
print(X.sort_values('pre15_clusters_yr', ascending=False)[['key', 'lakh', 'watchers_n', 'pre15_clusters_yr', 'burnt_forest_ha_yr']].head(12).round(1).to_string(index=False))
print(X.sort_values('lakh', ascending=False)[['key', 'lakh', 'watchers_n', 'pre15_clusters_yr', 'burnt_forest_ha_yr']].head(8).round(1).to_string(index=False))
pd.DataFrame(out).to_csv(OUT + 'd6_budget_vs_activity.csv', index=False); X.to_csv(OUT + 'd6_budget_vs_activity_divisions.csv', index=False)
