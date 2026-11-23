"""Rothermel-ready fuel layers from the fuel-load model (same terms as build_map.py), peak season Mar-Apr.
Units SI: loads kg/m2, depth m, SAV 1/m, moisture of extinction fraction. Mapped onto Scott & Burgan (2005) parameters:
  litter (teak/dry broadleaf leaves) ~ TL6/TL2 broadleaf litter: bulk density ~6 kg/m3, Mx 0.25, SAV 6562 1/m (2000 1/ft)
  cured grass ~ GR1/GR2: bulk density ~0.8 kg/m3, Mx 0.15, SAV 6562 1/m; fully cured by Mar-Apr except a small green share
Litter split: leaf 85% -> 1 h, twigs 15% -> 10 h (leaf is 79-91% of litterfall, Pande & Meshram 2002). No 100 h estimate (0)."""
import numpy as np, rasterio, os
from rasterio.transform import Affine
from scipy.ndimage import uniform_filter
D = '/tmp/claude-0/fuel/'; OUT = '/mnt/project-files/fuel-map/ratapani/rothermel/'; os.makedirs(OUT, exist_ok=True)
S = np.load(D + 'static10.npz'); N = np.load(D + 's2ndvi10.npz'); cover = np.load(D + 'canopy_s2.npz')['s2']
W, H = int(S['W']), int(S['H']); TR = Affine(*S['transform']); ins = S['inside']; wc = S['wc']; slope = S['slope']
forest = ins & np.isin(wc, [10, 20, 30])
on = N['leafon']; dry = N['dry'].copy(); v = np.isfinite(dry)
s_, n_ = uniform_filter(np.where(v, dry, 0), 15), uniform_filter(v.astype('float32'), 15)
dry = np.where(v, dry, np.where(n_ > .05, s_ / np.maximum(n_, 1e-6), np.nan))
cover_30 = uniform_filter(cover, 3); cover_eff = np.clip(cover_30 / 0.7, 0, 1)
SM = np.array([1.0, 0.95, 0.85, 0.75])[np.digitize(slope, [10, 20, 30])]
LF, CARRY, GMAX = 3.3, 0.28, 1.5
shed = np.clip((on - dry) / np.clip(on - 0.15, 0.05, None), 0, 1); shed = np.where(np.isfinite(shed), shed, 0.8)
vig = np.clip((np.nan_to_num(on, nan=0.4) - 0.2) / 0.5, 0, 1)
green = np.clip((np.nan_to_num(dry, nan=0.15) - 0.2) / 0.3, 0, 1) * (1 - cover_30)    # green share of the open ground in Mar-Apr
def burned(y):
    with rasterio.open(f'/mnt/project-files/research/ratapani-burn-labels/rasters/burn_{y}.tif') as s: b = s.read(1) > -999
    return np.repeat(np.repeat(b, 2, 0), 2, 1)[:H, :W]
def layers(last=None):
    carry = CARRY if last is None else np.where(last, 0, CARRY); gf = 1.0 if last is None else np.where(last, 0.7, 1.0)
    litter = LF * cover_eff * (shed + carry) * SM * 0.1          # t/ha -> kg/m2
    grass = GMAX * (1 - cover_30) * vig * gf * SM * 0.1
    herb = grass * np.clip(green, 0, 0.5); grass_dead = grass - herb
    w1 = 0.85 * litter + grass_dead; w10 = 0.15 * litter
    d_lit = litter / 6.0; d_gr = grass / 0.8
    tot = litter + grass
    depth = np.where(tot > 0, (litter * d_lit + grass * d_gr) / np.maximum(tot, 1e-6), 0)
    depth = np.clip(depth, 0.01, 0.6)
    mx = np.where(tot > 0, (litter * 0.25 + grass * 0.15) / np.maximum(tot, 1e-6), 0.25)
    gshare = grass / np.maximum(tot, 1e-6)
    # closest Scott-Burgan code: 91 NB, 101 GR1, 102 GR2, 181 TL1, 182 TL2, 186 TL6
    sb = np.where(tot < 0.03, 91, np.where(gshare > 0.5, np.where(grass < 0.1, 101, 102), np.where(litter < 0.15, 181, np.where(litter < 0.3, 182, 186))))
    out = dict(w_1h=w1, w_10h=w10, w_100h=np.zeros_like(w1), w_live_herb=herb, depth_m=depth, mx_dead=mx,
               sav_1h=np.full_like(w1, 6562.0), sb_model=sb.astype('float32'))
    for k in out: out[k] = np.where(forest, out[k], np.nan).astype('float32')
    out['sb_model'] = np.where(forest, out['sb_model'], 91)
    return out
NAMES = ['w_1h', 'w_10h', 'w_100h', 'w_live_herb', 'depth_m', 'mx_dead', 'sav_1h', 'sb_model']
def write(path, o, res):
    if res == 20:   # 2x2 mean onto the burn-scar 20 m grid (sb_model: majority via mode of 4 -> take top-left nearest)
        o = {k: (np.nanmean(o[k][:H // 2 * 2, :W // 2 * 2].reshape(H // 2, 2, W // 2, 2), (1, 3)) if k != 'sb_model' else o[k][:H // 2 * 2:2, :W // 2 * 2:2]) for k in o}
        tr = TR * Affine.scale(2)
    else: tr = TR
    h, w = o['w_1h'].shape
    with rasterio.open(path, 'w', driver='GTiff', width=w, height=h, count=len(NAMES), dtype='float32', crs='EPSG:32643', transform=tr,
                       nodata=np.nan, compress='deflate', predictor=3, tiled=True) as d:
        for i, k in enumerate(NAMES): d.write(o[k].astype('float32'), i + 1); d.set_band_description(i + 1, k)
        d.update_tags(units='w_*: kg/m2 oven-dry; depth_m: m; mx_dead: fraction; sav_1h: 1/m; sb_model: Scott-Burgan code (91 NB, 101 GR1, 102 GR2, 181 TL1, 182 TL2, 186 TL6)')
import warnings; warnings.filterwarnings('ignore')
o = layers(); write(OUT + 'rothermel_peak_10m.tif', o, 10); write(OUT + 'rothermel_peak_20m.tif', o, 20)
f = forest
print('peak: w1h mean', np.nanmean(o['w_1h'][f]).round(3), 'w10h', np.nanmean(o['w_10h'][f]).round(3), 'herb', np.nanmean(o['w_live_herb'][f]).round(3),
      'depth', np.nanmean(o['depth_m'][f]).round(3), 'mx', np.nanmean(o['mx_dead'][f]).round(3),
      'SB shares', {int(k): round(float(c), 3) for k, c in zip(*np.unique(o['sb_model'][f], return_counts=True)) for c in [c / f.sum()]})
for y in range(2018, 2027):
    o = layers(burned(y - 1)); write(OUT + f'rothermel_season_{y}_20m.tif', o, 20)
print('done')
