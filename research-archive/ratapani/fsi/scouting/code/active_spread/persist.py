import pandas as pd, numpy as np
d=pd.read_parquet('/mnt/project-files/ratapani/viirs_snpp_2013_2024.parquet')
print(d.reserve.value_counts().to_dict(), d.type.value_counts().to_dict(), d.confidence.value_counts().to_dict())
print(d.latitude.min(),d.latitude.max(),d.longitude.min(),d.longitude.max())
d=d[d.type==0].copy()
# local date: VIIRS night pass ~01:30 local = ~20:00 UTC previous day; use local solar time
d['t']=pd.to_datetime(d.acq_date)+pd.to_timedelta(d.acq_time//100,unit='h')+pd.to_timedelta(d.acq_time%100,unit='m')+pd.Timedelta(hours=5.5)
# "fire day" starting at 06 local: night pass at 01:30 belongs to previous fire-day
d['fday']=(d.t-pd.Timedelta(hours=6)).dt.normalize()
x=(d.longitude.values-77.75)*102.5; y=(d.latitude.values-23.1)*110.6
d['x']=x; d['y']=y
d=d.reset_index(drop=True)
fd=d.fday.values.astype('datetime64[D]').astype(int)
X=np.c_[x,y]
from collections import defaultdict
byday=defaultdict(list)
for i,f in enumerate(fd): byday[f].append(i)
for k in byday: byday[k]=np.array(byday[k])
def mind(i,day):
    j=byday.get(day)
    if j is None: return np.inf
    return np.sqrt(((X[j]-X[i])**2).sum(1)).min()
n=len(d)
D1=np.array([mind(i,fd[i]+1) for i in range(n)])
D2=np.array([mind(i,fd[i]+2) for i in range(n)])
Dm1=np.array([min(mind(i,fd[i]-1),mind(i,fd[i]-2),mind(i,fd[i]-3)) for i in range(n)])
# same-day neighbours within 1 km
same=np.array([ (np.sqrt(((X[byday[fd[i]]]-X[i])**2).sum(1))<1.0).sum()-1 for i in range(n)])
d['D1']=D1; d['D2']=D2; d['Dm1']=Dm1; d['nsame1k']=same
d.to_parquet('/tmp/claude-0/-home-user/be9b8f54-cc26-52cb-bdbb-9c8008a24baf/scratchpad/r3code/viirs_persist.parquet')
def rep(s,name):
    out={'n':len(s)}
    for r in [0.5,1,2,3]:
        out[f'P1<{r}']=round((s.D1<r).mean(),3)
    out['P12<1']=round(((s.D1<1)|(s.D2<1)).mean(),3)
    out['P12<2']=round(((s.D1<2)|(s.D2<2)).mean(),3)
    print(name.ljust(28),out)
rep(d,'all')
d['new']=d.Dm1>2
rep(d[d.new],'new (no det <2km prev 3d)'); rep(d[~d.new],'ongoing')
for dn in ['D','N']: rep(d[d.daynight==dn],'pass '+dn)
d['frpq']=pd.qcut(d.frp,4)
for q,g in d.groupby('frpq',observed=True): rep(g,f'FRP {q}')
for c,g in d.groupby('confidence'): rep(g,'conf '+str(c))
d['ns']=pd.cut(d.nsame1k,[-1,0,2,5,100])
for c,g in d.groupby('ns',observed=True): rep(g,f'same-day nbrs<1km {c}')
for m,g in d.groupby('month'): 
    if len(g)>50: rep(g,f'month {m}')
for yv,g in d.groupby('year'): rep(g,f'year {yv}')
# new fires only stratified by frp & nbrs
nw=d[d.new]
for q,g in nw.groupby('frpq',observed=True): rep(g,f'NEW FRP {q}')
for c,g in nw.groupby('ns',observed=True): rep(g,f'NEW nbrs {c}')
for dn in ['D','N']: rep(nw[nw.daynight==dn],'NEW pass '+dn)
# kernel: distribution of D1 among those with D1<5
k=d.D1[d.D1<5]; print('D1 quantiles given <5km', k.quantile([.1,.25,.5,.75,.9]).round(2).to_dict())
