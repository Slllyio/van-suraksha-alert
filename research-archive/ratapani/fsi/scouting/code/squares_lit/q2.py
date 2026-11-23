import pandas as pd, numpy as np
d=pd.read_pickle('/tmp/claude-0/-home-user/be9b8f54-cc26-52cb-bdbb-9c8008a24baf/scratchpad/r17_work/viirs.pkl')
# passes: per src, cluster times within 15 min
d=d.sort_values('t')
P=[]
for s,g in d.groupby('src'):
    t=g.t.values; brk=np.r_[True,np.diff(t)>np.timedelta64(15,'m')]; pid=np.cumsum(brk)
    gg=g.assign(pid=pid).groupby('pid').agg(t=('t','median'),n=('t','size'),scan=('scan','median'))
    gg['src']=s; P.append(gg)
P=pd.concat(P).sort_values('t').reset_index(drop=True)
# for each pass, next pass of other satellite within 3h
out=[]
for i,r in P.iterrows():
    nxt=P[(P.t>r.t)&(P.t<r.t+pd.Timedelta('3h'))&(P.src!=r.src)]
    for _,q in nxt.iterrows():
        out.append((r.src,q.src,(q.t-r.t).total_seconds()/60))
o=pd.DataFrame(out,columns=['a','b','gap'])
o['pair']=o.a+'>'+o.b
print(o.groupby('pair').gap.describe(percentiles=[.1,.5,.9]).round(0))
print(np.histogram(o.gap,bins=[0,15,30,45,60,75,90,120,180])[0])
# median pixel scan of passes by src
print(P.groupby('src').scan.describe().round(2))
