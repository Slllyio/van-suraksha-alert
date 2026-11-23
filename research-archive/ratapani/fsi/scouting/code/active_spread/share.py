import pandas as pd, numpy as np
d=pd.read_parquet('/tmp/claude-0/-home-user/be9b8f54-cc26-52cb-bdbb-9c8008a24baf/scratchpad/r3code/viirs_persist3.parquet')
T=d.t.values.astype('datetime64[m]').astype(np.int64)/60.0; X=d[['x','y']].values
def back(i,lo,hi):
    m=(T>=T[i]-hi)&(T<=T[i]-lo)
    return np.sqrt(((X[m]-X[i])**2).sum(1)).min() if m.any() else np.inf
s=np.where(d.daynight.values=='D')[0]
for lab,lo,hi in [('since yesterday day pass incl last night (6-30h)',6,30),('6-54h',6,54),('prev 1 day (18-30h)',18,30),('prev 2 days (18-54h)',18,54),('prev 3 days (18-78h)',18,78),('day before yesterday only (42-54h)',42,54),('prev 7 days',18,174)]:
    b=np.array([back(i,lo,hi) for i in s])
    print(lab, {r:round((b<r).mean(),3) for r in [0.5,1,2,3,5]})
# by year count of day dets
