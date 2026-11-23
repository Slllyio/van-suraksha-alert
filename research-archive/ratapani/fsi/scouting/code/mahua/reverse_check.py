"""Within-cell test of reverse causation: is a cell's April green-up anomaly higher in the season after it burned
(post-fire resprouting / coppice flush), and does a high green-up year precede more burning next season?"""
import numpy as np, pandas as pd, geopandas as gpd, rasterio
from rasterio.warp import reproject, Resampling
from rasterio.features import rasterize
B='/mnt/project-files/research/ratapani-burn-labels/rasters/burn_%d.tif'
ref=rasterio.open(B%2023); T,H,W=ref.transform,ref.height,ref.width
v=rasterio.open('/mnt/project-files/ratapani/fsi/scouting/data/vtm_roy2015_ratapani_5kmbuf.tif')
vtm=np.zeros((H,W),'int16'); reproject(v.read(1),vtm,src_transform=v.transform,src_crs=v.crs,dst_transform=T,dst_crs=ref.crs,resampling=Resampling.nearest)
forest=np.isin(vtm,[23,25,26,102,106,120,135])
g=gpd.read_file('/mnt/project-files/ratapani/grid_500m.geojson').to_crs(32643)
ids=rasterize(((geom,i+1) for i,geom in enumerate(g.geometry)),out_shape=(H,W),transform=T,fill=0,dtype='int32').ravel()
rows=[]
for y in range(2019,2027):
    z=np.load(f'out/gu_{y}.npz'); a=z['apr_ndvi']-z['mar_ndvi']; a[np.abs(a)>1]=np.nan
    b=rasterio.open(B%y).read(); m=~forest|((b[0]!=-999)&(b[1]<135)); a[m]=np.nan; a=a-np.nanmedian(a)
    df=pd.DataFrame({'k':ids,'f':(a>0.05).ravel().astype(float),'ok':np.isfinite(a).ravel()}); df=df[(df.k>0)&df.ok]
    s=df.groupby('k').f.agg(['mean','size']); s=s[s['size']>=100]
    rows.append(pd.DataFrame({'cell_id':g.cell_id.values[s.index-1],'season':y,'flush_y':s['mean'].values}))
P=pd.concat(rows)
cs=pd.read_csv('/mnt/project-files/research/ratapani-burn-labels/cell_season.csv'); cs=cs[cs.burned_ha_total>=1]
bs=set(zip(cs.season,cs.cell_id))
P['burn_prev']=[(s-1,c) in bs for s,c in zip(P.season,P.cell_id)]
P['burn_next']=[(s+1,c) in bs for s,c in zip(P.season,P.cell_id)]
P['dm']=P.flush_y-P.groupby('cell_id').flush_y.transform('mean')
P['dm']=P.dm-P.groupby('season').dm.transform('mean')
print('cell-years',len(P))
print('within-cell flush anomaly, burned previous season vs not:'); print(P.groupby('burn_prev').dm.agg(['mean','sem','size']))
Q=P[P.season<=2025]
Q['hi']=Q.dm>Q.dm.quantile(0.75)
r=Q.groupby('hi').burn_next.mean(); print('P(burn next season) by within-cell high-flush year:',r.round(4).to_dict())
