"""Per burned (cell, window): Sentinel-3 SYN 300 m one-step test inside the 20 m window.
Picks, for each cell-window, the 300 m bin holding most of its scar pixels. Writes ../r9data/s3soft_<year>.csv"""
import glob, sys, os, warnings, numpy as np, pandas as pd
from pyproj import Transformer
from scipy.ndimage import uniform_filter
sys.path.insert(0,os.path.dirname(os.path.abspath(__file__))); from common import *
warnings.filterwarnings('ignore')
year=int(sys.argv[1]); dirs=sys.argv[2:]; R=300; f=15
px,a,T,cr=windows_px(year); H,W=a.shape[1:]; H2,W2=H//f,W//f
burnt=a[0]!=-999
bfrac_all=burnt[:H2*f,:W2*f].reshape(H2,f,W2,f).mean(axis=(1,3))
x0,y1=T.c,T.f; tr=Transformer.from_crs(4326,32643,always_xy=True)
obs=[]
for fn in sorted(set(sum([glob.glob(f'{d}/*.npz') for d in dirs],[]))):
    z=np.load(fn)
    if 'empty' in z: continue
    t=pd.Timestamp(str(z['dt'])).tz_convert(None)+pd.Timedelta(hours=5.5)
    X,Y=tr.transform(z['lon'].ravel(),z['lat'].ravel()); c=((X-x0)//R).astype(int); rr=((y1-Y)//R).astype(int)
    nir=z['SDR_Oa17'].ravel().astype(float); sw=z['SDR_S6N'].ravel().astype(float)
    ok=(z['CLOUD'].ravel()==0)&(nir>0)&(sw>0)&((z['SYN'].ravel()&(1<<15))==0)&(c>=0)&(c<W2)&(rr>=0)&(rr<H2)
    s=np.zeros((H2,W2)); n=np.zeros((H2,W2)); v=(nir-sw)/(nir+sw)
    np.add.at(s,(rr[ok],c[ok]),v[ok]); np.add.at(n,(rr[ok],c[ok]),1)
    nbr=np.where(n>0,s/np.maximum(n,1),np.nan)
    if np.isfinite(nbr).mean()<0.2: continue
    ub=np.isfinite(nbr)&(bfrac_all<0.02); num=uniform_filter(np.where(ub,nbr,0),11); den=uniform_filter(ub.astype(float),11)
    obs.append((t,nbr-np.where(den>0.2,num/np.maximum(den,1e-9),np.nan)))
obs.sort(key=lambda o:o[0]); A=np.stack([o[1] for o in obs]); dd=np.array([ist_doy(o[0],year) for o in obs])
print(year,'S3 looks',len(obs),'span',obs[0][0].date(),obs[-1][0].date(),flush=True)
px['bi']=px.r//f; px['bj']=px.c//f; px=px[(px.bi<H2)&(px.bj<W2)]
bintot=px.groupby(['bi','bj']).size()
g=px.groupby(['cell_id','s','e','bi','bj']).size().rename('n').reset_index()
g=g.sort_values('n',ascending=False).drop_duplicates(['cell_id','s','e'])
rows=[]
for r in g.itertuples():
    i,j=r.bi,r.bj; lo=r.s+10.7/24; hi=r.e+10.7/24
    y=A[:,i,j]; ok=np.isfinite(y)
    pre=ok&(dd<=lo)&(dd>lo-12); post=ok&(dd>=hi)&(dd<hi+12); ins=np.where(ok&(dd>lo)&(dd<hi))[0]
    rec=dict(season=year,cell_id=r.cell_id,s=r.s,e=r.e,bi=i,bj=j,burned_frac=r.n/225,dominance=r.n/bintot[(i,j)],n_pre=int(pre.sum()),n_post=int(post.sum()),n_inside=len(ins))
    if pre.sum()>=2 and post.sum()>=2:
        dn=np.median(y[pre])-np.median(y[post]); sd=np.std(np.r_[y[pre]-np.median(y[pre]),y[post]-np.median(y[post])])
        cuts=np.r_[lo,dd[ins],hi]; best=None
        for k in range(len(cuts)-1):
            sse=((np.r_[y[pre],y[ins[:k]]]-np.median(y[pre]))**2).sum()+((np.r_[y[ins[k:]],y[post]]-np.median(y[post]))**2).sum()
            if best is None or sse<best[0]: best=(sse,k)
        k=best[1]; rec.update(dnbr=dn,snr=dn/(sd+1e-3),cut_lo=cuts[k],cut_hi=cuts[k+1])
    rows.append(rec)
out=pd.DataFrame(rows); out.to_csv(f'../r9data/s3soft_{year}.csv',index=False)
print(year,'cell-windows',len(out),'with test',out.snr.notna().sum(),'snr>2',(out.snr>2).sum(),flush=True)
