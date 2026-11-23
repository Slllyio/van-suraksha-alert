"""All-MP 500 m grid in EPSG:32643, aligned with the Ratapani grid (corners on multiples of 500 m).
Each cell gets the beat whose polygon covers the largest share of it (rasterised at 50 m). Output: mp_grid/mp_cells.parquet
(cell = row * W + col, row, col, x0, y0, beat_uid, beat_frac) for cells with >= 50% beat cover, and the 128-cell tile list."""
import json, numpy as np, pandas as pd, rasterio.features as rf
from rasterio.transform import from_origin
from pyproj import Transformer
from shapely.geometry import shape
from shapely.ops import transform as stx
X0, Y1, W, H, S = 399000.0, 2996000.0, 1829, 1332, 500.0
F = 10   # 50 m sub-pixels
g = json.load(open('/mnt/project-files/ratapani/beats/mp_beats.geojson'))['features']
t = Transformer.from_crs(4326, 32643, always_xy=True).transform
uids = [f['properties']['beat_uid'] for f in g]
shp = ((stx(t, shape(f['geometry'])), i + 1) for i, f in enumerate(g))
fine = rf.rasterize(shp, out_shape=(H * F, W * F), transform=from_origin(X0, Y1, S / F, S / F), fill=0, dtype='int32')
print('rasterised', flush=True)
blk = fine.reshape(H, F, W, F).transpose(0, 2, 1, 3).reshape(H, W, F * F)
rows = []
for r in range(H):
    b = blk[r]; nz = (b > 0).sum(1); cols = np.nonzero(nz >= F * F // 2)[0]
    for c in cols:
        v, n = np.unique(b[c][b[c] > 0], return_counts=True); k = n.argmax()
        rows.append((r * W + c, r, c, X0 + c * S, Y1 - (r + 1) * S, uids[v[k] - 1], n[k] / (F * F)))
df = pd.DataFrame(rows, columns=['cell', 'row', 'col', 'x0', 'y0', 'beat_uid', 'beat_frac'])
df.to_parquet('/mnt/project-files/ratapani/mp_grid/mp_cells.parquet')
T = 128; tiles = sorted({(r // T, c // T) for r, c in zip(df.row, df.col)})
json.dump({'X0': X0, 'Y1': Y1, 'W': W, 'H': H, 'S': S, 'T': T, 'tiles': tiles}, open('/mnt/project-files/ratapani/mp_grid/mp_grid.json', 'w'))
print('cells', len(df), 'beats', df.beat_uid.nunique(), 'tiles', len(tiles), 'of', -(-H // T) * -(-W // T))
# check against Ratapani cells
rc = pd.read_csv('/mnt/project-files/ratapani/beats/cell_beat.csv'); print(rc.head(2).to_dict())
