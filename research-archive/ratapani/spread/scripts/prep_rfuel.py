"""Fuel thread's Rothermel-ready 20 m layers -> padded model grid (w1, w10, depth, mx) per season."""
import numpy as np, rasterio
import sys
FM = sys.argv[1] if len(sys.argv) > 1 else '/mnt/project-files/fuel-map/ratapani/rothermel'
OUT = sys.argv[2] if len(sys.argv) > 2 else '/tmp/claude-0/spread/data/rfuel20.npz'
G = np.load('/tmp/claude-0/spread/data/grid20.npz'); H, W = G['shape']; PAD = 100
out = {}
for s in range(2017, 2025):
    p = f'{FM}/rothermel_season_{s}_20m.tif' if s >= 2018 else f'{FM}/rothermel_peak_20m.tif'
    with rasterio.open(p) as r:
        a = r.read([1, 2, 5, 6]); assert r.bounds.left == 739300
    g = np.full((4, H, W), np.nan, np.float32); g[:, PAD:PAD + a.shape[1], PAD:PAD + a.shape[2]] = a
    out[f'rf_{s}'] = g
    print(s, [float(np.nanmean(x)) for x in g])
np.savez_compressed(OUT, **out)
