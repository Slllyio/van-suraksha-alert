# Composite (stacked) GK2A 3.8-11.2 um anomaly by IST half-hour at FIRMS fire pixel-days vs no-fire controls: sub-threshold diurnal curve.
import sys,os
import sys,os,glob,numpy as np,pandas as pd,warnings; warnings.filterwarnings('ignore')
sys.path.insert(0,os.path.dirname(os.path.abspath(__file__)))
D=sys.argv[1]; yr=sys.argv[2]; OUT=sys.argv[3]
fs=sorted(glob.glob(D+'/gk2a_*.npz')); ts=pd.to_datetime([os.path.basename(f)[5:17] for f in fs],format='%Y%m%d%H%M')
T38=np.stack([np.load(f)['sw038'] for f in fs]); T11=np.stack([np.load(f)['ir112'] for f in fs]); dT=T38-T11
ist=ts+pd.Timedelta('5.5h'); isth=ist.hour.values; day=(isth>=7)&(isth<19)
clr=np.where(day[:,None,None],T11>295,T11>280)
from numpy.lib.stride_tricks import sliding_window_view as sw
P=np.pad(clr,((0,0),(1,1),(1,1)),constant_values=False); clr3=sw(P,(3,3),axis=(1,2)).all(axis=(-1,-2))
dTc=np.where(clr,dT,np.nan); slot=(ts.hour*60+ts.minute).values
A=np.full_like(dT,np.nan); S=np.full_like(dT,np.nan)
for s in np.unique(slot):
    m=slot==s; md=np.nanmedian(dTc[m],0); A[m]=dT[m]-md; S[m]=1.4826*np.nanmedian(np.abs(dTc[m]-md),0)
A-=np.nanmedian(np.where(clr,A,np.nan),axis=(1,2),keepdims=True)
A=np.where(clr3,A,np.nan)
Pa=np.pad(A,((0,0),(1,1),(1,1)),constant_values=np.nan); Amax=np.nanmax(sw(Pa,(3,3),axis=(1,2)),axis=(-1,-2))  # 3x3 max absorbs geolocation error
fday=(ist-pd.Timedelta('6h')).normalize(); tod=((ist-pd.Timedelta('6h'))-fday)/pd.Timedelta('1h')+6  # 6..30 h
v=pd.read_csv(os.path.dirname(os.path.abspath(D))+f'/firms_box_{yr}.csv',parse_dates=['t','ist','istday']); v=v[v.src!='MODIS']
nl,nc=A.shape[1:]; v=v[v.li.between(0,nl-1)&v.ci.between(0,nc-1)]
pdays=v.groupby(['istday','li','ci']).agg(frp=('frp','sum'),nd=('daynight',lambda x:(x=='D').sum()),nn=('daynight',lambda x:(x=='N').sum())).reset_index()
fireset=set(zip(v.istday,v.li,v.ci))
def busy(dd,l,c): return any((dd+pd.Timedelta(days=k),l+a,c+b) in fireset for k in (-1,0,1) for a in range(-3,4) for b in range(-3,4))
rng=np.random.default_rng(1); udays=pd.DatetimeIndex(sorted(set(fday)))
ctrl=[]
while len(ctrl)<3000:
    dd=udays[rng.integers(len(udays))]; l=rng.integers(3,nl-3); c=rng.integers(3,nc-3)
    if not busy(dd,l,c): ctrl.append((dd,l,c))
bins=np.arange(6,30.01,1.0)
def curve(rows):
    acc=[[] for _ in range(len(bins)-1)]
    for dd,l,c in rows:
        m=np.where(fday==dd)[0]
        for j in m:
            b=int(tod[j]-6)
            if 0<=b<len(acc):
                x=Amax[j,l,c]
                if np.isfinite(x): acc[b].append(x)
    return np.array([np.nanmean(a) if len(a)>20 else np.nan for a in acc]), np.array([len(a) for a in acc])
cc,nc_=curve(ctrl)
res={'hour':bins[:-1].astype(int)%24,'control':cc.round(2),'n_ctrl':nc_}
aoi=lambda df: df[(df.li.between(*AOIL))&(df.ci.between(*AOIC))]
from geos import ll2lc
l1,c1=ll2lc(np.array([22.82,23.10]),np.array([77.34,78.07])); L0=int(np.load(fs[0])['L0']); C0=int(np.load(fs[0])['C0'])
AOIL=(int(np.round(l1.min()))-L0-1,int(np.round(l1.max()))-L0-1); AOIC=(int(np.round(c1.min()))-C0-1,int(np.round(c1.max()))-C0-1)
groups={'all_firedays':pdays,'day_detected':pdays[pdays.nd>0],'night_only':pdays[(pdays.nd==0)&(pdays.nn>0)],
        'frp<10':pdays[pdays.frp<10],'frp10-50':pdays[(pdays.frp>=10)&(pdays.frp<50)],'frp>=50':pdays[pdays.frp>=50],
        'AOI_all':aoi(pdays)}
for k,g in groups.items():
    cu,n=curve(list(zip(g.istday,g.li,g.ci))); res[k+f' (n={len(g)})']=(cu-cc).round(2)
r=pd.DataFrame(res); r.to_csv(OUT,index=False); print(r.to_string(index=False)); print('AOI line/col idx',AOIL,AOIC)
