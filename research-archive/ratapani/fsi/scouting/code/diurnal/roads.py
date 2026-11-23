import pandas as pd, numpy as np, json
from sklearn.neighbors import BallTree
R=6371000.
P='/tmp/claude-0/-home-user/be9b8f54-cc26-52cb-bdbb-9c8008a24baf/scratchpad/papers_r7_diurnal/'
def densify(coords,step=30):
    out=[]
    for (x1,y1),(x2,y2) in zip(coords[:-1],coords[1:]):
        dx=(x2-x1)*102000; dy=(y2-y1)*111000; L=np.hypot(dx,dy); k=max(1,int(L/step))
        for t in np.linspace(0,1,k,endpoint=False): out.append((y1+t*(y2-y1),x1+t*(x2-x1)))
    out.append((coords[-1][1],coords[-1][0])); return out
rp=[]
for line in open('/mnt/project-files/ratapani/fsi/scouting/data/ms_roads_rata.tsv'):
    g=json.loads(line.split('\t',1)[1]); rp+=densify(g['geometry']['coordinates'])
rp=np.array(rp); print('road pts',len(rp))
g=json.load(open('/mnt/project-files/ratapani/ratapani_aoi.geojson'))
bp=[]
for f in g['features']:
    for poly in f['geometry']['coordinates']: bp+=densify(poly[0])
bp=np.array(bp)
s=pd.read_parquet('/mnt/project-files/ratapani/viirs_snpp_2013_2024.parquet'); s['acq_date']=pd.to_datetime(s.acq_date)
n=pd.read_parquet(P+'n20_aoi.parquet')
v=pd.concat([s.assign(sat='snpp'),n.assign(sat='n20')])
v['mo']=v.acq_date.dt.month
X=np.radians(v[['latitude','longitude']].values)
v['d_road']=BallTree(np.radians(rp),metric='haversine').query(X)[0][:,0]*R
v['d_bound']=BallTree(np.radians(bp),metric='haversine').query(X)[0][:,0]*R
v['grp']=np.select([v.mo.isin([11,12,1]),v.mo==2,v.mo.isin([3,4]),v.mo.isin([5,6])],['NovJan','Feb','MarApr','MayJun'],'other')
q=v.groupby(['grp','daynight']).agg(n=('frp','size'),frp_med=('frp','median'),d_road_med=('d_road','median'),road_le375=('d_road',lambda x:(x<=375).mean()),d_bound_med=('d_bound','median'),bound_le1k=('d_bound',lambda x:(x<=1000).mean())).round(3)
print(q)
# synthetic baseline: random points in AOI for road distance
import sys; sys.path.insert(0,'/tmp/claude-0/-home-user/be9b8f54-cc26-52cb-bdbb-9c8008a24baf/scratchpad/r7code_diurnal'); from pip import Path
paths=[Path(np.array(poly[0])) for f in g['features'] for poly in f['geometry']['coordinates']]
rng=np.random.default_rng(1); pts=np.c_[rng.uniform(77.2,78.25,60000),rng.uniform(22.7,23.35,60000)]
m=np.zeros(len(pts),bool)
for p in paths: m|=p.contains_points(pts)
pts=pts[m]; Y=np.radians(pts[:,::-1])
dr=BallTree(np.radians(rp),metric='haversine').query(Y)[0][:,0]*R; db=BallTree(np.radians(bp),metric='haversine').query(Y)[0][:,0]*R
print('random AOI: d_road_med',np.median(dr).round(0),'road<=375',(dr<=375).mean().round(3),'d_bound_med',np.median(db).round(0),'bound<=1k',(db<=1000).mean().round(3))
