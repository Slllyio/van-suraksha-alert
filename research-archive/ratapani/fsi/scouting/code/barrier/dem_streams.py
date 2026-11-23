import rasterio, numpy as np, glob, json
from rasterio.merge import merge
from rasterio.warp import reproject, Resampling, calculate_default_transform
from rasterio.transform import from_origin
D='/tmp/claude-0/-home-user/be9b8f54-cc26-52cb-bdbb-9c8008a24baf/scratchpad/r9_barrier_data/'
srcs=[rasterio.open(f) for f in sorted(glob.glob(D+'dem/*.tif'))]
mos,tr=merge(srcs,bounds=(77.35,22.65,78.35,23.35))
# reproject to UTM43 30 m on grid-aligned box
x0,x1,y0,y1=725000,830000,2512000,2576000
W=int((x1-x0)/30);H=int((y1-y0)/30)
dt=from_origin(x0,y1,30,30)
out=np.zeros((H,W),np.float32)
reproject(mos[0],out,src_transform=tr,src_crs='EPSG:4326',dst_transform=dt,dst_crs='EPSG:32643',resampling=Resampling.bilinear)
prof=dict(driver='GTiff',height=H,width=W,count=1,dtype='float32',crs='EPSG:32643',transform=dt,compress='deflate')
with rasterio.open(D+'dem_utm30.tif','w',**prof) as o: o.write(out,1)
np.in1d=np.isin
from pysheds.grid import Grid
g=Grid.from_raster(D+'dem_utm30.tif'); dem=g.read_raster(D+'dem_utm30.tif')
f=g.fill_pits(dem); f=g.fill_depressions(f); f=g.resolve_flats(f)
fd=g.flowdir(f); acc=g.accumulation(fd)
a=np.asarray(acc).astype(np.float32)
with rasterio.open(D+'flowacc_utm30.tif','w',**prof) as o: o.write(a,1)
np.save(D+'fdir.npy',np.asarray(fd))
for thr_km2 in [0.25,1,5,25]:
    n=int(thr_km2*1e6/900)
    br=g.extract_river_network(fd,acc>n)
    json.dump(br,open(D+f'streams_{thr_km2}km2.geojson','w'))
    print(thr_km2,len(br['features']))
