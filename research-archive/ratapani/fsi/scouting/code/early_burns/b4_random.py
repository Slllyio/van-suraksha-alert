"""Random control points inside beats (300 per division) with the same distance features."""
import geopandas as gpd, numpy as np, pandas as pd, shapely, pyarrow.parquet as pq
W='/tmp/claude-0/-home-user/be9b8f54-cc26-52cb-bdbb-9c8008a24baf/scratchpad/r15_firms_nd/'
CRS=7755
beats=gpd.read_file('/mnt/project-files/ratapani/beats/mp_beats.geojson')[['beat_uid','Division','geometry']].to_crs(CRS)
beats['geometry']=beats.geometry.buffer(0)
rng=np.random.default_rng(1); rows=[]
for dv,g in beats.groupby('Division'):
    u=g.union_all(); x0,y0,x1,y1=u.bounds; got=[]
    while len(got)<300:
        xs=rng.uniform(x0,x1,3000); ys=rng.uniform(y0,y1,3000)
        p=shapely.points(xs,ys); m=shapely.contains(u,p)
        got+=list(zip(xs[m],ys[m]))
    for x,y in got[:300]: rows.append((dv,x,y))
r=pd.DataFrame(rows,columns=['Division','x','y'])
rt=pq.read_table(W+'roads_mp.parquet').to_pandas()
geo=gpd.GeoSeries(shapely.from_wkb(rt.geometry.values),crs=4326).to_crs(CRS).values; cls=rt['class'].values
main=~np.isin(cls,['residential','living_street','footway','steps','pedestrian','cycleway','bridleway'])
pts=shapely.points(r.x.values,r.y.values)
def nd(geoms):
    tr=shapely.STRtree(geoms); i=tr.query_nearest(pts,return_distance=True); out=np.full(len(pts),np.nan); out[i[0][0]]=i[1]; return out
r['d_road']=nd(geo[main]); r['d_res']=nd(geo[~main]); r['d_track']=nd(geo[np.isin(cls,['track','path','unknown','unclassified'])])
r['d_beatedge']=nd(beats.geometry.boundary.values)
r.to_parquet(W+'random_pts.parquet'); print(r.describe())
