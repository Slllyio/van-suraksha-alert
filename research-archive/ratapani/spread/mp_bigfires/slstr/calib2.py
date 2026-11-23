import numpy as np, pandas as pd, pickle
from scipy.spatial import cKDTree
F=pickle.load(open('/tmp/claude-0/mpbig/fires_list.pkl','rb')); D={s:d for s,d,_ in F}
C=pd.read_parquet('cand.parquet'); O=pd.read_parquet('orbits.parquet'); O=O[O.valid>.5]
MO='/mnt/project-files/fire-alert-scars/mp/out'
A=pd.read_csv(f'{MO}/mp_alert_event.csv',usecols=['latitude','longitude','acq_date','acq_time'])
A['t']=pd.to_datetime(A.acq_date+' '+A.acq_time.astype(int).astype(str).str.zfill(4),format='%Y-%m-%d %H%M')
from pyproj import Transformer; to43=Transformer.from_crs(4326,32643,always_xy=True).transform
A['x'],A['y']=to43(A.longitude.values,A.latitude.values); A['th']=(A.t-pd.Timestamp('2017-01-01')).dt.total_seconds()/3600
# 3D tree: x,y in m, time scaled so 8 h ~ 1500 m
sc=1500/8; AT=cKDTree(np.c_[A.x,A.y,A.th*sc])
C['th']=(C.t-pd.Timestamp('2017-01-01')).dt.total_seconds()/3600
dist=AT.query(np.c_[C.x,C.y,C.th*sc],distance_upper_bound=1500*1.42)[0]
# confirmed if alert within 1.5 km and 8 h (approx via scaled sphere; then exact check)
C['conf']=np.isfinite(dist)
C['T0']=C.seed.map(lambda s:D[s].t.min()); C['pre']=C.t<C.T0-pd.Timedelta(days=1)
O['T0']=O.seed.map(lambda s:D[s].t.min()); O['pre']=O.t<O.T0-pd.Timedelta(days=1)
def hits(sel,od):
    n=h=0
    for r in O[(O.od==od)&~O.pre].itertuples():
        d=D[r.seed]; fd=d[(d.t>=r.t-pd.Timedelta(hours=8))&(d.t<=r.t+pd.Timedelta(hours=8))]
        if not len(fd): continue
        n+=1; q=sel[(sel.seed==r.seed)&(sel.t==r.t)&(sel.od==od)]
        if len(q) and (cKDTree(fd[['x','y']].values).query(q[['x','y']].values)[0]<1500).any(): h+=1
    return n,h
rows=[]
for od in ['ASC','DES']:
    npre=int((O.pre&(O.od==od)).sum())
    for kz in [3,4,5,6,8]:
        for kd in [3,5,8,12,16]:
            s=C[(C.od==od)&(C.zF>kz)&(C.zD>kz)&(C.dF>kd)&(C.dD>kd)]
            fa=s[s.pre&~s.conf]; n,h=hits(s,od)
            rows.append(dict(od=od,kz=kz,kd=kd,pre_orbits=npre,fa_per_orbit=round(len(fa)/npre,3),fa_orbit_share=round(fa.groupby(['seed','t']).ngroups/npre,3),
                             burning_orbits=n,hit_rate=round(h/max(n,1),3),conf_share_postT0=round(s[~s.pre].conf.mean(),3) if len(s) else None))
            print(rows[-1],flush=True)
pd.DataFrame(rows).to_csv('calib2.csv',index=False)
