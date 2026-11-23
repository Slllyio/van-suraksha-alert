"""For each burned window, find STAC acquisitions strictly inside (ws, we) that cover the cell and were NOT used
(not in clear_calendar for that date+sensor): Landsat-7, scenes with cloud>=60, others. Expected splits ~ sum P(clear)."""
import pandas as pd, numpy as np, json, geopandas as gpd
from shapely.geometry import shape
s=pd.read_csv('../r9data/stac_cal_geom.csv'); s['dt']=pd.to_datetime(s.datetime,format='ISO8601')
s['date']=s.dt.dt.strftime('%Y-%m-%d'); s['sensor']=np.where(s.col=='sentinel-2-l2a','s2','ls')
g=gpd.read_file('/mnt/project-files/ratapani/grid_500m.geojson'); g['pt']=g.geometry.centroid
s['geometry']=s.geom.apply(lambda x: shape(json.loads(x)))
S=gpd.GeoDataFrame(s,geometry='geometry',crs=4326)
pts=gpd.GeoDataFrame(g[['cell_id']],geometry=g.pt,crs=4326)
j=gpd.sjoin(pts,S[['date','sensor','platform','cloud','geometry']],predicate='within')
# per cell-date-sensor best (min cloud) item
cov=j.groupby(['cell_id','date','sensor']).agg(cloud=('cloud','min'),plat=('platform','first')).reset_index()
c=pd.read_parquet('/mnt/project-files/research/ratapani-burn-labels/clear_calendar.parquet')
used=set(zip(c.cell_id,c.date,c.sensor))
cov['used']=[(a,b,d) in used for a,b,d in zip(cov.cell_id,cov.date,cov.sensor)]
cov['cat']=np.select([cov.used, cov.plat.str.lower()=='landsat-7', cov.cloud>=60, cov.plat.str.lower()=='sentinel-2c'],
                     ['used','L7','cloud>=60','S2C_unused'],'other_unused')
cov.to_parquet('../r9data/cell_cov.parquet')
print(cov.cat.value_counts())
w=pd.read_csv('/mnt/project-files/research/ratapani-burn-labels/burn_windows.csv')
w=w[w.burned==1].copy(); w['gap']=(pd.to_datetime(w.window_end)-pd.to_datetime(w.window_start)).dt.days
print('burned windows',len(w),'median gap',w.gap.median())
cov['d']=pd.to_datetime(cov.date)
byc={k:v for k,v in cov[~cov.used].groupby('cell_id')}
res=[]
for r in w.itertuples():
    v=byc.get(r.cell_id)
    ws,we=pd.Timestamp(r.window_start),pd.Timestamp(r.window_end)
    inside=v[(v.d>ws)&(v.d<we)] if v is not None else None
    rec=dict(season=r.season,cell_id=r.cell_id,gap=r.gap)
    for cat in ['L7','cloud>=60','S2C_unused','other_unused']:
        x=inside[inside.cat==cat] if inside is not None else []
        rec['n_'+cat]=len(x)
        if cat=='L7': p=(0.78*(1-x.cloud/100)).clip(0,1) if len(x) else pd.Series([],dtype=float)
        else: p=(1-x.cloud/100).clip(0,1)*0.6 if len(x) else pd.Series([],dtype=float)  # [inference] high-cloud scenes: discount
        rec['p_'+cat]=1-np.prod(1-p.values) if len(x) else 0.0
    # nearest-split gain: expected new window length if split at midpoint ~ halving
    res.append(rec)
R=pd.DataFrame(res)
R['p_any']=1-(1-R['p_L7'])*(1-R['p_cloud>=60'])*(1-R['p_S2C_unused'])*(1-R['p_other_unused'])
R.to_csv('../r9data/split_est.csv',index=False)
print(R.describe().T[['mean','50%','max']])
print('share windows with >=1 unused covering scene:', (R[[c for c in R if c.startswith('n_')]].sum(1)>0).mean())
print('expected share split:', R.p_any.mean())
print(R.groupby('season').agg(n=('gap','size'),gap=('gap','median'),L7=('n_L7',lambda x:(x>0).mean()),hc=('n_cloud>=60',lambda x:(x>0).mean()),p=('p_any','mean')))
print('by gap bucket'); R['gb']=pd.cut(R.gap,[0,5,7,10,15,100]); print(R.groupby('gb').p_any.agg(['size','mean']))
