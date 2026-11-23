import sys; sys.path.insert(0,'/tmp/claude-0/-home-user/be9b8f54-cc26-52cb-bdbb-9c8008a24baf/scratchpad/r7code_diurnal')
from pip import Path
import pandas as pd, numpy as np, json, glob
from sklearn.neighbors import BallTree
R=6371000.
P='/tmp/claude-0/-home-user/be9b8f54-cc26-52cb-bdbb-9c8008a24baf/scratchpad/papers_r7_diurnal/'
g=json.load(open('/mnt/project-files/ratapani/ratapani_aoi.geojson'))
paths=[Path(np.array(poly[0])) for f in g['features'] for poly in f['geometry']['coordinates']]
n=pd.concat([pd.read_csv(f) for f in sorted(glob.glob(P+'n20_*.csv'))]).reset_index(drop=True)
msk=np.zeros(len(n),bool)
for p in paths: msk|=p.contains_points(n[['longitude','latitude']].values)
n=n[msk].reset_index(drop=True); n['acq_date']=pd.to_datetime(n.acq_date)
n.to_parquet(P+'n20_aoi.parquet')
s=pd.read_parquet('/mnt/project-files/ratapani/viirs_snpp_2013_2024.parquet'); s['acq_date']=pd.to_datetime(s.acq_date)
print('N20 in AOI',len(n), n.groupby(n.acq_date.dt.year).size().to_dict())
s18=s[(s.acq_date.dt.year>=2018)]
print('SNPP 2018-24',len(s18),' N20 2018-24',(n.acq_date.dt.year<=2024).sum())
n['ist']=(n.acq_time//100+(n.acq_time%100)/60+5.5)%24; s18=s18.assign(ist=(s18.acq_time//100+(s18.acq_time%100)/60+5.5)%24)
print('IST median day N20',n[n.daynight=='D'].ist.median(),'SNPP',s18[s18.daynight=='D'].ist.median())
print('night share N20',(n.daynight=='N').mean().round(3),'SNPP',(s18.daynight=='N').mean().round(3))
rows=[]
for dn in ['D','N']:
  for dt,gg in n[(n.daynight==dn)&(n.acq_date.dt.year<=2024)].groupby('acq_date'):
    ss=s18[(s18.acq_date==dt)&(s18.daynight==dn)]
    if len(ss)==0: rows.append(dict(dn=dn,mo=dt.month,nn=len(gg),n_in_s=0,ns=0,s_in_n=0,both=0)); continue
    b1=BallTree(np.radians(ss[['latitude','longitude']].values),metric='haversine')
    b2=BallTree(np.radians(gg[['latitude','longitude']].values),metric='haversine')
    c1=b1.query_radius(np.radians(gg[['latitude','longitude']].values),750/R,count_only=True)
    c2=b2.query_radius(np.radians(ss[['latitude','longitude']].values),750/R,count_only=True)
    rows.append(dict(dn=dn,mo=dt.month,nn=len(gg),n_in_s=(c1>0).sum(),ns=len(ss),s_in_n=(c2>0).sum(),both=1))
r=pd.DataFrame(rows)
for dn in 'DN':
  x=r[(r.dn==dn)]; xb=x[x.both==1]
  print(dn,'days N20',len(x),'days both',len(xb),'N20 pts seen by SNPP 50min later (both days)',round(xb.n_in_s.sum()/xb.nn.sum(),3),'SNPP pts seen by N20',round(xb.s_in_n.sum()/xb.ns.sum(),3))
  xb=xb.assign(sea=xb.mo.isin([11,12,1,2]))
  t=xb.groupby('sea')[['nn','n_in_s','ns','s_in_n']].sum(); print((t.n_in_s/t.nn).round(3).to_dict(),(t.s_in_n/t.ns).round(3).to_dict())
# union gain: unique fire-days detected
