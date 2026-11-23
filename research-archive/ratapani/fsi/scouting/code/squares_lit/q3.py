import numpy as np, pandas as pd
rng=np.random.default_rng(1)
d=pd.read_pickle('/tmp/claude-0/-home-user/be9b8f54-cc26-52cb-bdbb-9c8008a24baf/scratchpad/r17_work/viirs.pkl')
S=d.scan.values*1000; T=d.track.values*1000
N=200000
def fix(n):
    i=rng.integers(0,len(S),n); s,t=S[i],T[i]
    # point fire at 0; grid offset uniform -> pixel centre offset uniform in [-s/2,s/2]
    ex=rng.uniform(-.5,.5,n)*s; ey=rng.uniform(-.5,.5,n)*t
    gx=rng.normal(0,55,n)*s/375; gy=rng.normal(0,58,n)*t/375  # nadir-equiv RMSE scaled by pixel growth
    # random orientation of scan axis (orbits differ; approx same here ~ +-12 deg) ignore
    return ex+gx, ey+gy, s, t
x1,y1,s1,t1=fix(N); x2,y2,_,_=fix(N)
dist=np.hypot(x1-x2,y1-y2)
print('point fire, two sensors: median sep m',np.median(dist).round(0),' p90',np.percentile(dist,90).round(0))
x1,y1,_,_=fix(N)
print('single fix radial error median',np.median(np.hypot(x1,y1)).round(0),' per-axis sd x,y',x1.std().round(0),y1.std().round(0))
# grid-only component
ex=rng.uniform(-.5,.5,N)*S[rng.integers(0,len(S),N)]
print('grid-only per-axis sd',ex.std().round(0),' geoloc-only per-axis sd ~',(55*S.mean()/375).round(0))
# minimum detectable speed: difference of two fixes dt apart, 2-sigma one-axis along known direction
sd_axis=np.std(x1)
for dt in [25/60,50/60,75/60,12,24]:
    sdv=np.sqrt(2)*sd_axis/dt
    print(f'gap {dt*60:.0f} min: speed sd {sdv:.0f} m/h; 2sd detect {2*sdv:.0f} m/h; pairs needed to see 25 m/h at 2sd: {(2*sdv/25)**2:.0f}')
