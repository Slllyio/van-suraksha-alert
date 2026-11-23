# Match EUMETView msg_iodc:fire marker hits to FIRMS VIIRS (S-NPP+NOAA-20) and MODIS within the sweep box.
import sys, json, numpy as np, pandas as pd, datetime as dt
sw=json.load(open(sys.argv[1])); yr=sys.argv[2]; F=sys.argv[3]
S,N,W,E=21,25,75,81
def load(f,src):
    d=pd.read_csv(f); d=d[(d.latitude.between(S,N))&(d.longitude.between(W,E))].copy()
    d['t']=pd.to_datetime(d.acq_date+' '+d.acq_time.astype(str).str.zfill(4),format='%Y-%m-%d %H%M'); d['src']=src; return d
v=pd.concat([load(f'{F}/viirs-snpp_{yr}_India.csv','SNPP'),load(f'{F}/viirs-jpss1_{yr}_India.csv','N20'),load(f'{F}/modis_{yr}_India.csv','MODIS')])
# hits: centre of each connected marker blob (33x33 px blocks)
hits=[]
for k,val in sw.items():
    if not val['px']: continue
    p=np.array([(a,b) for a,b,c,d in val['px']]); cls=[ (c,d) for a,b,c,dd in val['px'] for d in [dd]]
    # split into blobs by rounding to 0.2 deg
    key=np.round(p/0.2)
    for kk in np.unique(key,axis=0):
        m=(key==kk).all(1); c=p[m].mean(0)
        col=val['px'][int(np.where(m)[0][0])][2:]
        hits.append(dict(t=pd.Timestamp(k),lat=c[0],lon=c[1],kind='fire' if tuple(col)==(252,0) or col[1]<50 else 'potential'))
h=pd.DataFrame(hits); print(len(h),'FIR hits'); 
t0=pd.Timestamp(min(sw)); t1=pd.Timestamp(max(sw))
vv=v[(v.t>=t0-pd.Timedelta('12h'))&(v.t<=t1+pd.Timedelta('12h'))]
print('FIRMS pts in box & window:',vv.groupby('src').size().to_dict())
for i,r in h.iterrows():
    d=np.hypot((vv.latitude-r.lat)*111,(vv.longitude-r.lon)*111*np.cos(np.radians(r.lat)))
    m=(d<10)&((vv.t-r.t).abs()<pd.Timedelta('14h'))
    s=vv[m]
    print(r.t+pd.Timedelta('5.5h'),'IST %.2f %.2f %s'%(r.lat,r.lon,r.kind),'| FIRMS<10km,±14h:',len(s),'sumFRP %.0f maxFRP %.0f'%(s.frp.sum(),s.frp.max() if len(s) else 0), sorted(set((s.t+pd.Timedelta('5.5h')).dt.strftime('%d %H:%M')))[:6])
# fraction of big VIIRS clusters (sum FRP per 0.1deg cell per pass) with any FIR hit within 15km +-3h
vs=vv[vv.src!='MODIS'].copy(); vs['cell']=list(zip((vs.latitude/0.1).round(),(vs.longitude/0.1).round(),vs.t.dt.floor('h')))
g=vs.groupby('cell').agg(frp=('frp','sum'),n=('frp','size'),lat=('latitude','mean'),lon=('longitude','mean'),t=('t','first')).reset_index()
def hit(r):
    if not len(h): return False
    d=np.hypot((h.lat-r.lat)*111,(h.lon-r.lon)*111*np.cos(np.radians(r.lat)))
    return bool(((d<15)&((h.t-r.t).abs()<pd.Timedelta('3h'))).any())
g['hit']=g.apply(hit,axis=1)
for lo,hi in [(0,10),(10,30),(30,100),(100,300),(300,1e9)]:
    s=g[(g.frp>=lo)&(g.frp<hi)]; print('VIIRS 0.1deg-cell-pass sumFRP %g-%g MW: n=%d, FIR hit within 15km/3h: %d (%.1f%%)'%(lo,hi,len(s),s.hit.sum(),100*s.hit.mean() if len(s) else 0))
