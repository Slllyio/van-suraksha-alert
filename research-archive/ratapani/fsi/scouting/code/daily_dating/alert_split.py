import pandas as pd, numpy as np, geopandas as gpd
L=pd.read_csv('/mnt/project-files/fire-alert-scars/alert_scar_lookup.csv')
g=gpd.read_file('/mnt/project-files/ratapani/grid_500m.geojson')
P=gpd.GeoDataFrame(L[['alert_id']],geometry=gpd.points_from_xy(L.longitude,L.latitude),crs=4326)
j=gpd.sjoin(P,g[['cell_id','geometry']],predicate='within').drop_duplicates('alert_id')
L=L.merge(j[['alert_id','cell_id']],on='alert_id',how='left')
s=L[L.scar_status.eq('scar')&L.gap_days.notna()].copy()
print('alerts',len(L),'with scar & gap',len(s)); print('gap_days pct',s.gap_days.quantile([.1,.25,.5,.75,.9]).tolist())
print('scar_status counts',L.scar_status.value_counts().to_dict())
E=pd.read_parquet('../r9data/extra_clear.parquet'); E=E[E.clear>=0.5]; E['d']=pd.to_datetime(E.date)
by={k:v.d.values for k,v in E.groupby('cell_id')}
s['pre']=pd.to_datetime(s.pre_date); s['post']=pd.to_datetime(s.post_date); s['acq']=pd.to_datetime(s.acq_date)
def f(r):
    v=by.get(r.cell_id)
    if v is None or pd.isna(r.cell_id): return (0,np.nan)
    x=v[(v>np.datetime64(r.pre))&(v<np.datetime64(r.post))]
    if len(x)==0: return (0,np.nan)
    # new bracket containing the VIIRS date
    cuts=np.sort(np.concatenate([[np.datetime64(r.pre)],x,[np.datetime64(r.post)]]))
    k=np.searchsorted(cuts,np.datetime64(r.acq),side='right')
    k=min(max(k,1),len(cuts)-1)
    return (len(x),(cuts[k]-cuts[k-1])/np.timedelta64(1,'D'))
res=s.apply(f,axis=1,result_type='expand'); s['n_extra']=res[0]; s['newgap']=res[1]
s['yr']=s.acq.dt.year
print('alert scars whose pre/post bracket would be split by an extra clear L7/hi-cloud S2 look:',(s.n_extra>0).mean().round(3))
print(s.groupby('yr').agg(n=('gap_days','size'),gap=('gap_days','median'),split=('n_extra',lambda x:(x>0).mean()),newgap=('newgap','median')).round(2).to_string())
print('pre/post sensors',s.pre_sensor.value_counts().to_dict(),s.post_sensor.value_counts().to_dict())
