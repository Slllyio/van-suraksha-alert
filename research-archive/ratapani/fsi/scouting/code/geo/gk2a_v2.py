# v2: temporal-contextual GK2A fire detection with cloud-edge screening and optional 2-slot persistence; validation vs FIRMS; hourly tables.
import sys,os,glob,numpy as np,pandas as pd
sys.path.insert(0,os.path.dirname(os.path.abspath(__file__)))
from geos import ll2lc
D,yr,FIRMS=sys.argv[1:4]; K=float(sys.argv[4]); PERSIST=int(sys.argv[5]); TAG=sys.argv[6]
SH=-1; T11DAY=295.
fs=sorted(glob.glob(D+'/gk2a_*.npz')); ts=pd.to_datetime([os.path.basename(f)[5:17] for f in fs],format='%Y%m%d%H%M')
z0=np.load(fs[0]); L0,C0=int(z0['L0']),int(z0['C0'])
T38=np.stack([np.load(f)['sw038'] for f in fs]); T11=np.stack([np.load(f)['ir112'] for f in fs]); dT=T38-T11
isth=(ts+pd.Timedelta('5.5h')).hour.values; day=(isth>=7)&(isth<19)
clr=np.where(day[:,None,None],T11>T11DAY,T11>280)
# cloud-edge: require all 8 neighbours clear
from numpy.lib.stride_tricks import sliding_window_view as sw
P=np.pad(clr,((0,0),(1,1),(1,1)),constant_values=False); clr3=sw(P,(3,3),axis=(1,2)).all(axis=(-1,-2))
T38c=np.where(clr,T38,np.nan); dTc=np.where(clr,dT,np.nan)
slot=(ts.hour*60+ts.minute).values
A=np.full_like(dT,np.nan); A38=np.full_like(dT,np.nan); S=np.full_like(dT,np.nan); S38=np.full_like(dT,np.nan)
import warnings; warnings.filterwarnings('ignore')
for s in np.unique(slot):
    m=slot==s; md=np.nanmedian(dTc[m],0); md38=np.nanmedian(T38c[m],0)
    S[m]=1.4826*np.nanmedian(np.abs(dTc[m]-md),0); S38[m]=1.4826*np.nanmedian(np.abs(T38c[m]-md38),0)
    A[m]=dT[m]-md; A38[m]=T38[m]-md38
A-=np.nanmedian(np.where(clr,A,np.nan),axis=(1,2),keepdims=True); A38-=np.nanmedian(np.where(clr,A38,np.nan),axis=(1,2),keepdims=True)
fire=(A>np.maximum(K*S,2.5))&(A38>np.maximum(K*S38,2.0))&clr3
if PERSIST:  # require detection in previous or next slot at same pixel or a neighbour
    Fp=np.pad(fire,((1,1),(1,1),(1,1))); nb=sw(Fp,(3,3),axis=(1,2)).any(axis=(-1,-2))  # (t+2,l,c)
    fire=fire&(nb[:-2]|nb[2:])
ii,ll,cc=np.where(fire)
det=pd.DataFrame({'t':ts[ii],'li':ll,'ci':cc,'A':A[ii,ll,cc],'A38':A38[ii,ll,cc],'S':S[ii,ll,cc]})
la=np.arange(20.5,25.5,0.01); lo=np.arange(74.5,81.5,0.01); LA,LO=np.meshgrid(la,lo,indexing='ij'); gl,gc=ll2lc(LA,LO)
key=pd.DataFrame({'li':(np.round(gl).astype(int)-L0+SH).ravel(),'ci':(np.round(gc).astype(int)-C0+SH).ravel(),'lat':LA.ravel(),'lon':LO.ravel()}).groupby(['li','ci']).mean()
det=det.join(key,on=['li','ci']); det['ist']=det.t+pd.Timedelta('5.5h'); det['istday']=(det.ist-pd.Timedelta('6h')).dt.normalize()
def load(f,src):
    d=pd.read_csv(f); d=d[d.latitude.between(21,25)&d.longitude.between(75,81)].copy(); d['src']=src
    d['t']=pd.to_datetime(d.acq_date+' '+d.acq_time.astype(str).str.zfill(4),format='%Y-%m-%d %H%M'); return d
