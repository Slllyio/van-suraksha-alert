# Temporal-contextual fire detection on GK2A SW038/IR112 box stacks; validate vs FIRMS VIIRS; diurnal curve.
import sys,os,glob,numpy as np,pandas as pd,datetime as dt
sys.path.insert(0,os.path.dirname(os.path.abspath(__file__)))
from geos import ll2lc
D=sys.argv[1]; yr=sys.argv[2]; FIRMS=sys.argv[3]; K=float(sys.argv[4]) if len(sys.argv)>4 else 4.0; T11MIN=float(sys.argv[5]) if len(sys.argv)>5 else 295.0; SH=-1
fs=sorted(glob.glob(D+'/gk2a_*.npz'))
ts=pd.to_datetime([os.path.basename(f)[5:17] for f in fs],format='%Y%m%d%H%M')
z0=np.load(fs[0]); L0,C0=int(z0['L0']),int(z0['C0'])
T38=np.stack([np.load(f)['sw038'] for f in fs]); T11=np.stack([np.load(f)['ir112'] for f in fs])
dT=T38-T11
isth=((ts+pd.Timedelta('5.5h')).hour).values
day=(isth>=7)&(isth<18)
clr=np.where(day[:,None,None],T11>T11MIN,T11>280)
T38c=np.where(clr,T38,np.nan); dTc=np.where(clr,dT,np.nan)
slot=(ts.hour*60+ts.minute).values; days=ts.normalize()
nl,nc=T38.shape[1:]
# per-slot medians across days (background) and MAD
A=np.full_like(dT,np.nan); A38=np.full_like(dT,np.nan); S=np.full_like(dT,np.nan); S38=np.full_like(dT,np.nan); C11=np.full_like(dT,np.nan)
for s in np.unique(slot):
    m=slot==s
    md=np.nanmedian(dTc[m],0); md38=np.nanmedian(T38c[m],0); md11=np.nanmedian(T11[m],0)
    mad=1.4826*np.nanmedian(np.abs(dTc[m]-md),0); mad38=1.4826*np.nanmedian(np.abs(T38c[m]-md38),0)
    A[m]=dT[m]-md; A38[m]=T38[m]-md38; S[m]=mad; S38[m]=mad38; C11[m]=T11[m]-md11
# remove slot-wide (regional) offset per time step
A-=np.nanmedian(A,axis=(1,2),keepdims=True); A38-=np.nanmedian(A38,axis=(1,2),keepdims=True)
C11r=C11-np.nanmedian(C11,axis=(1,2),keepdims=True)
fire=(A>np.maximum(K*S,2.5))&(A38>np.maximum(K*S38,2.0))&clr
print('clear fraction day %.2f night %.2f'%(clr[day].mean(),clr[~day].mean())); print('detections',int(fire.sum()),'per slot mean %.2f'%(fire.sum()/len(ts)))
ii,ll,cc=np.where(fire)
det=pd.DataFrame({'t':ts[ii],'li':ll,'ci':cc,'A':A[ii,ll,cc],'A38':A38[ii,ll,cc]})
# pixel centres lat/lon via lookup grid
la=np.arange(20.5,25.5,0.01); lo=np.arange(74.5,81.5,0.01); LA,LO=np.meshgrid(la,lo,indexing='ij'); gl,gc=ll2lc(LA,LO)
gli=np.round(gl).astype(int)-L0+SH; gci=np.round(gc).astype(int)-C0+SH
key=pd.DataFrame({'li':gli.ravel(),'ci':gci.ravel(),'lat':LA.ravel(),'lon':LO.ravel()}).groupby(['li','ci']).mean()
det=det.join(key,on=['li','ci'])
det['ist']=det.t+pd.Timedelta('5.5h')
det.to_csv(D+f'/../gk2a_det_{yr}_K{K:g}_T{T11MIN:g}.csv',index=False)
# FIRMS
def load(f,src):
    d=pd.read_csv(f); d=d[d.latitude.between(21,25)&d.longitude.between(75,81)].copy(); d['src']=src
    d['t']=pd.to_datetime(d.acq_date+' '+d.acq_time.astype(str).str.zfill(4),format='%Y-%m-%d %H%M'); return d
