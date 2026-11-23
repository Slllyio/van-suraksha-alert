"""Fuel map v3 (fuel-map/ratapani/v3/litter_v3.py) brought to the 500 m grid, per season and day, using only what is
known before the season: litter(t) = 5.75 t/ha * 0.5 * cover_eff * shed_rel * burn_factor(prior seasons only) * F(t),
F = per-pixel cumulative leaf-fall fraction (S2 monthly). No in-season fire resets (a live system would only know
confirmed scars; the v2 scorer already drops confirmed-burned squares). Mean over forest pixels of each 500 m cell.
Out: v2/fuel_cells.parquet (season, date, cell_id, fuel_litter, fuel_potential, fuel_leaffall, fuel_forest_px)"""
import json, numpy as np, pandas as pd, rasterio
from scipy.ndimage import uniform_filter
P = '/mnt/project-files/'; D = P + 'fuel-map/ratapani/work/'; V3 = P + 'fuel-map/ratapani/v3/'; OUT = P + 'ratapani/scoring/v2/'
S = np.load(D + 'static10.npz'); N = np.load(D + 's2ndvi10.npz'); L = np.load(D + 'leaffall.npz')
W, H = int(S['W']), int(S['H']); t = S['transform']
forest = S['inside'] & np.isin(S['wc'], [10, 20, 30])
cover = np.load(D + 'canopy_s2.npz')['s2']; cover_eff = np.clip(uniform_filter(cover, 3) / 0.7, 0, 1)
on, dry = N['leafon'], N['dry']
shed = np.clip((on - dry) / np.clip(on - 0.15, 0.05, None), 0, 1)
shed_rel = np.clip(np.where(np.isfinite(shed), shed / np.nanmean(shed[forest]), 1.0), 0.5, 1.5)
MD = np.array([0, 60, 91, 119, 150, 180])
MF = np.maximum.accumulate(np.stack([np.zeros((H, W), 'float32')] + [np.nan_to_num(L[k].astype('float32'), nan=1.0) for k in ('m12', 'm01', 'm02', 'm03', 'm04')]), 0)
with rasterio.open(V3 + 'burn_seasons_bitmask_10m.tif') as s: bits = s.read(1).astype('int64')
def burn_factor(Y):
    n = Y - 2017; burns = sum(((bits >> k) & 1) for k in range(n)).astype('float32') if n > 0 else np.zeros((H, W), 'float32')
    burns = uniform_filter(burns, 6); freq = (burns + 0.4) / (n + 2)
    return np.interp(freq, [0, 0.2, 0.5, 1.0], [1.0, 0.88, 0.76, 0.63]).astype('float32')
# pixel -> 500 m cell
G = json.load(open(P + 'ratapani/grid_500m.geojson'))['features']
key = {(int(f['properties']['x0']), int(f['properties']['y0'])): f['properties']['cell_id'] for f in G}
xs = t[2] + t[0] * (np.arange(W) + 0.5); ys = t[5] + t[4] * (np.arange(H) + 0.5)
cx = (np.floor(xs / 500) * 500).astype(int); cy = (np.floor(ys / 500) * 500).astype(int)
cell = np.full((H, W), -1, int)
for j in range(H):
    cell[j] = [key.get((x, cy[j]), -1) for x in cx]
m = forest & (cell >= 0); ci = cell[m]; n = 3614
cnt = np.bincount(ci, minlength=n).astype(float)
def cmean(a): return np.bincount(ci, weights=a[m], minlength=n) / np.maximum(cnt, 1)
base0 = 5.75 * 0.5 * cover_eff * shed_rel
rows = []
for Y in range(2017, 2027):
    base = base0 * burn_factor(Y)
    knots = np.stack([cmean(base * MF[k]) for k in range(6)])        # litter at each knot, per cell
    ff = np.stack([cmean(MF[k]) for k in range(6)])
    days = pd.date_range(f'{Y}-02-01', f'{Y}-06-20'); dn = np.clip((days - pd.Timestamp(f'{Y - 1}-11-01')).days.values - 1, 0, 180)   # known by t-1
    lit = np.stack([np.interp(dn, MD, knots[:, c]) for c in range(n)], 1); lf = np.stack([np.interp(dn, MD, ff[:, c]) for c in range(n)], 1)
    T = len(days); tt, cc = np.meshgrid(np.arange(T), np.arange(n), indexing='ij')
    df = pd.DataFrame({'season': Y, 'date': days[tt.reshape(-1)], 'cell_id': cc.reshape(-1), 'fuel_litter': lit.reshape(-1).astype('float32'),
                       'fuel_potential': np.repeat(knots[-1][None], T, 0).reshape(-1).astype('float32'), 'fuel_leaffall': lf.reshape(-1).astype('float32')})
    df.loc[np.repeat((cnt == 0)[None], T, 0).reshape(-1), ['fuel_litter', 'fuel_potential', 'fuel_leaffall']] = np.nan
    rows.append(df); print(Y, round(float(np.nanmean(knots[-1][cnt > 0])), 2), flush=True)
out = pd.concat(rows, ignore_index=True); out['fuel_forest_px'] = np.tile(cnt, len(out) // n).astype('float32')
out.to_parquet(OUT + 'fuel_cells.parquet', index=False); print('cells with forest', int((cnt > 0).sum()), 'FUEL_DONE')