v=pd.concat([load(f'{FIRMS}/viirs-snpp_{yr}_India.csv','SNPP'),load(f'{FIRMS}/viirs-jpss1_{yr}_India.csv','N20'),load(f'{FIRMS}/modis_{yr}_India.csv','MODIS')])
v=v[(v.t>=ts.min()-pd.Timedelta('1d'))&(v.t<=ts.max()+pd.Timedelta('1d'))]
l,c=ll2lc(v.latitude.values,v.longitude.values); v['li']=np.round(l).astype(int)-L0+SH; v['ci']=np.round(c).astype(int)-C0+SH
v['ist']=v.t+pd.Timedelta('5.5h'); v['istday']=(v.ist-pd.Timedelta('6h')).dt.normalize()
vk=set(zip(v.istday,v.li,v.ci)); vk1=set(zip(v.istday-pd.Timedelta('1d'),v.li,v.ci))|set(zip(v.istday+pd.Timedelta('1d'),v.li,v.ci))
det['conf_sameday']=[any((d,li+a,ci+b) in vk for a in range(-2,3) for b in range(-2,3)) for d,li,ci in zip(det.istday,det.li,det.ci)]
det["conf_pm1day"]=det.conf_sameday.values|np.array([any((d,li+a,ci+b) in vk1 for a in range(-2,3) for b in range(-2,3)) for d,li,ci in zip(det.istday,det.li,det.ci)])
vs=v[v.src!='MODIS'].copy(); g=vs.assign(pas=vs.t.dt.floor('30min')).groupby(['src','pas','li','ci']).agg(frp=('frp','sum'),t=('t','median'),dn=('daynight','first')).reset_index(drop=False)
fset={}
for r in det.itertuples(): fset.setdefault(r.t,set()).add((r.li,r.ci))
tarr=ts.values
def hit(r):
    j=np.argmin(np.abs(tarr-np.datetime64(r.t)))
    if abs(tarr[j]-np.datetime64(r.t))>np.timedelta64(20,'m'): return np.nan
    s=set().union(*[fset.get(pd.Timestamp(tarr[k]),set()) for k in range(max(j-1,0),min(j+2,len(tarr)))])
    return float(any((r.li+a,r.ci+b) in s for a in (-1,0,1) for b in (-1,0,1)))
g['hit']=g.apply(hit,axis=1)
out=[f'## {TAG}: K={K}, persist={PERSIST}; slots={len(ts)}; clear frac day {clr[day].mean():.2f} night {clr[~day].mean():.2f}; detections {len(det)}']
out.append('POD vs VIIRS (VIIRS FRP summed per GK2A pixel per pass; hit = GK2A detection within 1 px, +-30 min):')
for dn in 'DN':
    out.append('  '+dn+': '+'; '.join('%g-%g MW n=%d POD=%.1f%%'%(lo_,hi_,len(s),100*s.hit.mean()) for lo_,hi_ in [(0,5),(5,10),(10,30),(30,100),(100,1e9)] for s in [g[(g.dn==dn)&(g.frp>=lo_)&(g.frp<hi_)].dropna(subset=['hit'])] if len(s)))
h=det.groupby(det.ist.dt.hour).agg(n=('A','size'),conf=('conf_sameday','mean'),conf1=('conf_pm1day','mean'))
Sh=pd.Series([np.nanmedian(S[isth==k]) for k in range(24)],index=range(24))
h=h.reindex(range(24)); h['medS']=Sh.round(2)
out.append('By IST hour: n detections, share confirmed by FIRMS same fire-day / +-1 day, median background MAD (K):')
out.append(h.round(2).T.to_string())
det.to_csv(os.path.dirname(os.path.abspath(D))+f'/gk2a_det_{TAG}.csv',index=False); v.to_csv(os.path.dirname(os.path.abspath(D))+f'/firms_box_{yr}.csv',index=False)
g.to_csv(os.path.dirname(os.path.abspath(D))+f'/gk2a_pod_{TAG}.csv',index=False)
print('\n'.join(out))
