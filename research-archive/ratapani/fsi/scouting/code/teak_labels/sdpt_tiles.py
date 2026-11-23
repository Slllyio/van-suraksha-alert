import math, sys, json, os, subprocess, collections
import mapbox_vector_tile as mvt
from shapely.geometry import shape, mapping, box
from shapely.ops import transform, unary_union
import geopandas as gpd
OUT=sys.argv[1]; Z=int(sys.argv[2])
aoi=gpd.read_file('/mnt/project-files/ratapani/ratapani_aoi.geojson')
minx,miny,maxx,maxy=aoi.total_bounds; pad=0.1
def tile(lat,lon,z):
    n=2**z; x=int((lon+180)/360*n); y=int((1-math.log(math.tan(math.radians(lat))+1/math.cos(math.radians(lat)))/math.pi)/2*n); return x,y
x0,y0=tile(maxy+pad,minx-pad,Z); x1,y1=tile(miny-pad,maxx+pad,Z)
feats=[]
for x in range(x0,x1+1):
  for y in range(y0,y1+1):
    fn=f'{OUT}/{Z}_{x}_{y}.pbf'
    if not os.path.exists(fn):
        subprocess.run(['curl','-s','-o',fn,f'https://tiles.globalforestwatch.org/gfw_planted_forests/v20231128/dynamic/{Z}/{x}/{y}.pbf'])
    d=mvt.decode(open(fn,'rb').read())
    for L,v in d.items():
      ext=v.get('extent',4096); n=2**Z
      def tr(px,py,z=None):
          import numpy as np
          px=np.asarray(px);py=np.asarray(py)
          lon=(x+px/ext)/n*360-180
          yy=(y+1-py/ext)/n  # mvt decode default y-up
          lat=np.degrees(np.arctan(np.sinh(math.pi*(1-2*yy))))
          return lon,lat
      for f in v['features']:
        g=transform(tr,shape(f['geometry']))
        p=f['properties']; feats.append(dict(geometry=g,name=p.get('originalname'),sci=p.get('sciname'),fid=p.get('gfw_fid')))
gdf=gpd.GeoDataFrame(feats,crs=4326)
gdf=gdf[gdf.is_valid|True]
gdf['geometry']=gdf.buffer(0)
d=gdf.dissolve(by=['fid','name']).reset_index()
d.to_file(f'{OUT}/sdpt_ratapani_z{Z}.geojson',driver='GeoJSON')
u=d.to_crs(32643); a=aoi.to_crs(32643)
print('tiles',(x1-x0+1)*(y1-y0+1),'polys',len(d))
print('bbox+pad area by class (ha):',(u.area/1e4).groupby(u['name']).sum().round(0).to_dict())
inside=gpd.overlay(u,a[['geometry']],how='intersection')
print('inside AOI area by class (ha):',(inside.area/1e4).groupby(inside['name']).sum().round(0).to_dict(),'AOI ha',round(float(a.area.sum()/1e4)))
print('polys intersecting AOI by class:',inside.groupby('name').size().to_dict())
