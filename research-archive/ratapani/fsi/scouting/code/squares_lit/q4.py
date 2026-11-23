import numpy as np, pandas as pd
rng=np.random.default_rng(2)
d=pd.read_pickle('/tmp/claude-0/-home-user/be9b8f54-cc26-52cb-bdbb-9c8008a24baf/scratchpad/r17_work/viirs.pkl')
S=d.scan.values*1000; T=d.track.values*1000
def sensor():
    i=rng.integers(0,len(S)); s,t=S[i],T[i]
    ox,oy=rng.uniform(0,s),rng.uniform(0,t)        # grid phase
    ang=np.deg2rad(rng.normal(0,8))                 # small orbit-to-orbit rotation of axes
    gx,gy=rng.normal(0,55*s/375),rng.normal(0,58*t/375)
    return s,t,ox,oy,ang,gx,gy
def observe(fx,fy,sen,spill):
    s,t,ox,oy,ang,gx,gy=sen
    c,sn=np.cos(ang),np.sin(ang)
    u= c*fx+sn*fy; v=-sn*fx+c*fy
    iu=np.floor((u-ox)/s); iv=np.floor((v-oy)/t)
    cells=[(iu,iv)]
    fu=(u-ox)/s-iu; fv=(v-oy)/t-iv
    if fu<spill: cells.append((iu-1,iv))
    if fu>1-spill: cells.append((iu+1,iv))
    if fv<spill/2: cells.append((iu,iv-1))
    if fv>1-spill/2: cells.append((iu,iv+1))
    out=[]
    for a,b in cells:
        cu=ox+(a+.5)*s; cv=oy+(b+.5)*t
        X=c*cu-sn*cv+gx; Y=sn*cu+c*cv+gy   # reported centre with geoloc error
        out.append((X,Y))
    return np.array(out),sen
g=np.linspace(-500,500,101); GX,GY=np.meshgrid(g,g)
def inside(X,Y,cx,cy,sen,pad):
    s,t,ox,oy,ang,gx,gy=sen; c,sn=np.cos(ang),np.sin(ang)
    du=c*(X-cx)+sn*(Y-cy); dv=-sn*(X-cx)+c*(Y-cy)
    return (abs(du)<=s/2+pad)&(abs(dv)<=t/2+pad)
for spill in [0.0,0.15]:
  E={'one centroid':[],'mean of 3 centroids':[],'footprint intersection, 3 sats':[],'+ unlit-neighbour (negative) rule':[]}
  for k in range(3000):
    fx,fy=0.0,0.0
    obs=[observe(fx,fy,sensor(),spill) for _ in range(3)]
    cents=[o[0].mean(0) for o in obs]
    E['one centroid'].append(np.hypot(*cents[0]))
    m=np.mean(cents,0); E['mean of 3 centroids'].append(np.hypot(*m))
    # likelihood surface: inside union of lit pixels (pad 60 m for geoloc) for each sensor
    L=np.ones_like(GX,bool); Lneg=np.ones_like(GX,bool)
    for pts,sen in obs:
        U=np.zeros_like(GX,bool)
        for cx,cy in pts: U|=inside(GX,GY,cx,cy,sen,60)
        L&=U
        # negative: if only one pixel lit, fire not within spill zone near edges -> shrink to interior
        if len(pts)==1:
            s,t=sen[0],sen[1]
            Lneg&=inside(GX,GY,pts[0][0],pts[0][1],sen,60-spill*s)
        else:
            Lneg&=U
    for key,LL in [('footprint intersection, 3 sats',L),('+ unlit-neighbour (negative) rule',L&Lneg)]:
        if LL.sum()==0: LL=L
        if LL.sum()==0: E[key].append(np.hypot(*m)); continue
        E[key].append(np.hypot(GX[LL].mean(),GY[LL].mean()))
  print('PSF spill fraction',spill)
  for k,v in E.items(): print(f'  {k:40s} median {np.median(v):4.0f} m  p90 {np.percentile(v,90):4.0f} m')
