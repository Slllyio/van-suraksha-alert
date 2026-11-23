"""Calibrate the VIIRS control-like sort on Ratapani, the one division with January scar outlines. Every Jan-14 Feb VIIRS cluster
in Ratapani 2017-25 is matched to the scar fire (if any) within 750 m and +-3 days; the scar's class (block / strip / hot) is the
reference. Precision of the flag = share of flagged clusters whose scar is a department-like block or strip; recall = share of
department-like scar fires with a flagged cluster. Out: out/calibration_ratapani.csv"""
import os, numpy as np, pandas as pd, geopandas as gpd
HERE = os.path.dirname(os.path.abspath(__file__)); OUT = HERE + '/out/'
C = pd.read_csv(OUT + 'viirs_clusters_jan_feb.csv'); C = C[(C.Division == 'Obedullahganj') & (C.season >= 2017) & C.pre15].copy(); C['date'] = pd.to_datetime(C.date)
F = pd.read_csv(OUT + 'scar_fires_jan_feb.csv'); F = F[(F.key == 'Obedullahganj') & F.pre15].copy(); F['date'] = pd.to_datetime(F.date)
GC = gpd.GeoDataFrame(C, geometry=gpd.points_from_xy(C.lon, C.lat), crs=4326).to_crs(32643); GF = gpd.GeoDataFrame(F, geometry=gpd.points_from_xy(F.lon, F.lat), crs=4326).to_crs(32643)
GF['geometry'] = GF.buffer(np.sqrt(GF.ha * 1e4 / np.pi) + 750)
J = gpd.sjoin(GC, GF[['fire', 'date', 'cls', 'ha', 'dept_like', 'geometry']], how='left', predicate='within', lsuffix='c', rsuffix='f')
J = J[(J.fire.isna()) | ((J.date_c - J.date_f).dt.days.abs() <= 3)]
J = J.sort_values('ha', ascending=False).drop_duplicates('cid')
J['scar_class'] = J.cls_f.fillna('no scar (too small or unseen)')
t = pd.crosstab(J.flag, J.scar_class); print(t)
flagged = J[J.flag]; print('flagged clusters', len(flagged), 'with a scar', flagged.fire.notna().mean().round(2), 'scar dept-like given a scar', flagged[flagged.fire.notna()].dept_like.mean().round(2))
unfl = J[~J.flag]; print('unflagged clusters', len(unfl), 'with a scar', unfl.fire.notna().mean().round(2), 'scar dept-like given a scar', unfl[unfl.fire.notna()].dept_like.mean().round(2))
# recall: scar fires with a flagged cluster
JF = gpd.sjoin(GF[['fire', 'date', 'cls', 'ha', 'dept_like', 'geometry']], GC[['cid', 'date', 'flag', 'geometry']], how='left', predicate='contains', lsuffix='f', rsuffix='c')
JF = JF[(JF.cid.isna()) | ((JF.date_c - JF.date_f).dt.days.abs() <= 3)]
r = JF.groupby('fire').agg(cls=('cls', 'first'), ha=('ha', 'first'), any_cluster=('cid', lambda s: s.notna().any()), any_flag=('flag', lambda s: bool(s.fillna(False).any()))).reset_index()
print(r.groupby('cls').agg(fires=('fire', 'size'), ha_med=('ha', 'median'), with_cluster=('any_cluster', 'mean'), with_flag=('any_flag', 'mean')).round(2))
pd.concat([t.reset_index(), r.groupby('cls').agg(fires=('fire', 'size'), with_cluster=('any_cluster', 'mean'), with_flag=('any_flag', 'mean')).reset_index()], axis=0).to_csv(OUT + 'calibration_ratapani.csv', index=False)
