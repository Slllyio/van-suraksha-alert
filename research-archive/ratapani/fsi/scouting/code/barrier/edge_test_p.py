# Do burn-scar edges coincide with mapped lines more than chance?
# Local translate(<=500 m disc)+rotate(0-360) null per scar, after Choi & Chae 2026 (Fire 9:247).
import sys, json, numpy as np, geopandas as gpd, pandas as pd
from affine import Affine
from scipy import ndimage
from rasterio.features import rasterize
from multiprocessing import Pool
D='/tmp/claude-0/-home-user/be9b8f54-cc26-52cb-bdbb-9c8008a24baf/scratchpad/r9_barrier_data/'
NDRAW=int(sys.argv[1]) if len(sys.argv)>1 else 100
EXTRA=sys.argv[2].split(',') if len(sys.argv)>2 and sys.argv[2] else []
TAG=sys.argv[3] if len(sys.argv)>3 else 'main'
NULL=sys.argv[4] if len(sys.argv)>4 else 'rt'
z=np.load('/mnt/project-files/ratapani/spread/data_shared/grid20.npz')
T=Affine(*z['transform']); H,W=[int(v) for v in z['shape']]; Ti=~T
WC=z['wc']; BURNABLE=np.isin(WC,[10,20,30])
LZ=dict(np.load(D+'layers20.npz')); LZ.update(dict(np.load(D+'layers20_extra.npz')))
SD=np.load(D+'scar_doy20.npz'); SD={int(k[-4:]):SD[k] for k in SD.files}
BASE=['ms_roads','ov_osm_roads','ov_tomtom','rail','power','osm_water','stream_0.25km2','stream_1km2','stream_5km2','stream_25km2','ridge_100c','ridge_500c']
LAY=(BASE if 'nobase' not in EXTRA else ['ms_roads','ov_osm_roads','ov_tomtom','rail','power','osm_water'])+[e for e in EXTRA if e not in ('nobase','recur')]
RE=dict(np.load(D+__import__('os').environ.get('RECUR','recurrent_edges.npz'))) if 'recur' in EXTRA else None
M={k:LZ[k+'_m'] for k in LAY}; A={k:LZ[k+'_a'].astype(np.float32) for k in LAY}
M['all_mapped']=M['ms_roads']|M['ov_osm_roads']|M['ov_tomtom']|M['rail']|M['power']|M['osm_water']
A['all_mapped']=np.where(M['ms_roads'],A['ms_roads'],np.where(M['ov_osm_roads'],A['ov_osm_roads'],np.where(M['ov_tomtom'],A['ov_tomtom'],np.where(M['rail'],A['rail'],np.where(M['power'],A['power'],A['osm_water'])))))
M['fedge']=LZ['fedge_m']; A['fedge']=None
LAY2=LAY+['all_mapped','fedge','prior_burn','prior_scar']+(['recur'] if RE is not None else [])
BE={y:z[f'burn_end_{y}'] for y in range(2017,2027)}
rng=np.random.default_rng(42)

def sample_ring(c,step=20.0):
    seg=np.diff(c,axis=0); sl=np.hypot(seg[:,0],seg[:,1]); cum=np.r_[0,np.cumsum(sl)]
    if cum[-1]<200: return None,None
    s=np.arange(0,cum[-1],step)
    x=np.interp(s,cum,c[:,0]); y=np.interp(s,cum,c[:,1])
    # tangent over +-40 m (wraps)
    n=len(s); k=2
    xp=np.roll(x,-k); yp=np.roll(y,-k); xm=np.roll(x,k); ym=np.roll(y,k)
    ang=np.degrees(np.arctan2(yp-ym,xp-xm))%180
    nx=-(yp-ym); ny=(xp-xm); nn=np.hypot(nx,ny)+1e-9
    return np.c_[x,y,ang,nx/nn,ny/nn],cum[-1]

