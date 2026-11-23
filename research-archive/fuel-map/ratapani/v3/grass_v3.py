"""Grass v3 for open ground (2026-10-16). Numbers from FSI thread scouting note ratapani/fsi/scouting/grass_fuel_load.md (Jhansi rangeland, Vindhyan savanna grazing plots).
grass(d) = G(dist to buildings) * open_share * season_mult(d) ; zero after an in-season fire (no regrowth in the dry season).
  G at fire time (t/ha, central): 0.6 within 1 km of buildings -> 1.8 beyond 3 km, linear between; floor 0.5, cap 2.5   [borrowed + assumed shape]
  low / high = central x 0.6 / x 1.4                                                                                   [assumed spread]
  open_share = 1 - cover_eff (same canopy layer as litter)                                                             [measured cover]
  season_mult: 1.8 on 1 Nov falling linearly to 1.0 on 15 Feb, then 1.0 (Jhansi -48% Nov->Feb)                          [borrowed]
  distance to buildings = d_ob per 500 m cell (Google Open Buildings, FSI thread)                                       [measured]
"""
import numpy as np, rasterio, pandas as pd, geopandas as gpd
from rasterio.features import rasterize
from scipy.ndimage import uniform_filter
from affine import Affine
D = '/mnt/project-files/fuel-map/ratapani/work/'; O = '/mnt/project-files/fuel-map/ratapani/v3/'
S = np.load(D + 'static10.npz'); W, H = int(S['W']), int(S['H']); TR = Affine(*S['transform'])
forest = S['inside'] & np.isin(S['wc'], [10, 20, 30])
cover_eff = np.clip(uniform_filter(np.load(D + 'canopy_s2.npz')['s2'], 3) / 0.7, 0, 1); open_share = 1 - cover_eff
g = gpd.read_file('/mnt/project-files/ratapani/grid_500m.geojson').to_crs(32643)
g = g.merge(pd.read_csv('/mnt/project-files/ratapani/fsi/scouting/data/openbuildings_cell_features.csv')[['cell_id', 'd_ob']], on='cell_id')
dist = rasterize(zip(g.geometry, g.d_ob), (H, W), transform=TR, fill=np.nan, dtype='float32')
dist = np.where(np.isfinite(dist), dist, np.nanmedian(g.d_ob))
G = np.clip(np.interp(dist, [1000, 3000], [0.6, 1.8]), 0.5, 2.5)
with rasterio.open(O + 'burn_seasons_bitmask_10m.tif') as s: bits = s.read(1).astype('int64')
with rasterio.open(O + 'last_burn_day_10m.tif') as s: last = s.read(1).astype('int64')
def mult(day): return np.interp(day, [0, 106], [1.8, 1.0])
def save(path, a, desc):
    a = np.where(forest, np.round(a * 100), 65535).astype('uint16')
    with rasterio.open(path, 'w', driver='GTiff', width=W, height=H, count=1, dtype='uint16', crs='EPSG:32643', transform=TR, nodata=65535, compress='deflate') as d:
        d.write(a, 1); d.update_tags(units='t/ha x 100', note=desc + '; RELATIVE map, absolute values borrowed (+/-50%)')
rows = []
for tag, k in (('low', 0.6), ('central', 1.0), ('high', 1.4)):
    gr = np.clip(G * k, 0, 2.5) * open_share
    save(O + f'grass_potential_{tag}_10m.tif', gr, f'{tag}: grass from 15 Feb on if unburnt this season')
    rows.append(dict(map=f'grass_{tag}', mean=gr[forest].mean(), open_mean=gr[forest & (open_share >= 0.7)].mean()))
Y = 2026; fire_in = ((bits >> (Y - 2017)) & 1).astype(bool); s0 = (pd.Timestamp(f'{Y-1}-11-01') - pd.Timestamp('2016-11-01')).days
fday = np.where(fire_in, last - s0, 10 ** 6); gr = G * open_share
lit = rasterio.open(O + 'litter_2026_15apr_central_10m.tif').read(1).astype('float32'); lit = np.where(lit == 65535, 0, lit / 100)
g15 = np.where(fday <= 165, 0, gr * mult(165)); tot = lit + g15
save(O + 'grass_2026_15apr_central_10m.tif', g15, 'central: grass on 15apr 2026, zero where burnt earlier this season')
save(O + 'fuel_total_2026_15apr_central_10m.tif', tot, 'central: litter + grass on 15apr 2026')
pot = rasterio.open(O + 'litter_potential_central_10m.tif').read(1).astype('float32'); pot = np.where(pot == 65535, 0, pot / 100) + gr
save(O + 'fuel_total_potential_central_10m.tif', pot, 'central: end-April litter + grass if unburnt this season')
for nm, a in (('total_potential_central', pot), ('total_2026_15apr_central', tot)):
    rows.append(dict(map=nm, mean=a[forest].mean(), open_mean=a[forest & (open_share >= 0.7)].mean(), closed_mean=a[forest & (cover_eff >= 0.9)].mean(), p10=np.percentile(a[forest], 10), p50=np.percentile(a[forest], 50), p90=np.percentile(a[forest], 90)))
r = pd.DataFrame(rows); r.to_csv(O + 'grass_v3_summary.csv', index=False); print(r.round(2).to_string())
print('open share of forest >=0.7:', (open_share[forest] >= .7).mean().round(2), 'dist median', np.median(dist[forest]).round())
