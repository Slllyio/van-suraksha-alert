"""VIIRS detection as its real pixel footprint (scan x track km, ~375 m at nadir up to ~0.8 km at swath edge)
instead of its centre point. Compared with the burned-so-far measured in 331 mid-fire S2/Landsat scenes."""
import pandas as pd, numpy as np, glob, rasterio
from scipy import ndimage
from skimage.graph import MCP_Geometric
from pyproj import Transformer
d=pd.read_parquet('midscar.parquet'); d=d[(d.ok_frac>0.7)&(d.status=='ok')]
fr=[]
for f in glob.glob('/mnt/project-files/fire-alert-scars/alerts/viirs-*.csv'):
    a=pd.read_csv(f)
    if 'latitude' not in a: continue
    a=a[(a.latitude.between(22.6,23.4))&(a.longitude.between(77.2,78.2))]; fr.append(a)
a=pd.concat(fr); a['t']=pd.to_datetime(a.acq_date+' '+a.acq_time.astype(str).str.zfill(4),format='%Y-%m-%d %H%M')
a['x'],a['y']=Transformer.from_crs('EPSG:4326','EPSG:32643',always_xy=True).transform(a.longitude.values,a.latitude.values)
with rasterio.open('/mnt/project-files/research/ratapani-burn-labels/rasters/burn_2017.tif') as s: TR=s.transform
rows=[]
for _,r in d.iterrows():
    z=np.load(f'chips/{r.event}_{r.scene[:40]}.npz'); S,bym,ok=z['S'],z['bym'],z['ok']; i0,j0=int(z['i0']),int(z['j0']); H,W=S.shape
    g=a[(a.t>=r.t_first-pd.Timedelta(hours=1))&(a.t<=r.t_last+pd.Timedelta(days=2))]
    cx=(g.x.values-(TR.c+j0*20))/20-0.5; cy=((TR.f-i0*20)-g.y.values)/20-0.5
    hw=g.scan.values*1000/2/20; hh=g.track.values*1000/2/20
    yy,xx=np.mgrid[0:H,0:W]; fps=[]
    for k in range(len(g)):
        if cx[k]+hw[k]<0 or cy[k]+hh[k]<0 or cx[k]-hw[k]>W or cy[k]-hh[k]>H: fps.append(None); continue
        m=S&(np.abs(xx-cx[k])<=hw[k]+0.5)&(np.abs(yy-cy[k])<=hh[k]+0.5); fps.append(m if m.any() else None)
    use=[k for k in range(len(g)) if fps[k] is not None]
    if not use: continue
    g=g.iloc[use]; fps=[fps[k] for k in use]; t=g.t.values; t0=t.min()
    first=[k for k in range(len(g)) if t[k]<=t0+np.timedelta64(60,'m')]
    # origin as point (snapped) and as footprint
    dist,(iy,ix)=ndimage.distance_transform_edt(~S,return_indices=True)
    pc=[(int(np.clip(round(cy[use[k]]),0,H-1)),int(np.clip(round(cx[use[k]]),0,W-1))) for k in first]
    src_pt=[(iy[p],ix[p]) for p in pc]
    Gp,_=MCP_Geometric(np.where(S,1.,np.inf)).find_costs(src_pt); Gp=np.where(S&np.isfinite(Gp),Gp*20,np.nan)
    before=[k for k in range(len(g)) if t[k]<=np.datetime64(r['T'])]
    if not before: continue
    pt_front=max(Gp[iy[(int(np.clip(round(cy[use[k]]),0,H-1)),int(np.clip(round(cx[use[k]]),0,W-1)))],ix[(int(np.clip(round(cy[use[k]]),0,H-1)),int(np.clip(round(cx[use[k]]),0,W-1)))]] for k in before)
    lo=max(np.nanmin(Gp[fps[k]]) for k in before); hi=max(np.nanmax(Gp[fps[k]]) for k in before)
    obs=np.nanpercentile(Gp[bym&S],95) if (bym&S).sum()>3 else 0.0
    union=np.zeros_like(S)
    for k in before: union|=fps[k]
    rows.append(dict(event=r.event,scene=r.scene,h=(r['T']-pd.Timestamp(t0)).total_seconds()/3600,obs_front=obs,pt_front=pt_front,fp_lo=lo,fp_hi=hi,
                     obs_frac=bym[ok].mean(),pt_frac=np.nanmean((Gp<=pt_front)[ok]),hi_frac=np.nanmean((Gp<=hi)[ok]),union_frac=union[ok].mean(),
                     fp_km=float(np.median(g.scan.values*g.track.values)),n_before=len(before),scar_ha=S.sum()*.04))
x=pd.DataFrame(rows); x.to_parquet('footprint_check.parquet')
print(len(x)); inside=(x.obs_front>=x.fp_lo-60)&(x.obs_front<=x.fp_hi+60)
print('observed front within footprint bounds:',inside.mean().round(2),' below point front-60m:',(x.obs_front<x.pt_front-60).mean().round(2),' beyond footprint max:',(x.obs_front>x.fp_hi+60).mean().round(2))
print('front error vs truth (m), median |obs-x|: point',(x.obs_front-x.pt_front).abs().median().round(0),' footprint max',(x.obs_front-x.fp_hi).abs().median().round(0),' footprint mid',(x.obs_front-(x.fp_lo+x.fp_hi)/2).abs().median().round(0))
print('signed obs - point',(x.obs_front-x.pt_front).median().round(0),' obs - fp_hi',(x.obs_front-x.fp_hi).median().round(0))
for c in ['pt_frac','hi_frac','union_frac']: print(c,'median |obs-pred| frac',(x.obs_frac-x[c]).abs().median().round(2),'corr',np.corrcoef(x.obs_frac,x[c])[0,1].round(2),'bias',(x.obs_frac-x[c]).median().round(2))
print('footprint area km2 median',x.fp_km.median().round(3))
