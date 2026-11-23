"""Clip the Patra et al. 2025 10 m Sal map (Zenodo 15086956) to the Ratapani box and summarise per 500 m cell."""
import rasterio, numpy as np, geopandas as gpd, pandas as pd
from rasterio.windows import from_bounds
from rasterio.features import rasterize
u='/vsicurl/https://zenodo.org/records/15086956/files/Shorea_robusta_Distribution_India_10m.tif'
with rasterio.open(u) as r:
    w=from_bounds(77.33,22.81,78.07,23.11,r.transform); a=r.read(1,window=w); T=r.window_transform(w)
    prof=r.profile; prof.update(height=a.shape[0],width=a.shape[1],transform=T,compress='deflate')
with rasterio.open('out/sal_ratapani.tif','w',**prof) as o: o.write(a,1)
g=gpd.read_file('/mnt/project-files/ratapani/grid_500m.geojson')
ids=rasterize(((geom,i+1) for i,geom in enumerate(g.geometry)),out_shape=a.shape,transform=T,fill=0,dtype='int32')
df=pd.DataFrame({'k':ids.ravel(),'v':a.ravel()}); df=df[df.k>0]
s=df.groupby('k').v.mean(); out=pd.DataFrame({'cell_id':g.cell_id.values[s.index-1],'sal_frac':s.values})
out.to_csv('out/sal_cells.csv',index=False)
print((out.sal_frac>0).sum(),'cells with any sal;', (out.sal_frac>0.1).sum(),'>10%'); print(out.sal_frac.describe())
