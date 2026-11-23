"""Add per-cell elevation, slope and local relief (from the barrier note's 30 m DEM) and recheck the flush-burn partial correlation."""
import numpy as np, pandas as pd, geopandas as gpd, rasterio
from rasterio.features import rasterize
from scipy.stats import spearmanr
from numpy.linalg import lstsq
r=rasterio.open('/mnt/project-files/ratapani/fsi/scouting/data/barrier_extra/dem_utm30.tif'); z=r.read(1).astype('f4'); z[z<-100]=np.nan
gy,gx=np.gradient(z,r.res[1],r.res[0]); sl=np.degrees(np.arctan(np.hypot(gx,gy)))
g=gpd.read_file('/mnt/project-files/ratapani/grid_500m.geojson').to_crs(r.crs)
ids=rasterize(((geom,i+1) for i,geom in enumerate(g.geometry)),out_shape=z.shape,transform=r.transform,fill=0,dtype='int32')
df=pd.DataFrame({'k':ids.ravel(),'z':z.ravel(),'s':sl.ravel()}); df=df[df.k>0]
t=df.groupby('k').agg(elev=('z','mean'),relief=('z',lambda v:v.max()-v.min()),slope=('s','mean')); t['cell_id']=g.cell_id.values[t.index-1]
F=pd.read_csv('out/compare_cells.csv').merge(t,on='cell_id')
for c in ['elev','relief','slope']: print(c,'rho with flush %.3f, with bfreq %.3f'%(spearmanr(F[c],F.flush_frac,nan_policy='omit').statistic,spearmanr(F[c],F.bfreq,nan_policy='omit').statistic))
def partial(df,x,y,ctrl):
    Z=df[[x,y]+ctrl].dropna(); R=Z.rank(); A=np.c_[np.ones(len(R)),R[ctrl].values]
    rx=R[x]-A@lstsq(A,R[x],rcond=None)[0]; ry=R[y]-A@lstsq(A,R[y],rcond=None)[0]; return np.corrcoef(rx,ry)[0,1],len(Z)
for ctrl in [['elev','slope','relief'],['elev','slope','relief','feb_ndvi','apr_ndvi','d_ob','bld4']]:
    print(ctrl, 'partial flush_frac %.3f (n=%d)'%partial(F,'flush_frac','bfreq',ctrl), ' partial d_ob %.3f'%partial(F,'d_ob','bfreq',[c for c in ctrl if c not in('d_ob','bld4')]+['flush_frac'])[0])
t.to_csv('out/topo_cells.csv',index=False)
