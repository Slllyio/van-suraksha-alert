"""Per-cell mean class (1 least .. 5 extremely fire-prone) of FSI's 2021 fire-prone map (fuel-map/ratapani/fsi_fire_prone_2021_10m.tif)."""
import numpy as np, pandas as pd, rasterio, sys
sys.path.insert(0, '/mnt/project-files/research/reframe/scripts'); import data as D
r = rasterio.open('/mnt/project-files/fuel-map/ratapani/fsi_fire_prone_2021_10m.tif'); a = r.read(1); T = r.transform
print(r.crs, r.res, a.shape, np.unique(a, return_counts=True))
c = D.cells(); out = []
for x, y in zip(c.x, c.y):
    r0, c0 = rasterio.transform.rowcol(T, x - 250, y + 250)
    blk = a[max(r0, 0):max(r0 + 50, 0), max(c0, 0):max(c0 + 50, 0)]; blk = blk[(blk >= 1) & (blk <= 5)]
    out.append(blk.mean() if blk.size else np.nan)
c['fsi_prone'] = out; print(c.fsi_prone.describe())
c[['cell_id', 'fsi_prone']].to_csv('/mnt/project-files/research/reframe/results/cell_fsi_prone.csv', index=False)
