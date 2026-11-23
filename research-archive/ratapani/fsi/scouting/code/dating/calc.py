import json, numpy as np, pandas as pd
from scipy.spatial import cKDTree
P='/mnt/project-files/'
G=json.load(open(P+'ratapani/grid_500m.geojson'))['features']
xy=np.zeros((3614,2)); ll=[];ut=[]
for f in G:
    p=f['properties']; xy[p['cell_id']]=(p['x0']+250,p['y0']+250)
    c=np.array(f['geometry']['coordinates'][0][:4]); ll.append(c.mean(0)); ut.append((p['x0']+250,p['y0']+250))
ll,ut=np.array(ll),np.array(ut)
A,*_=np.linalg.lstsq(np.c_[ll,ll[:,:1]**2,ll[:,1:]**2,ll[:,:1]*ll[:,1:],np.ones(len(ll))],ut,rcond=None)
v=pd.read_parquet(P+'ratapani/viirs_snpp_2013_2024.parquet')
v=v[v.confidence.astype(str).str.lower().isin(['n','h','nominal','high'])].copy()
v['date']=pd.to_datetime(v.acq_date)
L=np.c_[v.longitude,v.latitude]; vxy=np.c_[L,L[:,:1]**2,L[:,1:]**2,L[:,:1]*L[:,1:],np.ones(len(L))]@A
tree=cKDTree(xy)
d,idx=tree.query(vxy); v['cell']=idx; v['dist']=d
v=v[v.dist<360]  # inside grid
v['season']=np.where(v.date.dt.month==12,v.date.dt.year+1,v.date.dt.year)
v=v[(v.date.dt.month<=6)&(v.season.between(2017,2024))]
bw=pd.read_csv(P+'research/ratapani-burn-labels/burn_windows.csv',parse_dates=['window_start','window_end'])
bw=bw[(bw.burned==1)&bw.season.between(2017,2024)]
fb=bw.sort_values(['season','cell_id','window_end']).drop_duplicates(['season','cell_id']).copy()
fb['L']=(fb.window_end-fb.window_start).dt.days
print('first burns',len(fb)); print('window length quantiles',fb.L.quantile([.1,.25,.5,.75,.9]).to_dict())
print(fb.groupby('season').L.median().to_dict())
# all VIIRS points within 750m of cell, as in pipeline
pairs=[(c,k) for k,nb in enumerate(tree.query_ball_point(vxy[v.index.map(lambda i: True)] if False else np.c_[v.longitude*0,0*v.longitude],r=1)) for c in nb] if False else None
vv=v.reset_index(drop=True)
VX=np.c_[np.c_[vv.longitude,vv.latitude],vv.longitude**2,vv.latitude**2,vv.longitude*vv.latitude,np.ones(len(vv))]@A
pr=[(c,k) for k,nb in enumerate(tree.query_ball_point(VX,r=750)) for c in nb]
pp=pd.DataFrame(pr,columns=['cell_id','k']); pp=pp.join(vv[['date','acq_time','daynight','frp','season']],on='k')
x=fb.merge(pp,on=['season','cell_id'])
x=x[(x.date>=x.window_start)&(x.date<=x.window_end+pd.Timedelta('1D'))]
first=x.sort_values(['date','acq_time']).drop_duplicates(['season','cell_id'])
first['k']=(first.date-first.window_start).dt.days
print('dated',len(first), 'share',len(first)/len(fb))
print('first detection day offset from window_start, as share:'); print((first.k).value_counts(normalize=True).sort_index().head(20).round(3).to_dict())
first['rel']=np.where(first.L>0,first.k/first.L,np.nan)
print('relative position quantiles',first.rel.quantile([.1,.25,.5,.75,.9]).round(2).to_dict())
print('on window_start day',(first.k==0).mean().round(3),' after window_end (we+1)',(first.date>first.window_end).mean().round(3))
print('daynight of first',first.daynight.value_counts(normalize=True).round(3).to_dict())
nd=x.groupby(['season','cell_id']).date.nunique(); print('distinct VIIRS days per dated cell',nd.value_counts(normalize=True).sort_index().round(3).to_dict())
# rel position by window length bucket
first['Lb']=pd.cut(first.L,[0,3,5,8,12,20,60])
print(first.groupby('Lb').rel.median().round(2).to_dict())
# capture-recapture: VIIRS events = (season, cell containing point), first detection per cell-season Jan-Jun
ve=vv[vv.date.dt.month>=1].sort_values('date').drop_duplicates(['season','cell'])
ve=ve.rename(columns={'cell':'cell_id'})
allb=bw.copy()
m=ve.merge(allb,on=['season','cell_id'])
m=m[(m.date>=m.window_start-pd.Timedelta('1D'))&(m.date<=m.window_end+pd.Timedelta('1D'))]
hit=ve.set_index(['season','cell_id']).index.isin(m.set_index(['season','cell_id']).index)
ve['scar']=hit
print('VIIRS cell-season events',len(ve),' with scar window in same cell (+-1d)',ve.scar.mean().round(3))
ve['frpb']=pd.cut(ve.frp,[0,3,5,8,15,1e4])
print('scar recall vs VIIRS by FRP bin', ve.groupby('frpb').scar.agg(['mean','size']).round(3).to_dict())
ve['mon']=ve.date.dt.month
print('scar recall vs VIIRS by month', ve.groupby('mon').scar.agg(['mean','size']).round(3).to_dict())
# VIIRS recall of scars (cell containing point only, i.e. stricter)
fb2=fb.merge(ve[['season','cell_id','date']],on=['season','cell_id'],how='left')
fb2['v']=(fb2.date>=fb2.window_start-pd.Timedelta('1D'))&(fb2.date<=fb2.window_end+pd.Timedelta('1D'))
print('scars with VIIRS point inside same cell',fb2.v.mean().round(3))
fb2['hab']=pd.cut(fb2.burned_ha,[0,2,5,10,25])
print('VIIRS recall of scar by ha',fb2.groupby('hab').v.agg(['mean','size']).round(3).to_dict())
n1=len(fb); n2=len(ve); mm=int(fb2.v.sum())
print('n_scar',n1,'n_viirs',n2,'m',mm,'Chapman N',round((n1+1)*(n2+1)/(mm+1)-1))
print('---')
first['t']=first.acq_time.astype(int)
print(first.groupby('daynight').t.describe())
print(pd.crosstab(first.k.clip(upper=6),first.daynight,normalize='columns').round(3))
# local date shift: night pass ~20 UTC -> IST next day
first['local_date']=first.date+pd.to_timedelta(np.where(first.t>=1830,1,0),unit='D')
first['kl']=(first.local_date-first.window_start).dt.days
print('local-date offset share', first.kl.clip(upper=6).value_counts(normalize=True).sort_index().round(3).to_dict())
print('local date > window_end', (first.local_date>first.window_end).mean().round(3))
# multi-day: gap between first and last VIIRS day in window
g=x.groupby(['season','cell_id']).date.agg(['min','max']); print('span days', ((g['max']-g['min']).dt.days).value_counts(normalize=True).sort_index().head(6).round(3).to_dict())
