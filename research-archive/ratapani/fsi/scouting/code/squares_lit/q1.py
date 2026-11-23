import pandas as pd, numpy as np, glob
from math import cos,radians
fs=[f for f in glob.glob('/mnt/project-files/fire-alert-scars/alerts/viirs-*.csv') if not f.endswith('2026.csv')]
d=pd.concat([pd.read_csv(f).assign(src=f.split('/')[-1].split('_')[0]) for f in fs])
d['acq_time']=d.acq_time.astype(float).astype(int).astype(str).str.zfill(4)
d['t']=pd.to_datetime(d.acq_date+' '+d.acq_time,format='%Y-%m-%d %H%M')
print(d.groupby('src').size())
print('scan q',d.scan.quantile([.05,.25,.5,.75,.95]).round(2).tolist(),'track q',d.track.quantile([.05,.5,.95]).round(2).tolist())
print(pd.cut(d.scan,[0,.4,.5,.6,.7,.8,1]).value_counts(normalize=True).sort_index().round(3))
d['pass']=d.src+'_'+d.t.dt.floor('20min').astype(str)
res=[]
for p,g in d.groupby('pass'):
    if len(g)<2: continue
    x=g.longitude.values*111.32*cos(radians(23.1)); y=g.latitude.values*110.57
    f=g.frp.values; s=g.scan.values
    for i in range(len(g)):
        dd=np.hypot(x-x[i],y-y[i]); dd[i]=99
        j=np.argmin(dd)
        res.append((dd[j],f[i]==f[j],s[i],g.src.values[i]))
r=pd.DataFrame(res,columns=['dist','samefrp','scan','src'])
near=r[r.dist<0.6]
print('detections in multi-pixel passes',len(r),' with neighbour <0.6 km',len(near))
print('nearest neighbour identical FRP (M13 split):',near.samefrp.mean().round(3))
print(near.groupby(pd.cut(near.scan,[0,.45,.6,.8,1])).samefrp.mean().round(3))
far=r[(r.dist>2)&(r.dist<10)]
print('control 2-10 km identical FRP:',far.samefrp.mean().round(4), len(far))
q=d.groupby([d.t.dt.date.rename('day'),'daynight','src']).t.median().unstack()
for a,b in [('viirs-snpp','viirs-jpss1'),('viirs-snpp','viirs-noaa21'),('viirs-jpss1','viirs-noaa21')]:
    dt=((q[b]-q[a]).dt.total_seconds()/60).dropna()
    for dn in ['D','N']:
        x=dt.xs(dn,level='daynight'); x=x[abs(x)<150]
        print(a,'->',b,dn,'n',len(x),'median min',round(x.median(),1),'IQR',x.quantile([.25,.75]).round(0).tolist())
d.to_pickle('/tmp/claude-0/-home-user/be9b8f54-cc26-52cb-bdbb-9c8008a24baf/scratchpad/r17_work/viirs.pkl')
