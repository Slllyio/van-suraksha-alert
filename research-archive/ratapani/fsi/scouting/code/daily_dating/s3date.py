"""Test: can daily Sentinel-3 SYN 300 m reflectance date Ratapani burn scars to a day inside the S2/Landsat window?
Bins S3 pixels to a 300 m UTM grid, builds a per-bin NBR (Oa17 vs S6N) series minus a local unburned background,
finds the largest step, and compares its date with the 20 m scar window and with VIIRS alert dates."""
import glob, sys, numpy as np, pandas as pd, rasterio
from pyproj import Transformer
from scipy.ndimage import uniform_filter
year=int(sys.argv[1]); D=sys.argv[2]
R=300
with rasterio.open(f'/mnt/project-files/research/ratapani-burn-labels/rasters/burn_{year}.tif') as r:
    a=r.read(); T=r.transform
we,ws=a[0].astype(float),a[1].astype(float); burnt=a[0]!=-999
H,W=a.shape[1:]; f=R//20
H2,W2=H//f,W//f
def agg(x): return x[:H2*f,:W2*f].reshape(H2,f,W2,f)
bfrac=agg(burnt).mean(axis=(1,3))
# modal window per bin: median of burned pixels' we/ws
wem=np.where(burnt,we,np.nan); wsm=np.where(burnt,ws,np.nan)
import warnings; warnings.filterwarnings('ignore')
we2=np.nanmedian(agg(wem),axis=(1,3)); ws2=np.nanmedian(agg(wsm),axis=(1,3))
x0,y1=T.c,T.f
tr=Transformer.from_crs(4326,32643,always_xy=True)
files=sorted(glob.glob(f'{D}/*.npz'))
obs=[]
for fn in files:
    z=np.load(fn)
    if 'empty' in z: continue
    t=pd.Timestamp(str(z['dt'])).tz_localize(None) if pd.Timestamp(str(z['dt'])).tzinfo is None else pd.Timestamp(str(z['dt'])).tz_convert(None)
    X,Y=tr.transform(z['lon'].ravel(),z['lat'].ravel())
    c=((X-x0)//R).astype(int); rr=((y1-Y)//R).astype(int)
    nir=z['SDR_Oa17'].ravel().astype(float); sw=z['SDR_S6N'].ravel().astype(float)
    ok=(z['CLOUD'].ravel()==0)&(nir>0)&(sw>0)&((z['SYN'].ravel()&(1<<15))==0)&(c>=0)&(c<W2)&(rr>=0)&(rr<H2)
    nbr=np.full((H2,W2),np.nan); cnt=np.zeros((H2,W2)); s=np.zeros((H2,W2))
    v=(nir-sw)/(nir+sw)
    np.add.at(s,(rr[ok],c[ok]),v[ok]); np.add.at(cnt,(rr[ok],c[ok]),1)
    nbr[cnt>0]=s[cnt>0]/cnt[cnt>0]
    if np.isfinite(nbr).mean()<0.2: continue
    # background: mean NBR of unburned bins (bfrac<0.02) in a ~3 km box
    ub=np.isfinite(nbr)&(bfrac<0.02)
    num=uniform_filter(np.where(ub,nbr,0),11); den=uniform_filter(ub.astype(float),11)
    bg=np.where(den>0.2,num/np.maximum(den,1e-9),np.nan)
    obs.append((t,nbr-bg))
obs.sort(key=lambda o:o[0])
t=np.array([o[0] for o in obs]); A=np.stack([o[1] for o in obs])  # (n,H2,W2)
doy=np.array([(x-pd.Timestamp(f'{year}-01-01')).days+(x.hour+5.5)/24 for x in t])
print('S3 obs used',len(t),'mean valid frac',np.isfinite(A).mean().round(2),'median gap d',np.median(np.diff(doy)).round(2))
def step(series,dy,lo,hi,k=5):
    best=(-9,None,None)
    ok=np.isfinite(series); s=series[ok]; d=dy[ok]
    for i in range(k,len(s)-k+1):
        if d[i]<lo or d[i]>hi: continue
        pre=s[max(0,i-k):i]; post=s[i:i+k]
        if d[i-1]<d[i]-6: continue  # need an obs within 6 days before
        sc=(np.median(pre)-np.median(post))/(np.std(pre)+np.std(post)+1e-3)*2
        if sc>best[0]: best=(sc,d[i-1],d[i])
    return best
rows=[]
rng=np.random.default_rng(0)
cand=np.argwhere((bfrac>=0.15)&np.isfinite(we2)&(we2>=40)&(we2<=140))
ctrl=np.argwhere(bfrac==0); ctrl=ctrl[rng.choice(len(ctrl),min(1500,len(ctrl)),replace=False)]
for kind,cells in (('burn',cand),('ctrl',ctrl)):
    for i,j in cells:
        if kind=='burn': lo,hi=ws2[i,j]-10,we2[i,j]+10
        else:
            k=cand[rng.integers(len(cand))]; lo,hi=ws2[k[0],k[1]]-10,we2[k[0],k[1]]+10
        sc,d0,d1=step(A[:,i,j],doy,lo,hi)
        rows.append(dict(kind=kind,i=i,j=j,bfrac=bfrac[i,j],ws=ws2[i,j] if kind=='burn' else np.nan,we=we2[i,j] if kind=='burn' else np.nan,score=sc,d0=d0,d1=d1))
Rr=pd.DataFrame(rows)
Rr.to_csv(f'{D}_steps.csv',index=False)
c=Rr[Rr.kind=='ctrl'].score; thr=c.quantile(0.95)
print('control score p50/p90/p95/p99',c.quantile([.5,.9,.95,.99]).round(2).tolist())
b=Rr[Rr.kind=='burn'].copy()
b['det']=b.score>thr
# day of step expressed as the obs at/after the drop; inside window if ws < d1 <= we+1 (S2 at ~10:40, S3 at ~10:00 IST)
b['inside']=(b.d1>b.ws)&(b.d0<b.we+0.5)
b['newlen']=b.d1-np.maximum(b.d0,b.ws)
b['fb']=pd.cut(b.bfrac,[0.15,0.3,0.5,0.75,1.01])
print(b.groupby('fb').agg(n=('det','size'),det=('det','mean'),inside_if_det=('inside',lambda x: x[b.loc[x.index,'det']].mean()),
      newlen=('newlen',lambda x: x[b.loc[x.index,'det']&b.loc[x.index,'inside']].median()),S2len=('we',lambda x:(x-b.loc[x.index,'ws']).median())).round(3).to_string())
# VIIRS check
L=pd.read_csv('/mnt/project-files/fire-alert-scars/alert_scar_lookup.csv',usecols=['latitude','longitude','acq_date','acq_time','sensor'])
L=L[L.acq_date.str.startswith(str(year))&L.sensor.str.contains('viirs')]
X,Y=tr.transform(L.longitude.values,L.latitude.values)
L['j']=((X-x0)//R).astype(int); L['i']=((y1-Y)//R).astype(int)
L['vd']=[(pd.Timestamp(d)-pd.Timestamp(f'{year}-01-01')).days+ (int(str(tm).zfill(4)[:2])+5.5)/24 for d,tm in zip(L.acq_date,L.acq_time)]
first=L.groupby(['i','j']).vd.min()
bb=b[b.det].set_index(['i','j']).join(first,how='inner')
bb=bb[(bb.vd>bb.ws-1)&(bb.vd<bb.we+1.5)]
if len(bb):
    bb['err']=bb.d1-bb.vd   # S3 obs after drop minus VIIRS time (days); should be in (0, gap]
    print('VIIRS-matched detected bins',len(bb),'; S3 drop bracket contains VIIRS time:',((bb.d0<=bb.vd+0.3)&(bb.d1>=bb.vd-0.3)).mean().round(3),
          '; |d1-viirs|<=1.5 d:',(bb.err.abs()<=1.5).mean().round(3),'; median d1-viirs',bb.err.median().round(2))
