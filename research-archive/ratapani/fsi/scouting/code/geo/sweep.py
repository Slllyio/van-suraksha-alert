# Sweep EUMETView WMS msg_iodc:fire over central India for every 15-min slot; record coloured pixels.
import sys, io, time, datetime as dt, urllib.request, numpy as np, json, concurrent.futures as cf
from PIL import Image
out=sys.argv[1]; d0=dt.datetime.fromisoformat(sys.argv[2]); d1=dt.datetime.fromisoformat(sys.argv[3]); layer=sys.argv[4] if len(sys.argv)>4 else 'msg_iodc:fire'
S,N,Wl,E=21.0,25.0,75.0,81.0; W,H=1200,800
base='https://view.eumetsat.int/geoserver/ows?service=WMS&version=1.3.0&request=GetMap&layers=%s&styles=&crs=EPSG:4326&bbox=%s,%s,%s,%s&width=%d&height=%d&format=image/png&transparent=true&time='%(layer,S,Wl,N,E,W,H)
def get(t):
    u=base+t.strftime('%Y-%m-%dT%H:%M:00Z')
    for k in range(4):
        try:
            b=urllib.request.urlopen(u,timeout=60).read()
            a=np.array(Image.open(io.BytesIO(b)).convert('RGBA'))
            r,c=np.where(a[...,3]>0)
            px=[(round(N-(rr+.5)*(N-S)/H,4),round(Wl+(cc+.5)*(E-Wl)/W,4),int(a[rr,cc,0]),int(a[rr,cc,1])) for rr,cc in zip(r,c)]
            return t.isoformat(),px,None
        except Exception as e:
            err=str(e); time.sleep(3)
    return t.isoformat(),None,err
ts=[]; t=d0
while t<d1: ts.append(t); t+=dt.timedelta(minutes=15)
res={}
with cf.ThreadPoolExecutor(4) as ex:
    for k,px,err in ex.map(get,ts):
        res[k]={'px':px,'err':err}
json.dump(res,open(out,'w'))
print('done',len(res),sum(1 for v in res.values() if v['err']), sum(1 for v in res.values() if v['px']))
