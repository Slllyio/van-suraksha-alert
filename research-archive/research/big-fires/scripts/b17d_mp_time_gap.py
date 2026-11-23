import os, numpy as np, pandas as pd
from pyproj import Transformer
R='/mnt/project-files/research/big-fires/results'; M='/mnt/project-files/fire-alert-scars/mp/out'; CL='/tmp/claude-0/mp_eco/clips'
D=pd.read_csv(f'{R}/mp_ecostress_passes.csv',parse_dates=['t0']); V=D[D.visible==True]
A=pd.read_csv(f'{M}/mp_alert_event.csv',usecols=['latitude','longitude','acq_date','acq_time','satellite','instrument','scan','track','event_id'])
A=A[(A.instrument=='VIIRS')&A.event_id.isin(V.event_id)]
A['t']=pd.to_datetime(A.acq_date+' '+A.acq_time.astype(int).astype(str).str.zfill(4),format='%Y-%m-%d %H%M')
to43=Transformer.from_crs('EPSG:4326','EPSG:32643',always_xy=True); A['x'],A['y']=to43.transform(A.longitude.values,A.latitude.values)
rows=[]
for r in V.itertuples():
    z=np.load(f'{CL}/{r.event_id}_{r.granule}.npz'); lst=z['lst'].astype(float); clear=np.isfinite(lst)&(lst>250)&(z['cloud']==0)
    v=A[(A.event_id==r.event_id)&((A.t-r.t0).abs()<=pd.Timedelta(hours=1))]
    g=v[v.satellite==r.sensor]
    if g.empty: continue
    dmin=np.hypot(z['x'][:,None]-v.x.values[None],z['y'][:,None]-v.y.values[None]).min(1)
    near,ring=dmin<=600,(dmin>=1500)&(dmin<=3000); bg=np.median(lst[clear&ring]); hot=(lst-bg>10)&clear&near
    hx,hy=z['x'][hot],z['y'][hot]; bx,by=g.x.values,g.y.values; hw=g.scan.values*500; hh=g.track.values*500
    d=np.hypot(hx[:,None]-bx[None],hy[:,None]-by[None]); i=d.argmin(1)
    u=np.maximum(np.abs(hx-bx[i])/hw[i],np.abs(hy-by[i])/hh[i])
    gap=(r.t0-g.t.iloc[0]).total_seconds()/60   # + = 70 m after VIIRS
    rows.append(dict(event_id=r.event_id,sensor=r.sensor,gap=gap,absgap=abs(gap),dnear=np.median(d.min(1)),outer=(u>0.5).mean(),inside=(u<=1).mean(),nb=len(g)))
X=pd.DataFrame(rows); X.to_csv('/tmp/claude-0/work/gap_rows.csv',index=False)
print(X.absgap.describe().round(1).to_dict())
print('gap sign: 70m after VIIRS',(X.gap>0).mean().round(2))
X['b']=pd.cut(X.absgap,[-0.1,5,15,30,45,61],labels=['0-5','5-15','15-30','30-45','45-60'])
print(X.groupby('b',observed=True).agg(passes=('gap','size'),dist_m=('dnear','median'),outer=('outer','mean'),inside=('inside','mean')).round(2).to_string())
print('by sensor', X.groupby('sensor').absgap.median().to_dict())
print('corr absgap~dist', np.corrcoef(X.absgap,X.dnear)[0,1].round(3))
