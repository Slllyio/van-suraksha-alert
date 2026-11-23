import json, numpy as np, pandas as pd
from scipy.spatial import cKDTree
P='/mnt/project-files/'
g=json.load(open(P+'ratapani/grid_500m.geojson'))
cid=[];cx=[];cy=[];ff=[]
for f in g['features']:
    c=np.array(f['geometry']['coordinates'][0][:4]); cid.append(f['properties']['cell_id']); cx.append(c[:,0].mean()); cy.append(c[:,1].mean()); ff.append(f['properties']['forest_frac'])
cells=pd.DataFrame(dict(cell_id=cid,lon=cx,lat=cy,forest=ff)).set_index('cell_id')
K=111.32; cl=np.cos(np.radians(23.0))
def xy(lon,lat): return np.c_[np.asarray(lon)*K*cl, np.asarray(lat)*K]
tree=cKDTree(xy(cells.lon,cells.lat))
v=pd.read_parquet(P+'ratapani/viirs_snpp_2013_2024.parquet')
v=v[v.confidence.astype(str).str.lower().isin(['n','h','nominal','high'])] if 'confidence' in v else v
v['date']=pd.to_datetime(v.acq_date)
v['season']=np.where(v.date.dt.month==12, v.date.dt.year+1, v.date.dt.year)
v=v[(v.season>=2017)&(v.season<=2024)]
vxy=xy(v.longitude,v.latitude)
# map each VIIRS point to all cells whose centre is within 750 m (cell + neighbours)
pairs=[]
for k,nb in enumerate(tree.query_ball_point(vxy, r=0.75)):
    for c in nb: pairs.append((cells.index[c], v.date.iloc[k]))
vp=pd.DataFrame(pairs,columns=['cell_id','date']).drop_duplicates()
print('VIIRS pts',len(v),'cell-date pairs',len(vp))
b=pd.read_csv(P+'research/ratapani-burn-labels/burn_windows.csv',parse_dates=['window_start','window_end'])
b=b[(b.burned==1)&(b.season<=2024)].copy()
# first burn per cell-season
b=b.sort_values('window_end').drop_duplicates(['season','cell_id'])
s=pd.read_parquet(P+'research/ratapani-ignition/s2_cells.parquet')
s['date']=pd.to_datetime(s.date)
s=s.sort_values('date')
# pre-window NDVI: last clear obs on or before window_start, within 30 days
b=b.sort_values('window_start')
m=pd.merge_asof(b, s[['date','cell_id','ndvi']].rename(columns={'date':'obs'}), left_on='window_start', right_on='obs', by='cell_id', direction='backward', tolerance=pd.Timedelta('30D'))
vset=vp.groupby('cell_id').date.apply(lambda x: np.sort(x.values.astype('datetime64[D]')))
def hit(c, a, z):
    d=vset.get(c)
    if d is None: return False
    i=np.searchsorted(d, np.datetime64(a,'D')); return i<len(d) and d[i]<=np.datetime64(z,'D')
pad=pd.Timedelta('1D')
m['viirs']=[hit(c,a-pad,z+pad) for c,a,z in zip(m.cell_id,m.window_start,m.window_end)]
# chance: same cell, same window length, shifted -40/+40 days
m['null']=[(hit(c,a-pad-pd.Timedelta('40D'),z+pad-pd.Timedelta('40D'))+hit(c,a-pad+pd.Timedelta('40D'),z+pad+pd.Timedelta('40D')))/2 for c,a,z in zip(m.cell_id,m.window_start,m.window_end)]
m['month']=m.window_end.dt.month
m['nd']=pd.cut(m.ndvi,[-1,0.25,0.35,0.45,0.55,1])
m['ha']=pd.cut(m.burned_ha,[0,2,5,10,25,1000])
for col in ['nd','month','ha','season']:
    t=m.groupby(col,observed=True).agg(n=('viirs','size'),viirs=('viirs','mean'),chance=('null','mean'),ha=('burned_ha','median'))
    t['lift']=t.viirs/t.chance
    print(t.round(3),'\n')
print('all', m.viirs.mean().round(3), m.null.mean().round(3))
m.to_csv('/mnt/project-files/ratapani/fsi/scar_viirs_check.csv',index=False)
