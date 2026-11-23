"""Variant: same loads as v2, looser litter bed for the spread thread. Fuel map v2 (14 Oct, after full read of Jhariya 2017, Saha 2002, Mondal & Sukumar 2016, Thakur 2022).
Per 10 m pixel, peak (April) floor fuel for season Y:
  floor  = 0.5 * LF_closed * cover_eff * shed_rel * freq_factor * slope_mult       (Jhariya: pre-monsoon floor ~0.5 x annual litterfall)
  grass  = grass_tsf(years since last burn) * (1 - cover30) * vigour * slope_mult  (Mondal & Sukumar MR3: 0.6 t/ha 1st yr, +0.9/yr, cap 2.5)
  freq_factor from burn frequency: 1.0 never, 0.88 ~1 in 5 yr, 0.76 every 2nd yr, 0.63 every yr (Jhariya Table 2 litterfall ratios)
  No litter carry-over across the monsoon (Saha 2002; Jhariya K~0.7 already inside the 0.5 ratio).
Monthly build-up (Saha 2002): Jan 0.5 [inference], Feb 0.70, Mar 0.88, Apr 1.0, May 1.0 of the April value.
Outputs (FUEL_OUT): fuel_continuous_peak_10m.tif (all-years burn frequency; descriptive only), fuel_season_<Y>_peak_10m.tif
(prior seasons only, usable as a model input), rothermel/ layers, cell aggregates."""
import numpy as np, rasterio, json, os, warnings
from rasterio.transform import Affine
from scipy.ndimage import uniform_filter
warnings.filterwarnings('ignore')
D = '/tmp/claude-0/fuel/'; OUT = '/mnt/project-files/fuel-map/ratapani/'; RO = OUT + 'rothermel/loosebed/'; os.makedirs(RO, exist_ok=True)
S = np.load(D + 'static10.npz'); N = np.load(D + 's2ndvi10.npz'); cover = np.load(D + 'canopy_s2.npz')['s2']
W, H = int(S['W']), int(S['H']); TR = Affine(*S['transform']); ins = S['inside']; wc = S['wc']; slope = S['slope']
forest = ins & np.isin(wc, [10, 20, 30])
on = N['leafon']; dry = N['dry'].copy(); v = np.isfinite(dry)
s_, n_ = uniform_filter(np.where(v, dry, 0), 15), uniform_filter(v.astype('float32'), 15)
dry = np.where(v, dry, np.where(n_ > .05, s_ / np.maximum(n_, 1e-6), np.nan))
cover_30 = uniform_filter(cover, 3); cover_ha = uniform_filter(cover, 10); cover_eff = np.clip(cover_30 / 0.7, 0, 1)
SM = np.array([1.0, 0.95, 0.85, 0.75])[np.digitize(slope, [10, 20, 30])]
shed = np.clip((on - dry) / np.clip(on - 0.15, 0.05, None), 0, 1)
m = np.nanmean(shed[forest]); shed_rel = np.clip(np.where(np.isfinite(shed), shed / m, 1.0), 0.5, 1.5)
vig = np.clip((np.nan_to_num(on, nan=0.4) - 0.2) / 0.5, 0, 1)
green = np.clip((np.nan_to_num(dry, nan=0.15) - 0.2) / 0.3, 0, 1)
LF_CLOSED = 5.0      # t/ha/yr leaf+wood litterfall, closed unburnt dry deciduous at ~1100-1200 mm (Bhoramdeo 7.6 @ wetter site; AABR 4.2; Satpura teak 3.3-4.5 leaf only)
YEARS = list(range(2017, 2027))
B = {}
for y in YEARS:
    with rasterio.open(f'/mnt/project-files/research/ratapani-burn-labels/rasters/burn_{y}.tif') as s: b = (s.read(1) > -999).astype('float32')
    b = uniform_filter(b, 3)                                     # 60 m: fire history is a stand property, not a pixel one
    B[y] = np.repeat(np.repeat(b, 2, 0), 2, 1)[:H, :W]
def freq_factor(freq):
    return np.interp(freq, [0, 0.2, 0.5, 1.0], [1.0, 0.88, 0.76, 0.63])
def grass_tsf(tsf):                                              # t/ha cured grass by years since last burn (MR3, Mudumalai)
    return np.minimum(0.6 + 0.9 * (tsf - 1), 2.5)
