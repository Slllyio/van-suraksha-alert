"""Constrained test: inside each 20 m scar window (ws, we], use daily Sentinel-3 SYN 300 m relative NBR to pick the
sub-interval between consecutive S3 looks where the drop happened; score against VIIRS first-detection time.
Baseline = pick the sub-interval with probability proportional to its length (what a uniform prior gives)."""
import glob, sys, warnings, numpy as np, pandas as pd, rasterio
from pyproj import Transformer
from scipy.ndimage import uniform_filter
warnings.filterwarnings('ignore')
year=int(sys.argv[1]); D=sys.argv[2]; R=300
with rasterio.open(f'/mnt/project-files/research/ratapani-burn-labels/rasters/burn_{year}.tif') as r:
    a=r.read(); T=r.transform
burnt=a[0]!=-999; H,W=a.shape[1:]; f=R//20; H2,W2=H//f,W//f
agg=lambda x: x[:H2*f,:W2*f].reshape(H2,f,W2,f)
bfrac=agg(burnt).mean(axis=(1,3))
we2=np.nanmedian(agg(np.where(burnt,a[0],np.nan).astype(float)),axis=(1,3)); ws2=np.nanmedian(agg(np.where(burnt,a[1],np.nan).astype(float)),axis=(1,3))
x0,y1=T.c,T.f; tr=Transformer.from_crs(4326,32643,always_xy=True)
obs=[]
for fn in sorted(glob.glob(f'{D}/*.npz')):
    z=np.load(fn)
    if 'empty' in z: continue
    t=pd.Timestamp(str(z['dt'])).tz_convert(None)+pd.Timedelta(hours=5.5)  # IST
    X,Y=tr.transform(z['lon'].ravel(),z['lat'].ravel()); c=((X-x0)//R).astype(int); rr=((y1-Y)//R).astype(int)
    nir=z['SDR_Oa17'].ravel().astype(float); sw=z['SDR_S6N'].ravel().astype(float)
    ok=(z['CLOUD'].ravel()==0)&(nir>0)&(sw>0)&((z['SYN'].ravel()&(1<<15))==0)&(c>=0)&(c<W2)&(rr>=0)&(rr<H2)
    s=np.zeros((H2,W2)); n=np.zeros((H2,W2)); v=(nir-sw)/(nir+sw)
    np.add.at(s,(rr[ok],c[ok]),v[ok]); np.add.at(n,(rr[ok],c[ok]),1)
    nbr=np.where(n>0,s/np.maximum(n,1),np.nan)
    if np.isfinite(nbr).mean()<0.2: continue
    ub=np.isfinite(nbr)&(bfrac<0.02); num=uniform_filter(np.where(ub,nbr,0),11); den=uniform_filter(ub.astype(float),11)
    obs.append((t,nbr-np.where(den>0.2,num/np.maximum(den,1e-9),np.nan)))
obs.sort(key=lambda o:o[0]); t=np.array([o[0] for o in obs]); A=np.stack([o[1] for o in obs])
dd=np.array([(x-pd.Timestamp(f'{year}-01-01')).total_seconds()/86400 for x in t])
print('S3 looks',len(t),'clear share',np.isfinite(A).mean().round(2))
# VIIRS first detection per bin
L=pd.read_csv('/mnt/project-files/fire-alert-scars/alert_scar_lookup.csv',usecols=['latitude','longitude','acq_date','acq_time','sensor'])
L=L[L.acq_date.str.startswith(str(year))&L.sensor.str.contains('viirs')].copy()
X,Y=tr.transform(L.longitude.values,L.latitude.values); L['j']=((X-x0)//R).astype(int); L['i']=((y1-Y)//R).astype(int)
L['vd']=[(pd.Timestamp(d)-pd.Timestamp(f'{year}-01-01')).days+(int(str(tm).zfill(4)[:2])+int(str(tm).zfill(4)[2:])/60+5.5)/24 for d,tm in zip(L.acq_date,L.acq_time.astype(float).astype(int))]
first=L.groupby(['i','j']).vd.min().to_dict()
rows=[]
for i,j in np.argwhere((bfrac>=0.1)&np.isfinite(we2)&(we2>=35)&(we2<=150)):
    lo=ws2[i,j]+10.7/24; hi=we2[i,j]+10.7/24   # S2/L look times (~10:40 IST)
    y=A[:,i,j]; ok=np.isfinite(y)
    pre=ok&(dd<=lo)&(dd>lo-12); post=ok&(dd>=hi)&(dd<hi+12); ins=np.where(ok&(dd>lo)&(dd<hi))[0]
    if pre.sum()<2 or post.sum()<2: continue
    dn=np.median(y[pre])-np.median(y[post]); sd=np.std(np.r_[y[pre]-np.median(y[pre]),y[post]-np.median(y[post])])
    cuts=np.r_[lo,dd[ins],hi]
    # each candidate split k: obs before -> pre-like, after -> post-like; pick max likelihood (least squares)
    best=None
    for k in range(len(cuts)-1):
        ypre=np.r_[y[pre],y[ins[:k]]]; ypost=np.r_[y[ins[k:]],y[post]]
        sse=((ypre-np.median(y[pre]))**2).sum()+((ypost-np.median(y[post]))**2).sum()
        if best is None or sse<best[0]: best=(sse,k)
    k=best[1]; seg=np.diff(cuts)
    v=first.get((i,j),np.nan)
    hit=(cuts[k]<v<=cuts[k+1]+0.25) if np.isfinite(v) else np.nan
    hit_s=(cuts[k]<v<=cuts[k+1]) if np.isfinite(v) else np.nan
    off=(v-cuts[k+1]) if np.isfinite(v) else np.nan
    # uniform baseline: P(hit)=length of the segment containing v / total
    if np.isfinite(v) and lo<v<=hi+0.25:
        kv=min(np.searchsorted(cuts,v)-1,len(seg)-1); pbase=seg[max(kv,0)]/seg.sum()
    else: pbase=np.nan
    rows.append(dict(i=i,j=j,bfrac=bfrac[i,j],L=hi-lo,n_inside=len(ins),dnbr=dn,snr=dn/(sd+1e-3),newlen=seg[k],viirs=v,hit=hit,hit_s=hit_s,off=off,pbase=pbase))
Rr=pd.DataFrame(rows); Rr.to_csv(f'{D}_constrained.csv',index=False)
Rr['fb']=pd.cut(Rr.bfrac,[0.1,0.3,0.5,0.75,1.01])
print(Rr.groupby('fb').agg(n=('L','size'),win=('L','median'),looks_inside=('n_inside','median'),dnbr300=('dnbr','median'),snr=('snr','median'),
      snr_gt2=('snr',lambda x:(x>2).mean()),newlen=('newlen','median')).round(3).to_string())
import subprocess; subprocess.run(["python3","-I",__file__.replace("s3date2.py","s3summ.py"),f"{D}_constrained.csv"]); sys.exit()
print('VIIRS-dated bins with >=1 S3 look inside window:',len(V))
for lab,sub in [('all',V),('snr>2',V[V.snr>2]),('bfrac>=0.5',V[V.bfrac>=0.5]),('bfrac>=0.5 & snr>2',V[(V.bfrac>=0.5)&(V.snr>2)])]:
    if len(sub): print(f'  {lab}: n={len(sub)} S3 hit rate={sub.hit.mean():.3f} vs uniform baseline={sub.pbase.mean():.3f}; median new interval {sub.newlen.median():.2f} d vs window {sub.L.median():.1f} d')
