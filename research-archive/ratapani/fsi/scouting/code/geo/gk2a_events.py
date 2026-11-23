import sys,numpy as np,pandas as pd
D='/tmp/claude-0/-home-user/be9b8f54-cc26-52cb-bdbb-9c8008a24baf/scratchpad/geo_r8/'; TAG=sys.argv[1]; yr=sys.argv[2]
d=pd.read_csv(D+f'gk2a_det_{TAG}.csv',parse_dates=['t','ist','istday']); v=pd.read_csv(D+f'firms_box_{yr}.csv',parse_dates=['t','ist','istday'])
d=d[~d.ist.dt.hour.isin([16,17,18])]  # drop sunset-artefact hours
days=sorted(d.istday.unique()); nl,nc=d.li.max()+3,d.ci.max()+3
# chance confirmation: random pixel-days in box
vk=set(zip(v.istday,v.li,v.ci)); rng=np.random.default_rng(0)
vd=v[v.istday.isin(days)]
L=rng.integers(vd.li.min(),vd.li.max(),20000); C=rng.integers(vd.ci.min(),vd.ci.max(),20000); Dd=rng.choice(days,20000)
ch=np.mean([any((dd,l+a,c+b) in vk for a in range(-2,3) for b in range(-2,3)) for dd,l,c in zip(Dd,L,C)])
print(f'{TAG}: detections kept {len(d)}; confirmed {d.conf_sameday.mean():.2f}; chance confirmation for random pixel-day {ch:.2f}')
# events: pixel clusters per fire-day (merge within 1 px)
d=d.sort_values('t'); ev=[]
for day,g in d.groupby('istday'):
    lab=-np.ones(len(g),int); pts=g[['li','ci']].values; k=0
    for i in range(len(g)):
        if lab[i]<0:
            st=[i]; lab[i]=k
            while st:
                j=st.pop(); nb=np.where((np.abs(pts[:,0]-pts[j,0])<=1)&(np.abs(pts[:,1]-pts[j,1])<=1)&(lab<0))[0]; lab[nb]=k; st+=list(nb)
            k+=1
    g=g.assign(ev=lab)
    for e,h in g.groupby('ev'):
        vv=v[(v.istday==day)&(v.li.between(h.li.min()-2,h.li.max()+2))&(v.ci.between(h.ci.min()-2,h.ci.max()+2))]
        hr=lambda x:(x.dt.hour+x.dt.minute/60)
        ev.append(dict(day=day,first=h.ist.min(),last=h.ist.max(),nslot=h.t.nunique(),lat=h.lat.mean(),lon=h.lon.mean(),
            viirs_day=((vv.src!='MODIS')&(vv.daynight=='D')).sum(),viirs_night=((vv.src!='MODIS')&(vv.daynight=='N')).sum(),modis=(vv.src=='MODIS').sum(),
            first_viirs=vv[vv.src!='MODIS'].ist.min(), maxfrp=vv.frp.max() if len(vv) else np.nan))
ev=pd.DataFrame(ev); fh=ev['first'].dt.hour+ev['first'].dt.minute/60
print('events',len(ev),'| first-detection IST hour counts:',fh.astype(int).value_counts().sort_index().to_dict())
print('share of events with a VIIRS day detection same fire-day %.2f, night-only %.2f, none %.2f'%((ev.viirs_day>0).mean(),((ev.viirs_day==0)&(ev.viirs_night>0)).mean(),((ev.viirs_day==0)&(ev.viirs_night==0)).mean()))
print('median maxFRP of FIRMS pixels in matched events %.0f MW'%ev.maxfrp.median())
aoi=ev[ev.lat.between(22.8,23.15)&ev.lon.between(77.3,78.1)]; print('AOI events:',len(aoi)); print(aoi.to_string() if len(aoi) else '')
ev.to_csv(D+f'gk2a_events_{TAG}.csv',index=False)
