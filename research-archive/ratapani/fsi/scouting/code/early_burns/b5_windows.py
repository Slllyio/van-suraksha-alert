import pandas as pd, numpy as np
W='/tmp/claude-0/-home-user/be9b8f54-cc26-52cb-bdbb-9c8008a24baf/scratchpad/r15_firms_nd/'
d=pd.read_parquet(W+'pts_feat.parquet'); r=pd.read_parquet(W+'random_pts.parquet')
m=d.date_ist.dt.month; dd=d.date_ist.dt.day
d['win']=np.select([m>=10,(m==1)|((m==2)&(dd<15)),((m==2)&(dd>=15))|((m==3)&(dd<=15)),(m<=5)],['0 Oct-Dec','1 Jan-14Feb','2 15Feb-15Mar','3 16Mar-May'],'4 Jun')
d['day']=d.daynight=='D'
d.to_parquet(W+'pts_feat2.parquet')
def summ(x):
    return pd.Series({'n':len(x),'day':x.day.mean(),'frp_med_day':x.frp[x.day].median(),'no_night_near':1-x.night_near[x.day].mean(),
      'persist(+1..3d)':x.persist.mean(),'road<=375m':(x.d_road<=375).mean(),'track<=375m':(x.d_track<=375).mean(),'res<=375m':(x.d_res<=375).mean(),'beatedge<=100m':(x.d_beatedge<=100).mean(),'d_road_med':x.d_road.median()})
s=d[d.sat=='snpp']
t=s.groupby('win').apply(summ).round(3)
t.loc['random']=[np.nan]*9+[r.d_road.median()]
t.loc['random',['road<=375m','track<=375m','res<=375m','beatedge<=100m']]=[(r.d_road<=375).mean(),(r.d_track<=375).mean(),(r.d_res<=375).mean(),(r.d_beatedge<=100).mean()]
print(t.to_string()); t.to_csv('windows_snpp.csv')
