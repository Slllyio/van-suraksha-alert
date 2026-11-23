"""Static 10 m layers on one UTM grid over Ratapani: NASADEM (SRTM) elevation + slope, ESA WorldCover 2021."""
import numpy as np, geopandas as gpd, rasterio, planetary_computer as pc, pystac_client
from rasterio.vrt import WarpedVRT
from rasterio.enums import Resampling
from rasterio.features import geometry_mask
OUT = '/tmp/claude-0/fuel/'
CRS, RES = 'EPSG:32643', 10.0
a = gpd.read_file('/mnt/project-files/ratapani/ratapani_aoi.geojson').to_crs(CRS)
x0, y0, x1, y1 = a.total_bounds
x0, y0 = np.floor(x0 / 20) * 20 - 200, np.floor(y0 / 20) * 20 - 200
x1, y1 = np.ceil(x1 / 20) * 20 + 200, np.ceil(y1 / 20) * 20 + 200
W, H = int((x1 - x0) / RES), int((y1 - y0) / RES)
TR = rasterio.transform.from_origin(x0, y1, RES, RES)
inside = ~geometry_mask(a.geometry, (H, W), TR)
print(W, H, inside.sum())
cat = pystac_client.Client.open('https://planetarycomputer.microsoft.com/api/stac/v1', modifier=pc.sign_inplace)
bbox = list(a.to_crs(4326).total_bounds)
def mosaic(coll, asset, resamp, query=None, dtype='float32'):
    items = list(cat.search(collections=[coll], bbox=bbox, query=query).items())
    out = np.full((H, W), np.nan, 'float32')
    for it in items:
        with rasterio.open(it.assets[asset].href) as s, WarpedVRT(s, crs=CRS, transform=TR, width=W, height=H, resampling=resamp, src_nodata=s.nodata, nodata=np.nan, dtype='float32') as v:
            d = v.read(1); m = np.isnan(out) & ~np.isnan(d); out[m] = d[m]
    print(coll, len(items)); return out
# slope at native 30 m first (FSI used 30 m SRTM), then bilinear to 10 m
items = list(cat.search(collections=['nasadem'], bbox=bbox).items())
R30 = 30.0; W3, H3 = int((x1 - x0) / R30) + 1, int((y1 - y0) / R30) + 1
T3 = rasterio.transform.from_origin(x0, y1, R30, R30)
dem = np.full((H3, W3), np.nan, 'float32')
for it in items:
    with rasterio.open(it.assets['elevation'].href) as s, WarpedVRT(s, crs=CRS, transform=T3, width=W3, height=H3, resampling=Resampling.bilinear, nodata=np.nan, dtype='float32') as v:
        d = v.read(1); m = np.isnan(dem) & ~np.isnan(d); dem[m] = d[m]
gy, gx = np.gradient(dem, R30)
slope30 = np.degrees(np.arctan(np.hypot(gx, gy))).astype('float32')
asp30 = (np.degrees(np.arctan2(-gx, gy)) % 360).astype('float32')   # aspect, 0 = north-facing downslope... kept for reference
from rasterio.warp import reproject
def up(a30):
    o = np.zeros((H, W), 'float32'); reproject(a30, o, src_transform=T3, src_crs=CRS, dst_transform=TR, dst_crs=CRS, resampling=Resampling.bilinear); return o
slope = up(slope30); elev = up(dem)
wc = mosaic('esa-worldcover', 'map', Resampling.nearest, query={'esa_worldcover:product_version': {'eq': '2.0.0'}})
np.savez_compressed(OUT + 'static10.npz', slope=slope, elev=elev, wc=wc.astype('uint8'), inside=inside, transform=np.array(TR)[:6], W=W, H=H)
print('slope pct by FSI class (inside):', np.histogram(slope[inside], [0, 10, 20, 30, 90])[0] / inside.sum())
print('worldcover inside:', {int(k): round(float(v), 3) for k, v in zip(*np.unique(wc[inside], return_counts=True)) if v} )
