"""Ratapani 10 m surface fuel load, FSI method + satellite-continuous version.

A) FSI-structure map: forest type group (Group 5 tropical dry deciduous for all forest pixels) x canopy density class
   (VDF >=70 / MDF 40-70 / OF 10-40 / Scrub <10 %, from 1 m canopy height >=3 m) x slope class (0-10/10-20/20-30/>30 deg,
   SRTM 30 m), each stratum given a literature value in g/ft2 (FSI does not publish its stratum means).
B) Continuous map (peak season, Mar-Apr, area not yet burned this season), per 10 m pixel:
      leaf litter  = LF * cover_eff * shed  +  carry * LF * cover_eff
      grass        = G_MAX * (1 - cover) * grass_vigour
      fuel         = (leaf litter + grass) * slope multiplier
   LF = annual leaf fall of a closed dry teak stand (t/ha/yr), shed = share of leaf-on greenness lost by Mar-Apr (Sentinel-2),
   carry = undecomposed litter left from last year (~28% survives the monsoon, Jhariya 2017), grass vigour from leaf-on NDVI
   of the open fraction. Constants from central Indian studies, see README.
C) Season maps: B with fuel reset where our burn-scar maps show a burn last season (no carry-over) or this season (residual).
"""
import numpy as np, rasterio, json, os
from rasterio.transform import Affine
D = '/tmp/claude-0/fuel/'; OUT = os.environ.get('FUEL_OUT', D + 'out/'); os.makedirs(OUT, exist_ok=True)
S = np.load(D + 'static10.npz'); C = np.load(D + 'chm10.npz'); N = np.load(D + 's2ndvi10.npz')
W, H = int(S['W']), int(S['H']); TR = Affine(*S['transform']); ins = S['inside']; wc = S['wc']; slope = S['slope']
GFT = 9.29                      # 1 t/ha = 9.29 g/ft2
cover = np.load(D + 'canopy_s2.npz')['s2']   # Sentinel-2 canopy cover trained on 1 m tree heights (see canopy_s2.py)
from scipy.ndimage import uniform_filter
cover_ha = uniform_filter(cover, 10, mode='nearest')   # FSI canopy density is defined over >=1 ha, so classes use a 100 m window
cover_30 = uniform_filter(cover, 3, mode='nearest')    # leaf litter drifts a crown-width or so: 30 m window for the litter term
on, dry = N['leafon'], N['dry'].copy()   # dry composite has pixels burned that season masked out
from scipy.ndimage import uniform_filter as _uf
_v = np.isfinite(dry); _s = _uf(np.where(_v, dry, 0), 15); _n = _uf(_v.astype('float32'), 15)
dry = np.where(_v, dry, np.where(_n > 0.05, _s / np.maximum(_n, 1e-6), np.nan)).astype('float32')   # fill from unburned neighbours within ~75 m
forest = ins & np.isin(wc, [10, 20, 30])          # tree, shrub, grass: FSI forest + scrub; crops/built/water/bare excluded
# ---- classes
ccls = np.digitize(cover_ha * 100, [10, 40, 70])     # 0 scrub, 1 OF, 2 MDF, 3 VDF
scls = np.digitize(slope, [10, 20, 30])           # 0..3
SLOPE_MULT = np.array([1.0, 0.95, 0.85, 0.75])    # assumption: litter washes/blows off steep slopes, shallow soils
# ---- A: stratum table (g/ft2 at 0-10 deg), Group 5; rows scrub, OF, MDF, VDF
BASE = np.array([12.0, 17.0, 22.0, 28.0])
TABLE = np.round(BASE[:, None] * SLOPE_MULT[None, :], 1)
fsi = np.where(forest, TABLE[ccls, scls], np.nan).astype('float32')
# ---- B: continuous
LF, CARRY, G_MAX = 3.3, 0.28, 1.5                 # t/ha/yr leaf fall closed stand; litter surviving monsoon; t/ha cured grass, open ground
cover_eff = np.clip(cover_30 / 0.7, 0, 1)            # leaf fall saturates at ~70% cover (VDF)
NDVI_BARE = 0.15
shed = np.clip((on - dry) / np.clip(on - NDVI_BARE, 0.05, None), 0, 1); shed = np.where(np.isfinite(shed), shed, 0.8)
vig = np.clip((np.nan_to_num(on, nan=0.4) - 0.2) / 0.5, 0, 1)
leaf = LF * cover_eff * (shed + CARRY)
grass = G_MAX * (1 - cover_30) * vig
cont = np.where(forest, (leaf + grass) * SLOPE_MULT[scls] * GFT, np.nan).astype('float32')
def cls(x): return np.digitize(x, [20, 40, 60])
def save(name, arr, dtype='float32', nodata=np.nan):
    with rasterio.open(OUT + name, 'w', driver='GTiff', width=W, height=H, count=1, dtype=dtype, crs='EPSG:32643', transform=TR,
                       nodata=nodata, compress='deflate', tiled=True, predictor=3 if dtype == 'float32' else 1) as d:
        d.write(arr.astype(dtype), 1)
