"""Litter v3: one-season leaf-fall budget (fuel review section 5, step 4). Relative map, absolute values borrowed.
litter(d) = LF_annual * RET * cover_eff * shed_rel * F(d) * burn_factor ; reset at monsoon (1 Nov) and at each fire this season:
  after a fire on day f: litter(d) = LF*RET*cover_eff*shed_rel*(F(d)-F(f))
  LF_annual (t/ha/yr, closed dry deciduous, Jhariya): low 4.75 / central 5.75 / high 7.6   [borrowed]
  RET = 0.5 (pre-monsoon floor ~ half of annual litterfall, Jhariya)                     [borrowed]
  cover_eff = canopy cover (S2, 30 m smooth) / 0.7, capped at 1                             [measured cover, assumed closed=0.7]
  shed_rel  = per-pixel leaf-shed amount (S2 NDVI leaf-on minus dry) / forest mean, 0.5-1.5   [measured, relative]
  F(d)      = per-pixel cumulative leaf-fall fraction by month end (S2 monthly, Dec-Apr)    [measured]
  burn_factor = Jhariya litterfall ratio vs burn frequency in PRIOR seasons (scar outlines v1)  [borrowed curve, measured history]
No slope multipliers. No grass (open ground gets ~0 here; grass is a separate layer, not done).
Truth for burn history = scar outlines v1 (2026-10-15), error bands per USE_AND_LIMITS.md (outlines lean small).
"""
import numpy as np, rasterio, pandas as pd
from scipy.ndimage import uniform_filter
from affine import Affine
D = '/mnt/project-files/fuel-map/ratapani/work/'; O = '/mnt/project-files/fuel-map/ratapani/v3/'
S = np.load(D + 'static10.npz'); N = np.load(D + 's2ndvi10.npz'); L = np.load(D + 'leaffall.npz')
W, H = int(S['W']), int(S['H']); TR = Affine(*S['transform'])
forest = S['inside'] & np.isin(S['wc'], [10, 20, 30])
cover = np.load(D + 'canopy_s2.npz')['s2']; cover_eff = np.clip(uniform_filter(cover, 3) / 0.7, 0, 1)
on, dry = N['leafon'], N['dry']
shed = np.clip((on - dry) / np.clip(on - 0.15, 0.05, None), 0, 1)
shed_rel = np.clip(np.where(np.isfinite(shed), shed / np.nanmean(shed[forest]), 1.0), 0.5, 1.5)
# cumulative leaf-fall fraction at month ends (days since 1 Nov): Dec31=60, Jan31=91, Feb28=119, Mar31=150, Apr30=180
MD = np.array([0, 60, 91, 119, 150, 180]); MF = [np.zeros((H, W), 'float32')] + [np.nan_to_num(L[k].astype('float32'), nan=1.0) for k in ('m12', 'm01', 'm02', 'm03', 'm04')]
MF = np.stack(MF); MF = np.maximum.accumulate(MF, 0)
def F(day):                                          # day: scalar or array (days since 1 Nov)
    day = np.clip(day, 0, 180); k = np.clip(np.searchsorted(MD, day, 'right') - 1, 0, 4)
    if np.isscalar(day):
        w = (day - MD[k]) / (MD[k + 1] - MD[k]); return MF[k] * (1 - w) + MF[k + 1] * w
    jj, ii = np.indices(day.shape); w = (day - MD[k]) / (MD[k + 1] - MD[k])
    return MF[k, jj, ii] * (1 - w) + MF[k + 1, jj, ii] * w
