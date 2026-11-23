"""Meta/WRI 1 m canopy height -> 10 m canopy cover (share of 1 m pixels >= 5 m tall) and mean / p90 height."""
import numpy as np, rasterio
from rasterio.warp import reproject, transform_bounds
from rasterio.enums import Resampling
from rasterio.transform import Affine
S = np.load('/tmp/claude-0/fuel/static10.npz'); W, H = int(S['W']), int(S['H']); TR = Affine(*S['transform'])
CRS = 'EPSG:32643'; K = 8
bnd = transform_bounds(CRS, 'EPSG:3857', TR.c, TR.f - H * 10, TR.c + W * 10, TR.f)
cov = np.full((H, W), np.nan, "float32"); hgt = cov.copy(); cov3 = cov.copy()
for t in ['123123321', '123123330', '123123331']:
    with rasterio.open(f'/tmp/claude-0/chm/{t}.tif') as s:
        win = rasterio.windows.from_bounds(*bnd, transform=s.transform).round_offsets().round_lengths()
        win = win.intersection(rasterio.windows.Window(0, 0, s.width, s.height))
        r0, c0, nr, nc = int(win.row_off), int(win.col_off), int(win.height) // K * K, int(win.width) // K * K
        C = np.zeros((nr // K, nc // K), "float32"); Hm = C.copy(); C3 = C.copy()
        for r in range(0, nr, 1024):
            d = s.read(1, window=rasterio.windows.Window(c0, r0 + r, nc, min(1024, nr - r))).astype('float32')
            b = d.reshape(d.shape[0] // K, K, nc // K, K)
            C[r // K: r // K + b.shape[0]] = (b >= 5).mean((1, 3)); C3[r // K: r // K + b.shape[0]] = (b >= 3).mean((1, 3)); Hm[r // K: r // K + b.shape[0]] = b.mean((1, 3))
        st = s.transform * Affine.translation(c0, r0) * Affine.scale(K)
        for src, dst in ((C, cov), (Hm, hgt), (C3, cov3)):
            o = np.full((H, W), np.nan, 'float32')
            reproject(src, o, src_transform=st, src_crs=s.crs, dst_transform=TR, dst_crs=CRS, resampling=Resampling.average, dst_nodata=np.nan)
            m = np.isnan(dst) & ~np.isnan(o); dst[m] = o[m]
        print(t, C.shape, flush=True)
ins = S['inside']
np.savez_compressed('/tmp/claude-0/fuel/chm10.npz', cover=cov, height=hgt, cover3=cov3)
print('nan inside', np.isnan(cov[ins]).mean(), 'cover classes (scrub<10, OF 10-40, MDF 40-70, VDF>=70):', np.histogram(cov[ins] * 100, [-1, 10, 40, 70, 101])[0] / ins.sum(), 'mean height', np.nanmean(hgt[ins]))
