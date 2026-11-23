"""Shared helpers: true (rotated) VIIRS/MODIS footprints, photo truth cache, scoring."""
import glob, os, pickle
import numpy as np, pandas as pd
ROOT = '/mnt/project-files'
SC = os.environ.get('SQ_SCRATCH', os.path.dirname(os.path.abspath(__file__)))
OUT = os.environ.get('SQ_OUT', f'{ROOT}/ratapani/fsi/scouting/code/squares/results'); os.makedirs(OUT, exist_ok=True)
TD = f'{ROOT}/fuel-map/ratapani/timing/'

def axes(heading_deg):
    h = np.radians(np.asarray(heading_deg, float))
    ut = np.stack([np.sin(h), np.cos(h)], -1)      # along track (x=E, y=N)
    us = np.stack([np.cos(h), -np.sin(h)], -1)     # along scan
    return us, ut

def foot_dist(X, Y, d, rotate=True, scale=1.0, pad=0.0):
    """Distance (m) from points (X, Y) to each footprint in d (0 inside). Footprint = scan_m x track_m rectangle centred on
    the detection, rotated so its track side follows the satellite heading (rotate=False: scan along E-W as before).
    scale shrinks/grows the rectangle; pad adds a margin. Returns (npts, ndet)."""
    dx = X[:, None] - d.x.values[None]; dy = Y[:, None] - d.y.values[None]
    hs = d.scan_m.values[None] * scale / 2 + pad; ht = d.track_m.values[None] * scale / 2 + pad
    if rotate:
        us, ut = axes(d.heading.values)
        a = np.abs(dx * us[None, :, 0] + dy * us[None, :, 1]); b = np.abs(dx * ut[None, :, 0] + dy * ut[None, :, 1])
    else:
        a, b = np.abs(dx), np.abs(dy)
    return np.hypot(np.maximum(a - hs, 0), np.maximum(b - ht, 0))

def inside(X, Y, d, **kw):
    return foot_dist(X, Y, d, **kw) <= 0

def corners(r, scale=1.0):
    us, ut = axes(r.heading); hs, ht = r.scan_m * scale / 2, r.track_m * scale / 2
    return np.array([[r.x, r.y] + sa * hs * us + sb * ht * ut for sa, sb in [(-1, -1), (1, -1), (1, 1), (-1, 1)]])

def poly(r, scale=1.0):
    from shapely.geometry import Polygon
    return Polygon(corners(r, scale))

def load_det():
    D = pd.read_parquet(f'{SC}/det_all.parquet')
    return D

def photos(maxpx=5000):
    """Mid-fire photo truth (fuel thread chips): per photo the scar pixels (x, y), burned-by-photo flag, photo time, fire."""
    fn = f'{SC}/photos.pkl'
    if os.path.exists(fn): return pickle.load(open(fn, 'rb'))
    import rasterio
    from scipy.spatial import cKDTree
    with rasterio.open(f'{ROOT}/research/ratapani-burn-labels/rasters/burn_2017.tif') as r: TRB = r.transform
    ms = pd.read_parquet(TD + 'midscar.parquet'); ms = ms[ms.status == 'ok']
    D = load_det(); V = D[(D.kind == 'viirs') & (D.fire >= 0)].reset_index(drop=True); tree = cKDTree(V[['x', 'y']].values)
    F = pd.read_csv(f'{ROOT}/research/big-fires/results/fires.csv')
    big = set(F[(F.area_ha >= 200) & (F.n_looks >= 4) & (F.n_viirs >= 10) & ~F.still_at_edge].fire)
    rng = np.random.default_rng(0); out = []
    for f in sorted(glob.glob(TD + 'chips/*.npz')):
        b = os.path.basename(f); ev = int(b.split('_')[0]); sc = b[len(str(ev)) + 1:-4]
        m = ms[(ms.event == ev) & (ms.scene.str[:40] == sc)]
        if not len(m): continue
        m = m.iloc[0]; z = np.load(f); Sm, bym, ok = z['S'], z['bym'], z['ok']; i0, j0 = int(z['i0']), int(z['j0'])
        rr, cc = np.where(Sm & ok)
        if len(rr) < 20: continue
        if len(rr) > maxpx:
            k = rng.choice(len(rr), maxpx, replace=False); rr, cc = rr[k], cc[k]
        xs, ys = rasterio.transform.xy(TRB, rr + i0, cc + j0); X, Y = np.array(xs), np.array(ys)
        yb = bym[rr, cc].astype(int)
        near = np.unique(np.concatenate(tree.query_ball_point(np.c_[X[::5], Y[::5]], 1000)))
        if not len(near): continue
        dd = V.iloc[near]; dd = dd[(dd.t >= m.t_first - pd.Timedelta(hours=26)) & (dd.t <= m.t_last + pd.Timedelta(hours=26))]
        if not len(dd): continue
        fire = int(dd.fire.value_counts().index[0]); T = pd.Timestamp(m['T'])
        out.append(dict(event=ev, scene=sc, T=T, season=T.year, fire=fire, big=fire in big, X=X, Y=Y, y=yb))
    pickle.dump(out, open(fn, 'wb')); return out

def auc(y, s):
    from sklearn.metrics import roc_auc_score
    y = np.asarray(y); s = np.asarray(s, float)
    return roc_auc_score(y, s) if 0 < y.sum() < len(y) else np.nan

def boot_diff(df, a, b, key='fire', n=1000, seed=0):
    """95% range of mean(df[a] - df[b]) resampling fires."""
    rng = np.random.default_rng(seed); g = df.dropna(subset=[a, b]); d = (g[a] - g[b]).groupby(g[key]).agg(['sum', 'size'])
    ids = np.arange(len(d)); s, c = d['sum'].values, d['size'].values; v = []
    for _ in range(n):
        k = rng.choice(ids, len(ids)); v.append(s[k].sum() / c[k].sum())
    return [round(float(np.quantile(v, .025)), 4), round(float(np.quantile(v, .975)), 4)]
