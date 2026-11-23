import pandas as pd, numpy as np
from scipy.spatial import cKDTree
d=pd.read_csv('/mnt/project-files/research/big-fires/results/detections.csv',parse_dates=['t','t_ist'])
d['date']=d.t_ist.dt.date
V=d[d.sensor.isin(['S-NPP','NOAA-20','NOAA-21'])&(d.daynight=='D')]
H=d[d.sensor.isin(['Sentinel-2','Landsat'])]
rows=[];off=[]
for (f,day),hv in V.groupby(['fire','date']):
    hh=H[(H.fire==f)&(H.date==day)]
    if len(hh)<3: continue
    gap=(hv.t.median()-hh.t.median()).total_seconds()/3600
    if not (1<gap<5): continue
    th=cKDTree(hh[['x','y']].values)
    P=hv[['x','y']].values
    # per-detection: single centroid error = dist to nearest hot pixel
    e1,_=th.query(P)
    # joint estimate: mean of all VIIRS centroids (any of the 3 sats, this day pass window <2h) within 400 m incl. self, other sensors only counted
    tv=cKDTree(P); J=[]
    for i,p in enumerate(P):
        idx=tv.query_ball_point(p,400)
        other=[j for j in idx if hv.sensor.values[j]!=hv.sensor.values[i]]
        if not other: J.append(np.nan); continue
        sel=[i]+other
        J.append(th.query(P[sel].mean(0))[0])
    J=np.array(J)
    for i in range(len(P)):
        rows.append(dict(fire=f,day=day,sensor=hv.sensor.values[i],gap=gap,e_single=e1[i],e_joint=J[i],w=hv.pix_w_m.values[i],h=hv.pix_h_m.values[i]))
        # offset of nearest hotpixel in pixel units (x~scan, y~track)
        dd,j=th.query(P[i]); dx,dy=hh.x.values[j]-P[i][0],hh.y.values[j]-P[i][1]
        off.append((dx/hv.pix_w_m.values[i],dy/hv.pix_h_m.values[i],dd))
r=pd.DataFrame(rows); o=pd.DataFrame(off,columns=['u','v','d'])
print('fire-days',r.groupby(['fire','day']).ngroups,'VIIRS detections',len(r),'median gap h',r.gap.median().round(2))
print('single-centroid dist to nearest S2/L hot pixel: median',r.e_single.median().round(0),'p75',r.e_single.quantile(.75).round(0))
m=r.dropna(subset=['e_joint'])
print('detections with another sat within 400 m:',len(m))
print('  single',m.e_single.median().round(0),' joint',m.e_joint.median().round(0), ' share joint closer',(m.e_joint<m.e_single).mean().round(3))
# bootstrap by fire
fs=m.fire.unique(); rng=np.random.default_rng(0); bs=[]
for _ in range(500):
    s=rng.choice(fs,len(fs)); mm=pd.concat([m[m.fire==x] for x in s])
    bs.append(mm.e_joint.median()-mm.e_single.median())
print('  median diff joint-single 95%:',np.percentile(bs,[2.5,97.5]).round(0))
print('nearest hot pixel offset in pixel units: |u|<0.5',(o.u.abs()<.5).mean().round(3),' |v|<0.5',(o.v.abs()<.5).mean().round(3),' both',((o.u.abs()<.5)&(o.v.abs()<.5)).mean().round(3))
print('  sd u',o.u.std().round(2),' sd v',o.v.std().round(2),' (uniform within pixel would be 0.29)')
# per-sensor registration bias vs S2/Landsat hot pixels (nearest hot pixel within 600 m), metres
recs=[]
for (f,day),hv in V.groupby(['fire','date']):
    hh=H[(H.fire==f)&(H.date==day)]
    if len(hh)<3: continue
    th=cKDTree(hh[['x','y']].values)
    dd,j=th.query(hv[['x','y']].values)
    for k in range(len(hv)):
        if dd[k]<600: recs.append((hv.sensor.values[k],f,hh.x.values[j[k]]-hv.x.values[k],hh.y.values[j[k]]-hv.y.values[k]))
R=pd.DataFrame(recs,columns=['s','fire','dx','dy'])
rng=np.random.default_rng(1)
for s,g in R.groupby('s'):
    fs=g.fire.unique(); b=[]
    for _ in range(400):
        ss=rng.choice(fs,len(fs)); gg=pd.concat([g[g.fire==x] for x in ss]); b.append((gg.dx.mean(),gg.dy.mean()))
    b=np.array(b)
    print(s,len(g),'mean dx (east) %.0f [%.0f,%.0f]  dy (north) %.0f [%.0f,%.0f]'%(g.dx.mean(),*np.percentile(b[:,0],[2.5,97.5]),g.dy.mean(),*np.percentile(b[:,1],[2.5,97.5])))
