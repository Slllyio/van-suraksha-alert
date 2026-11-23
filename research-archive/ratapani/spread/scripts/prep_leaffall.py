"""Leaf-fall fraction (fuel-map thread, 10 m, bands Dec..Apr, 0-100) resampled to the 20 m grid -> data/leaffall20.npz"""
import numpy as np, rasterio
from rasterio.vrt import WarpedVRT
from rasterio.enums import Resampling
import sim
with rasterio.open('/mnt/project-files/fuel-map/ratapani/leaf_fall_fraction_10m.tif') as src, \
     WarpedVRT(src, crs='EPSG:32643', transform=rasterio.transform.Affine(*sim.TR[:6]), width=sim.NX, height=sim.NY, resampling=Resampling.average, src_nodata=255, nodata=255) as vv:
    a = vv.read().astype(np.float32)
a[a == 255] = np.nan
np.savez_compressed(f'{sim.DATA}/leaffall20.npz', lf=a / 100.0)
print(a.shape, 'median by band (deciduous):', [round(float(np.nanmedian(a[b])), 1) for b in range(5)])