with rasterio.open(O + 'burn_seasons_bitmask_10m.tif') as s: bits = s.read(1).astype('int64')
with rasterio.open(O + 'last_burn_day_10m.tif') as s: last = s.read(1).astype('int64')
LF = dict(low=4.75, central=5.75, high=7.6); RET = 0.5
def burn_factor(Y):
    n = Y - 2017; burns = sum(((bits >> k) & 1) for k in range(n)).astype('float32')
    burns = uniform_filter(burns, 6)                 # 60 m: history is a stand property
    freq = (burns + 0.2 * 2) / (n + 2)               # shrink toward 1-in-5
    return np.interp(freq, [0, 0.2, 0.5, 1.0], [1.0, 0.88, 0.76, 0.63]).astype('float32')
def save(path, a, desc):
    a = np.where(forest, np.round(a * 100), 65535).astype('uint16')
    with rasterio.open(path, 'w', driver='GTiff', width=W, height=H, count=1, dtype='uint16', crs='EPSG:32643', transform=TR, nodata=65535, compress='deflate') as d:
        d.write(a, 1); d.update_tags(units='t/ha x 100', note=desc + '; RELATIVE map, absolute values borrowed (+/-50%)')
def save_ha(path, a):                               # 1 ha = 10x10 pixels mean over forest pixels
    h, w = H // 10, W // 10; m = forest[:h * 10, :w * 10].reshape(h, 10, w, 10); v = np.where(forest, a, 0)[:h * 10, :w * 10].reshape(h, 10, w, 10)
    n = m.sum((1, 3)); r = np.where(n >= 50, v.sum((1, 3)) / np.maximum(n, 1), np.nan)
    with rasterio.open(path, 'w', driver='GTiff', width=w, height=h, count=1, dtype='float32', crs='EPSG:32643', transform=TR * Affine.scale(10), nodata=np.nan, compress='deflate') as d:
        d.write(r.astype('float32'), 1); d.update_tags(units='t/ha', note='1 ha mean of forest pixels (>=50% forest); relative map')
Y = 2026; bf = burn_factor(Y); base = cover_eff * shed_rel * bf * RET
fire_in = ((bits >> (Y - 2017)) & 1).astype(bool); s0 = (pd.Timestamp(f'{Y-1}-11-01') - pd.Timestamp('2016-11-01')).days
fday = np.where(fire_in, last - s0, 10 ** 6)        # in-season fire day (days since 1 Nov)
rows = []
for tag, lf in LF.items():
    pot = lf * base * F(180.0)                       # end-April potential, no fire this season
    save(O + f'litter_potential_{tag}_10m.tif', pot, f'{tag}: end-April litter if unburnt this season ({Y})')
    if tag == 'central': save_ha(O + 'litter_potential_central_1ha.tif', pot)
    rows.append(dict(map=f'potential_{tag}', **{q: float(np.nanpercentile(pot[forest], p)) for q, p in (('p10', 10), ('p50', 50), ('p90', 90))}, mean=float(pot[forest].mean()),
                     closed_mean=float(pot[forest & (cover_eff >= 0.9)].mean())))
for name, day in (('15feb', 106), ('15mar', 134), ('15apr', 165), ('15may', 195)):
    st = 5.75 * base * np.where(fday <= day, F(np.full((H, W), float(day))) - F(np.minimum(fday, 180).astype('float32')), F(float(day)))
    st = np.clip(st, 0, None); save(O + f'litter_{Y}_{name}_central_10m.tif', st, f'central: litter on {name} {Y}, reset at fires so far this season')
    rows.append(dict(map=f'{Y}_{name}_central', p10=float(np.percentile(st[forest], 10)), p50=float(np.percentile(st[forest], 50)), p90=float(np.percentile(st[forest], 90)), mean=float(st[forest].mean()),
                     closed_mean=float(st[forest & (cover_eff >= 0.9)].mean()), burned_so_far=float((fday[forest] <= day).mean())))
r = pd.DataFrame(rows); r.to_csv(O + 'litter_v3_summary.csv', index=False); print(r.round(2).to_string())
print('forest px', forest.sum(), 'cover_eff>=0.9 share', (cover_eff[forest] >= .9).mean().round(2), 'median cover', np.median(cover[forest]).round(2))
