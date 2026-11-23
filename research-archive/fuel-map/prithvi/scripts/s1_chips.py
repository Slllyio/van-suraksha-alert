"""Training chips for 'what burns around the first alert' (frozen Prithvi + trained head).
One chip per fire first seen on/after 15 Feb: 104 x 104 px at 30 m (3.1 km) on the HLS grid, aligned to the 240 m token grid,
centred on the first-pass dots. Channels: raw HLS 4 frames x 6 bands (30 m), canopy (30 m mean of 10 m), distance to nearest
first-pass dot, dot mask; Prithvi tokens 15 x 15 nodes (frame-mean last layer 1024 + Feb-minus-Nov 1024), float16.
Target: final scar (outlines v2) rasterised at 30 m.  Out: scratch chips.npz"""
import json, numpy as np, pandas as pd, rasterio, pyproj
from rasterio.features import rasterize
from rasterio.warp import reproject, Resampling
from shapely.geometry import shape
from shapely.ops import transform, unary_union
from scipy.ndimage import distance_transform_edt
import common as C
H, W, S, X0, Y1 = 1120, 2500, 30.0, 739500.0, 2558520.0; N = 104
to_utm = pyproj.Transformer.from_crs(4326, 32643, always_xy=True).transform
ev = {f['properties']['event_id']: transform(to_utm, shape(f['geometry'])).buffer(0) for f in json.load(open('/mnt/project-files/fire-alert-scars/reference/v2_2026-10-16/firms_event_scars.geojson'))['features']}
F = pd.read_csv('/mnt/project-files/research/big-fires/results/fires.csv')
G = pd.read_parquet(f'{C.SP}/fires.parquet'); G = G[G.doy >= 46].merge(F[['fire', 'events']], on='fire'); D = pd.read_parquet(f'{C.SP}/dots.parquet')
can_src = rasterio.open('/mnt/project-files/fuel-map/ratapani/canopy_cover_10m.tif'); CAN = can_src.read(1).astype(np.float32); CAN[CAN == 65535] = np.nan
raw_, tok_, aux_, y_, meta = [], [], [], [], []
for Y, gs in G.groupby('season'):
    hls = np.stack([np.load(f'{C.SP}/hls/{Y}_F{k}.npy') for k in (1, 2, 3, 4)]).reshape(24, H, W)
    z = np.load(f'{C.SP}/emb/{Y}.npz'); L = z['last']; Tm = L.astype(np.float32).mean(0).astype(np.float16); Td = (L[3].astype(np.float32) - L[1].astype(np.float32)).astype(np.float16); del L
    for g in gs.itertuples():
        d = D[D.fire == g.fire][['x', 'y']].values; cx, cy = d.mean(0)
        r0 = int(round((Y1 - cy) / S)) - N // 2; c0 = int(round((cx - X0) / S)) - N // 2; r0 -= r0 % 8; c0 -= c0 % 8
        m0, n0 = r0 // 8 - 1, c0 // 8 - 1
        if r0 < 0 or c0 < 0 or r0 + N > H or c0 + N > W or m0 < 0 or n0 < 0 or m0 + 15 > Tm.shape[0] or n0 + 15 > Tm.shape[1]: continue
        tr = rasterio.transform.from_origin(X0 + c0 * S, Y1 - r0 * S, S, S)
        scar = unary_union([ev[e] for e in g.events.split(';') if e in ev])
        y = rasterize([scar], out_shape=(N, N), transform=tr, fill=0, all_touched=False).astype(np.uint8)
        can = np.full((N, N), np.nan, np.float32); reproject(CAN, can, src_transform=can_src.transform, src_crs=can_src.crs, dst_transform=tr, dst_crs=can_src.crs, resampling=Resampling.average, src_nodata=np.nan, dst_nodata=np.nan)
        dm = np.zeros((N, N), bool); rr = ((Y1 - d[:, 1]) / S - r0).astype(int); cc = ((d[:, 0] - X0) / S - c0).astype(int); ok = (rr >= 0) & (rr < N) & (cc >= 0) & (cc < N); dm[rr[ok], cc[ok]] = True
        dist = distance_transform_edt(~dm) * S
        raw_.append(hls[:, r0:r0 + N, c0:c0 + N]); tok_.append(np.concatenate([Tm[m0:m0 + 15, n0:n0 + 15], Td[m0:m0 + 15, n0:n0 + 15]], -1).transpose(2, 0, 1))
        aux_.append(np.stack([np.nan_to_num(can, nan=np.nanmean(can) if np.isfinite(can).any() else 30.0), dist, dm.astype(np.float32)]).astype(np.float32)); y_.append(y)
        meta.append((g.fire, Y, g.area_ha, int(y.sum())))
    print(Y, len(meta), flush=True)
np.savez(f'{C.SP}/chips.npz', raw=np.stack(raw_), tok=np.stack(tok_), aux=np.stack(aux_), y=np.stack(y_), meta=np.array(meta))
print('chips', len(meta))
