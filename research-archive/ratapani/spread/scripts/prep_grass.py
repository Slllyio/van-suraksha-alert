"""Fuel thread's inversion (fuel-map/ratapani/inversion): grass/scrub/sparse land (S2 canopy < 0.1) carries 2-4x the mapped load.
Make a loose-bed fuel file with those pixels' loads x3. Usage: prep_grass.py in.npz out.npz [mult]"""
import numpy as np, rasterio, sys
from rasterio.warp import reproject, Resampling
import sim
mult = float(sys.argv[3]) if len(sys.argv) > 3 else 3.0
src = np.load(sys.argv[1])
can = np.full((sim.NY, sim.NX), np.nan, np.float32)
with rasterio.open('/mnt/project-files/fuel-map/ratapani/canopy_cover_10m.tif') as s:
    reproject(rasterio.band(s, 1), can, src_nodata=65535, dst_transform=rasterio.transform.from_origin(sim.X0, sim.Y0, sim.RES, sim.RES), dst_crs='EPSG:32643', resampling=Resampling.average, dst_nodata=np.nan)
grass = (can < 100) & np.isin(sim.WC, [10, 20, 30])   # raster stores percent x 10; < 10% canopy
print('grass/scrub/sparse share of vegetated pixels', round(grass.sum() / np.isin(sim.WC, [10, 20, 30]).sum(), 3))
out = {}
for k in src.files:
    a = src[k].copy()
    if k.startswith('rf_'):
        a[:3][:, grass] *= mult
    out[k] = a
np.savez_compressed(sys.argv[2], **out); print('written', sys.argv[2])
