import numpy as np, rasterio
from scipy.ndimage import uniform_filter
R='/mnt/project-files/fuel-map/ratapani/'
def rd(f):
    with rasterio.open(R+f) as s: a=s.read(1).astype('float32'); nd=s.nodata; t=s.tags()
    return np.where(a==nd,np.nan,a*0.1),t
p,t=rd('fuel_continuous_peak_10m.tif'); print(t)
x=p[np.isfinite(p)]; print('n px',x.size,'area km2',x.size*1e-4,'mean gft2',x.mean(),'t/ha',x.mean()/9.29)
print('Low/Mod/High',np.bincount(np.digitize(x,[20,40,60]),minlength=4)/x.size)
print('pctl t/ha',np.percentile(x/9.29,[1,10,25,50,75,90,99]).round(2), 'max',x.max()/9.29)
cov,_=rd('canopy_cover_10m.tif')
m=np.isfinite(p)&np.isfinite(cov)
for lo,hi in [(0,10),(10,40),(40,70),(70,101)]:
    k=m&(cov>=lo)&(cov<hi); print('cover',lo,hi,'share',k.sum()/m.sum(),'mean t/ha',np.nanmean(p[k])/9.29)
# effective resolution: variance retained after block averaging
v=np.where(np.isfinite(p),p,np.nan)
def blk(a,b):
    H,W=a.shape; a=a[:H//b*b,:W//b*b].reshape(H//b,b,W//b,b); return np.nanmean(a,axis=(1,3))
tot=np.nanvar(v)
for b in [3,10,30]:
    bb=blk(v,b); print('block',b*10,'m: var share kept',np.nanvar(bb)/tot)
s,_=rd('fuel_fsi_strata_10m.tif'); y=s[np.isfinite(s)]; print('strata Low share',(y<20).mean(),'mean',y.mean()/9.29)
f2,_=rd('fuel_fsi_strata_fsicanopy_10m.tif'); y=f2[np.isfinite(f2)]; print('fsicanopy strata Low',(y<20).mean())
for yr in [2018,2022,2026]:
    a,_=rd(f'fuel_season_{yr}_peak_10m.tif'); z=a[np.isfinite(a)]; print(yr,z.mean()/9.29,(z<20).mean())
