import numpy as np, geopandas as gpd, pandas as pd, rasterio
from rasterio.features import rasterize
from rasterio.enums import Resampling
from scipy.ndimage import binary_dilation, binary_erosion
R='/mnt/project-files/fuel-map/ratapani/'
src=rasterio.open(R+'cover_phenology_10m.tif'); H,W=src.height//2,src.width//2
T=src.transform*src.transform.scale(2,2)
cls=src.read(1,out_shape=(H,W),resampling=Resampling.mode)
lf=rasterio.open(R+'leaf_fall_fraction_10m.tif').read(out_shape=(5,H,W),resampling=Resampling.average).astype(np.float32)
g=gpd.read_file('/mnt/project-files/fire-alert-scars/event_scars.geojson').to_crs(src.crs)
g['date']=pd.to_datetime(g.date); md=g.date.dt.strftime('%m%d'); g=g[(md>='0215')&(md<='0615')]
g['yr']=g.date.dt.year; g=g.sort_values('date').reset_index(drop=True)
forest=np.isin(cls,[1,2,3,4])
rng=np.random.default_rng(3); K=2  # 40 m band
rows=[]
for y,gy in g.groupby('yr'):
    prior=np.zeros((H,W),bool)
    for _,r in gy.iterrows():
        b=r.geometry.bounds; c0,r0=~T*(b[0]-600,b[3]+600); c1,r1=~T*(b[2]+600,b[1]-600)
        r0,c0=max(int(r0),0),max(int(c0),0); r1,c1=min(int(r1)+1,H),min(int(c1)+1,W)
        if r1-r0<10 or c1-c0<10: continue
        Tw=T*T.translation(c0,r0)
        m=rasterize([(r.geometry,1)],out_shape=(r1-r0,c1-c0),transform=Tw,fill=0,dtype='uint8').astype(bool)
        if m.sum()<5: continue
        mon=r.date.month; band=min(mon,4)-0  # Feb->idx2? bands Dec,Jan,Feb,Mar,Apr => Feb=2,Mar=3,Apr+=4
        bi={2:2,3:3}.get(mon,4)
        for shift in [None,'null']:
            mm=m
            if shift:
                dy,dx=rng.integers(25,40,2)*rng.choice([-1,1],2)
                mm=np.roll(np.roll(m,dy,0),dx,1)
            ins=mm&~binary_erosion(mm,iterations=K); out=binary_dilation(mm,iterations=K)&~mm
            fw=forest[r0:r1,c0:c1]&~prior[r0:r1,c0:c1]
            for side,s in [('in',ins&fw),('out',out&fw)]:
                cc=cls[r0:r1,c0:c1][s]; ll=lf[bi,r0:r1,c0:c1][s]
                rows.append(dict(event=r.event_id if 'event_id' in r else _,yr=y,mon=mon,null=bool(shift),side=side,n=s.sum(),
                                 n_dec=(cc==1).sum(),n_grn=(cc==2).sum(),n_grass=(cc==4).sum(),lf_sum=float(ll.sum())))
        prior[r0:r1,c0:c1]|=m
D=pd.DataFrame(rows); D.to_csv('h2_edges.csv',index=False)
def summ(d):
    a=d.groupby(['null','side'])[['n','n_dec','n_grn','n_grass','lf_sum']].sum()
    a['dec']=a.n_dec/a.n; a['grn']=a.n_grn/a.n; a['grass']=a.n_grass/a.n; a['lf']=a.lf_sum/a.n
    return a[['n','dec','grn','grass','lf']].round(3)
print('ALL'); print(summ(D))
for lab,ms in [('Feb15-Mar',[2,3]),('Apr',[4]),('May-Jun',[5,6])]:
    print(lab); print(summ(D[D.mon.isin(ms)]))