def one(args):
    idx,geom,doy,yr=args
    parts=[p for p in (geom.geoms if geom.geom_type=='MultiPolygon' else [geom]) if p.area>=1e4]
    if not parts: return None
    pts=[];
    for p in parts:
        r,_=sample_ring(np.asarray(p.exterior.coords))
        if r is not None: pts.append(r)
    if not pts: return None
    P=np.vstack(pts)
    cx,cy=np.asarray(geom.centroid.coords[0]); R=np.max(np.hypot(P[:,0]-cx,P[:,1]-cy))+700
    c0,r0=[int(v) for v in Ti*(cx-R,cy+R)]; c1,r1=[int(v)+1 for v in Ti*(cx+R,cy-R)]
    if c0<0 or r0<0 or c1>W or r1>H: return None
    wT=T*Affine.translation(c0,r0); wTi=~wT; h,w=r1-r0,c1-c0
    mask=rasterize([(geom,1)],out_shape=(h,w),transform=wT,fill=0,dtype='uint8').astype(bool)
    def rc(x,y):
        c=((x-wT.c)/20).astype(int); r=((wT.f-y)/20).astype(int)
        ok=(c>=0)&(c<w)&(r>=0)&(r<h); return r.clip(0,h-1),c.clip(0,w-1),ok
    # per-point intrinsic flags: gap (burned again 60-100 m outward = fire crossed a narrow unburned strip)
    x,y,ang,nx,ny=P.T
    rr,cc,_=rc(x+nx*20,y+ny*20); inside_pos=mask[rr,cc]
    sgn=np.where(inside_pos,-1.0,1.0)  # outward
    gap=np.zeros(len(P),bool)
    for d in (60,80,100):
        rr,cc,ok=rc(x+sgn*nx*d,y+sgn*ny*d); gap|=mask[rr,cc]&ok
    rr,cc,_=rc(x+sgn*nx*40,y+sgn*ny*40)
    outb=BURNABLE[r0:r1,c0:c1][rr,cc]   # outside neighbour is burnable land (an in-forest edge)
    res={'idx':idx,'n':len(P),'gap_frac':gap.mean(),'inforest_frac':outb.mean()}
    # draws
    phis=rng.uniform(0,2*np.pi,NDRAW) if NULL=='rt' else np.zeros(NDRAW); rad=500*np.sqrt(rng.uniform(0,1,NDRAW)); th=rng.uniform(0,2*np.pi,NDRAW)
    tx=rad*np.cos(th); ty=rad*np.sin(th)
    dx=x-cx; dy=y-cy
    X=cx+np.cos(phis)[:,None]*dx-np.sin(phis)[:,None]*dy+tx[:,None]
    Y=cy+np.sin(phis)[:,None]*dx+np.cos(phis)[:,None]*dy+ty[:,None]
    ANG=(ang[None,:]+np.degrees(phis)[:,None])%180
    RRn,CCn,_=rc(X,Y); rr0,cc0,_=rc(x,y)
    for k in LAY2:
        if k=='prior_burn':
            if yr not in BE: continue
            be=BE[yr][r0:r1,c0:c1]; m=(be>=0)&(be<doy-2)&~mask; m=m&~ndimage.binary_erosion(m)
        elif k=='prior_scar':
            if yr not in SD: continue
            sd=SD[yr][r0:r1,c0:c1]; m=(sd>0)&(sd<doy-1)&~mask; m=m&~ndimage.binary_erosion(m)
        elif k=='recur':
            m=RE[f'm_{yr}'][r0:r1,c0:c1]
        else: m=M[k][r0:r1,c0:c1]
        if not m.any():
            res.update({f'{k}_{s}':0.0 for s in ['R30o','R30n','A30o','A30n','S30o','S30n','R60o','R60n','RFo','RFn']}); continue
        dist,ind=ndimage.distance_transform_edt(~m,sampling=20,return_indices=True)
        do=dist[rr0,cc0]; dn=dist[RRn,CCn]
        res[f'{k}_R30o']=(do<=30).mean(); res[f'{k}_R30n']=(dn<=30).mean()
        nd=(dn<=30).mean(1); ob=res[f'{k}_R30o']; res[f'{k}_R30pit']=(nd<ob).mean()+0.5*(nd==ob).mean()
        res[f'{k}_R60o']=(do<=60).mean(); res[f'{k}_R60n']=(dn<=60).mean()
        res[f'{k}_S30o']=((do<=30)&~gap).mean(); res[f'{k}_S30n']=((dn<=30)&~gap[None,:]).mean()
        # in-forest edges only (outside neighbour burnable): the null keeps the same point flags
        res[f'{k}_RFo']=((do<=30)&outb).mean(); res[f'{k}_RFn']=((dn<=30)&outb[None,:]).mean()
        if A.get(k) is not None or k=='recur':
            aw=A[k][r0:r1,c0:c1] if k!='recur' else RE[f'a_{yr}'][r0:r1,c0:c1].astype(np.float32)
            lo=aw[ind[0][rr0,cc0],ind[1][rr0,cc0]]; ln=aw[ind[0][RRn,CCn],ind[1][RRn,CCn]]
            dd=lambda a,b: np.minimum(np.abs(a-b)%180,180-np.abs(a-b)%180)
            res[f'{k}_A30o']=((do<=30)&(dd(ang,lo)<=30)).mean(); res[f'{k}_A30n']=((dn<=30)&(dd(ANG,ln)<=30)).mean()
        # line density in window (availability)
        res[f'{k}_dens']=m.mean()
    return res

if __name__=='__main__':
    g=gpd.read_file('/mnt/project-files/fire-alert-scars/event_scars.geojson').to_crs(32643)
    g=g[(~g.touches_chip_edge.astype(bool))&(g.date.dt.month<=6)].copy()
    g['doy']=g.date.dt.dayofyear; g['yr']=g.date.dt.year
    args=[(i,geo,int(d),int(y)) for i,geo,d,y in zip(g.event_id,g.geometry,g.doy,g.yr)]
    with Pool(4) as p: out=[r for r in p.imap_unordered(one,args,chunksize=8) if r is not None]
    df=pd.DataFrame(out); df.to_parquet(D+f'edge_test_{TAG}.parquet'); print(len(df),'scars')
