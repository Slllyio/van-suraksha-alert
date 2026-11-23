import rasterio, numpy as np, json
np.in1d=np.isin
from pysheds.grid import Grid
D='/tmp/claude-0/-home-user/be9b8f54-cc26-52cb-bdbb-9c8008a24baf/scratchpad/r9_barrier_data/'
with rasterio.open(D+'dem_utm30.tif') as s: a=s.read(1); prof=s.profile
inv=(a.max()+1-a).astype(np.float32)
with rasterio.open(D+'dem_inv.tif','w',**prof) as o: o.write(inv,1)
g=Grid.from_raster(D+'dem_inv.tif'); dem=g.read_raster(D+'dem_inv.tif')
f=g.fill_pits(dem); f=g.fill_depressions(f); f=g.resolve_flats(f)
fd=g.flowdir(f); acc=g.accumulation(fd)
for n in [100,500]:
    br=g.extract_river_network(fd,acc>n); json.dump(br,open(D+f'ridges_{n}cells.geojson','w')); print(n,len(br['features']))
