# aggregate one EMIT L2A granule to the shared MP 500 m grid (mean spectrum per cell)
import sys, numpy as np, netCDF4, pandas as pd
from pyproj import Transformer
f=sys.argv[1]; out=sys.argv[2]
d=netCDF4.Dataset(f); d.set_auto_mask(False)
R=d['reflectance'][:]                          # (y,x,b)
w=d['sensor_band_parameters']['wavelengths'][:]; good=d['sensor_band_parameters']['good_wavelengths'][:].astype(bool)
lon=d['location']['lon'][:]; lat=d['location']['lat'][:]
X,Y=Transformer.from_crs(4326,32643,always_xy=True).transform(lon.ravel(),lat.ravel())
col=np.floor((X-399000)/500).astype(int); row=np.floor((2996000-Y)/500).astype(int)
ok=(col>=0)&(col<1829)&(row>=0)&(row<1332)
R=R.reshape(-1,R.shape[2])[:,good]; wg=w[good]
b450=np.argmin(abs(wg-450)); 
valid=ok&(R[:,0]>-1)&(R[:,b450]<0.18)&(R[:,b450]>0)&np.isfinite(R).all(1)   # drop fill, cloud/haze-bright, bad
cell=(row*1829+col)[valid]; R=R[valid]
df=pd.DataFrame(R,columns=[f'w{x:.0f}' for x in wg]); df['cell']=cell
g=df.groupby('cell'); m=g.mean(); m['npix']=g.size()
m=m[m.npix>=30]; m['granule']=f.split('/')[-1][:-3]
m.reset_index().to_parquet(out)
print(f, len(m), 'cells; valid frac', valid.sum()/ok.sum())
