# SIS-DP v2 1:10k LULC (Bhuvan WMS render) -> class raster on 20 m grid; class areas in sanctuary; class-boundary line layers
import numpy as np, rasterio, geopandas as gpd
from rasterio.warp import reproject, Resampling
from rasterio.features import rasterize
from affine import Affine
from scipy import ndimage
D='/tmp/claude-0/-home-user/be9b8f54-cc26-52cb-bdbb-9c8008a24baf/scratchpad/r9_barrier_data/'
G={1:('forest',[(80,187,62)]),2:('plantation',[(121,200,0)]),3:('grazing',[(181,214,41)]),
   4:('scrub',[(255,30,250),(255,51,255),(204,51,204),(210,10,255)]),5:('crop',[(255,255,115),(253,243,23),(255,201,176)]),
   6:('water',[(0,61,222),(0,51,204),(99,153,255),(51,153,255),(52,52,254),(0,168,132),(0,153,153)]),
   7:('built',[(255,0,0),(185,0,0),(220,80,101),(255,127,127),(230,0,0),(239,69,39),(255,174,174),(255,0,94),(200,133,68),(132,43,0)]),
   8:('barren',[(255,150,232),(255,153,255),(225,171,242),(229,207,255),(230,230,248)])}
z=np.load('/mnt/project-files/ratapani/spread/data_shared/grid20.npz'); T=Affine(*z['transform']); H,W=[int(v) for v in z['shape']]
out=np.zeros((H,W),np.uint8)
for f in ['sisdpv2_MP_Raisen_lulc_v2.tif','sisdpv2_MP_Sehore_lulc_v2.tif']:
    with rasterio.open(D+'bhuvan/'+f) as s: a=s.read(); st=s.transform; crs=s.crs
    cls=np.zeros(a.shape[1:],np.uint8); rgb=a[:3].astype(int); al=a[3]>0
    for k,(nm,cols) in G.items():
        for c in cols:
            m=al&(np.abs(rgb[0]-c[0])<=6)&(np.abs(rgb[1]-c[1])<=6)&(np.abs(rgb[2]-c[2])<=6); cls[m]=k
    print(f,'alpha',al.mean().round(3),'classified share of alpha',(cls>0).sum()/max(al.sum(),1))
    o=np.zeros((H,W),np.uint8)
    reproject(cls,o,src_transform=st,src_crs=crs,dst_transform=T,dst_crs='EPSG:32643',resampling=Resampling.mode)
    out=np.where(out==0,o,out)
np.save(D+'sisdp_lulc20.npy',out)
aoi=gpd.read_file('/mnt/project-files/ratapani/ratapani_aoi.geojson').to_crs(32643)
A=rasterize([(g,1) for g in aoi.geometry],out_shape=(H,W),transform=T,fill=0,dtype='uint8').astype(bool)
print('sanctuary pixels',A.sum(),'unclassified share',(out[A]==0).mean().round(3))
for k,(nm,_) in G.items(): print(f'{nm:10s} share of sanctuary {(out[A]==k).mean():.3f}  ({(out[A]==k).sum()*0.04:.0f} ha)')
# boundary layers between forest and other burnable classes
def orient(m,sig=2.0):
    f=m.astype(np.float32); gx=ndimage.sobel(f,1); gy=ndimage.sobel(f,0)
    Jxx=ndimage.gaussian_filter(gx*gx,sig); Jyy=ndimage.gaussian_filter(gy*gy,sig); Jxy=ndimage.gaussian_filter(gx*gy,sig)
    th=0.5*np.arctan2(2*Jxy,Jxx-Jyy); return ((-(np.degrees(th)+90))%180).astype(np.float16)
L={}
F=out==1
for k,nm in [(2,'plantation'),(3,'grazing'),(4,'scrub')]:
    m=F&ndimage.binary_dilation(out==k,np.ones((3,3),bool)); L[f'lulc_forest_{nm}_m']=m; L[f'lulc_forest_{nm}_a']=orient(m); print(nm,'boundary km',m.sum()*0.02)
np.savez_compressed(D+'layers20_lulc.npz',**L)
