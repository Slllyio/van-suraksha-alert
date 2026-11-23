import pandas as pd, numpy as np
lab=pd.read_parquet('/mnt/project-files/ratapani/labels_v3/labels_v3.parquet',columns=['season','date','cell_id','pos_main','fire_day'])
vt=pd.read_csv('/mnt/project-files/ratapani/fsi/scouting/data/vtm_roy2015_grid500m.csv')
v=pd.read_parquet('/mnt/project-files/ratapani/fsi/scouting/data/viirs_cells.parquet',columns=['cell_id','year','month','date','season','forest_frac'])
# burned seasons per cell: any pos_main in season
b=lab[lab.pos_main].groupby(['cell_id','season']).date.min().reset_index()
b['doy']=b.date.dt.dayofyear
ns=lab.season.nunique()
per=b.groupby('cell_id').agg(n_burn=('season','nunique'),med_doy=('doy','median')).reindex(vt.cell_id).fillna({'n_burn':0})
vt=vt.set_index('cell_id').join(per)
vv=v.groupby('cell_id').size().rename('viirs_n'); vt=vt.join(vv).fillna({'viirs_n':0})
vt['ff']=v.groupby('cell_id').forest_frac.first()
vt['burn_frac']=vt.n_burn/ns
cls=['teakmix_moist','dry_decid','moist_decid','degraded','agri']
print('seasons',ns, sorted(lab.season.unique()))
g=vt[vt.vtm_major.isin(cls)].groupby('vtm_major').agg(cells=('n_burn','size'),burn_frac=('burn_frac','mean'),any_burn=('n_burn',lambda s:(s>0).mean()),viirs_per_cell=('viirs_n','mean'),first_burn_doy_med=('med_doy','median'))
print(g.round(3).to_string())
# pure cells only (>=0.8 of class)
for c in ['teakmix_moist','dry_decid','moist_decid','degraded']:
    s=vt[vt[c]>=0.8]
    print(c,'pure>=0.8 n',len(s),'burn_frac',round(s.burn_frac.mean(),3),'viirs/cell',round(s.viirs_n.mean(),2),'first-burn doy med',s.med_doy.median())
import geopandas as gpd
g=gpd.read_file('/mnt/project-files/ratapani/grid_500m.geojson').set_index('cell_id')
c=g.to_crs(32643).centroid.to_crs(4326); vt['lon']=c.x.reindex(vt.index); vt['lat']=c.y.reindex(vt.index)
vt['ffrac']=g.forest_frac.reindex(vt.index)
s=vt[vt.vtm_major.isin(['teakmix_moist','dry_decid'])&(vt.ffrac>=0.9)].copy()
s['lonbin']=pd.qcut(s.lon,5); s['latbin']=pd.qcut(s.lat,3)
t=s.groupby(['lonbin','vtm_major'],observed=True).burn_frac.agg(['mean','size']).unstack()
print(t.round(3).to_string())
t2=s.groupby(['latbin','lonbin','vtm_major'],observed=True).burn_frac.mean().unstack().dropna()
print('strata with both:',len(t2),' mean diff (teak - dry):',round((t2.teakmix_moist-t2.dry_decid).mean(),3),' strata teak lower:',int((t2.teakmix_moist<t2.dry_decid).sum()))
import statsmodels.formula.api as smf
s['teak']=(s.vtm_major=='teakmix_moist').astype(int)
m=smf.ols('burn_frac ~ teak + C(lonbin) + C(latbin)',data=s).fit(cov_type='HC1'); print(m.params['teak'].round(3), m.bse['teak'].round(3), 'n',len(s))
