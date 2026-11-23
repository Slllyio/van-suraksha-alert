"""Which of the plan's patches the department already burns early, and which it never has. Every Jan-Feb VIIRS cluster
2017-26 and scar fire 2017-25 from the capture is placed in the tr3 patch it falls in (j1_patches.geojson). Per patch: seasons
with any department-like early burn, seasons with any Jan-Feb burning, last season burnt early, count 2023-26; then the plan's
first programme (role_S3 burn, 465 patches) split into 'already burnt early by the department', 'burnt early some years',
'never': the gap list per division. Out: out/plan_patches_dept.csv, out/plan_gap_by_division.csv"""
import os, numpy as np, pandas as pd, geopandas as gpd
HERE = os.path.dirname(os.path.abspath(__file__)); OUT = HERE + '/out/'
P = gpd.read_file('/mnt/project-files/ratapani/fsi/scouting/code/joint_plan/out/j1_patches.geojson').to_crs(32643)
C = pd.read_csv(OUT + 'viirs_clusters_jan_feb.csv'); C = C[C.season >= 2017]
G = gpd.GeoDataFrame(C, geometry=gpd.points_from_xy(C.lon, C.lat), crs=4326).to_crs(32643)
J = gpd.sjoin(G, P[['key', 'patch', 'geometry']], how='inner', predicate='within')
J = J.reset_index(drop=True); J['dept'] = J.flag | (J.pre15 & (J.d_edge <= 100))
J['s_dept'] = np.where(J.dept, J.season, np.nan); J['s_pre15'] = np.where(J.pre15, J.season, np.nan); J['s_recent'] = np.where(J.dept & (J.season >= 2023), J.season, np.nan)
a = J.groupby(['key', 'patch']).agg(seasons_any=('season', 'nunique'), seasons_dept=('s_dept', 'nunique'), seasons_pre15=('s_pre15', 'nunique'), last_early=('season', 'max'), recent_dept=('s_recent', 'nunique'), clusters=('cid', 'size'), points=('n', 'sum')).reset_index()
F = pd.read_csv(OUT + 'scar_fires_jan_feb.csv'); GF = gpd.GeoDataFrame(F, geometry=gpd.points_from_xy(F.lon, F.lat), crs=4326).to_crs(32643)
JF = gpd.sjoin(GF, P[['key', 'patch', 'geometry']], how='inner', predicate='within', lsuffix='f', rsuffix='p').reset_index(drop=True); JF['dept_ha'] = np.where(JF.dept_like, JF.ha, 0.0)
b = JF.groupby(['key_p', 'patch']).agg(scar_jan_feb_ha=('ha', 'sum'), scar_dept_ha=('dept_ha', 'sum')).reset_index().rename(columns={'key_p': 'key'})
M = P.drop(columns='geometry').merge(a, on=['key', 'patch'], how='left').merge(b, on=['key', 'patch'], how='left').fillna({'seasons_any': 0, 'seasons_dept': 0, 'seasons_pre15': 0, 'recent_dept': 0, 'clusters': 0, 'points': 0, 'scar_jan_feb_ha': 0, 'scar_dept_ha': 0})
M['status'] = np.where(M.recent_dept >= 2, 'department burns it (2+ of 2023-26)', np.where(M.seasons_dept >= 1, 'burnt early some seasons', np.where(M.seasons_any >= 1, 'Jan-Feb fire, not department-like', 'never burnt early')))
M.to_csv(OUT + 'plan_patches_dept.csv', index=False)
for role in ('burn', 'lines'):
    d = M[M.role_S3 == role]; print(role, len(d)); print(d.status.value_counts().to_string()); print('forest ha by status', d.groupby('status').forest_ha.sum().round(0).to_dict())
B3 = M[M.role_S3 == 'burn'].copy(); B3['nev'] = B3.status.isin(['never burnt early', 'Jan-Feb fire, not department-like']); B3['nev_ha'] = np.where(B3.nev, B3.forest_ha, 0.0)
D = B3.groupby('division').agg(patches=('patch', 'size'), forest_ha=('forest_ha', 'sum'), dept_burns=('status', lambda s: (s == 'department burns it (2+ of 2023-26)').sum()), some=('status', lambda s: (s == 'burnt early some seasons').sum()), never=('nev', 'sum'), never_ha=('nev_ha', 'sum')).reset_index().sort_values('never_ha', ascending=False)
D.to_csv(OUT + 'plan_gap_by_division.csv', index=False); print(D.head(15).round(0).to_string(index=False))
print('all tr3 patches:', M.status.value_counts().to_dict())
