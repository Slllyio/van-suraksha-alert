import pickle, numpy as np, pandas as pd, os, sys
from concurrent.futures import ThreadPoolExecutor
from pyproj import Transformer
from orb import fetch
to4=Transformer.from_crs(32643,4326,always_xy=True).transform
F=pickle.load(open('/tmp/claude-0/mpbig/fires_list.pkl','rb'))
os.makedirs('raw',exist_ok=True)
def one(f):
    seed,d,_=f; out=f'raw/{seed}.npz'
    if os.path.exists(out): return seed,'cached'
    p=f'/tmp/claude-0/mpbig/fire_{seed}.pkl'
    if not os.path.exists(p): return seed,'nofire'
    x0,y1,W,H=pickle.load(open(p,'rb'))['box']; x1=x0+W*20; y0=y1-H*20
    x0-=3000;x1+=3000;y0-=3000;y1+=3000
    lo0,la0=to4(x0,y0); lo1,la1=to4(x1,y1)
    w=max(int((lo1-lo0)/0.009),4); h=max(int((la1-la0)/0.009),4)
    fr=(d.t.min()-pd.Timedelta(days=4)).floor('D'); to=(d.t.max()+pd.Timedelta(days=1)).ceil('D')
    res={}
    for od in ['ASCENDING','DESCENDING']:
        try: ds,a=fetch([lo0,la0,lo1,la1],fr.isoformat()+'Z',to.isoformat()+'Z',od,w,h)
        except Exception as e: return seed,'err '+str(e)[:100]
        res[od[:3]+'_dates']=np.array(ds); res[od[:3]]=a.astype(np.float32)
    np.savez_compressed(out,bbox=np.array([lo0,la0,lo1,la1]),**res); return seed,'ok'
with ThreadPoolExecutor(4) as ex:
    for i,(s,st) in enumerate(ex.map(one,F)):
        if st not in('ok','cached') or i%50==0: print(i,s,st,flush=True)
print('EXIT',flush=True)
