import json, numpy as np, pandas as pd
from scipy.spatial import cKDTree
P='/mnt/project-files/'
g=json.load(open(P+'ratapani/grid_500m.geojson'))
rows=[(f['properties']['cell_id'],*np.array(f['geometry']['coordinates'][0][:4]).mean(0),f['properties']['forest_frac']) for f in g['features']]
cells=pd.DataFrame(rows,columns=['cell_id','lon','lat','forest'])
K=111.32; cl=np.cos(np.radians(23.0)); xy=lambda lo,la: np.c_[np.asarray(lo)*K*cl,np.asarray(la)*K]
tree=cKDTree(xy(cells.lon,cells.lat))
v=pd.read_parquet(P+'ratapani/viirs_snpp_2013_2024.parquet'); v['date']=pd.to_datetime(v.acq_date)
v['season']=np.where(v.date.dt.month==12,v.date.dt.year+1,v.date.dt.year)
v=v[(v.season.between(2018,2024))&(v.date.dt.month.between(1,6))]
d,i=tree.query(xy(v.longitude,v.latitude)); v=v[d<0.36].copy(); v['cell']=cells.cell_id.values[i[d<0.36]]
b=pd.read_csv(P+'research/ratapani-burn-labels/burn_windows.csv',parse_dates=['window_start','window_end'])
b=b[b.burned_ha>0]
nb=tree.query_ball_point(xy(cells.lon,cells.lat),r=0.75)
win={}
for r in b.itertuples(): win.setdefault(r.cell_id,[]).append((r.window_start-pd.Timedelta('2D'),r.window_end+pd.Timedelta('6D')))
def has(c,t):
    for n in nb[c]:
        for a,z in win.get(cells.cell_id.iloc[n],[]):
            if a<=t<=z: return True
    return False
v['scar']=[has(c,t) for c,t in zip(v.cell,v.date)]
v['m']=v.date.dt.month
v['fr']=pd.cut(v.frp,[0,5,10,20,1e4])
print('VIIRS fire points with a scar nearby in the window:',round(v.scar.mean(),3),'n',len(v))
for c in ['m','fr','season']: print(v.groupby(c,observed=True).scar.agg(['size','mean']).round(3),'\n')
