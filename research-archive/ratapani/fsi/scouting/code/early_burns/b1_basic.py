"""Early (1 Jan-14 Feb) share by reserve and season, S-NPP and all sats; day share, FRP."""
import pandas as pd, numpy as np
P='/mnt/project-files/ratapani/fsi/scouting/code/mp_types/out/viirs_vtm.parquet'
d=pd.read_parquet(P)
d=d[d.type==0]
d['early']=d.doy<=45  # 1 Jan-14 Feb
d['mam']=(d.t_ist.dt.month>=3)&(d.t_ist.dt.month<=5)
d['day']=d.daynight=='D'
R={'Kanha Tiger Reserve':'Kanha','Satpura_TR':'Satpura','Kuno_Palpur':'Kuno','PTR MP':'Pench','BTR':'Bandhavgarh',
   'Panna_TR':'Panna','SANJAY_DUBRI':'Sanjay-Dubri','Noradehi':'Noradehi(VDTR)','Madhav_National_Park':'Madhav','Obedullahganj':'Ratapani'}
d['grp']=d.Division.map(R).fillna('other')
d.to_parquet('pts.parquet')
s=d[d.sat=='snpp']
t=s.groupby(['grp','season']).early.mean().unstack().round(2)
t.loc['ALL MP']=s.groupby('season').early.mean().round(3)
t.loc['other div median']=s[s.grp=='other'].groupby(['Division','season']).early.mean().unstack().median().round(3)
print(t.to_string())
t.to_csv('early_share_snpp.csv')
n=s[s.early].groupby(['grp','season']).size().unstack().fillna(0).astype(int); print(n.to_string())
n.to_csv('early_n_snpp.csv')
# day share and FRP for early vs Mar-May
g=s.groupby(['grp',np.where(s.early,'early',np.where(s.mam,'MarMay','other'))]).agg(n=('frp','size'),day=('day','mean'),frp_med=('frp','median'),frp_day_med=('frp',lambda x: x[s.loc[x.index,'day']].median()))
print(g.round(2).to_string())
