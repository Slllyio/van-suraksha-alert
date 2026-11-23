"""Layer 1b: true pixel footprint of every VIIRS detection spread onto 500 m squares as fractional weights.
Footprint = rectangle of FIRMS scan (along-scan) x track (along-track) km centred on the detection, along-scan axis
perpendicular to the ground track (heading 347 deg day / 193 deg night, turned to UTM grid north with the local meridian
convergence). 8 x 8 sample points per pixel -> weight of each square = share of the pixel's area inside it.
Variant OFF: centre first moved by the per-satellite static-site offsets (relative to S-NPP).
Output (scratch): fp.parquet / fp_off.parquet with det (index in det_all.parquet), row, col, w."""
import sys, numpy as np, pandas as pd
from pyproj import Transformer
import common as C

if __name__ == '__main__':
    off_mode = len(sys.argv) > 1 and sys.argv[1] == 'off'
    v = C.load_det(); v = v[v.type == 0]
    tf = Transformer.from_crs(4326, 32643, always_xy=True)
    x2, y2 = tf.transform(v.longitude.values, v.latitude.values + 0.01)
    gam = np.degrees(np.arctan2(x2 - v.x.values, y2 - v.y.values))   # grid bearing of true north
    head = np.where(v.daynight.values == 'D', 347.0, 193.0) + gam
    h = np.radians(head); at = np.c_[np.sin(h), np.cos(h)]; ac = np.c_[np.cos(h), -np.sin(h)]
    x = v.x.values.astype(float); y = v.y.values.astype(float)
    if off_mode:
        off = {('jpss1', 'D'): (52, -93), ('jpss1', 'N'): (-20, 79), ('noaa21', 'D'): (-57, -25), ('noaa21', 'N'): (27, -44)}
        dx = np.array([off.get(k, (0, 0))[0] for k in zip(v.sat.values, v.daynight.values)]); dy = np.array([off.get(k, (0, 0))[1] for k in zip(v.sat.values, v.daynight.values)])
        x = x - dx; y = y - dy
    K = 8; u = (np.arange(K) + .5) / K - .5; su, sv = np.meshgrid(u, u); su = su.ravel(); sv = sv.ravel()
    scan = v.scan.values * 1000; track = v.track.values * 1000; det = v.index.values
    parts = []
    for a in range(0, len(v), 200000):
        b = slice(a, a + 200000)
        px = x[b, None] + su[None] * scan[b, None] * ac[b, 0, None] + sv[None] * track[b, None] * at[b, 0, None]
        py = y[b, None] + su[None] * scan[b, None] * ac[b, 1, None] + sv[None] * track[b, None] * at[b, 1, None]
        col = np.floor((px - C.X0) / C.S).astype(np.int32); row = np.floor((C.Y1 - py) / C.S).astype(np.int32)
        d = np.repeat(det[b], K * K)
        key = pd.DataFrame(dict(det=d, row=row.ravel(), col=col.ravel()))
        g = key.groupby(['det', 'row', 'col']).size().rename('n').reset_index(); g['w'] = (g.n / (K * K)).astype(np.float32)
        parts.append(g.drop(columns='n')); print(a, flush=True)
    F = pd.concat(parts, ignore_index=True)
    F.to_parquet(C.SC + ('fp_off.parquet' if off_mode else 'fp.parquet'))
    print('rows', len(F), 'per detection', len(F) / len(v), 'share of weight in own square (point square):',
          float(F.merge(v[['row', 'col']].reset_index().rename(columns={'index': 'det'}), on=['det', 'row', 'col']).w.sum() / len(v)))
