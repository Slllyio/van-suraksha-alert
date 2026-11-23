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
