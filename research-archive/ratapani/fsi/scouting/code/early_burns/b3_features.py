"""Per-point and per-burn-day-cluster features for all MP VIIRS points in beats (Oct-Jun seasons).
season = year of Jan-Jun; Oct-Dec points belong to next season."""
import pandas as pd, numpy as np, geopandas as gpd, glob, os, shapely, pyarrow.parquet as pq
from scipy.sparse.csgraph import connected_components
from scipy.spatial import cKDTree
from scipy.sparse import coo_matrix
W='/tmp/claude-0/-home-user/be9b8f54-cc26-52cb-bdbb-9c8008a24baf/scratchpad/r15_firms_nd/'
CRS=7755
beats=gpd.read_file('/mnt/project-files/ratapani/beats/mp_beats.geojson')[['beat_uid','Division','geometry']].to_crs(CRS)
beats['geometry']=beats.geometry.buffer(0)
# Jan-Jun points
a=pd.read_parquet('/mnt/project-files/ratapani/fsi/scouting/code/mp_types/out/viirs_vtm.parquet')
a=a[a.type==0].drop(columns=['vtm_name'])
# Oct-Dec points, join to beats
parts=[]
for f in sorted(glob.glob(W+'viirs-*_ond.csv')):
    sat='snpp' if 'snpp' in f else 'jpss1'
    df=pd.read_csv(f,usecols=['latitude','longitude','acq_date','acq_time','confidence','frp','daynight','type'])
    df['sat']=sat; parts.append(df)
o=pd.concat(parts); o=o[o.type==0]
g=gpd.GeoDataFrame(o,geometry=gpd.points_from_xy(o.longitude,o.latitude),crs=4326).to_crs(CRS)
j=gpd.sjoin(g,beats,predicate='within',how='inner'); j=j[~j.index.duplicated()]
o=pd.DataFrame(j.drop(columns=['geometry','index_right']))
t=pd.to_datetime(o.acq_date)+pd.to_timedelta(o.acq_time//100,unit='h')+pd.to_timedelta(o.acq_time%100,unit='m')+pd.Timedelta(minutes=330)
o['t_ist']=t; o['date_ist']=t.dt.normalize(); o['season']=t.dt.year+1; o['doy']=t.dt.dayofyear; o['vtm']=-1
o=o[t.dt.month>=10]
print('Oct-Dec in beats',len(o))
d=pd.concat([a,o],ignore_index=True)
d['date_ist']=pd.to_datetime(d.date_ist)
# season day: days since 1 Oct of previous year
d['sday']=(d.date_ist-pd.to_datetime((d.season-1).astype(str)+'-10-01')).dt.days
P=gpd.GeoSeries(gpd.points_from_xy(d.longitude,d.latitude),crs=4326).to_crs(CRS)
d['x']=P.x.values; d['y']=P.y.values
# "fire date": night points 00:00-05:59 IST belong to previous day
d['fday']=d.sday-np.where((d.daynight=='N')&(d.t_ist.dt.hour<6),1,0)
# distances
rt=pq.read_table(W+'roads_mp.parquet').to_pandas()
geo=shapely.from_wkb(rt.geometry.values)
geo=gpd.GeoSeries(geo,crs=4326).to_crs(CRS).values
cls=rt['class'].values
main=~np.isin(cls,['residential','living_street','footway','steps','pedestrian','cycleway','bridleway'])
pts=shapely.points(d.x.values,d.y.values)
def nd(geoms):
    tr=shapely.STRtree(geoms); i=tr.query_nearest(pts,return_distance=True,all_matches=False)
    out=np.full(len(pts),np.nan); out[i[0][0]]=i[1]; return out
d['d_road']=nd(geo[main]); d['d_res']=nd(geo[~main])
d['d_track']=nd(geo[np.isin(cls,['track','path','unknown','unclassified'])])
bl=beats.geometry.boundary.values
d['d_beatedge']=nd(bl)
print('dist done',flush=True)
# burn-day clusters: same fday, within 750 m (any sat)
d=d.sort_values(['fday','season']).reset_index(drop=True)
lab=np.full(len(d),-1); off=0
for (s,fd),idx in d.groupby(['season','fday']).indices.items():
    xy=d.loc[idx,['x','y']].values
    if len(idx)==1: lab[idx]=off; off+=1; continue
    pr=cKDTree(xy).query_pairs(750,output_type='ndarray')
    m=coo_matrix((np.ones(len(pr)),(pr[:,0],pr[:,1])),shape=(len(idx),len(idx)))
    n,l=connected_components(m,directed=False); lab[idx]=l+off; off+=n
d['cid']=lab
# persistence: any point within 1 km on fday+1..+3 (any sat), and night point same fday within 1.5 km
from collections import defaultdict
key=d.season*1000+d.fday
trees={}; 
for k,idx in d.groupby(key).indices.items(): trees[k]=(cKDTree(d.loc[idx,['x','y']].values),idx)
nightmask=(d.daynight=='N').values
pers=np.zeros(len(d),bool); prev=np.zeros(len(d),bool); night_near=np.zeros(len(d),bool)
xy=d[['x','y']].values
for k,(tr,idx) in trees.items():
    q=xy[idx]
    for dd in (1,2,3):
        if k+dd in trees:
            t2,_=trees[k+dd]; pers[idx]|=np.array([len(r)>0 for r in t2.query_ball_point(q,1000)])
    for dd in (1,2):
        if k-dd in trees:
            t2,_=trees[k-dd]; prev[idx]|=np.array([len(r)>0 for r in t2.query_ball_point(q,1000)])
    nidx=idx[nightmask[idx]]
    if len(nidx):
        tn=cKDTree(xy[nidx]); night_near[idx]=np.array([len(r)>0 for r in tn.query_ball_point(q,1500)])
d['persist']=pers; d['prev2']=prev; d['night_near']=night_near
d.drop(columns=['geometry'],errors='ignore').to_parquet(W+'pts_feat.parquet')
print(len(d), d.cid.nunique())