save('fuel_fsi_strata_10m.tif', fsi); save('fuel_continuous_peak_10m.tif', cont)
strata = np.where(forest, 5 * 100 + ccls * 10 + scls, 0).astype('uint16')   # code GTT: group, canopy class, slope class
save('fsi_strata_code_10m.tif', strata, 'uint16', 0)
save('canopy_cover_10m.tif', np.where(ins, cover * 100, np.nan).astype('float32')); save('canopy_density_1ha_10m.tif', np.where(ins, cover_ha * 100, np.nan).astype('float32'))
# ---- C: season maps with burn history
BR = '/mnt/project-files/research/ratapani-burn-labels/rasters/burn_{}.tif'
def burned(y):
    with rasterio.open(BR.format(y)) as s: b = s.read(1) > -999
    return np.repeat(np.repeat(b, 2, 0), 2, 1)[:H, :W]
seasons = {}
for y in range(2018, 2027):
    last = burned(y - 1)
    fy = LF * cover_eff * (shed + np.where(last, 0, CARRY)) + grass * np.where(last, 0.7, 1.0)   # grass regrows in one monsoon
    seasons[y] = np.where(forest, fy * SLOPE_MULT[scls] * GFT, np.nan).astype('float32')
    save(f'fuel_season_{y}_peak_10m.tif', seasons[y])
# ---- summaries
f = forest
rep = {'pixels_forest': int(f.sum()), 'area_forest_km2': round(f.sum() * 1e-4, 1),
       'canopy_class_share': dict(zip(['scrub', 'open', 'mod_dense', 'very_dense'], np.round(np.bincount(ccls[f], minlength=4) / f.sum(), 3).tolist())),
       'slope_class_share': np.round(np.bincount(scls[f], minlength=4) / f.sum(), 3).tolist(),
       'strata_table_gft2': TABLE.tolist()}
for k, a in (('fsi_strata', fsi), ('continuous', cont)) + tuple((f'season_{y}', seasons[y]) for y in seasons):
    v = a[f]; rep[k] = {'mean': round(float(np.nanmean(v)), 1), 'p10': round(float(np.nanpercentile(v, 10)), 1), 'p90': round(float(np.nanpercentile(v, 90)), 1),
                        'class_share_low_mod_high_vhigh': np.round(np.bincount(cls(v[np.isfinite(v)]), minlength=4) / np.isfinite(v).sum(), 3).tolist()}
json.dump(rep, open(OUT + 'summary.json', 'w'), indent=1); print(json.dumps(rep, indent=1))
np.savez_compressed(D + 'maps10.npz', fsi=fsi, cont=cont, forest=forest, **{f's{y}': seasons[y] for y in seasons})
