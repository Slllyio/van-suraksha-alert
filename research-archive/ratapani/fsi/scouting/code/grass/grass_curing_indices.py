"""Apply published grassland-curing and dry-grass formulas to our monthly Sentinel-2 composites (Sep 2023-May 2025 pooled by month),
by cover class, on pixels not burned in the 2024 and 2025 seasons (scar outlines v2).
- MODIS 'Method B' (Newnham et al. 2010, as given in Chaivaranont et al. 2018 eq. 5): C = 237.31 - 190.14*NDVI - 142.66*(rho7/rho6)
  with MODIS b6 (1640 nm) ~ S2 B11, b7 (2130 nm) ~ S2 B12.
- MapVictoria (Martin et al. 2015, eq. 6): C = 113.80 - 88.41*NDVI - 67.71*GVMI, GVMI = ((b2+0.1)-(b6+0.02))/((b2+0.1)+(b6+0.02)), b2 ~ S2 B8A.
- Zang et al. 2023 dry-grass fuel (NE China marsh, exponential on DGI2 = NDTI): AGB g/m2 = 12.745*exp(20.454*NDTI).  Transfer is untested here.
- McArthur Mk4 GFDI curing factor f(C) = exp(-0.009432*(100-C)^1.536); CSIRO/Cruz 2015 curing coefficient 1.036/(1+103.989*exp(-0.0996*(C-20))).
These are sensor-swapped, uncalibrated applications: read them as relative curves, not absolute curing."""
import numpy as np, pandas as pd, geopandas as gpd, rasterio
from rasterio.features import rasterize
from rasterio.enums import Resampling
R = '/mnt/project-files/fuel-map/ratapani/'; WK = R + 'work/'
src = rasterio.open(R + 'cover_phenology_10m.tif'); H, W = src.height // 2, src.width // 2
T = src.transform * src.transform.scale(2, 2)
cls = src.read(1, out_shape=(H, W), resampling=Resampling.mode)
g = gpd.read_file('/mnt/project-files/fire-alert-scars/reference/v2_2026-10-16/firms_event_scars.geojson', columns=['date']).to_crs(src.crs)
g['date'] = pd.to_datetime(g.date); g['season'] = np.where(g.date.dt.month >= 8, g.date.dt.year + 1, g.date.dt.year)
burn = rasterize(((geom, 1) for geom in g[g.season.isin([2024, 2025])].geometry if geom is not None), out_shape=(H, W), transform=T, fill=0, dtype='uint8').astype(bool)
NAMES = {1: 'deciduous tree', 2: 'green tree', 4: 'open grass/low', 5: 'sparse/bare'}
fGF = lambda C: np.exp(-0.009432 * np.clip(100 - C, 0, 100) ** 1.536)
fCR = lambda C: np.where(C < 20, 0, 1.036 / (1 + 103.989 * np.exp(-0.0996 * (C - 20))))
rows = []
for mo in [10, 12, 2, 4, 5]:
    nd = np.load(f'{WK}monthly/m{mo:02d}.npz')['ndvi'][::2, ::2].astype('float32')
    q = np.load(f'{WK}monthly_re/m{mo:02d}.npz')
    b8a, b11, b12 = (q[b][::2, ::2].astype('float32') for b in ['B8A', 'B11', 'B12'])
    cB = np.clip(237.31 - 190.14 * nd - 142.66 * (b12 / b11), 0, 100)
    gv = ((b8a + 0.1) - (b11 + 0.02)) / ((b8a + 0.1) + (b11 + 0.02))
    cM = np.clip(113.80 - 88.41 * nd - 67.71 * gv, 0, 100)
    ndti = (b11 - b12) / (b11 + b12); agb = 12.745 * np.exp(20.454 * ndti)
    for k in NAMES:
        m = (cls == k) & ~burn & np.isfinite(cB)
        rows.append(dict(month=mo, cls=NAMES[k], curing_methodB=np.nanmedian(cB[m]), curing_mapvic=np.nanmedian(cM[m]),
                         gfdi_fC=np.nanmedian(fGF(cB[m])), cruz_coeff=np.nanmedian(fCR(cB[m])),
                         ndti=np.nanmedian(ndti[m]), zang_drygrass_gm2=np.nanmedian(agb[m]), b12_b11=np.nanmedian((b12 / b11)[m])))
D = pd.DataFrame(rows); D.to_csv('grass_curing_indices.csv', index=False)
print(D.round(3).to_string(index=False))
