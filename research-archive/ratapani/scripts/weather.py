import sys, pickle, time, numpy as np, pandas as pd
from datetime import date, datetime
sys.path.insert(0,'/home/user/vanagni')
from src.data.openmeteo_archive import fetch_cell_range, HOURLY_VARS
from src.data.openmeteo_ingest import noon_rows
from shapely.geometry import Point
TR=pickle.load(open('tr.pkl','rb'))
out=[]
for k,g in TR.items():
    # points: 0.25-degree grid nodes inside the reserve, else its representative point (cap 4)
    x0,y0,x1,y1=g.bounds
    pts=[(x,y) for x in np.arange(np.floor(x0*4)/4,x1+0.01,0.25) for y in np.arange(np.floor(y0*4)/4,y1+0.01,0.25) if g.contains(Point(x,y))]
    if len(pts)>4: pts=[pts[i] for i in np.linspace(0,len(pts)-1,4).astype(int)]
    if not pts: rp=g.representative_point(); pts=[(rp.x,rp.y)]
    frames=[]
    for (lon,lat) in pts:
        h=fetch_cell_range(lat,lon,date(2012,10,1),date(2024,12,31),backoff_s=20)
        times=[t.to_pydatetime() for t in h['time']]
        rows=noon_rows(times,{v:h[v].to_numpy(float) for v in HOURLY_VARS})
        d=pd.DataFrame([{'date':r['time'].date(),'temp_c':r['temperature_2m'],'rh_pct':r['relative_humidity_2m'],'wind_kmh':r['wind_speed_10m'],'precip_mm':r['precip_mm']} for r in rows])
        frames.append(d); time.sleep(2)
    w=pd.concat(frames).groupby('date',as_index=False).mean(); w['reserve']=k; w['n_points']=len(pts)
    out.append(w); print(k,len(pts),len(w),flush=True)
pd.concat(out).to_parquet('weather_noon.parquet')
