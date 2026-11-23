# rasterise candidate barrier lines on the spread thread's 20 m grid (EPSG:32643), with segment orientation
import json, numpy as np, geopandas as gpd, pandas as pd, rasterio
from rasterio.features import rasterize
from affine import Affine
from shapely.geometry import LineString, shape, MultiLineString
D='/tmp/claude-0/-home-user/be9b8f54-cc26-52cb-bdbb-9c8008a24baf/scratchpad/r9_barrier_data/'
z=np.load('/mnt/project-files/ratapani/spread/data_shared/grid20.npz')
T=Affine(*z['transform']); H,W=z['shape']
def segs(geoms):
    out=[]
    for g in geoms:
        if g is None or g.is_empty: continue
        parts = g.geoms if hasattr(g,'geoms') else [g]
        for p in parts:
            if p.geom_type=='Polygon': p=p.exterior
            if p.geom_type not in ('LineString','LinearRing'): continue
            c=np.asarray(p.coords)
            for a,b in zip(c[:-1],c[1:]):
                ang=np.degrees(np.arctan2(b[1]-a[1],b[0]-a[0]))%180
                out.append((LineString([a,b]),ang))
    return out
def rast(geoms):
    s=segs(geoms)
    if not s: return np.zeros((H,W),bool),np.zeros((H,W),np.float32)
    ang=rasterize([(g,a+1) for g,a in s],out_shape=(H,W),transform=T,fill=0,dtype='float32',all_touched=True)
    return ang>0, ang-1
L={}
def to32643(gdf): return gdf.to_crs(32643) if gdf.crs and gdf.crs.to_epsg()!=32643 else gdf
# Microsoft roads
rows=[json.loads(l.split('\t',1)[1]) for l in open('/mnt/project-files/ratapani/fsi/scouting/data/ms_roads_rata.tsv')]
ms=gpd.GeoDataFrame([r['properties'] for r in rows],geometry=[shape(r['geometry']) for r in rows],crs=4326).to_crs(32643)
L['ms_roads']=ms.geometry
seg=to32643(gpd.read_file(D+'overture_segment.geojson'))
L['ov_osm_roads']=seg[(seg.subtype=='road')&(seg.src=='OpenStreetMap')].geometry
L['ov_osm_paths']=seg[(seg.subtype=='road')&(seg.src=='OpenStreetMap')&seg['class'].isin(['track','path','footway','bridleway'])].geometry
L['ov_tomtom']=seg[seg.src!='OpenStreetMap'].geometry
L['rail']=seg[seg.subtype=='rail'].geometry
inf=to32643(gpd.read_file(D+'overture_infrastructure.geojson'))
L['power']=inf[inf['class'].isin(['power_line','minor_line','cable'])].geometry
wat=to32643(gpd.read_file(D+'overture_water.geojson'))
L['osm_water']=wat.geometry
for t in ['0.25','1','5','25']:
    g=gpd.read_file(D+f'streams_{t}km2.geojson'); g=g.set_crs(32643,allow_override=True); L[f'stream_{t}km2']=g.geometry
for n in ['100','500']:
    g=gpd.read_file(D+f'ridges_{n}cells.geojson'); g=g.set_crs(32643,allow_override=True); L[f'ridge_{n}c']=g.geometry
out={}
for k,v in L.items():
    m,a=rast(list(v)); out[k+'_m']=m; out[k+'_a']=a.astype(np.float16)
    print(k,len(v),'pixels',m.sum(),'km~',round(m.sum()*0.02,1))
# forest/burnable edge (burnable = tree, shrub, grass) vs crop/built/bare/water
wc=z['wc']; burn=np.isin(wc,[10,20,30])
from scipy import ndimage
edge=burn & ~ndimage.binary_erosion(burn,np.ones((3,3)))
out['fedge_m']=edge; print('fedge pixels',edge.sum())
np.savez_compressed(D+'layers20.npz',**out)
