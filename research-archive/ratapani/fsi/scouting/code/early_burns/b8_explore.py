import pandas as pd, numpy as np
W='/tmp/claude-0/-home-user/be9b8f54-cc26-52cb-bdbb-9c8008a24baf/scratchpad/r15_firms_nd/'
c=pd.read_parquet(W+'clusters.parquet')
c['day_only']=~c.any_night & ~c.night_near
c['short']=~c.persist & ~c.prev2
c['lin']=(c.n>=3)&(c.elong>=3)
c['n3']=c.n>=3
c['near_track']=c.d_track<=375; c['near_road']=c.d_road<=375; c['near_edge']=c.d_edge<=100
c['rep2']=c.repeat_seasons>=2
# burst: division-day cluster count relative to division-season median of active days
med=c.groupby(['Division','season']).div_day_n.transform('median')
c['burst']=c.div_day_n>=np.maximum(3,2*med)
for q in [3,5,8,12]: c[f'frp<={q}']=c.frp_max<=q
cols=['day_only','short','n3','lin','near_track','near_road','near_edge','rep2','burst','frp<=3','frp<=5','frp<=8','frp<=12']
t=c.groupby('win')[cols].mean().T.round(3); t['lift_Jan/MarMay']=(t['1 Jan-14Feb']/t['3 16Mar-May']).round(2)
print(c.groupby('win').size()); print(t.to_string())
print(c.groupby('win').frp_max.describe(percentiles=[.25,.5,.75]).round(2))
print('elong among n>=3', c[c.n3].groupby('win').elong.median())
c.to_parquet(W+'clusters2.parquet')
