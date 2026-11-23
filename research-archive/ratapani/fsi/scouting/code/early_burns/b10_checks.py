import pandas as pd, numpy as np
W='/tmp/claude-0/-home-user/be9b8f54-cc26-52cb-bdbb-9c8008a24baf/scratchpad/r15_firms_nd/'
c=pd.read_parquet(W+'clusters3.parquet')
c['dow']=c.date.dt.dayofweek
t=c.groupby(['win','dow']).size().unstack(); print('cluster count by weekday (Mon=0), index = obs/mean'); print((t.div(t.mean(1),axis=0)).round(2).to_string())
c['w2']=np.where((c.win=='2 15Feb-15Mar')&(c.date.dt.day<=28)&(c.date.dt.month==2),'2a 15-28Feb',c.win)
t=c[c.flag].groupby(['w2','dow']).size().unstack(); print('flagged only'); print((t.div(t.mean(1),axis=0)).round(2).to_string())
# Kuno, Satpura, Kanha early clusters
for dv in ['Kuno_Palpur','Satpura_TR','Kanha Tiger Reserve','Obedullahganj','Noradehi','Panna_TR']:
    q=c[(c.Division==dv)&(c.win=='1 Jan-14Feb')]
    top3=q.groupby(['season','fday']).n.sum().groupby('season').apply(lambda s: s.nlargest(3).sum()/s.sum())
    print(dv,'clusters',len(q),'pts',q.n.sum(),'median n',q.n.median(),'mean n',round(q.n.mean(),1),'frp_med',q.frp_max.median(),'day_only',round(q.day_only.mean(),2),'short',round(q.short.mean(),2),'flag',round(q.flag.mean(),2),'site>=2',round((q.early_site_seasons>=2).mean(),2),'top3days share med',round(top3.median(),2),'nseasons',q.season.nunique())
q=c[c.win=='1 Jan-14Feb']; top3=q.groupby(['Division','season','fday']).n.sum().groupby(['Division','season']).apply(lambda s: s.nlargest(3).sum()/s.sum()); nd=q.groupby(['Division','season']).fday.nunique()
print('MP all division-seasons with >=20 early pts: median top3-day share',top3[q.groupby(['Division','season']).n.sum()>=20].median())
for w in ['1 Jan-14Feb','3 16Mar-May']:
    print(w,'strict',c[c.win==w].flag_strict.mean(),'site>=2',(c[c.win==w].early_site_seasons>=2).mean())
