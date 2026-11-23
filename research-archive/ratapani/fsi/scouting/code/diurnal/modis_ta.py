import pandas as pd, numpy as np, json, glob
import sys; sys.path.insert(0,"/tmp/claude-0/-home-user/be9b8f54-cc26-52cb-bdbb-9c8008a24baf/scratchpad/r7code_diurnal"); from pip import Path
P='/tmp/claude-0/-home-user/be9b8f54-cc26-52cb-bdbb-9c8008a24baf/scratchpad/papers_r7_diurnal/'
g=json.load(open('/mnt/project-files/ratapani/ratapani_aoi.geojson'))
paths=[Path(np.array(poly[0])) for f in g['features'] for poly in (f['geometry']['coordinates'] if f['geometry']['type']=='MultiPolygon' else [f['geometry']['coordinates']])]
def inside(df):
    pts=df[['longitude','latitude']].values
    m=np.zeros(len(df),bool)
    for p in paths: m|=p.contains_points(pts)
    return df[m]
m=pd.concat([pd.read_csv(f) for f in sorted(glob.glob(P+'modis_*.csv'))])
m=inside(m.reset_index(drop=True)).reset_index(drop=True).copy(); print('MODIS in AOI',len(m))
m['acq_date']=pd.to_datetime(m.acq_date); m['mo']=m.acq_date.dt.month; m['yr']=m.acq_date.dt.year
m['ist']=(m.acq_time//100+ (m.acq_time%100)/60 +5.5)%24
print(m.groupby(['satellite','daynight']).size())
print('median IST by sat/yr'); print(m[m.daynight=='D'].groupby(['yr','satellite']).ist.median().unstack().round(2))
day=m[m.daynight=='D']
t=pd.crosstab(day.mo,day.satellite); t['aqua_frac']=(t.Aqua/(t.Aqua+t.Terra)).round(2); print(t)
t=pd.crosstab(day.yr,day.satellite); t['aqua_frac']=(t.Aqua/(t.Aqua+t.Terra)).round(2); print(t)
# season split, years 2013-2021 before drift
e=day[day.yr<=2021]
t=pd.crosstab(e.mo,e.satellite); t['aqua_frac']=(t.Aqua/(t.Aqua+t.Terra)).round(2); print('2013-2021',t)
print('FRP median by sat & season'); print(day.assign(s=day.mo.isin([11,12,1,2])).groupby(['s','satellite']).frp.median())
print('night share all MODIS by month', m.assign(n=m.daynight=='N').groupby('mo').n.mean().round(2).to_dict())
# same-day co-location: Terra (10:30) fire seen also by Aqua (13:30) within 1.5km
from sklearn.neighbors import BallTree
R=6371000.
res=[]
for dt,gg in day.groupby('acq_date'):
    te=gg[gg.satellite=='Terra']; aq=gg[gg.satellite=='Aqua']
    if len(te) and len(aq):
        bt=BallTree(np.radians(aq[['latitude','longitude']].values),metric='haversine')
        c=bt.query_radius(np.radians(te[['latitude','longitude']].values),1500/R,count_only=True)
        bt2=BallTree(np.radians(te[['latitude','longitude']].values),metric='haversine')
        c2=bt2.query_radius(np.radians(aq[['latitude','longitude']].values),1500/R,count_only=True)
        res.append(dict(mo=dt.month,yr=dt.year,nte=len(te),te_in_aq=(c>0).sum(),naq=len(aq),aq_in_te=(c2>0).sum()))
r=pd.DataFrame(res); r['s']=r.mo.isin([11,12,1,2])
s=r.groupby('s')[['nte','te_in_aq','naq','aq_in_te']].sum(); s['te_persist']=s.te_in_aq/s.nte; s['aq_preseen']=s.aq_in_te/s.naq; print('days with both sats:',len(r)); print(s.round(3))
m.to_parquet(P+'modis_aoi.parquet')
