"""Per-pixel multi-year hot-season green-up (Apr-May minus Mar, and minus Feb) on the 20 m burn grid,
same-season burned pixels masked, non-forest (VTM agri/water/settlement) masked; then per-500 m-cell features."""
import numpy as np, pandas as pd, geopandas as gpd, rasterio, glob
from rasterio.warp import reproject, Resampling
from rasterio.features import rasterize
B='/mnt/project-files/research/ratapani-burn-labels/rasters/burn_%d.tif'
ref=rasterio.open(B%2023); T,H,W=ref.transform,ref.height,ref.width
v=rasterio.open('/mnt/project-files/ratapani/fsi/scouting/data/vtm_roy2015_ratapani_5kmbuf.tif')
vtm=np.zeros((H,W),'int16'); reproject(v.read(1),vtm,src_transform=v.transform,src_crs=v.crs,dst_transform=T,dst_crs=ref.crs,resampling=Resampling.nearest)
forest=np.isin(vtm,[23,25,26,102,106,120,135])
dam,daf,dre,aprv,febv,marv=[],[],[],[],[],[]
yrs=list(range(2019,2027))
for y in yrs:
    z0=np.load(f'out/gu_{y}.npz'); z={k:(np.where(np.abs(z0[k])<=1,z0[k],np.nan) if z0[k].dtype.kind=='f' else z0[k]) for k in z0.files}
    b=rasterio.open(B%y).read(); burned=(b[0]!=-999)&(b[1]<135)   # any scar that started before mid-May
    m=~forest|burned
    a=z['apr_ndvi']-z['mar_ndvi']; a[m]=np.nan
    f=z['apr_ndvi']-z['feb_ndvi']; f[m]=np.nan
    r=z['apr_ndre']-z['mar_ndre']; r[m]=np.nan
    # remove the landscape-wide drying of that year: anomaly vs forest median
    dam.append(a-np.nanmedian(a)); daf.append(f-np.nanmedian(f)); dre.append(r-np.nanmedian(r))
    ap=z['apr_ndvi'].copy(); ap[m]=np.nan; aprv.append(ap)
    fe=z['feb_ndvi'].copy(); fe[~forest]=np.nan; febv.append(fe)
    print(y,'masked burned frac in forest',round((burned&forest).sum()/forest.sum(),3),'median dAM',round(float(np.nanmedian(z['apr_ndvi'][forest]-z['mar_ndvi'][forest])),3),flush=True)
st=lambda L: np.nanmedian(np.stack(L),0)
DAM,DAF,DRE,APR,FEB=st(dam),st(daf),st(dre),st(aprv),st(febv)
nyr=np.isfinite(np.stack(dam)).sum(0)
# persistent flusher: anomaly > +0.05 in at least half the observed years
P=(np.stack(dam)>0.05).sum(0)/np.maximum(nyr,1); P[nyr<3]=np.nan
prof=ref.profile; prof.update(count=5,dtype='float32',nodata=np.nan,compress='deflate')
with rasterio.open('out/flush_20m.tif','w',**prof) as o:
    for i,a in enumerate([DAM,DAF,DRE,APR,P]): o.write(a.astype('f4'),i+1)
    o.descriptions=('dNDVI_aprmar_anom','dNDVI_aprfeb_anom','dNDRE_aprmar_anom','aprNDVI','persist_frac')
g=gpd.read_file('/mnt/project-files/ratapani/grid_500m.geojson').to_crs(32643)
ids=rasterize(((geom,i+1) for i,geom in enumerate(g.geometry)),out_shape=(H,W),transform=T,fill=0,dtype='int32')
df=pd.DataFrame({'k':ids.ravel(),'dam':DAM.ravel(),'daf':DAF.ravel(),'dre':DRE.ravel(),'apr':APR.ravel(),'feb':FEB.ravel(),'pers':P.ravel()})
df=df[df.k>0]
agg=df.groupby('k').agg(n_px=('dam','count'),dam_mean=('dam','mean'),dam_p90=('dam',lambda s:s.quantile(.9)),daf_mean=('daf','mean'),dre_mean=('dre','mean'),
    flush_frac=('pers',lambda s:(s>=0.5).mean() if s.notna().any() else np.nan),apr_ndvi=('apr','mean'),feb_ndvi=('feb','mean'))
agg['cell_id']=g.cell_id.values[agg.index-1]
agg.to_csv('out/flush_cells.csv',index=False); print(agg.describe().T.round(3))
