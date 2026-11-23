import sys,numpy as np,pandas as pd
for f in sys.argv[1:]:
    r=pd.read_csv(f); r['tod']=np.where(r.hour<6,r.hour+24,r.hour)+0.25  # bin centre
    print('==',f.split('/')[-1])
    for col in [c for c in r.columns if c not in ('hour','control','n_ctrl','tod')]:
        y=r[col].values; t=r.tod.values
        ok=np.isfinite(y)&(t>=8)&(t<=18.0)   # daytime window, before day/night mask switch artefacts
        night=np.nanmean(y[(t>=21.5)&(t<=29.5)&np.isfinite(y)])
        best=None
        for h in np.arange(9,17.01,0.05):
            for s in np.arange(1,5.01,0.05):
                g=np.exp(-(t[ok]-h)**2/(2*s*s)); X=np.c_[np.ones(ok.sum()),g]; coef,res,*_=np.linalg.lstsq(X,y[ok],rcond=None)
                sse=((X@coef-y[ok])**2).sum()
                if best is None or sse<best[0]: best=(sse,h,s,coef)
        sse,h,s,coef=best; peak=coef[0]+coef[1]
        # empirical: time of max, half-max crossings (on 30-min series)
        tt=t[ok]; yy=y[ok]; i=np.nanargmax(yy); hm=0.5*yy[i]
        up=tt[:i+1][yy[:i+1]<hm]; dn=tt[i:][yy[i:]<hm]
        print(f'{col:28s} Gaussian fit: peak {h:5.2f} h IST, sigma {s:4.2f} h, FWHM {2.355*s:4.1f} h | empirical max at {tt[i]:5.2f}, half-max {up.max() if len(up) else np.nan:5.2f}-{dn.min() if len(dn) else np.nan:5.2f} | night(21:30-05:30) mean/peak = {night/yy[i]:.2f}')