v=pd.concat([load(f'{FIRMS}/viirs-snpp_{yr}_India.csv','SNPP'),load(f'{FIRMS}/viirs-jpss1_{yr}_India.csv','N20'),load(f'{FIRMS}/modis_{yr}_India.csv','MODIS')])
v=v[(v.t>=ts.min()-pd.Timedelta('1h'))&(v.t<=ts.max()+pd.Timedelta('1h'))]
l,c=ll2lc(v.latitude.values,v.longitude.values); v['li']=np.round(l).astype(int)-L0+SH; v['ci']=np.round(c).astype(int)-C0+SH
v.to_csv(D+f'/../firms_box_{yr}.csv',index=False)
# 1) detection probability: VIIRS pixel-cells (GK2A pixel) per pass, by summed FRP; GK2A hit within 1 px at nearest slot (+-20 min)
vs=v[v.src!='MODIS'].copy(); vs['pass']=vs.t.dt.floor('30min')
g=vs.groupby(['src','pass','li','ci']).agg(frp=('frp','sum'),n=('frp','size'),t=('t','median'),dn=('daynight','first')).reset_index()
fset={}
for r in det.itertuples(): fset.setdefault(r.t,set()).add((r.li,r.ci))
tarr=ts.values
def hit(r):
    j=np.argmin(np.abs(tarr-np.datetime64(r.t)));
    if abs(tarr[j]-np.datetime64(r.t))>np.timedelta64(20,'m'): return np.nan
    s=fset.get(pd.Timestamp(tarr[j]),set())
    return float(any((r.li+a,r.ci+b) in s for a in (-1,0,1) for b in (-1,0,1)))
g['hit']=g.apply(hit,axis=1)
print('\nDetection probability of GK2A (K=%g) for VIIRS fire pixels aggregated to GK2A pixels, by pass FRP:'%K)
for dn in ['D','N']:
    for lo_,hi_ in [(0,5),(5,10),(10,30),(30,100),(100,1e9)]:
        s=g[(g.dn==dn)&(g.frp>=lo_)&(g.frp<hi_)].dropna(subset=['hit']); print('  %s FRP %g-%g MW: n=%d hit=%.1f%%'%(dn,lo_,hi_,len(s),100*s.hit.mean() if len(s) else np.nan))
# 2) commission: GK2A detections at slots within 20 min of a VIIRS pass over that pixel area: is there any FIRMS fire (any sensor) within 2 px same IST day?
v['istday']=(v.t+pd.Timedelta('5.5h')-pd.Timedelta('6h')).dt.normalize()
det['istday']=(det.ist-pd.Timedelta('6h')).dt.normalize()
vk=set(zip(v.istday,v.li,v.ci))
det['firms_sameday_2px']=[any((d,li+a,ci+b) in vk for a in range(-2,3) for b in range(-2,3)) for d,li,ci in zip(det.istday,det.li,det.ci)]
print('\nGK2A detections confirmed by any FIRMS fire within 2 px same fire-day (06-06 IST): %.1f%% of %d'%(100*det.firms_sameday_2px.mean(),len(det)))
# 3) diurnal curve (confirmed detections only), by IST hour
dc=det[det.firms_sameday_2px]
h=dc.groupby(dc.ist.dt.hour).size().reindex(range(24),fill_value=0)
print('\nConfirmed GK2A detections by IST hour (pixel-slots):',h.to_dict())
# first detection hour per pixel-day event (confirmed)
ev=dc.sort_values('t').groupby(['istday','li','ci']).agg(first=('ist','min'),last=('ist','max'),n=('t','size'),lat=('lat','first'),lon=('lon','first')).reset_index()
print('events',len(ev),'first-detection IST hour distribution:',ev['first'].dt.hour.value_counts().sort_index().to_dict())
print('median first hour %.2f, IQR %s'%((ev['first'].dt.hour+ev['first'].dt.minute/60).median(), np.percentile(ev['first'].dt.hour+ev['first'].dt.minute/60,[25,75]).round(2)))
ev.to_csv(D+f'/../gk2a_events_{yr}_K{K:g}_T{T11MIN:g}.csv',index=False)
