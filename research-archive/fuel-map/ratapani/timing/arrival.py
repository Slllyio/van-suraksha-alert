"""Per-fire front-vs-time fit from precise snapshots + VIIRS footprints.
Front distance (walking distance inside the scar from the first-pass points) at each timed observation:
  snapshot (S2/Landsat, minute-exact): 95th pct distance of burned-so-far pixels, sigma 40 m
  VIIRS detection: far edge of its footprint inside the scar, sigma 130 m (validated, footprint_check.py)
Fit front(t) = v * (t - t_ign) on observations before the front saturates (< 90% of scar extent);
weighted least squares, needs the snapshot + >= 1 other non-saturated observation."""
import pandas as pd, numpy as np, glob, rasterio
from scipy import ndimage
from skimage.graph import MCP_Geometric
from pyproj import Transformer
d=pd.read_parquet('midscar.parquet'); d=d[(d.ok_frac>0.7)&(d.status=='ok')]
cls=np.load('/tmp/claude-0/fuel/inv/cls20.npy')
fr=[]
for f in glob.glob('/mnt/project-files/fire-alert-scars/alerts/viirs-*.csv'):
    a=pd.read_csv(f)
    if 'latitude' in a: fr.append(a[(a.latitude.between(22.6,23.4))&(a.longitude.between(77.2,78.2))])
a=pd.concat(fr); a['t']=pd.to_datetime(a.acq_date+' '+a.acq_time.astype(str).str.zfill(4),format='%Y-%m-%d %H%M')
a['x'],a['y']=Transformer.from_crs('EPSG:4326','EPSG:32643',always_xy=True).transform(a.longitude.values,a.latitude.values)
with rasterio.open('/mnt/project-files/research/ratapani-burn-labels/rasters/burn_2017.tif') as s: TR=s.transform
rows=[]; obsrows=[]
for _,r in d.iterrows():
    z=np.load(f'chips/{r.event}_{r.scene[:40]}.npz'); S,bym,ok=z['S'],z['bym'],z['ok']; i0,j0=int(z['i0']),int(z['j0']); H,W=S.shape
    g=a[(a.t>=r.t_first-pd.Timedelta(hours=1))&(a.t<=r.t_last+pd.Timedelta(days=2))]
    cx=(g.x.values-(TR.c+j0*20))/20-0.5; cy=((TR.f-i0*20)-g.y.values)/20-0.5; hw=g.scan.values*25+.5; hh=g.track.values*25+.5
    inside=[(0<=cy[k]+hh[k]) and (cy[k]-hh[k]<H) and (0<=cx[k]+hw[k]) and (cx[k]-hw[k]<W) for k in range(len(g))]
    g=g[inside]; cx,cy,hw,hh=cx[inside],cy[inside],hw[inside],hh[inside]
    if len(g)==0: continue
    t=g.t.values; t0=t.min(); f0=np.where(t<=t0+np.timedelta64(60,'m'))[0]
    dist,(iy,ix)=ndimage.distance_transform_edt(~S,return_indices=True)
    src=[(iy[int(np.clip(round(cy[k]),0,H-1)),int(np.clip(round(cx[k]),0,W-1))],ix[int(np.clip(round(cy[k]),0,H-1)),int(np.clip(round(cx[k]),0,W-1))]) for k in f0]
    G,_=MCP_Geometric(np.where(S,1.,np.inf)).find_costs(src); G=np.where(S&np.isfinite(G),G*20,np.nan); ext=np.nanmax(G)
    obs=[]
    for k in range(len(g)):
        sub=G[int(max(cy[k]-hh[k],0)):int(min(cy[k]+hh[k],H-1))+1,int(max(cx[k]-hw[k],0)):int(min(cx[k]+hw[k],W-1))+1]
        if np.isfinite(sub).any(): obs.append((pd.Timestamp(t[k]),float(np.nanmax(sub)),130.,'viirs'))
    # running max per pass (front never retreats)
    o=pd.DataFrame(obs,columns=['t','f','sd','src']).groupby('t').agg(f=('f','max'),sd=('sd','first'),src=('src','first')).reset_index()
    o['f']=o.f.cummax()
    snapf=float(np.nanpercentile(G[bym&S],95)) if (bym&S).sum()>3 else 0.0
    o=pd.concat([o,pd.DataFrame([dict(t=r['T'],f=snapf,sd=40.,src='snap')])]).sort_values('t')
    u=o[(o.f<0.9*ext)|(o.src=='snap')]; u=u[(u.src=='snap')|(u.t<=r['T'])|(u.f<0.9*ext)]
    for _,q in o.iterrows(): obsrows.append(dict(event=r.event,scene=r.scene,t=q.t,f=q.f,src=q.src,ext=ext))
    if len(u)<2 or u.t.nunique()<2 or snapf>=0.9*ext: continue
    x=(u.t-pd.Timestamp(t0)).dt.total_seconds().values/3600; y=u.f.values; w=1/u.sd.values**2
    X=np.c_[x,np.ones_like(x)]; Wm=np.diag(w); beta=np.linalg.lstsq(np.sqrt(Wm)@X,np.sqrt(w)*y,rcond=None)[0]
    v,c=beta; t_ign=-c/v if v>0 else np.nan
    comp=np.bincount(cls[i0:i0+H,j0:j0+W][S],minlength=5)/S.sum()
    rows.append(dict(event=r.event,scene=r.scene,season=r.season,v=v,t_ign_h=t_ign,n_obs=len(u),snap_h=(r['T']-pd.Timestamp(t0)).total_seconds()/3600,snapf=snapf,ext=ext,scar_ha=S.sum()*.04,
                     c1=comp[1],c2=comp[2],c3=comp[3],c4=comp[4],month=r['T'].month,first_daynight=g.daynight.values[f0[0]]))
x=pd.DataFrame(rows); x.to_parquet('arrival_fit.parquet'); pd.DataFrame(obsrows).to_parquet('arrival_obs.parquet')
ok=x[(x.v>0)]
print(len(x),'fits,',len(ok),'with v>0'); print(ok.v.describe(percentiles=[.25,.5,.75,.9]).round(1))
print('ignition before first VIIRS (h), median',(-ok.t_ign_h).median().round(1),'IQR',(-ok.t_ign_h).quantile([.25,.75]).round(1).tolist())
ok=ok.assign(dom=ok[['c1','c2','c3','c4']].values.argmax(1)+1)
print(ok.groupby('dom').v.agg(['size','median']).round(1)); print(ok.groupby('month').v.agg(['size','median']).round(1)); print(ok.groupby('first_daynight').v.agg(['size','median']).round(1))
print(ok.groupby('season').v.agg(['size','median']).round(1))
