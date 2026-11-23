import pandas as pd, numpy as np
d=pd.read_parquet('/tmp/claude-0/-home-user/be9b8f54-cc26-52cb-bdbb-9c8008a24baf/scratchpad/r3code/viirs_persist.parquet')
T=d.t.values.astype('datetime64[m]').astype(np.int64)/60.0  # hours
X=d[['x','y']].values
o=np.argsort(T); 
def window_min(lo,hi):
    out=np.full(len(d),np.inf)
    for i in range(len(d)):
        m=(T>T[i]+lo)&(T<=T[i]+hi)
        if m.any(): out[i]=np.sqrt(((X[m]-X[i])**2).sum(1)).min()
    return out
d['W12']=window_min(6,18)   # next pass ~12h
d['W24']=window_min(18,30)  # same pass next day
d['W1']=np.minimum(d.W12,d.W24)
d['W2']=window_min(30,54)
d['Wprev']=window_min(-72,-6)  # wrong sign handled below
d['new']=d.Wprev>2
def rep(s,name):
    out={'n':len(s)}
    for r in [0.5,1,2]:
        out[f'next{r}']=round((s.W1<r).mean(),3)
    out['12h<1']=round((s.W12<1).mean(),3); out['24h<1']=round((s.W24<1).mean(),3)
    out['d2<1']=round((s.W2<1).mean(),3)
    out['1or2<1']=round(((s.W1<1)|(s.W2<1)).mean(),3); out['1or2<2']=round(((s.W1<2)|(s.W2<2)).mean(),3)
    print(name.ljust(30),out)
for dn in ['D','N']:
    s=d[d.daynight==dn]; rep(s,'pass '+dn); rep(s[s.new],' new '+dn)
    s=s.copy(); s['q']=pd.qcut(s.frp,4)
    for q,g in s.groupby('q',observed=True): rep(g,f' {dn} FRP {q}')
    s['ns']=pd.cut(s.nsame1k,[-1,0,2,5,100])
    for q,g in s.groupby('ns',observed=True): rep(g,f' {dn} nbrs {q}')
    for c,g in s.groupby('confidence'): rep(g,f' {dn} conf {c}')
    for m,g in s.groupby('month'):
        if len(g)>100: rep(g,f' {dn} month {m}')
# scan size effect (off-nadir)
s=d[d.daynight=='D'].copy(); s['sc']=pd.cut(s.scan,[0,0.45,0.6,1.0])
for q,g in s.groupby('sc',observed=True): rep(g,f' D scan {q}')
# day-pass: hour of acquisition proxy n/a. Direction momentum: for day dets with W24<2km, displacement vector to nearest; compare with displacement from previous-day nearest
# compute kernel among day-pass: distribution of nearest distance next day, conditional on being <3km
s=d[(d.daynight=='D')]
print('D W24 quantiles|<3km', s.W24[s.W24<3].quantile([.1,.25,.5,.75,.9]).round(2).to_dict())
for r in [0.375,0.75,1,1.5,2,3,5]: print('D: P(next-day det within',r,'km)=',round((s.W1<r).mean(),3))
d.to_parquet('/tmp/claude-0/-home-user/be9b8f54-cc26-52cb-bdbb-9c8008a24baf/scratchpad/r3code/viirs_persist2.parquet')
