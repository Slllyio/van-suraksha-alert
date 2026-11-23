# Hold rate: where a season's scars reach a mapped line (burned within 60 m on at least one side),
# how often is the other side unburned (line held) vs burned (crossed)? Compare with the same layer shifted.
import numpy as np, geopandas as gpd, pandas as pd
from affine import Affine
from rasterio.features import rasterize
D='/tmp/claude-0/-home-user/be9b8f54-cc26-52cb-bdbb-9c8008a24baf/scratchpad/r9_barrier_data/'
z=np.load('/mnt/project-files/ratapani/spread/data_shared/grid20.npz')
T=Affine(*z['transform']); H,W=[int(v) for v in z['shape']]
burnable=np.isin(z['wc'],[10,20,30])
g=gpd.read_file('/mnt/project-files/fire-alert-scars/event_scars.geojson').to_crs(32643); g=g[g.date.dt.month<=6]
YRS=range(2017,2027)
B0={y:rasterize([(geo,1) for geo in g[g.date.dt.year==y].geometry],out_shape=(H,W),transform=T,fill=0,dtype='uint8').astype(bool) for y in YRS}
from scipy import ndimage
import sys
MIND=float(sys.argv[1]) if len(sys.argv)>1 else 500
pts=g.copy(); pts['geometry']=gpd.points_from_xy(g.lon,g.lat,crs=4326).to_crs(32643)
pc=((pts.geometry.x-T.c)/20).astype(int).clip(0,W-1).values; pr=((T.f-pts.geometry.y)/20).astype(int).clip(0,H-1).values
LZ=dict(np.load(D+'layers20.npz')); LZ.update(dict(np.load(D+'layers20_extra.npz'))); LZ.update(dict(np.load(D+'layers20_ms.npz')))
import os
if os.path.exists(D+'layers20_lulc.npz'): LZ.update(dict(np.load(D+'layers20_lulc.npz'))); RE=np.load(D+__import__('os').environ.get('RECUR','recurrent_edges.npz'))
rng=np.random.default_rng(1)
def stats(m,a,shift=(0,0),yearly=None):
    rows=[]
    tot=np.zeros(4)
    for y in YRS:
        mm=yearly[f'm_{y}'] if yearly is not None else m; aa=(yearly[f'a_{y}'] if yearly is not None else a).astype(np.float32)
        r,c=np.nonzero(mm); ang=np.radians(aa[r,c])
        r=r+shift[0]; c=c+shift[1]; ok=(r>=5)&(r<H-5)&(c>=5)&(c<W-5)
        r,c,ang=r[ok],c[ok],ang[ok]
        # line pixel must itself sit in burnable land on both sides
        nx=-np.sin(ang); ny=np.cos(ang)   # normal in map coords (x east, y north) -> rows go south
        res=[]
        for d in (3,):  # 60 m
            r1=np.round(r-ny*d).astype(int); c1=np.round(c+nx*d).astype(int); r2=np.round(r+ny*d).astype(int); c2=np.round(c-nx*d).astype(int)
            fb=burnable[r1,c1]&burnable[r2,c2]
            b1=B[y][r1,c1]; b2=B[y][r2,c2]
            both=(b1&b2&fb).sum(); one=((b1^b2)&fb).sum()
        tot+=np.array([both,one,fb.sum(),len(r)])
    crossed,held,elig,n=tot
    return dict(reached=int(crossed+held),crossed=int(crossed),held=int(held),hold_rate=round(held/max(crossed+held,1),3),reach_per_px_season=round((crossed+held)/max(elig,1),4))
rows=[]
LAYS=sys.argv[2].split(',') if len(sys.argv)>2 else None
for k in ['lulc_forest_plantation','lulc_forest_grazing','lulc_forest_scrub','ms_w_lt7','ms_w_7_10','ms_w_ge10','ms_roads','ov_osm_roads','ov_tomtom','mmi_roads','rail','power','bh_drain','mmi_hydro','stream_0.25km2','stream_1km2','stream_5km2','stream_25km2','ridge_100c','ridge_500c','recurrent_LOSO']:
    if LAYS and k not in LAYS: continue
    if k=='recurrent_LOSO': m=a=None; yearly=RE; dist=None
    else: m=LZ[k+'_m']; a=LZ[k+'_a']; yearly=None
    if yearly is None:
        dist=ndimage.distance_transform_edt(~m,sampling=20); far=dist[pr,pc]>MIND
        B={y:rasterize([(geo,1) for geo in g[(g.date.dt.year==y).values&far].geometry],out_shape=(H,W),transform=T,fill=0,dtype='uint8').astype(bool) for y in YRS}
    else: B=B0
    o=stats(m,a,yearly=yearly)
    nulls=[]
    for i in range(10):
        sh=rng.integers(15,50,2)*rng.choice([-1,1],2)   # 300-1000 m shift
        nulls.append(stats(m,a,shift=tuple(sh),yearly=yearly)['hold_rate'])
    o.update(layer=k,mind=MIND,null_hold=round(float(np.mean(nulls)),3),null_sd=round(float(np.std(nulls)),3))
    rows.append(o); print(o,flush=True)
pd.DataFrame(rows).to_csv(D+f'hold_rate_far{int(MIND)}.csv',index=False)