def model(prior):
    n = len(prior)
    burns = sum(B[y] for y in prior) if n else np.zeros((H, W), 'float32')
    freq = (burns + 0.2 * 2) / (n + 2)                           # shrink toward 1-in-5 with 2 pseudo-seasons
    tsf = np.full((H, W), 5.0, 'float32')                        # unburnt in record -> treat as >=5 yr (cap reached)
    for k, y in enumerate(sorted(prior)): tsf = np.where(B[y] > 0.5, n - k, tsf)
    floor = 0.5 * LF_CLOSED * cover_eff * shed_rel * freq_factor(freq) * SM
    grass = grass_tsf(tsf) * (1 - cover_30) * vig * SM
    return floor, grass, freq, tsf
GFT = 9.29
def save(path, arr, scale=10, tags=None):
    q = np.where(forest & np.isfinite(arr), np.round(arr * scale), 65535).astype('uint16')
    with rasterio.open(path, 'w', driver='GTiff', width=W, height=H, count=1, dtype='uint16', crs='EPSG:32643', transform=TR, nodata=65535,
                       compress='deflate', predictor=2, tiled=True) as d:
        d.write(q, 1); d.update_tags(scale_factor=str(1 / scale), **(tags or {}))
NAMES = ['w_1h', 'w_10h', 'w_100h', 'w_live_herb', 'depth_m', 'mx_dead', 'sav_1h', 'sb_model']
def roth(floor, grass):
    fl, gr = floor * 0.1, grass * 0.1                            # kg/m2
    herb = gr * np.clip(green, 0, 0.5); gdead = gr - herb
    w1 = 0.75 * fl + gdead; w10 = 0.25 * fl                      # Jhariya summer floor: fresh + partly decayed leaf ~70-75%, wood ~25-30%
    d_l, d_g = fl / 2.5, gr / 0.8                                 # loose teak bed: 2.5 kg/m3 (large curled leaves; packing ratio near Rothermel optimum) [assumption]
    tot = fl + gr
    depth = np.clip(np.where(tot > 0, (fl * d_l + gr * d_g) / np.maximum(tot, 1e-6), 0), 0.01, 0.6)
    mx = np.where(tot > 0, (fl * 0.25 + gr * 0.15) / np.maximum(tot, 1e-6), 0.25)
    gs = gr / np.maximum(tot, 1e-6)
    sb = np.where(tot < 0.03, 91, np.where(gs > 0.5, np.where(gr < 0.1, 101, 102), 186))
    o = dict(w_1h=w1, w_10h=w10, w_100h=np.zeros_like(w1), w_live_herb=herb, depth_m=depth, mx_dead=mx, sav_1h=np.full_like(w1, 6562.0), sb_model=sb.astype('float32'))
    for k in o: o[k] = np.where(forest, o[k], np.nan if k != 'sb_model' else 91).astype('float32')
    return o
def write_roth(path, o, res):
    if res == 20:
        o = {k: (np.nanmean(o[k][:H // 2 * 2, :W // 2 * 2].reshape(H // 2, 2, W // 2, 2), (1, 3)) if k != 'sb_model' else o[k][:H // 2 * 2:2, :W // 2 * 2:2]) for k in o}
        tr = TR * Affine.scale(2)
    else: tr = TR
    h, w = o['w_1h'].shape
    with rasterio.open(path, 'w', driver='GTiff', width=w, height=h, count=8, dtype='float32', crs='EPSG:32643', transform=tr, nodata=np.nan,
                       compress='deflate', predictor=3, tiled=True) as d:
        for i, k in enumerate(NAMES): d.write(o[k].astype('float32'), i + 1); d.set_band_description(i + 1, k)
        d.update_tags(units='w_*: kg/m2 oven-dry at April peak; depth_m: m; mx_dead: fraction; sav_1h: 1/m; sb_model: Scott-Burgan code (91 NB, 101 GR1, 102 GR2, 181 TL1, 182 TL2, 186 TL6)',
                      month_factor='multiply loads (and depth) by Jan 0.5, Feb 0.70, Mar 0.88, Apr 1.0, May 1.0', version='v2-loosebed 2026-10-14 (litter bulk density 2.5 kg/m3, litter coded TL6)')
fl, gr, _, _ = model(YEARS); o = roth(fl, gr); write_roth(RO + 'rothermel_peak_20m.tif', o, 20)
for y in range(2018, 2027):
    fl, gr, _, _ = model([p for p in YEARS if p < y]); write_roth(RO + f'rothermel_season_{y}_20m.tif', roth(fl, gr), 20)
print('depth mean', float(np.nanmean(o['depth_m'][forest])))
