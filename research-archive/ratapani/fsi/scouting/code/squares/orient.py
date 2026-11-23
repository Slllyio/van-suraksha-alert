import numpy as np, pandas as pd, pyproj
from scipy.spatial import cKDTree
tp = pyproj.Transformer.from_crs(4326, 32643, always_xy=True).transform
M='/mnt/project-files/fire-alert-scars/alerts_mp/'
# numeric ground-track heading for a sun-synchronous orbit (i=98.7 deg, alt 830 km), rotating Earth
i=np.radians(98.74); a=6371+834; mu=398600.; n=np.sqrt(mu/a**3); we=7.2921e-5
t=np.linspace(0,6000,600001); u=n*t
x=np.cos(u); y=np.sin(u)*np.cos(i); z=np.sin(u)*np.sin(i)
lon=np.arctan2(y,x)-we*t; lat=np.arcsin(z)
for asc in [True,False]:
    k=np.where((np.abs(np.degrees(lat)-23)<0.05)&((np.gradient(lat)>0)==asc))[0][0]
    dlat=lat[k+1]-lat[k]; dlon=(lon[k+1]-lon[k])*np.cos(lat[k])
    print('ascending' if asc else 'descending','track heading deg',np.degrees(np.arctan2(dlon,dlat))%360)
for f in ['viirs-snpp_2021.csv','viirs-jpss1_2021.csv']:
    a=pd.read_csv(M+f); a=a[a.type==0]
    a['x'],a['y']=tp(a.longitude.values,a.latitude.values)
    for dn,g in a.groupby('daynight'):
        angs=[]
        for _,p in g.groupby(['acq_date','acq_time']):
            if len(p)<2: continue
            P=p[['x','y']].values; tr=cKDTree(P); pr=tr.query_pairs(560,output_type='ndarray')
            if len(pr)==0: continue
            d=P[pr[:,1]]-P[pr[:,0]]; L=np.hypot(*d.T); s=p.scan.values[pr[:,0]]*1000
            ok=L<1.2*np.minimum(s,p.track.values[pr[:,0]]*1000)
            angs.append(np.degrees(np.arctan2(d[ok,0],d[ok,1]))%180)
        an=np.concatenate(angs); h,_=np.histogram(an,bins=36,range=(0,180))
        top=np.argsort(-h)[:4]*5+2.5
        print(f,dn,len(an),'top 5-deg bins (deg from N):',top, 'hist',h.tolist())
