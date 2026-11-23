# Bhuvan WMS rasters -> line masks + orientation on 20 m grid; event-scar earliest-DOY rasters per season
import numpy as np, rasterio, geopandas as gpd
from rasterio.warp import reproject, Resampling
from affine import Affine
from scipy import ndimage
from skimage.morphology import skeletonize
from rasterio.features import rasterize
D='/tmp/claude-0/-home-user/be9b8f54-cc26-52cb-bdbb-9c8008a24baf/scratchpad/r9_barrier_data/'
z=np.load('/mnt/project-files/ratapani/spread/data_shared/grid20.npz')
T=Affine(*z['transform']); H,W=[int(v) for v in z['shape']]
out={}
def orient(m,sig=2.0):
    f=m.astype(np.float32); gx=ndimage.sobel(f,1); gy=ndimage.sobel(f,0)
    Jxx=ndimage.gaussian_filter(gx*gx,sig); Jyy=ndimage.gaussian_filter(gy*gy,sig); Jxy=ndimage.gaussian_filter(gx*gy,sig)
    # gradient dominant direction; line direction is perpendicular. rows go south -> flip y
    th=0.5*np.arctan2(2*Jxy,Jxx-Jyy)      # in image coords (x right, y down)
    gdir=np.degrees(th); line=(-(gdir+90))%180   # convert to math angle with y north
    return line.astype(np.float32)
for name,f,sel in [('bh_drain','hydrology_bdrain_qgs.tif',lambda a:(a[3]>0)&(a[2]>200)&(a[0]<60)),
                   ('mmi_roads','mmi_MP_ROAD_NETWORK_Q4_2022.tif',lambda a:(a[3]>0)&~((a[0]<90)&(a[1]<90)&(a[2]<90))&~((a[0]>230)&(a[1]>200)&(a[2]<150))),
                   ('mmi_hydro','mmi_MP_HYDROLOGY_R_Q4_2022.tif',lambda a:(a[3]>0)&(a[2]>150)&~((a[0]<90)&(a[1]<90)&(a[2]<90)))]:
    with rasterio.open(D+'bhuvan/'+f) as s: a=s.read(); st=s.transform; crs=s.crs
    m=sel(a)
    # remove watermark-size blobs: keep components with >= 30 px
    lab,n=ndimage.label(m,np.ones((3,3))); sz=np.bincount(lab.ravel()); keep=sz>=30; keep[0]=False; m=keep[lab]
    sk=skeletonize(m)
    ang=orient(sk)
    dm=np.zeros((H,W),np.uint8); da=np.zeros((H,W),np.float32)
    reproject(sk.astype(np.uint8),dm,src_transform=st,src_crs=crs,dst_transform=T,dst_crs='EPSG:32643',resampling=Resampling.max)
    reproject(np.where(sk,ang,0).astype(np.float32),da,src_transform=st,src_crs=crs,dst_transform=T,dst_crs='EPSG:32643',resampling=Resampling.max)
    out[name+'_m']=dm>0; out[name+'_a']=da.astype(np.float16)
    print(name,'px',out[name+'_m'].sum(),'km~',out[name+'_m'].sum()*0.02)
np.savez_compressed(D+'layers20_extra.npz',**out)
# event scars: earliest DOY per pixel per season (all scars incl. chip-edge)
g=gpd.read_file('/mnt/project-files/fire-alert-scars/event_scars.geojson').to_crs(32643)
g=g[g.date.dt.month<=6]
S={}
for yr,gg in g.groupby(g.date.dt.year):
    gg=gg.sort_values('date',ascending=False)  # later first so earlier overwrite
    S[f'scar_doy_{yr}']=rasterize([(geo,int(d.dayofyear)) for geo,d in zip(gg.geometry,gg.date)],out_shape=(H,W),transform=T,fill=0,dtype='int16')
    # rasterize keeps last-drawn on overlaps -> earliest date wins
np.savez_compressed(D+'scar_doy20.npz',**S); print('scar doy years',list(S))
