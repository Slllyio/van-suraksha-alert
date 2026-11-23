import pandas as pd, numpy as np
from sklearn.neighbors import BallTree
R=6371000.
def near(a,b,r):
    if len(b)==0 or len(a)==0: return np.zeros(len(a),bool)
    t=BallTree(np.radians(b[['latitude','longitude']].values),metric='haversine')
    c=t.query_radius(np.radians(a[['latitude','longitude']].values),r/R,count_only=True)
    return c>0
d=pd.read_parquet('/mnt/project-files/ratapani/viirs_snpp_2013_2024.parquet')
d['acq_date']=pd.to_datetime(d.acq_date)
print(d.daynight.value_counts(), d.satellite.value_counts())
rows=[]
for dt,g in d.groupby('acq_date'):
    day=g[g.daynight=='D']; nig=g[g.daynight=='N']
    prev=d[(d.acq_date==dt-pd.Timedelta(days=1))]
    nxt=d[(d.acq_date==dt+pd.Timedelta(days=1))&(d.daynight=='D')]
    # night on UTC date dt = 01-03 IST of dt+1, after day pass dt
    for r_ in [750,1500]:
        if len(nig):
            rows.append(dict(kind='night_has_day_same',r=r_,m=dt.month,n=len(nig),k=near(nig,day,r_).sum()))
            rows.append(dict(kind='night_has_nextday',r=r_,m=dt.month,n=len(nig),k=near(nig,nxt,r_).sum()))
        if len(day):
            rows.append(dict(kind='day_has_night_same',r=r_,m=dt.month,n=len(day),k=near(day,nig,r_).sum()))
            prevn=prev[prev.daynight=='N']
            rows.append(dict(kind='day_has_prevnight',r=r_,m=dt.month,n=len(day),k=near(day,prevn,r_).sum()))
            rows.append(dict(kind='day_has_nextday',r=r_,m=dt.month,n=len(day),k=near(day,nxt,r_).sum()))
x=pd.DataFrame(rows)
x['mm']=x.m.map(lambda m:'NovFeb' if m in (11,12,1,2) else ('MarApr' if m in (3,4) else 'other'))
s=x.groupby(['kind','r','mm'])[['n','k']].sum(); s['frac']=s.k/s.n; print(s)
s=x.groupby(['kind','r'])[['n','k']].sum(); s['frac']=s.k/s.n; print(s)
# FRP day vs night by month; day FRP for points with/without night
