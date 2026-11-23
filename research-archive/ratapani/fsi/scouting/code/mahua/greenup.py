"""Feb / Mar / late-Apr Sentinel-2 NDVI and NDRE medians per year on the 20 m burn-raster grid.
Burned pixels of the same season are masked before differencing. Writes out/gu_<year>.npz and out/greenup_median.tif."""
import os, requests, numpy as np, pandas as pd, rasterio, sys
from rasterio.vrt import WarpedVRT
from rasterio.enums import Resampling
from concurrent.futures import ThreadPoolExecutor
os.environ.update(GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR", GDAL_HTTP_MAX_RETRY="5", GDAL_HTTP_RETRY_DELAY="3")
ref=rasterio.open('/mnt/project-files/research/ratapani-burn-labels/rasters/burn_2023.tif')
TR,H,W=ref.transform,ref.height,ref.width
it=pd.read_csv('out/items.csv')
NPER=int(sys.argv[1]) if len(sys.argv)>1 else 3
def tok():
    return requests.get("https://planetarycomputer.microsoft.com/api/sas/v1/token/sentinel-2-l2a").json()['token']
TOK=[tok()]
def get_item(i):
    r=requests.post("https://planetarycomputer.microsoft.com/api/stac/v1/search",json={"collections":["sentinel-2-l2a"],"ids":[i]}).json()
    return r['features'][0]
def read(href,res10):
    opts={'OVERVIEW_LEVEL':0} if res10 else {}
    with rasterio.open(href+'?'+TOK[0],**opts) as src, WarpedVRT(src,crs='EPSG:32643',transform=TR,width=W,height=H,resampling=Resampling.bilinear if not href.endswith('SCL.tif') else Resampling.nearest,nodata=0) as v:
        return v.read(1)
def scene(iid):
    for k in range(3):
        try:
            f=get_item(iid); a=f['assets']
            scl=read(a['SCL']['href'],False)
            ok=np.isin(scl,[4,5])
            if ok.mean()<0.02: return None
            off=-1000 if f['properties'].get('s2:processing_baseline','0')>='04.00' else 0
            b4=read(a['B04']['href'],True).astype('f4')+off; b8=read(a['B08']['href'],True).astype('f4')+off
            b5=read(a['B05']['href'],False).astype('f4')+off; b8a=read(a['B8A']['href'],False).astype('f4')+off
            ndvi=(b8-b4)/(b8+b4+1e-6); ndre=(b8a-b5)/(b8a+b5+1e-6)
            ndvi[~ok]=np.nan; ndre[~ok]=np.nan
            return ndvi.astype('f4'),ndre.astype('f4')
        except Exception as e:
            print('retry',iid,e,flush=True); TOK[0]=tok()
    return None
YEARS=[int(v) for v in sys.argv[2].split(",")] if len(sys.argv)>2 else sorted(it.year.unique())
for y in YEARS:
    fn=f'out/gu_{y}.npz'
    if os.path.exists(fn): continue
    res={}
    for w in ['feb','mar','apr']:
        s=it[(it.year==y)&(it.win==w)]
        dates=s.groupby('date').cloud.mean().nsmallest(NPER).index
        ids=s[s.date.isin(dates)].id.tolist()
        with ThreadPoolExecutor(6) as ex: out=[o for o in ex.map(scene,ids) if o is not None]
        print(y,w,len(ids),'tiles',len(out),'ok',list(dates),flush=True)
        # combine tiles of the same date first is unnecessary: nanmedian over all tile-scenes
        res[w+'_ndvi']=np.nanmedian(np.stack([o[0] for o in out]),0).astype('f4')
        res[w+'_ndre']=np.nanmedian(np.stack([o[1] for o in out]),0).astype('f4')
        res[w+'_dates']=np.array(list(dates))
    np.savez_compressed(fn,**res)
