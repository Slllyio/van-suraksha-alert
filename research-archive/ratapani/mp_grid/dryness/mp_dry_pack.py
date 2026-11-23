"""Pack the all-MP dryness tiles into one file per season for the shared folder: push/mp_dry_{season}.npz with
cells (cell = row * 1829 + col, the cells with >= 50% beat cover, rasterised at 50 m as in the pipeline's mp_cells.parquet),
steps (YYYY-MM-DD), X (n_steps, n_cells, 4) int16: ndvi, ndmi, nbr x 10000, clear %; -9999 = no clear look.
Usage: python mp_dry_pack.py [seasons...]"""
import os, sys, json, glob, numpy as np, pandas as pd, rasterio.features as rf
from rasterio.transform import from_origin
from shapely.geometry import shape
from shapely.ops import transform as stx
from pyproj import Transformer
HERE = r'E:\FIRE\mp'; X0, Y1, W, H, S, T, F = 399000.0, 2996000.0, 1829, 1332, 500.0, 128, 10
mf = HERE + r'\mp_cells_mask.npy'
if not os.path.exists(mf):
    g = json.load(open(r'E:\FIRE\data\aoi\mp_beats_wgs84.geojson'))['features']
    t = Transformer.from_crs(4326, 32643, always_xy=True).transform
    fine = rf.rasterize(((stx(t, shape(f['geometry'])), 1) for f in g), out_shape=(H * F, W * F), transform=from_origin(X0, Y1, S / F, S / F), fill=0, dtype='uint8')
    np.save(mf, fine.reshape(H, F, W, F).sum((1, 3)) >= F * F // 2)
mask = np.load(mf); rr, cc = np.nonzero(mask); cells = (rr * W + cc).astype(np.int32); print('cells', len(cells), flush=True)
os.makedirs(HERE + r'\push', exist_ok=True)
for Y in [int(v) for v in sys.argv[1:]] or range(2017, 2027):
    steps = pd.date_range(f'{Y}-01-02', f'{Y}-06-21', freq='10D'); X = np.full((len(steps), len(cells), 4), -9999, np.int16); miss = 0
    for k, d in enumerate(steps):
        full = np.full((4, (H // T + 1) * T, (W // T + 1) * T), -9999, np.int16)
        for f in glob.glob(HERE + rf"\tiles\{d.strftime('%Y_%m%d')}_*.npy"):
            tr, tc = int(f[-9:-7]), int(f[-6:-4]); full[:, tr * T:(tr + 1) * T, tc * T:(tc + 1) * T] = np.load(f)
        X[k] = full[:, rr, cc].T; miss += int((X[k, :, 0] == -9999).sum())
    np.savez_compressed(HERE + rf'\push\mp_dry_{Y}.npz', cells=cells, steps=np.array([str(d.date()) for d in steps]), X=X)
    print(Y, 'missing share', round(miss / X[:, :, 0].size, 3), os.path.getsize(HERE + rf'\push\mp_dry_{Y}.npz') // 1e6, 'MB', flush=True)
print('PACK_DONE')
