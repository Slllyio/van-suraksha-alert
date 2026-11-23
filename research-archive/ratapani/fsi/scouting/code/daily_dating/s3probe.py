import sys, requests, h5py, numpy as np
sys.path.insert(0,'/tmp/claude-0/-home-user/be9b8f54-cc26-52cb-bdbb-9c8008a24baf/scratchpad/r9code_dating')
from rangefile import RangeFile
tok=requests.get("https://planetarycomputer.microsoft.com/api/sas/v1/token/sentinel-3-synergy-syn-l2-netcdf").json()['token']
j=requests.post("https://planetarycomputer.microsoft.com/api/stac/v1/search",json={"collections":["sentinel-3-synergy-syn-l2-netcdf"],"ids":["S3A_SY_2_SYN_20230308T044616_20230308T044916_0179_096_190_2520"]}).json()
a=j['features'][0]['assets']
rf=RangeFile(a['geolocation']['href']+'?'+tok)
f=h5py.File(rf,'r'); print(list(f.keys()))
for k in f: 
    d=f[k]; print(k,d.shape,d.dtype,d.chunks,d.compression,dict(d.attrs).get('scale_factor'))
lat=f['lat'][:]; print('nreq',rf.nreq)
import time
t=time.time()
lon=f['lon'][:]*1e-6; lat=lat*1e-6
m=(lat>22.8)&(lat<23.12)&(lon>77.33)&(lon<78.08)
r,c=np.where(m); print('time',time.time()-t, r.min(),r.max(),c.min(),c.max(), m.sum())
for b in ['syn-oa17-reflectance','syn-s6n-reflectance','syn-flags']:
    rf2=RangeFile(a[b]['href']+'?'+tok); g=h5py.File(rf2,'r'); 
    for k in g: print(b,k,g[k].shape,g[k].dtype,g[k].chunks,{kk:vv for kk,vv in g[k].attrs.items() if kk in ('scale_factor','add_offset','_FillValue','flag_meanings')})
