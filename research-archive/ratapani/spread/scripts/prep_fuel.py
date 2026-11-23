"""Fuel-map thread's 10 m surface fuel load (g/ft2) -> 20 m model grid, per season (2017 uses the static map)."""
import numpy as np, rasterio
FM = '/mnt/project-files/fuel-map/ratapani'
G = np.load('/tmp/claude-0/spread/data/grid20.npz'); H, W = G['shape']; PAD = 100
out = {}
for s in range(2017, 2025):
    p = f'{FM}/fuel_season_{s}_peak_10m.tif' if s >= 2018 else f'{FM}/fuel_continuous_peak_10m.tif'
    with rasterio.open(p) as r:
        a = r.read(1).astype(np.float32); assert r.bounds.left == 739300 and r.bounds.top == 2558500, r.bounds
    a[a == 65535] = np.nan; a *= 0.1
    a20 = np.nanmean(a.reshape(a.shape[0] // 2, 2, a.shape[1] // 2, 2), axis=(1, 3))
    g = np.full((H, W), np.nan, np.float32); g[PAD:PAD + a20.shape[0], PAD:PAD + a20.shape[1]] = a20
    out[f'load_{s}'] = g
    print(s, np.nanpercentile(g, [5, 50, 95]), np.isfinite(g).mean())
np.savez_compressed('/tmp/claude-0/spread/data/fuel20.npz', **out)
