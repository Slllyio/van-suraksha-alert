import pandas as pd, geopandas as gpd, numpy as np
from scipy.stats import spearmanr
ig=pd.read_csv('/mnt/project-files/ratapani/fsi/scouting/data/ignition_points.csv')
ig=ig[(ig.event_role=='first_day_of_fire')&(ig.status=='ok')].copy()
ig['date']=pd.to_datetime(ig.date); ig['m']=ig.date.dt.month; ig['doy']=ig.date.dt.dayofyear
g=gpd.read_file('/mnt/project-files/ratapani/grid_500m.geojson')[['cell_id','forest_frac','geometry']]
p=gpd.GeoDataFrame(ig,geometry=gpd.points_from_xy(ig.ign_lon,ig.ign_lat),crs=4326).to_crs(g.crs)
p=gpd.sjoin(p,g,how='inner',predicate='within')
f=pd.read_csv('/mnt/project-files/ratapani/fsi/scouting/data/mahua/flush_cells.csv')
p=p.merge(f[['cell_id','flush_frac']],on='cell_id')
F=g.merge(f,on='cell_id'); F=F[F.forest_frac>0.5]
p=p[p.cell_id.isin(F.cell_id)]
F['q']=pd.qcut(F.flush_frac.rank(method='first'),5,labels=False)
qmap=dict(zip(F.cell_id,F.q)); p['q']=p.cell_id.map(qmap)
p['per']=np.select([p.date.dt.strftime('%m%d')<'0215',p.m<=3,p.m<=4],['Jan-14Feb','15Feb-Mar','Apr'],'May-Jun')
print('forest cells',len(F),'ignitions',len(p)); print(p.per.value_counts())
tab=pd.crosstab(p.per,p.q,normalize='index').round(3); print('share of ignitions by mahua-proxy quintile (each quintile = 20% of forest cells)'); print(tab)
for per,d in p.groupby('per'):
    c=d.groupby('cell_id').size().reindex(F.cell_id,fill_value=0)
    print(per,'rho(ign count, flush)',round(spearmanr(c.values,F.set_index('cell_id').flush_frac.reindex(c.index).values).correlation,3),'top/bottom quintile rate ratio',round(tab.loc[per,4]/tab.loc[per,0],2))
p['hr']=pd.to_datetime(p.t_ign_med_ist).dt.hour
print('median ignition hour IST by period'); print(p.groupby('per').hr.median())
print('ignition hour by quintile in 15Feb-Mar'); print(p[p.per=='15Feb-Mar'].groupby('q').hr.median())
p[['event_id','date','per','cell_id','flush_frac','q','hr']].to_csv('h1_ign_cells.csv',index=False)
