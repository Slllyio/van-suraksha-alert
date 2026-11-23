"""First-day fire starts from all-MP S-NPP VIIRS points inside forest beats.
New start = point with no S-NPP point within 1.5 km in the prior 3 days; same-day new points within 1.5 km
(single-linkage) are merged into one start. Two day definitions: 'cday' = IST calendar date; 'bday' = burning day
= date of (IST time - 6 h), so the ~01:30 IST night pass is assigned to the previous evening.
Input: mp_types/out/viirs_vtm.parquet. Output: out/starts.parquet"""
import pandas as pd, numpy as np
from sklearn.neighbors import BallTree
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components
V='/mnt/project-files/ratapani/fsi/scouting/code/mp_types/out/viirs_vtm.parquet'
d=pd.read_parquet(V); d=d[(d.sat=='snpp')&(d.season.between(2014,2026))].copy()
d=d[d.type!=2]  # drop static land sources (type 2) [none matter much: 0.9%]
d['day']=d.date_ist.dt.normalize()
R=1.5/6371.0
out=[]
for yr,g in d.groupby('season'):
    g=g.sort_values('t_ist').reset_index(drop=True)
    X=np.radians(g[['latitude','longitude']].values)
    tree=BallTree(X,metric='haversine')
    nb=tree.query_radius(X,r=R)
    dn=g.day.values.astype('datetime64[D]').astype(int)
    new=np.array([not np.any((dn[j]>=dn[i]-3)&(dn[j]<dn[i])) for i,j in enumerate(nb)])
    g['new']=new
    # merge same-day new points within 1.5 km
    idx=np.where(new)[0]; pos={k:n for n,k in enumerate(idx)}
    rows=[];cols=[]
    for i in idx:
        for j in nb[i]:
            if j in pos and dn[j]==dn[i]: rows.append(pos[i]); cols.append(pos[j])
    m=coo_matrix((np.ones(len(rows)),(rows,cols)),shape=(len(idx),len(idx)))
    nc,lab=connected_components(m,directed=False)
    s=g.iloc[idx].copy(); s['cl']=lab
    s=s.sort_values('t_ist').groupby('cl').first().reset_index()  # earliest point = start
    out.append(s); print(yr,len(g),'new pts',new.sum(),'starts',len(s),flush=True)
s=pd.concat(out,ignore_index=True)
s['cday']=s.t_ist.dt.normalize(); s['bday']=(s.t_ist-pd.Timedelta(hours=6)).dt.normalize()
s['nonforest']=s.vtm_name.isin(['Agriculture','Water body','Settlement','Scrub'])
s[['latitude','longitude','t_ist','cday','bday','daynight','frp','Division','vtm_name','nonforest','season']].to_parquet('out/starts.parquet')
print(len(s)); print(s.daynight.value_counts(normalize=True))
