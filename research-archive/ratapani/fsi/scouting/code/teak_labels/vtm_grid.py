import rasterio, numpy as np, geopandas as gpd, pandas as pd, sys
from rasterio.features import rasterize
src=rasterio.open(sys.argv[1]); a=src.read(1)
g=gpd.read_file('/mnt/project-files/ratapani/grid_500m.geojson').to_crs(src.crs)
ids=rasterize(((geom,i+1) for i,geom in enumerate(g.geometry)),out_shape=a.shape,transform=src.transform,fill=0,all_touched=False,dtype='int32')
df=pd.DataFrame({'cell':ids.ravel(),'v':a.ravel()}); df=df[df.cell>0]
cls={25:'teakmix_moist',26:'dry_decid',23:'moist_decid',106:'degraded',170:'agri',190:'water',120:'scrub',200:'settle',135:'grass',102:'mixplant'}
df['c']=df.v.map(cls).fillna('other')
t=pd.crosstab(df.cell,df.c,normalize='index')
t.index=g.cell_id.values[t.index-1]
t['vtm_major']=t.idxmax(axis=1)
t=t.reset_index().rename(columns={'index':'cell_id','cell':'cell_id'})
t.to_csv(sys.argv[2],index=False,float_format='%.3f')
print(len(t), 'cells'); print(t.vtm_major.value_counts())
