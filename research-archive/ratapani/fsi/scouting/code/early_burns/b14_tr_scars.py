"""Tiger-reserve scars (v1 method, 15 Feb-15 Jun 2017-25): Mar-May events, scar found and size by reserve, pre (2017-22) vs post (2023-25).
Note: chip-edge clipping (v1) caps big fires; compare within reserve only."""
import pandas as pd, numpy as np
O='/mnt/project-files/fire-alert-scars/mp/out/'
s=pd.read_csv(O+'set_tiger_reserves.csv',usecols=['event_id','acq_date','Division','n_alerts'])
r=pd.read_csv(O+'scars_tiger_reserves.csv',usecols=['event_id','status','scar_ha','touches_chip_edge'])
d=s.merge(r,on='event_id'); d['date']=pd.to_datetime(d.acq_date); d=d[d.date.dt.month.between(3,5)]
d['season']=d.date.dt.year; d['post']=d.season>=2023
d['ha']=np.where(d.status=='scar',d.scar_ha,0.0)
g=d.groupby(['Division','post']).agg(events=('event_id','size'),per_season=('season',lambda x: len(x)/x.nunique()),scar_found=('status',lambda x:(x=='scar').mean()),
  median_ha=('scar_ha','median'),mean_ha=('ha','mean'),total_ha_per_season=('ha',lambda x: x.sum()/d.loc[x.index,'season'].nunique()),edge=('touches_chip_edge','mean')).round(2)
print(g.to_string()); g.to_csv('tr_scars_pre_post.csv')
