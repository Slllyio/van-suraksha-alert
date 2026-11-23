import pandas as pd, numpy as np
rng=np.random.default_rng(0)
d=pd.read_parquet('/tmp/claude-0/-home-user/be9b8f54-cc26-52cb-bdbb-9c8008a24baf/scratchpad/r3code/viirs_persist2.parquet')
T=d.t.values.astype('datetime64[m]').astype(np.int64)/60.0; X=d[['x','y']].values
yr=d.year.values
# same-pass neighbours
nsp=np.array([(((np.abs(T-T[i])<3))&(np.sqrt(((X-X[i])**2).sum(1))<1.0)).sum()-1 for i in range(len(d))])
d['nsp']=nsp
def wmin(xy,t,lo,hi):
    m=(T>t+lo)&(T<=t+hi)
    return np.sqrt(((X[m]-xy)**2).sum(1)).min() if m.any() else np.inf
# control: random location from another year's detections, same time
ctrl=[]
for i in range(len(d)):
    j=rng.choice(np.where(yr!=yr[i])[0]); ctrl.append(min(wmin(X[j],T[i],6,30),np.inf))
d['C1']=ctrl
# control 2: spatial shift of 3-5 km random direction (local neighbourhood control)
c2=[]
for i in range(len(d)):
    a=rng.uniform(0,2*np.pi); r=rng.uniform(3,5); c2.append(wmin(X[i]+r*np.array([np.cos(a),np.sin(a)]),T[i],6,30))
d['C2']=c2
for dn in ['D','N']:
    s=d[d.daynight==dn]
    for r in [0.5,1,2]:
        print(dn,r,'obs %.3f  ctrl-otheryear-site %.3f  ctrl-3-5km-shift %.3f'%((s.W1<r).mean(),(s.C1<r).mean(),(s.C2<r).mean()))
    s=s.copy(); s['ns']=pd.cut(s.nsp,[-1,0,1,3,100])
    print(s.groupby('ns',observed=True).agg(n=('W1','size'),p1km=('W1',lambda v:(v<1).mean()),p2km=('W1',lambda v:(v<2).mean()),p12h1=('W12',lambda v:(v<1).mean())).round(3))
# FRP effect within day pass controlling nsp: logistic-like table
s=d[d.daynight=='D'].copy(); s['q']=pd.qcut(s.frp,3,labels=['lo','mid','hi']); s['ns']=pd.cut(s.nsp,[-1,0,2,100],labels=['0','1-2','3+'])
print(s.pivot_table(index='q',columns='ns',values='W1',aggfunc=lambda v:(v<1).mean(),observed=True).round(3))
print(s.pivot_table(index='q',columns='ns',values='W1',aggfunc='size',observed=True))
# sum FRP of same-pass cluster within 1km
d.to_parquet('/tmp/claude-0/-home-user/be9b8f54-cc26-52cb-bdbb-9c8008a24baf/scratchpad/r3code/viirs_persist3.parquet')
