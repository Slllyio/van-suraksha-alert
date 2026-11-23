"""New question 3. Why did some repeat patches cool? Per tr3 patch: burnt share per season 2017-21 (selection years) vs 2022-25;
'cooled' = 2017-21 >= 0.6 and 2022-25 < 0.25, 'held' = 2022-25 >= 0.5. Against: the division's own nine-season trend (regional),
early-season greenness change 2017-19 -> 2023-25 (Jan NDVI and NBR, HLS 500 m: canopy gone, or regrowth), and access / land-use
layers (roads, villages, farm share, forest edge, slope). Out: out/n3_patches.csv, out/n3_tests.csv"""
import os, sys
import numpy as np, pandas as pd, geopandas as gpd
from rasterio import features
from rasterio.transform import from_origin
from scipy import stats
HERE = os.path.dirname(os.path.abspath(__file__)); OUT = HERE + '/out/'
G = gpd.read_file('/mnt/project-files/ratapani/fsi/scouting/code/joint_plan/out/j1_patches.geojson').to_crs(32643)
G['s9'] = G.burnt_share_per_season_2017_25; G['s4'] = G.burnt_share_per_season_2022_25; G['s5'] = (9 * G.s9 - 4 * G.s4) / 5
G['change'] = G.s4 - G.s5
G['cls'] = np.where((G.s5 >= 0.6) & (G.s4 < 0.25), 'cooled', np.where(G.s4 >= 0.5, 'held', 'between'))
print(G.cls.value_counts().to_dict())
# patches -> 500 m cells
H, W = 1332, 1829; tr = from_origin(399000, 2996000, 500, 500)
ras = features.rasterize(((geom, i + 1) for i, geom in enumerate(G.geometry)), out_shape=(H, W), transform=tr, all_touched=True, dtype='int32')
rr, cc = np.nonzero(ras); cells = rr * W + cc; pid = ras[rr, cc] - 1
C = pd.DataFrame({'cell': cells, 'pidx': pid})
S = pd.read_parquet('/mnt/project-files/ratapani/mp_grid/static_gis_v1.parquet')
C = C.merge(S, on='cell', how='left'); print('patch cells', len(C), 'with static', C.elev.notna().sum())
# greenness: Jan steps (first three) mean NDVI and NBR per cell, early seasons vs late seasons
def jan(season):
    Z = np.load(f'/mnt/project-files/ratapani/mp_grid/dryness/mp_dry_{season}.npz'); X = Z['X'][:3].astype(float); X[X <= -9000] = np.nan; X[np.abs(X) > 10000] = np.nan
    m = np.nanmean(X, axis=0) / 10000
    return pd.DataFrame({'cell': Z['cells'], f'ndvi_{season}': m[:, 0], f'nbr_{season}': m[:, 2]})
for y in (2017, 2018, 2019, 2023, 2024, 2025):
    C = C.merge(jan(y), on='cell', how='left')
C['ndvi_early'] = C[['ndvi_2017', 'ndvi_2018', 'ndvi_2019']].mean(1); C['ndvi_late'] = C[['ndvi_2023', 'ndvi_2024', 'ndvi_2025']].mean(1)
C['nbr_early'] = C[['nbr_2017', 'nbr_2018', 'nbr_2019']].mean(1); C['nbr_late'] = C[['nbr_2023', 'nbr_2024', 'nbr_2025']].mean(1)
C['dndvi'] = C.ndvi_late - C.ndvi_early; C['dnbr'] = C.nbr_late - C.nbr_early
cov = ['elev', 'slope', 'road_km', 'road_km_5k', 'd_road', 'd_village', 'villages_5k', 'farm_5k', 'lc_farm', 'lc_degraded', 'lc_forest', 'd_edge_in', 'd_forest_out', 'settle_5k', 'ndvi_early', 'ndvi_late', 'dndvi', 'nbr_early', 'dnbr']
A = C.groupby('pidx')[cov].mean(); P = G.drop(columns='geometry').reset_index(drop=True).join(A)
T = pd.read_csv(OUT + 'n2_trend.csv')[['key', 'change_pct_per_yr_scar']]; P = P.merge(T, on='key', how='left')
P.to_csv(OUT + 'n3_patches.csv', index=False)
# state-wide forest reference for greenness change: all forest cells in static (lc_forest >= 0.8), not in patches
ref = S[(S.lc_forest >= 0.8) & ~S.cell.isin(C.cell)][['cell']]
for y in (2017, 2018, 2019, 2023, 2024, 2025): ref = ref.merge(jan(y), on='cell', how='left')
ref_d = (ref[['ndvi_2023', 'ndvi_2024', 'ndvi_2025']].mean(1) - ref[['ndvi_2017', 'ndvi_2018', 'ndvi_2019']].mean(1))
print('reference forest Jan NDVI change 2017-19 -> 2023-25: mean', round(ref_d.mean(), 4), 'median', round(ref_d.median(), 4), 'n', ref_d.notna().sum())
rows = []
for c in cov + ['change_pct_per_yr_scar', 'forest_ha']:
    d = P[P.cls.isin(['cooled', 'held'])].dropna(subset=[c])
    a = d[d.cls == 'cooled'][c]; b = d[d.cls == 'held'][c]
    u = stats.mannwhitneyu(a, b).pvalue if len(a) > 5 and len(b) > 5 else np.nan
    # within-division: demean by division, then correlate with the change in burnt share over all patches
    dd = P.dropna(subset=[c]).copy(); dd['x'] = dd[c] - dd.groupby('key')[c].transform('mean'); dd['y'] = dd.change - dd.groupby('key').change.transform('mean')
    rho, p = stats.spearmanr(dd.x, dd.y)
    rows.append(dict(covariate=c, cooled_median=a.median(), held_median=b.median(), mannwhitney_p=u, within_division_spearman_with_change=rho, p=p, n=len(dd)))
R = pd.DataFrame(rows); R.to_csv(OUT + 'n3_tests.csv', index=False); print(R.round(4).to_string(index=False))
# how much of the cooling is the division: variance of change explained by division means
P2 = P.dropna(subset=['change']); dm = P2.groupby('key').change.transform('mean'); print('share of patch change variance that is division-level:', round(1 - ((P2.change - dm) ** 2).sum() / ((P2.change - P2.change.mean()) ** 2).sum(), 3))
print(P.groupby('cls')[['dndvi', 'dnbr', 'ndvi_early', 'd_village', 'road_km_5k', 'farm_5k', 'forest_ha']].median().round(4))
