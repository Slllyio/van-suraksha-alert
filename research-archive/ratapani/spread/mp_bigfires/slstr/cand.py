import numpy as np, pandas as pd, pickle, os
from pyproj import Transformer
from concurrent.futures import ProcessPoolExecutor
to43=Transformer.from_crs(4326,32643,always_xy=True).transform
HOUR={'ASC':16.83,'DES':5.0}
F=pickle.load(open('/tmp/claude-0/mpbig/fires_list.pkl','rb'))
def one(seed):
    z=np.load(f'raw/{seed}.npz'); lo0,la0,lo1,la1=z['bbox']; out=[]; orb=[]
    for od in ['ASC','DES']:
        a=z[od]; h,w=a.shape[:2]
        for i,dt in enumerate(z[od+'_dates']):
            f1=a[...,2*i]; s8=a[...,2*i+1]; fv=np.isfinite(f1).mean()
            t=pd.Timestamp(dt[:10])+pd.Timedelta(hours=HOUR[od]); orb.append((seed,od,t,fv))
            if fv<.5: continue
            dT=f1-s8; mf=np.nanmedian(f1); md=np.nanmedian(dT)
            sf=1.4826*np.nanmedian(np.abs(f1-mf)); sd=1.4826*np.nanmedian(np.abs(dT-md))
            hit=(f1>mf+2.5)&(dT>md+2.5)
            for r,c in zip(*np.nonzero(hit)):
                out.append((seed,od,t,lo0+(c+.5)*(lo1-lo0)/w,la1-(r+.5)*(la1-la0)/h,f1[r,c]-mf,dT[r,c]-md,(f1[r,c]-mf)/max(sf,.1),(dT[r,c]-md)/max(sd,.1),f1[r,c]))
    return out,orb
if __name__=='__main__':
    with ProcessPoolExecutor(8) as ex: res=list(ex.map(one,[f[0] for f in F]))
    C=pd.DataFrame([r for o,_ in res for r in o],columns=['seed','od','t','lon','lat','dF','dD','zF','zD','F1'])
    O=pd.DataFrame([r for _,o in res for r in o],columns=['seed','od','t','valid'])
    C['x'],C['y']=to43(C.lon.values,C.lat.values)
    C.to_parquet('cand.parquet'); O.to_parquet('orbits.parquet'); print(len(C),len(O), O.groupby('od').valid.apply(lambda v:(v>.5).mean()).to_dict())
