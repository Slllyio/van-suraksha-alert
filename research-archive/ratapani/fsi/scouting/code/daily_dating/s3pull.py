"""Pull Sentinel-3 SYN L2 (300 m) Oa17, S5N, S6N, cloud & SYN flags over the Ratapani box for a date range, via HTTP range reads."""
import sys, os, requests, h5py, numpy as np, time
from multiprocessing import Pool
sys.path.insert(0,os.path.dirname(os.path.abspath(__file__)))
from rangefile import RangeFile
d0,d1,out=sys.argv[1],sys.argv[2],sys.argv[3]; os.makedirs(out,exist_ok=True)
B=dict(la0=22.78,la1=23.14,lo0=77.30,lo1=78.10)
def tok(): return requests.get("https://planetarycomputer.microsoft.com/api/sas/v1/token/sentinel-3-synergy-syn-l2-netcdf").json()['token']
items=[]; body={"collections":["sentinel-3-synergy-syn-l2-netcdf"],"bbox":[77.34,22.82,78.07,23.11],"datetime":f"{d0}T00:00:00Z/{d1}T23:59:59Z","limit":200}
j=requests.post("https://planetarycomputer.microsoft.com/api/stac/v1/search",json=body).json(); items=j['features']
print(len(items),flush=True)
T=tok()
def one(f):
    fn=os.path.join(out,f['id']+'.npz')
    if os.path.exists(fn): return
    a=f['assets']
    try:
        g=h5py.File(RangeFile(a['geolocation']['href']+'?'+T),'r')
        lat=g['lat'][:]*1e-6; lon=g['lon'][:]*1e-6
        m=(lat>B['la0'])&(lat<B['la1'])&(lon>B['lo0'])&(lon<B['lo1'])
        if m.sum()<100: np.savez(fn,empty=1); return
        r,c=np.where(m); r0,r1,c0,c1=r.min(),r.max()+1,c.min(),c.max()+1
        o=dict(lat=lat[r0:r1,c0:c1].astype(np.float32),lon=lon[r0:r1,c0:c1].astype(np.float32))
        for k,v in [('syn-oa17-reflectance','SDR_Oa17'),('syn-s5n-reflectance','SDR_S5N'),('syn-s6n-reflectance','SDR_S6N'),('syn-oa08-reflectance','SDR_Oa08')]:
            h=h5py.File(RangeFile(a[k]['href']+'?'+T),'r'); o[v]=h[v][r0:r1,c0:c1]
        h=h5py.File(RangeFile(a['syn-flags']['href']+'?'+T),'r')
        o['CLOUD']=h['CLOUD_flags'][r0:r1,c0:c1]; o['SYN']=h['SYN_flags'][r0:r1,c0:c1]
        np.savez_compressed(fn,dt=f['properties']['datetime'],**o); print('ok',f['id'],flush=True)
    except Exception as e: print('ERR',f['id'],e,flush=True)
if __name__=='__main__':
    with Pool(5) as p: p.map(one,items,chunksize=1)
