import pandas as pd, numpy as np, glob
from sklearn.neighbors import BallTree
R=6371000.
def near(a,b,r):
    if len(b)==0 or len(a)==0: return np.zeros(len(a),bool)
    t=BallTree(np.radians(b[['Lat','Lon']].values),metric='haversine')
    return t.query_radius(np.radians(a[['Lat','Lon']].values),r/R,count_only=True)>0
P='/mnt/project-files/ratapani/fsi/fsi_portal/'
fs=glob.glob(P+'fsi_pts_*.csv')+[P+'obd_2026.csv']
d=pd.concat([pd.read_csv(f) for f in fs]).drop_duplicates(['Fire_Date','Fire_Time','Lat','Lon']).reset_index(drop=True)
d['dt']=pd.to_datetime(d.Fire_Date+' '+d.Fire_Time); d['date']=pd.to_datetime(d.Fire_Date)
d['h']=d.dt.dt.hour+d.dt.dt.minute/60
d['pass']=np.select([d.h<5,(d.h>=12)&(d.h<13.1),(d.h>=13.1)&(d.h<14.6)&(d.Source_Type=='VIIRS'),d.Source_Type=='MODIS'],['night','v_early','v_late','aqua'],'other')
print(d['pass'].value_counts())
# times per pass per day: list distinct minute clusters
print(d[d.Source_Type=='VIIRS'].groupby(d.h.round(1)).size().loc[11.5:15].to_string())
out=[]
for r in [750,1500]:
  for dt,g in d.groupby('date'):
    ve=g[g['pass']=='v_early']; vl=g[g['pass']=='v_late']; aq=g[g['pass']=='aqua']
    vday=pd.concat([ve,vl])
    nx=d[(d.date==dt+pd.Timedelta(days=1))&(d['pass']=='night')]
    pn=g[g['pass']=='night']  # night of this date precedes day
    m=dt.month
    if len(aq): out.append(dict(r=r,m=m,k='aqua_seen_by_viirs_day',n=len(aq),c=near(aq,vday,r).sum()))
    if len(vl): out.append(dict(r=r,m=m,k='vlate_seen_by_vearly',n=len(vl),c=near(vl,ve,r).sum()))
    if len(vday): out.append(dict(r=r,m=m,k='vday_seen_by_aqua_after',n=len(vday),c=near(vday,aq,r).sum()))
    if len(vday): out.append(dict(r=r,m=m,k='vday_has_prevnight',n=len(vday),c=near(vday,pn,r).sum()))
    if len(nx): out.append(dict(r=r,m=m,k='night_has_prevday',n=len(nx),c=near(nx,pd.concat([vday,aq]),r).sum()))
    if len(ve) and len(vl): out.append(dict(r=r,m=m,k='vearly_seen_by_vlate(days both)',n=len(ve),c=near(ve,vl,r).sum()))
o=pd.DataFrame(out); o['season']=o.m.map(lambda m:'NovFeb' if m in(11,12,1,2) else 'MarJun' if m in (3,4,5,6) else 'other')
s=o.groupby(['k','r','season'])[['n','c']].sum(); s['frac']=(s.c/s.n).round(3); print(s)
s=o.groupby(['k','r'])[['n','c']].sum(); s['frac']=(s.c/s.n).round(3); print(s)
