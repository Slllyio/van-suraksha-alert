"""Per-cell clear fraction for scenes the labels did not use (Landsat-7; S2 with scene cloud>=60), read from the QA band at 100 m."""
import requests, numpy as np, pandas as pd, geopandas as gpd, rasterio, sys
from rasterio.vrt import WarpedVRT
from rasterio.enums import Resampling
from concurrent.futures import ThreadPoolExecutor
import os
os.environ.update(GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR", GDAL_HTTP_MAX_RETRY="4", GDAL_HTTP_RETRY_DELAY="2")
g=gpd.read_file('/mnt/project-files/ratapani/grid_500m.geojson')
X0,Y0=g.x0.min(),g.y0.min(); X1,Y1=g.x0.max()+500,g.y0.max()+500
RES=100; W=int((X1-X0)/RES); H=int((Y1-Y0)/RES)
TR=rasterio.transform.from_origin(X0,Y1,RES,RES)
ci=((g.x0-X0)/RES).astype(int).values; cj=((Y1-(g.y0+500))/RES).astype(int).values
tok={c:requests.get(f"https://planetarycomputer.microsoft.com/api/sas/v1/token/{c}").json()['token'] for c in ['landsat-c2-l2','sentinel-2-l2a']}
s=pd.read_csv('../r9data/stac_items_aoi.csv')
s['dt']=pd.to_datetime(s.datetime,format='ISO8601'); s['season']=s.dt.dt.year+(s.dt.dt.month==12)
sel=s[(s.season>=2017)&(~s.used)&(((s.platform=='landsat-7')&(s.tile=='145/044'))|((s.sensor=='s2')&(s.cloud>=60)))]
print(len(sel),flush=True)
def item(col,i):
    r=requests.post("https://planetarycomputer.microsoft.com/api/stac/v1/search",json={"collections":[col],"ids":[i]}).json()
    return r['features'][0]
def run(row):
    try:
        f=item(row.col,row.id); key='qa_pixel' if row.sensor=='ls' else 'SCL'
        href=f['assets'][key]['href']+'?'+tok[row.col]
        with rasterio.open(href) as src, WarpedVRT(src,crs='EPSG:32643',transform=TR,width=W,height=H,resampling=Resampling.nearest,src_nodata=None,nodata=None) as v:
            q=v.read(1)
        if row.sensor=='ls':
            ok=(q>0)&(q&1==0)&(q&(1<<1)==0)&(q&(1<<3)==0)&(q&(1<<4)==0)
        else:
            ok=np.isin(q,[4,5,6,7,2])
        frac=np.array([ok[j:j+5,i:i+5].mean() for i,j in zip(ci,cj)])
        return row.id,row.date if 'date' in row._fields else None,row.sensor,frac
    except Exception as e:
        print('ERR',row.id,e,flush=True); return None
out=[]
with ThreadPoolExecutor(8) as ex:
    for r in ex.map(run,sel.itertuples()):
        if r: out.append(r)
rows=[]
for i,d,sn,fr in out:
    for c,v in zip(g.cell_id.values,fr): rows.append((i,d,sn,c,v))
P=pd.DataFrame(rows,columns=['id','date','sensor','cell_id','clear'])
P.to_parquet('../r9data/extra_clear.parquet'); print(P.groupby('sensor').clear.describe())
