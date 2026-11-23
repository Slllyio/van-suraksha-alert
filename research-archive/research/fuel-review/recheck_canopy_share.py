import numpy as np, rasterio
from scipy.ndimage import uniform_filter
R='/mnt/project-files/fuel-map/ratapani/'
def rd(f,sc=0.1):
    with rasterio.open(R+f) as s: a=s.read(1).astype('float32'); nd=s.nodata
    return np.where(a==nd,np.nan,a*sc)
p=rd('fuel_continuous_peak_10m.tif'); cov=rd('canopy_cover_10m.tif'); bf=rd('burn_frequency_2017_2026_10m.tif')
c30=uniform_filter(np.nan_to_num(cov),3)
m=np.isfinite(p)&np.isfinite(cov)&np.isfinite(bf)
rng=np.random.default_rng(0); idx=rng.choice(np.flatnonzero(m),400000,replace=False)
y=p.ravel()[idx]; X1=np.clip(c30.ravel()[idx]/70,0,1)
def r2(X,y):
    X=np.column_stack([np.ones(len(y))]+X); b=np.linalg.lstsq(X,y,rcond=None)[0]; e=y-X@b; return 1-e.var()/y.var()
print('R2 fuel ~ capped canopy cover (30 m):',r2([X1,X1**2],y))
print('R2 + burn freq:',r2([X1,X1**2,bf.ravel()[idx],X1*bf.ravel()[idx]],y))
print('burn freq pct dist',np.percentile(bf[m],[10,50,90]))
