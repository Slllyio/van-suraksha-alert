import pandas as pd, numpy as np
d=pd.read_parquet('/tmp/claude-0/-home-user/be9b8f54-cc26-52cb-bdbb-9c8008a24baf/scratchpad/r3code/viirs_persist3.parquet')
T=d.t.values.astype('datetime64[m]').astype(np.int64)/60.0; X=d[['x','y']].values
def nearest(i,lo,hi,rmax):
    m=np.where((T>T[i]+lo)&(T<=T[i]+hi))[0]
    if len(m)==0: return None
    dd=np.sqrt(((X[m]-X[i])**2).sum(1)); k=dd.argmin()
    return m[k] if dd[k]<rmax and dd[k]>0.2 else None
cos=[];ang=[];steps=[]
for i in np.where(d.daynight.values=='D')[0]:
    p=nearest(i,-30,-18,2.0); n=nearest(i,18,30,2.0)
    if n is not None:
        v=X[n]-X[i]; ang.append(np.degrees(np.arctan2(v[0],v[1]))%360); steps.append(np.hypot(*v))
    if p is not None and n is not None:
        a=X[i]-X[p]; b=X[n]-X[i]; cos.append(a@b/np.linalg.norm(a)/np.linalg.norm(b))
cos=np.array(cos); print('pairs',len(cos),'mean cos %.3f'%cos.mean(),'share same-direction (cos>0) %.3f'%(cos>0).mean(), 'share within 45deg %.3f'%(cos>np.cos(np.pi/4)).mean())
# bootstrap CI
rng=np.random.default_rng(1); bs=[rng.choice(cos,len(cos)).mean() for _ in range(2000)]; print('95%% CI mean cos %.3f..%.3f'%tuple(np.percentile(bs,[2.5,97.5])))
ang=np.array(ang); h,_=np.histogram(ang,bins=np.arange(-22.5,360+22.5,45)); 
h[0]+=h[-1]; h=h[:-1] if len(h)>8 else h
print('bearing counts N,NE,E,SE,S,SW,W,NW', np.histogram((ang+22.5)%360,bins=np.arange(0,361,45))[0])
print('step km quantiles', np.quantile(steps,[.25,.5,.75]).round(2))
