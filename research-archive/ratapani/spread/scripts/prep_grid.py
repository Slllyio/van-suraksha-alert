"""Build the 20 m model grid for Ratapani (EPSG:32643, aligned to the burn-scar rasters, 2 km pad):
elevation, slope, aspect (Copernicus GLO-30), WorldCover 2021 class, per-season burn DOY."""
import numpy as np, rasterio, glob, sys
from rasterio.warp import reproject, Resampling
from rasterio.transform import from_origin
RAW, OUT = sys.argv[1], sys.argv[2]
LABELS = '/mnt/project-files/research/ratapani-burn-labels/rasters'
PAD = 2000; RES = 20.0
left, bottom, right, top = 739300 - PAD, 2525020 - PAD, 814740 + PAD, 2558500 + PAD
W, H = int((right - left) / RES), int((top - bottom) / RES)
T = from_origin(left, top, RES, RES); CRS = 'EPSG:32643'
def warp(paths, resampling, dtype, nodata):
    out = np.full((H, W), nodata, dtype)
    for p in paths:
        with rasterio.open(p) as s:
            tmp = np.full((H, W), nodata, dtype)
            reproject(rasterio.band(s, 1), tmp, dst_transform=T, dst_crs=CRS, resampling=resampling, dst_nodata=nodata)
            m = tmp != nodata; out[m] = tmp[m]
    return out
dem = warp(sorted(glob.glob(RAW + '/Copernicus_DSM*.tif')), Resampling.bilinear, np.float32, -9999)
gy, gx = np.gradient(dem.astype(np.float64), RES)          # gy: d/d(row) -> row increases southward
dzdx, dzdy_north = gx, -gy
slope = np.degrees(np.arctan(np.hypot(dzdx, dzdy_north))).astype(np.float32)
# upslope direction (azimuth, deg clockwise from north) = direction of steepest ascent
upslope_az = (np.degrees(np.arctan2(dzdx, dzdy_north)) % 360).astype(np.float32)
wc = warp(sorted(glob.glob(RAW + '/ESA_WorldCover*.tif')), Resampling.mode, np.uint8, 0)
burn = {}
for p in sorted(glob.glob(LABELS + '/burn_*.tif')):
    yr = int(p[-8:-4]); b = np.full((H, W), -999, np.int16)
    with rasterio.open(p) as s:
        a = s.read(1); r0 = int(round((top - s.bounds.top) / RES)); c0 = int(round((s.bounds.left - left) / RES))
        b[r0:r0 + a.shape[0], c0:c0 + a.shape[1]] = a
    burn[f'burn_end_{yr}'] = b
    with rasterio.open(p) as s:
        a = s.read(2); b2 = np.full((H, W), -999, np.int16); b2[r0:r0 + a.shape[0], c0:c0 + a.shape[1]] = a
    burn[f'burn_start_{yr}'] = b2
np.savez_compressed(OUT, elev=dem, slope=slope, upslope_az=upslope_az, wc=wc,
                    transform=np.array(T)[:6], shape=np.array([H, W]), **burn)
print(H, W, 'slope mean', slope.mean(), 'wc classes', np.unique(wc, return_counts=True))
