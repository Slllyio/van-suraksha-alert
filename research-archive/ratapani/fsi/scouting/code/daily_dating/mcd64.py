"""MCD64A1 (500 m monthly, daily burn date) over Ratapani 2017-2026 vs our 20 m scar windows."""
import requests, numpy as np, pandas as pd, geopandas as gpd, rasterio, os
from rasterio.warp import transform as wtransform
os.environ.update(GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR")
tok=requests.get("https://planetarycomputer.microsoft.com/api/sas/v1/token/modis-64A1-061").json()['token']
g=gpd.read_file('/mnt/project-files/ratapani/grid_500m.geojson'); c=g.to_crs(32643).centroid.to_crs(4326)
lon,lat=c.x.values,c.y.values
rows=[]
for y in range(2017,2027):
    j=requests.post("https://planetarycomputer.microsoft.com/api/stac/v1/search",json={"collections":["modis-64A1-061"],"bbox":[77.34,22.82,78.07,23.11],"datetime":f"{y}-01-01T00:00:00Z/{y}-06-30T23:59:59Z","limit":50}).json()
    for f in j['features']:
        if 'h25v06' not in f['id']: continue
        out={}
        for b in ['Burn_Date','Burn_Date_Uncertainty']:
            sh=requests.get('https://planetarycomputer.microsoft.com/api/sas/v1/sign',params={'href':f['assets'][b]['href']}).json()['href']
            with rasterio.open(sh) as src:
                xs,ys=wtransform('EPSG:4326',src.crs,lon,lat)
                out[b]=np.array([v[0] for v in src.sample(list(zip(xs,ys)))])
        for cid,bd,u in zip(g.cell_id.values,out['Burn_Date'],out['Burn_Date_Uncertainty']):
            if bd>0: rows.append((y,cid,int(bd),int(u)))
    print(y,len(rows),flush=True)
M=pd.DataFrame(rows,columns=['season','cell_id','bd','unc']); M.to_csv('../r9data/mcd64_cells.csv',index=False)
w=pd.read_csv('/mnt/project-files/research/ratapani-burn-labels/burn_windows.csv'); w=w[w.burned==1]
w['wsd']=pd.to_datetime(w.window_start).dt.dayofyear; w['wed']=pd.to_datetime(w.window_end).dt.dayofyear
w.loc[pd.to_datetime(w.window_start).dt.month==12,'wsd']-=pd.to_datetime(w.window_start).dt.dayofyear.where(pd.to_datetime(w.window_start).dt.month==12,0)*0+365
x=w.merge(M,on=['season','cell_id'],how='left')
x['hit']=x.bd.notna()
print('burned windows',len(w),'with an MCD64 burn in same cell-season',x.groupby(['season','cell_id']).hit.max().mean().round(3))
x['inwin']=(x.bd>x.wsd-1)&(x.bd<=x.wed+1)
cs=w.groupby(['season','cell_id']).burned_ha.sum().reset_index().merge(M.groupby(['season','cell_id']).size().rename('m').reset_index(),how='left')
cs['hb']=pd.cut(cs.burned_ha,[0,2,5,10,25,100]); print('MCD64 detection by cell burned ha:',cs.groupby('hb').m.apply(lambda s:s.notna().mean()).round(3).to_dict())
xi=x[x.hit]; print('matched windows: MCD64 date inside (ws-1, we+1]:',xi.inwin.mean().round(3),' median MCD64 uncertainty (days):',xi.unc.median(),' unc<window length:',(xi.unc<(xi.wed-xi.wsd)).mean().round(3))
print('MCD64 cells not in any burned window (commission vs our labels):', 1-M.merge(w[['season','cell_id']].drop_duplicates(),how='inner').shape[0]/len(M))
