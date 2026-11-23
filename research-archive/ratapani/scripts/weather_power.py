import pickle, time, requests, numpy as np, pandas as pd
from shapely.geometry import Point
TR=pickle.load(open('tr.pkl','rb'))
URL="https://power.larc.nasa.gov/api/temporal/daily/point"
out=[]
for k,g in TR.items():
    x0,y0,x1,y1=g.bounds
    pts=[(x,y) for x in np.arange(np.floor(x0*2)/2+0.25,x1,0.5) for y in np.arange(np.floor(y0*2)/2+0.25,y1,0.5) if g.contains(Point(x,y))]
    if len(pts)>3: pts=[pts[i] for i in np.linspace(0,len(pts)-1,3).astype(int)]
    if not pts: rp=g.representative_point(); pts=[(rp.x,rp.y)]
    frames=[]
    for lon,lat in pts:
        for a in range(4):
            r=requests.get(URL,params=dict(parameters="T2M,RH2M,WS2M,PRECTOTCORR",community="AG",longitude=f"{lon:.3f}",latitude=f"{lat:.3f}",start="20121001",end="20241231",format="JSON"),timeout=180)
            if r.ok: break
            time.sleep(10*(a+1))
        p=r.json()['properties']['parameter']
        d=pd.DataFrame({'date':pd.to_datetime(list(p['T2M'])),'temp_c':list(p['T2M'].values()),'rh_pct':list(p['RH2M'].values()),
                        'wind_kmh':np.array(list(p['WS2M'].values()))*3.6,'precip_mm':list(p['PRECTOTCORR'].values())}).replace(-999.0,np.nan)
        frames.append(d)
    w=pd.concat(frames).groupby('date',as_index=False).mean(); w['reserve']=k; w['n_points']=len(pts)
    out.append(w); print(k,len(pts),len(w),int(w.temp_c.isna().sum()),flush=True)
pd.concat(out).to_parquet('weather_power.parquet')
