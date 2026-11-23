"""List Sentinel-2 L2A items over the Ratapani burn-raster box for Feb, Mar and late-Apr windows, 2019-2026."""
import requests, pandas as pd, rasterio
from pyproj import Transformer
r=rasterio.open('/mnt/project-files/research/ratapani-burn-labels/rasters/burn_2023.tif'); b=r.bounds
t=Transformer.from_crs(32643,4326,always_xy=True)
x0,y0=t.transform(b.left,b.bottom); x1,y1=t.transform(b.right,b.top)
bbox=[x0,y0,x1,y1]; print(bbox)
W={'feb':('02-01','02-28'),'mar':('03-01','03-25'),'apr':('04-15','05-10')}
rows=[]
for y in range(2019,2027):
  for w,(a,c) in W.items():
    q={"collections":["sentinel-2-l2a"],"bbox":bbox,"datetime":f"{y}-{a}T00:00:00Z/{y}-{c}T23:59:59Z","limit":200,
       "query":{"eo:cloud_cover":{"lt":20}}}
    js=requests.post("https://planetarycomputer.microsoft.com/api/stac/v1/search",json=q).json()
    for f in js['features']:
      p=f['properties']; rows.append(dict(year=y,win=w,id=f['id'],date=p['datetime'][:10],tile=p.get('s2:mgrs_tile'),cloud=p['eo:cloud_cover'],epsg=p.get('proj:epsg')))
d=pd.DataFrame(rows); d.to_csv('out/items.csv',index=False)
print(d.groupby(['year','win']).size().unstack()); print(d.tile.value_counts())
