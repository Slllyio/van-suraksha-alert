"""Shared ground features (rasters, 500 m cell data, ERA5-Land weather, sector sampling). Extracted from b9_ml_table.py so
b14 can reuse the exact same definitions."""
import json, numpy as np, pandas as pd, rasterio
from scipy.spatial import cKDTree
ROOT = '/mnt/project-files'
# ---- rasters
G = np.load(f'{ROOT}/ratapani/spread/data_shared/grid20.npz'); TR20 = G['transform']
def s20(arr, x, y):
    c = ((np.asarray(x) - TR20[2]) / TR20[0]).astype(int); r = ((np.asarray(y) - TR20[5]) / TR20[4]).astype(int)
    ok = (r >= 0) & (r < arr.shape[0]) & (c >= 0) & (c < arr.shape[1]); o = np.full(len(c), np.nan, np.float32); o[ok] = arr[r[ok], c[ok]]; return o
ELEV, SLOPE, UPAZ, WC = G['elev'].astype(np.float32), G['slope'].astype(np.float32), G['upslope_az'].astype(np.float32), G['wc']
BURN = {y: G[f'burn_start_{y}'] for y in range(2017, 2027)}
R10 = {}
for name, f in [('canopy', 'canopy_cover_10m.tif'), ('teak', 'teak_probability_10m.tif'), ('litter_v3', 'v3/litter_potential_central_10m.tif'),
                ('grass_v3', 'v3/grass_potential_central_10m.tif'), ('fuel_total_v3', 'v3/fuel_total_potential_central_10m.tif'),
                ('burn_count', 'v3/burn_count_10m.tif')]:
    with rasterio.open(f'{ROOT}/fuel-map/ratapani/{f}') as r:
        a = r.read(1).astype(np.float32)
        if r.nodata is not None: a[a == r.nodata] = np.nan
        a *= {'canopy': 0.1, 'litter_v3': 0.01, 'grass_v3': 0.01, 'fuel_total_v3': 0.01}.get(name, 1.0)   # canopy %, fuel t/ha
        R10[name] = (a, r.transform)
def s10(name, x, y):
    a, tr = R10[name]; c = ((np.asarray(x) - tr[2]) / tr[0]).astype(int); r = ((np.asarray(y) - tr[5]) / tr[4]).astype(int)
    ok = (r >= 0) & (r < a.shape[0]) & (c >= 0) & (c < a.shape[1]); o = np.full(len(c), np.nan, np.float32); o[ok] = a[r[ok], c[ok]]; return o
grid = json.load(open(f'{ROOT}/ratapani/grid_500m.geojson'))
gc = pd.DataFrame([dict(cell_id=g['properties']['cell_id'], x=g['properties']['x0'] + 250, y=g['properties']['y0'] + 250) for g in grid['features']])
gc = gc.merge(pd.read_csv(f'{ROOT}/ratapani/fsi/scouting/data/openbuildings_cell_features.csv')[['cell_id', 'd_ob', 'nham4']], on='cell_id', how='left') \
       .merge(pd.read_csv(f'{ROOT}/ratapani/ee/proximity.csv'), on='cell_id', how='left')
gtree = cKDTree(gc[['x', 'y']].values)
def cell(x, y, col):
    d, i = gtree.query(np.c_[np.atleast_1d(x), np.atleast_1d(y)]); v = gc[col].values[i].astype(float); v[d > 400] = np.nan; return v
E5 = pd.read_csv(f'{ROOT}/ratapani/ee/era5land_daily.csv', parse_dates=['time']).set_index('time')
E5['rh'] = 100 * np.exp(17.625 * (E5.dewpoint_temperature_2m - 273.15) / (E5.dewpoint_temperature_2m - 30.11)) / \
           np.exp(17.625 * (E5.temperature_2m - 273.15) / (E5.temperature_2m - 30.11))
E5['rain7'] = E5.total_precipitation_sum.rolling(7).sum() * 1000; E5['rain30'] = E5.total_precipitation_sum.rolling(30).sum() * 1000
def wx(t):
    d = pd.Timestamp(t).normalize()
    if d not in E5.index: return {}
    e = E5.loc[d]; u, v = e.u_component_of_wind_10m, e.v_component_of_wind_10m
    return dict(wx_tmax_c=e.temperature_2m_max - 273.15, wx_tmean_c=e.temperature_2m - 273.15, wx_rh=e.rh, wx_wind_ms=np.hypot(u, v),
                wx_wind_to_deg=np.degrees(np.arctan2(u, v)) % 360, wx_soil_water=e.volumetric_soil_water_layer_1, wx_rain7_mm=e.rain7, wx_rain30_mm=e.rain30)

def comp(dx, dy): return np.degrees(np.arctan2(dx, dy)) % 360
def ang(a, b): return np.cos(np.radians(a - b))

def ring_pts(cx, cy, bearing, r0=300, r1=1500, half=22.5):
    rr = np.linspace(r0, r1, 6); aa = np.radians(bearing + np.linspace(-half, half, 5))
    R_, A_ = np.meshgrid(rr, aa); return cx + R_.ravel() * np.sin(A_.ravel()), cy + R_.ravel() * np.cos(A_.ravel())

def sector_feats(cx, cy, b, year, doy, burned_pts):
    x, y = ring_pts(cx, cy, b)
    e0 = s20(ELEV, [cx], [cy])[0]
    bs = s20(BURN[year].astype(np.float32), x, y) if year in BURN else np.full(len(x), np.nan)
    f = dict(elev_diff=np.nanmean(s20(ELEV, x, y)) - e0, slope=np.nanmean(s20(SLOPE, x, y)),
             canopy=np.nanmean(s10('canopy', x, y)), teak=np.nanmean(s10('teak', x, y)), litter_v3=np.nanmean(s10('litter_v3', x, y)),
             grass_v3=np.nanmean(s10('grass_v3', x, y)), fuel_total_v3=np.nanmean(s10('fuel_total_v3', x, y)),
             burn_count=np.nanmean(s10('burn_count', x, y)),
             burn_prior=np.nanmean(np.sum([s20((BURN[y_] > 0).astype(np.float32), x, y) for y_ in range(2017, year)], axis=0)) if year > 2017 else 0.0, wc_tree=np.nanmean(s20(WC, x, y) == 10), wc_open=np.nanmean(np.isin(s20(WC, x, y), [20, 30])),
             wc_nonfuel=np.nanmean(np.isin(s20(WC, x, y), [40, 50, 60, 80])),
             burned_this_season_before=np.nanmean((bs > 0) & (bs < doy - 1)),
             own_fire_already=np.mean(cKDTree(burned_pts).query(np.c_[x, y])[0] < 400) if len(burned_pts) else 0.0,
             d_building=np.nanmean(cell(x, y, 'd_ob')), d_road=np.nanmean(cell(x, y, 'dist_road')))
    return f

