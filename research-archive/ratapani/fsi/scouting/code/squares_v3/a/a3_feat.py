"""A3 features for the anisotropy test (per fire pair, at the pair mid-point M):
  grain: terrain grain from the structure tensor of the ~140 m SRTM elevation gradient, smoothed over ~1.4 km (sigma 10 px).
         grain_az = azimuth of the ridge/valley axis (perpendicular to the dominant gradient axis), 0-180 deg;
         grain_coh = coherence 0..1 (1 = all slopes face the same two ways, i.e. parallel ridges/valleys);
         relief = local SD of elevation over ~1.4 km (m).
  canopy: forest fraction (Roy et al. VTM 60 m, forest classes 11-119) on a 300 m grid; its gradient (towards denser
          forest) smoothed over ~1 km: can_az (deg from N), can_grad (fraction per km), can_frac at M.
  elongation: principal axis of the fire's earlier VIIRS detections (2-48 h before A, within 2 km of M, >= 4 points):
          elong_az (0-180 deg), elong_ratio = sqrt(major/minor eigenvalue).
Out (scratch): r20_a/feat.parquet, indexed by pair_row (pairs.parquet row)."""
import os, sys
import numpy as np, pandas as pd, rasterio, pyproj
from rasterio.windows import from_bounds
from scipy.ndimage import gaussian_filter, uniform_filter
from scipy.spatial import cKDTree
SC = '/tmp/claude-0/-home-user/be9b8f54-cc26-52cb-bdbb-9c8008a24baf/scratchpad'
POOL = f'{SC}/r19_pool'; OUTS = f'{SC}/r20_a'
D = pd.read_parquet(f'{OUTS}/pairs_corr.parquet', columns=['pair_row', 'fire', 'latA', 'latB', 'lonA', 'lonB', 'mx', 'my', 'tA'])
D = D[D.fire == 1].reset_index(drop=True)
lat = (D.latA + D.latB).values / 2; lon = (D.lonA + D.lonB).values / 2
# ---- terrain grain
Z = np.load(f'{POOL}/dem_mp.npz'); E = Z['elev']; x0, y0 = int(Z['x0']), int(Z['y0'])
E = np.where(np.isfinite(E), E, np.nanmean(E))
Es = gaussian_filter(E, 1.0); gy, gx = np.gradient(Es)
n = 256 * 2 ** 10
rows = np.arange(E.shape[0]) + 256 * y0 + .5
latr = np.degrees(np.arctan(np.sinh(np.pi * (1 - 2 * rows / n))))
res = (40075016.686 / n * np.cos(np.radians(latr)))[:, None]
ex = gx / res; en = -gy / res
S = 10.0
Jxx = gaussian_filter(ex * ex, S); Jnn = gaussian_filter(en * en, S); Jxn = gaussian_filter(ex * en, S)
ang = 0.5 * np.arctan2(2 * Jxn, Jxx - Jnn)          # math angle (from east) of the dominant gradient axis
grad_az = (90 - np.degrees(ang)) % 180               # azimuth of gradient axis
grain_az = (grad_az + 90) % 180                      # ridge / valley axis
coh = np.sqrt((Jxx - Jnn) ** 2 + 4 * Jxn ** 2) / (Jxx + Jnn + 1e-12)
m1 = uniform_filter(E, 21); m2 = uniform_filter(E * E, 21); relief = np.sqrt(np.clip(m2 - m1 * m1, 0, None))
px = (lon + 180) / 360 * n - 256 * x0
r = np.radians(lat); py = (1 - np.log(np.tan(r) + 1 / np.cos(r)) / np.pi) / 2 * n - 256 * y0
i = np.clip(py.astype(int), 0, E.shape[0] - 1); j = np.clip(px.astype(int), 0, E.shape[1] - 1)
D['grain_az'] = grain_az[i, j].astype(np.float32); D['grain_coh'] = coh[i, j].astype(np.float32); D['relief'] = relief[i, j].astype(np.float32)
del Jxx, Jnn, Jxn, ang, grad_az, grain_az, coh, m1, m2, relief, Es, gx, gy, ex, en
print('grain done', flush=True)
# ---- canopy gradient
tp = pyproj.Transformer.from_crs(4326, 32643, always_xy=True).transform
ux, uy = tp(lon, lat)
with rasterio.open(f'{SC}/r14_types_data/vtm.tif') as src:
    bx0, by0 = tp(73.8, 20.9); bx1, by1 = tp(83.0, 27.0)
    w = from_bounds(min(bx0, bx1) - 5000, min(by0, by1) - 5000, max(bx0, bx1) + 5000, max(by0, by1) + 5000, src.transform)
    w = w.round_offsets().round_lengths()
    out = []
    # read in row strips and block-average forest indicator to 300 m (5 x 5)
    H = (w.height // 5) * 5; W = (w.width // 5) * 5
    for r0 in range(0, H, 2000):
        hh = min(2000, H - r0)
        a = src.read(1, window=rasterio.windows.Window(w.col_off, w.row_off + r0, W, hh))
        f = ((a >= 11) & (a <= 119)).astype(np.float32)
        out.append(f.reshape(hh // 5, 5, W // 5, 5).mean((1, 3)))
    T = src.window_transform(w)
FF = np.vstack(out); del out
FFs = gaussian_filter(FF, 3.3)                        # ~1 km
gr, gc = np.gradient(FFs)                              # per 300 m; rows go south
gE = gc / 0.3; gN = -gr / 0.3                          # fraction per km
col = ((ux - T.c) / 300).astype(int); row = ((T.f - uy) / 300).astype(int)
ok = (row >= 0) & (row < FF.shape[0]) & (col >= 0) & (col < FF.shape[1])
row, col = np.clip(row, 0, FF.shape[0] - 1), np.clip(col, 0, FF.shape[1] - 1)
D['can_frac'] = np.where(ok, FFs[row, col], np.nan); D['can_gE'] = np.where(ok, gE[row, col], np.nan); D['can_gN'] = np.where(ok, gN[row, col], np.nan)
D['can_az'] = np.degrees(np.arctan2(D.can_gE, D.can_gN)) % 360; D['can_grad'] = np.hypot(D.can_gE, D.can_gN)
del FF, FFs, gr, gc, gE, gN
print('canopy done', flush=True)
# ---- elongation of earlier detections
A = pd.read_parquet(f'{POOL}/pts.parquet', columns=['sensor', 't', 'x', 'y', 'type'])
A = A[A.sensor.isin(['S-NPP', 'NOAA-20', 'NOAA-21']) & (A.type == 0)]
pt = A.t.values.astype('datetime64[s]').astype(np.int64); o = np.argsort(pt); px_, py_, pt = A.x.values[o], A.y.values[o], pt[o]
tA = D.tA.values.astype('datetime64[s]').astype(np.int64); day = tA // 86400
ea = np.full(len(D), np.nan, np.float32); er = np.full(len(D), np.nan, np.float32); ne = np.zeros(len(D), np.int32)
for dd in np.unique(day):
    sel = np.where(day == dd)[0]
    lo, hi = np.searchsorted(pt, [dd * 86400 - 3 * 86400, dd * 86400 + 86400])
    if hi <= lo: continue
    qx, qy, qt = px_[lo:hi], py_[lo:hi], pt[lo:hi]; tree = cKDTree(np.c_[qx, qy])
    nb = tree.query_ball_point(np.c_[D.mx.values[sel], D.my.values[sel]], 2000.0)
    for ii, k in enumerate(sel):
        jj = np.asarray(nb[ii], int)
        if len(jj) < 4: continue
        tt = qt[jj]; e = jj[(tt >= tA[k] - 48 * 3600) & (tt <= tA[k] - 2 * 3600)]
        ne[k] = len(e)
        if len(e) < 4: continue
        C = np.cov(np.c_[qx[e], qy[e]].T); w_, v_ = np.linalg.eigh(C)
        if w_[0] <= 0: w_[0] = 1.0
        ea[k] = np.degrees(np.arctan2(v_[0, 1], v_[1, 1])) % 180; er[k] = np.sqrt(w_[1] / w_[0])
D['elong_az'] = ea; D['elong_ratio'] = er; D['nE_elong'] = ne
D.drop(columns=['latA', 'latB', 'lonA', 'lonB', 'tA']).to_parquet(f'{OUTS}/feat.parquet')
print(D[['grain_coh', 'relief', 'can_frac', 'can_grad', 'elong_ratio']].describe().T.to_string())
