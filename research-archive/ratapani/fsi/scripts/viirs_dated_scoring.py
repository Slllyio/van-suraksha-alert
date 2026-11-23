import numpy as np, pandas as pd
P='/mnt/project-files/ratapani/scoring/'
p=pd.read_parquet(P+'pipeline_lean_pred_loso_2017_24.parquet')
bt=pd.read_csv(P+'pseudo_beats_pipeline.csv'); p=p.merge(bt,on='cell_id')
p['date']=pd.to_datetime(p.date)
g=p.groupby(['date','pseudo_beat'])
p['rk']=g.pipeline_lean.rank(ascending=False,method='first'); p['n']=g.cell_id.transform('size')
p['listed']=p.rk<=5; p['rand']=np.minimum(5,p.n)/p.n
m=pd.read_csv('/mnt/project-files/ratapani/fsi/scar_viirs_check.csv',parse_dates=['window_start','window_end'])
# need VIIRS first date in window: recompute quickly
import json
from scipy.spatial import cKDTree
G=json.load(open('/mnt/project-files/ratapani/grid_500m.geojson'))
rows=[(f['properties']['cell_id'],*np.array(f['geometry']['coordinates'][0][:4]).mean(0)) for f in G['features']]
cells=pd.DataFrame(rows,columns=['cell_id','lon','lat'])
K=111.32; cl=np.cos(np.radians(23.0)); xy=lambda lo,la: np.c_[np.asarray(lo)*K*cl,np.asarray(la)*K]
tree=cKDTree(xy(cells.lon,cells.lat))
v=pd.read_parquet('/mnt/project-files/ratapani/viirs_snpp_2013_2024.parquet'); v['date']=pd.to_datetime(v.acq_date)
pairs=[(cells.cell_id.iloc[c],v.date.iloc[k]) for k,nb in enumerate(tree.query_ball_point(xy(v.longitude,v.latitude),r=0.75)) for c in nb]
vp=pd.DataFrame(pairs,columns=['cell_id','vd']).drop_duplicates()
x=m[m.viirs].merge(vp,on='cell_id')
x=x[(x.vd>=x.window_start)&(x.vd<=x.window_end+pd.Timedelta('1D'))]   # fire day inside (ws, we] (+1 day slack for night pass)
x=x.sort_values('vd').drop_duplicates(['season','cell_id'])
x['d']=x.vd.clip(lower=x.window_start+pd.Timedelta('1D'),upper=x.window_end)
print('VIIRS-dated first burns 2017-24:',len(x),' window days median',(x.window_end-x.window_start).dt.days.median())
# expand to positive issue days t in [ws-1, we-1] (scoring rule) and classify vs true fire day d
rec=[]
for r in x.itertuples():
    for t in pd.date_range(r.window_start-pd.Timedelta('1D'), r.window_end-pd.Timedelta('1D')):
        k=(r.d-t).days   # fire happens k days after issue
        rec.append((r.season,r.cell_id,t,k))
e=pd.DataFrame(rec,columns=['season','cell_id','date','k']).merge(p[['date','cell_id','listed','rand']],on=['date','cell_id'])
e['cls']=np.select([e.k.isin([1,2]),e.k<=0],['on time (fire in next 2 days)','late (fire already happened)'],'early (fire 3+ days out)')
t=e.groupby('cls').agg(cell_days=('listed','size'),model=('listed','mean'),random=('rand','mean'))
t['lift']=t.model/t.random; print(t.round(3))
print('all scored days', e.listed.mean().round(3), e.rand.mean().round(3))
# per-fire: caught on a true forecast day (t=d-1 or d-2) at least once
f=e[e.k.isin([1,2])].groupby(['season','cell_id']).agg(hit=('listed','max'),r=('rand',lambda s:1-np.prod(1-s)))
print('fires caught on a real forecast day:',len(f),f.hit.mean().round(3),'random',f.r.mean().round(3))
print('share of scoring-rule positive days that are late:',(e.k<=0).mean().round(3))
