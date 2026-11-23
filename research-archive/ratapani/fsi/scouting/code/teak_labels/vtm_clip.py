import rasterio, numpy as np, geopandas as gpd, pandas as pd, sys
from rasterio.mask import mask
src=rasterio.open(sys.argv[1]); out=sys.argv[2]
print(src.crs, src.res, src.dtypes, src.nodata, src.bounds)
aoi=gpd.read_file('/mnt/project-files/ratapani/ratapani_aoi.geojson').to_crs(src.crs)
att=pd.read_csv(sys.argv[3],encoding='utf-8-sig')
names=dict(zip(att.Value,att.Class_name))
buf=aoi.buffer(5000)
arr,tr=mask(src,buf.geometry,crop=True,nodata=0)
prof=src.profile; prof.update(height=arr.shape[1],width=arr.shape[2],transform=tr,compress='deflate',nodata=0)
with rasterio.open(out,'w',**prof) as d: d.write(arr)
ins,_=mask(src,aoi.geometry,crop=True,nodata=0)
px=src.res[0]*src.res[1]/1e4
for lab,a in (('AOI',ins),('AOI+5km',arr)):
    v,c=np.unique(a[a>0],return_counts=True)
    tot=c.sum()
    print('==',lab,'mapped ha',round(tot*px))
    for vv,cc in sorted(zip(v,c),key=lambda t:-t[1]):
        print(f'{vv:4d} {names.get(vv)!s:45s} {cc*px:10.0f} ha {100*cc/tot:5.1f}%')
