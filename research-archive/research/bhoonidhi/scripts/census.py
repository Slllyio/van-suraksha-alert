import json, sys, time, datetime as dt, pandas as pd
from qp import search
SETS={'awifs':['ResourceSat-2_AWIFS','ResourceSat-2A_AWIFS'],'liss3':['ResourceSat-2_LISS3','ResourceSat-2A_LISS3'],
      'liss4':['ResourceSat-2_LISS4(MX70)','ResourceSat-2A_LISS4(MX70)'],'eos04':['EOS-04_SAR(MRS)']}
which=sys.argv[1]; rows=[]
YRS={'awifs':range(2017,2026),'eos04':range(2022,2026),'liss3':range(2024,2026),'liss4':range(2024,2026)}[which]
import os
for yr in YRS:
    fo=f'cat_{which}_{yr}.csv'
    if os.path.exists(fo): continue
    rows=[]
    d=dt.date(yr,2,15)
    while d<=dt.date(yr,6,15):
        e=min(d+dt.timedelta(days=4),dt.date(yr,6,15))
        f=lambda x:x.strftime('%b/%d/%Y')
        off=0
        while True:
            j=search(SETS[which],f(d),f(e),offset=off); r=j.get('Results',[])
            rows+= [dict(sensor=which,**{k:x[k] for k in ['ID','SATELLITE','SENSOR','DOP','PATHNO','SCENE_NO','PRICED','ImgCrnNWLat','ImgCrnNWLon','ImgCrnNELat','ImgCrnNELon','ImgCrnSELat','ImgCrnSELon','ImgCrnSWLat','ImgCrnSWLon','IMAGING_MODE']}) for x in r]
            if len(r)==0 or off>5000: break
            off+=len(r)
        d=e+dt.timedelta(days=1); time.sleep(1.5)
    pd.DataFrame(rows).drop_duplicates('ID').to_csv(fo,index=False); print(which,yr,len(rows),flush=True)
import glob
pd.concat([pd.read_csv(f) for f in sorted(glob.glob(f'cat_{which}_20*.csv'))]).to_csv(f'cat_{which}.csv',index=False)
