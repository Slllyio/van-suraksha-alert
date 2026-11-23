# Fetch EUMETView msg_iodc ir039 and ir108 greyscale PNGs over a central-India box every 15 min; save as uint8 npz stack.
import sys, io, time, datetime as dt, urllib.request, numpy as np, concurrent.futures as cf
from PIL import Image
out=sys.argv[1]; d0=dt.datetime.fromisoformat(sys.argv[2]); d1=dt.datetime.fromisoformat(sys.argv[3])
S,N,W_,E=22.0,24.0,76.5,79.0; W,H=250,200
def url(layer,t): return ('https://view.eumetsat.int/geoserver/ows?service=WMS&version=1.3.0&request=GetMap&layers=%s&styles=&crs=EPSG:4326&bbox=%s,%s,%s,%s&width=%d&height=%d&format=image/png&time='%(layer,S,W_,N,E,W,H))+t.strftime('%Y-%m-%dT%H:%M:00Z')
def get(args):
    layer,t=args
    for k in range(4):
        try:
            b=urllib.request.urlopen(url(layer,t),timeout=60).read()
            return np.array(Image.open(io.BytesIO(b)).convert('L'))
        except Exception as e: time.sleep(3)
    return np.full((H,W),0,np.uint8)
ts=[]; t=d0
while t<d1: ts.append(t); t+=dt.timedelta(minutes=15)
res={}
with cf.ThreadPoolExecutor(4) as ex:
    a39=list(ex.map(get,[('msg_iodc:ir039',t) for t in ts]))
    a108=list(ex.map(get,[('msg_iodc:ir108',t) for t in ts]))
np.savez_compressed(out,t=np.array([x.isoformat() for x in ts]),ir039=np.stack(a39),ir108=np.stack(a108),bbox=np.array([S,N,W_,E]))
print('done',len(ts))
