"""Read Landsat-7 C2 L2 (path 145/044 and 146/044) NIR (B4), SWIR2 (B7) and QA onto the 20 m burn-raster grid; save NBR*10000 (int16) with -32768 = invalid."""
import os, sys, requests, numpy as np, pandas as pd, rasterio
from rasterio.vrt import WarpedVRT
from rasterio.enums import Resampling
from multiprocessing import Pool
from scipy.ndimage import binary_dilation
os.environ.update(GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR", CPL_VSIL_CURL_ALLOWED_EXTENSIONS=".tif,.TIF", GDAL_HTTP_MAX_RETRY="5", GDAL_HTTP_RETRY_DELAY="2")
OUT=sys.argv[1]
with rasterio.open('/mnt/project-files/research/ratapani-burn-labels/rasters/burn_2023.tif') as r: TR,W,H,CRS=r.transform,r.width,r.height,r.crs
def items():
    rows=[]
    for y in range(2017,2024):
        body={"collections":["landsat-c2-l2"],"bbox":[77.337,22.816,78.068,23.107],"datetime":f"{y-1}-10-15T00:00:00Z/{y}-07-15T23:59:59Z","limit":500,"query":{"platform":{"eq":"landsat-7"}}}
        j=requests.post("https://planetarycomputer.microsoft.com/api/stac/v1/search",json=body,timeout=120).json()
        rows+=j['features']
    u={f['id']:f for f in rows}; return list(u.values())
def sign(h): return requests.get('https://planetarycomputer.microsoft.com/api/sas/v1/sign',params={'href':h},timeout=60).json()['href']
def rd(h,rs):
    for k in range(4):
        try:
            with rasterio.open(sign(h)) as s, WarpedVRT(s,crs=CRS,transform=TR,width=W,height=H,resampling=rs,src_nodata=s.nodata) as v: return v.read(1)
        except Exception as e: err=e
    raise err
def one(f):
    fn=os.path.join(OUT,f['id']+'.npz')
    if os.path.exists(fn): return
    try:
        a=f['assets']; q=rd(a['qa_pixel']['href'],Resampling.nearest)
        if (q>0).mean()<0.01: np.savez(fn,empty=1); return
        cloud=((q&(1<<1))>0)|((q&(1<<3))>0)|((q&(1<<4))>0)
        ok=(q>0)&(q&1==0)&~binary_dilation(cloud,iterations=25)
        n=rd(a['nir08']['href'],Resampling.bilinear).astype(np.float32)*0.0000275-0.2
        s=rd(a['swir22']['href'],Resampling.bilinear).astype(np.float32)*0.0000275-0.2
        ok&=(n>0.01)&(s>0.005)
        nbr=np.where(ok,np.clip((n-s)/(n+s+1e-6),-1,1)*10000,-32768).astype(np.int16)
        np.savez_compressed(fn,nbr=nbr,date=f['properties']['datetime'][:10]); print('ok',f['id'],round(ok.mean(),3),flush=True)
    except Exception as e: print('ERR',f['id'],e,flush=True)
if __name__=='__main__':
    it=items(); print(len(it),flush=True)
    with Pool(6) as p: p.map(one,it,chunksize=1)
