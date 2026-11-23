# Recurrent scar edges: pixels that are an in-forest scar edge in many seasons -> candidate fire lines / persistent barriers.
# Leave-one-season-out versions for honest testing.
import numpy as np, geopandas as gpd
from affine import Affine
from scipy import ndimage
from rasterio.features import rasterize
from skimage.morphology import skeletonize, remove_small_objects
D='/tmp/claude-0/-home-user/be9b8f54-cc26-52cb-bdbb-9c8008a24baf/scratchpad/r9_barrier_data/'
z=np.load('/mnt/project-files/ratapani/spread/data_shared/grid20.npz')
T=Affine(*z['transform']); H,W=[int(v) for v in z['shape']]
burnable=np.isin(z['wc'],[10,20,30])
g=gpd.read_file('/mnt/project-files/fire-alert-scars/event_scars.geojson').to_crs(32643)
g=g[g.date.dt.month<=6]
YRS=list(range(2017,2027)); E={}; X={}
k3=np.ones((3,3),bool)
for y in YRS:
    gg=g[g.date.dt.year==y]
    B=rasterize([(geo,1) for geo in gg.geometry],out_shape=(H,W),transform=T,fill=0,dtype='uint8').astype(bool)
    # in-forest edge: unburned burnable pixel adjacent to burned (outer edge, where fire stopped in fuel)
    E[y]=ndimage.binary_dilation(B,k3)&~B&burnable
    X[y]=ndimage.binary_dilation(B,iterations=5)&~B&burnable     # exposure: within 100 m outside a scar
def orient(m,sig=2.0):
    f=m.astype(np.float32); gx=ndimage.sobel(f,1); gy=ndimage.sobel(f,0)
    Jxx=ndimage.gaussian_filter(gx*gx,sig); Jyy=ndimage.gaussian_filter(gy*gy,sig); Jxy=ndimage.gaussian_filter(gx*gy,sig)
    th=0.5*np.arctan2(2*Jxy,Jxx-Jyy); return ((-(np.degrees(th)+90))%180).astype(np.float32)
def build(years, minc=3, minf=0.4):
    C=sum(ndimage.binary_dilation(E[y],k3).astype(np.int16) for y in years)  # tolerate 20 m mis-registration
    N=sum(ndimage.binary_dilation(X[y],k3).astype(np.int16) for y in years)
    f=np.where(N>0,C/np.maximum(N,1),0)
    m=(C>=minc)&(f>=minf)
    m=remove_small_objects(m,min_size=10,connectivity=2)
    sk=skeletonize(m); sk=remove_small_objects(sk,min_size=8,connectivity=2)   # >=160 m long
    return sk,C,N
out={}
sk,C,N=build(YRS); out['m_all']=sk; out['a_all']=orient(sk).astype(np.float16); out['C_all']=C; out['N_all']=N
print('all seasons: recurrent-edge skeleton px',sk.sum(),'km~',sk.sum()*0.02)
for y in YRS:
    sk,_,_=build([v for v in YRS if v!=y]); out[f'm_{y}']=sk; out[f'a_{y}']=orient(sk).astype(np.float16)
    print(y,'LOSO skeleton km~',round(sk.sum()*0.02))
np.savez_compressed(D+'recurrent_edges.npz',**out)
