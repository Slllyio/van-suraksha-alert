"""Aggregate 10 m fuel maps to the 3,614 x 500 m scoring cells."""
import numpy as np, geopandas as gpd, pandas as pd
from rasterio.features import rasterize
from rasterio.transform import Affine
S=np.load('static10.npz'); M=np.load('maps10.npz'); TR=Affine(*S['transform']); H,W=int(S['H']),int(S['W'])
g=gpd.read_file('/mnt/project-files/ratapani/grid_500m.geojson').to_crs(32643)
cid=rasterize(((geom,c+1) for geom,c in zip(g.geometry,g.cell_id)),out_shape=(H,W),transform=TR,fill=0,dtype='int32')-1
k=cid>=0; c=cid[k]
def agg(a,fn='mean'):
    v=a[k]; ok=np.isfinite(v); s=np.bincount(c[ok],v[ok],3614); n=np.bincount(c[ok],minlength=3614)
    return np.where(n>0,s/np.maximum(n,1),np.nan)
rows=dict(cell_id=np.arange(3614), fuel_fsi=agg(M['fsi']), fuel_cont=agg(M['cont']),
          fuel_cont_modplus=agg(np.where(np.isfinite(M['cont']),(M['cont']>20).astype('float32'),np.nan)),
          fuel_cont_sd=np.sqrt(np.maximum(agg(M['cont']**2)-agg(M['cont'])**2,0)))
df=pd.DataFrame(rows); df.to_csv('out/fuel_cells_static.csv',index=False)
se=[]
for y in range(2017,2027):
    a=M[f's{y}'] if f's{y}' in M.files else M['cont']
    se.append(pd.DataFrame(dict(season=y,cell_id=np.arange(3614),fuel_season=agg(a))))
pd.concat(se).to_csv('out/fuel_cells_season.csv',index=False)
print(df.describe().round(2))
