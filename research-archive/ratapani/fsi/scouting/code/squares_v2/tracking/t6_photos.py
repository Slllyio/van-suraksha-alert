"""Tracking step 6: score burning-time maps on the 340 mid-fire Sentinel-2/Landsat photos (independent truth, never used
for any choice). Truth per photo pixel (20 m): burned by the photo minute (fuel thread chips, as in fire-continuity).
Methods on identical pixels:
  inversion        : this thread's multi-pass map (config given on the command line)
  nearest          : time of the nearest VIIRS footprint (each detection separate, footprints turned to the track)
  idw2 / idw4      : inverse-distance-weighted mean of detection times, p = 2 (Parks 2014 type) / p = 4 (blend type, straight line)
  linear           : Delaunay linear interpolation of detection times (natural-neighbour type, Scaduto 2020); nearest outside hull
  blend (continuity): the fire-continuity thread's chosen map, its own per-photo score (results/photo_scores.parquet;
                     computed on all chip pixels, so only compared photo by photo)
Scores: pixel accuracy (T <= photo time vs burned), AUC of -T, burned-share error. 95% ranges by bootstrap over fires.
Usage: python3 t6_photos.py <config>  -> results/t6_photos_<config>.csv, .json"""
import sys, os, json, pickle, hashlib
import numpy as np, pandas as pd
from scipy.spatial import cKDTree
from scipy.interpolate import LinearNDInterpolator
from sklearn.metrics import roc_auc_score
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from t2_lib import *

def mapdir(name): return f'{SC}/maps/{name if len(name) < 40 else hashlib.md5(name.encode()).hexdigest()[:10]}'

def load_map(name, fire):
    fn = f'{mapdir(name)}/{fire}.npz'
    if not os.path.exists(fn): return None
    z = dict(np.load(fn, allow_pickle=True)); z['t0'] = pd.Timestamp(str(z['t0'])); return z

def T_at(z, X, Y, key='T'):
    tr = z['tr']; x0, y1 = tr[2], tr[5]
    cx = x0 + (z['cc'] + .5) * z['tr'][0]; cy = y1 - (z['rr'] + .5) * z['tr'][0]
    _, j = cKDTree(np.c_[cx, cy]).query(np.c_[X, Y]); return z[key][j]

def foot_dist(X, Y, d):
    us, ut = axes(d.heading.values); dx = X[:, None] - d.xc.values[None]; dy = Y[:, None] - d.yc.values[None]
    a = np.abs(dx * us[None, :, 0] + dy * us[None, :, 1]) - d.scan_m.values[None] / 2
    b = np.abs(dx * ut[None, :, 0] + dy * ut[None, :, 1]) - d.track_m.values[None] / 2
    return np.hypot(np.maximum(a, 0), np.maximum(b, 0)) + 1e-3 * np.hypot(dx, dy)

def baselines(X, Y, d, t0):
    th = (d.t - t0).dt.total_seconds().values / 3600; out = {}
    E = foot_dist(X, Y, d); out['nearest'] = th[np.argmin(E, 1)]
    dd = np.hypot(X[:, None] - d.xc.values[None], Y[:, None] - d.yc.values[None])
    for p in [2, 4]:
        w = 1 / (dd + 50) ** p; out[f'idw{p}'] = (w * th[None]).sum(1) / w.sum(1)
    if len(d) >= 3 and np.linalg.matrix_rank(np.c_[d.xc - d.xc.mean(), d.yc - d.yc.mean()]) == 2:
        try:
            li = LinearNDInterpolator(np.c_[d.xc, d.yc], th)(X, Y); out['linear'] = np.where(np.isfinite(li), li, out['nearest'])
        except Exception: out['linear'] = out['nearest']
    else: out['linear'] = out['nearest']
    return out

def auc(y, s): return roc_auc_score(y, s) if 0 < y.sum() < len(y) else np.nan

def boot(df, a, b, col, n=2000, seed=0):
    g = df.dropna(subset=[f'{col}_{a}', f'{col}_{b}']); d = (g[f'{col}_{a}'] - g[f'{col}_{b}']).groupby(g.fire).agg(['sum', 'size'])
    rng = np.random.default_rng(seed); s, c = d['sum'].values, d['size'].values; v = []
    for _ in range(n):
        k = rng.integers(0, len(d), len(d)); v.append(s[k].sum() / c[k].sum())
    return [round(float(s.sum() / c.sum()), 4), round(float(np.quantile(v, .025)), 4), round(float(np.quantile(v, .975)), 4)]

if __name__ == '__main__':
    name = sys.argv[1] if len(sys.argv) > 1 else 'base'
    PH = pickle.load(open(f'{R17}/photos.pkl', 'rb')); D = data()['D']
    CS = pd.read_parquet(f'{ROOT}/research/fire-continuity/results/photo_scores.parquet')
    CS['key'] = CS.event.astype(str) + '|' + CS.scene.str[:40]
    rows = []
    for ph in PH:
        z = load_map(name, ph['fire'])
        if z is None: continue
        t0 = z['t0']; X, Y, y = ph['X'], ph['Y'], ph['y']; th = (pd.Timestamp(ph['T']) - t0).total_seconds() / 3600
        d = D[(D.fire == ph['fire']) & (D.kind == 'viirs')]
        maps = {'inversion': T_at(z, X, Y).astype(float)}
        if 'T_boot_med' in z: maps['inversion_bootmed'] = T_at(z, X, Y, 'T_boot_med').astype(float)
        maps.update(baselines(X, Y, d, t0))
        tdet = (d.t - t0).dt.total_seconds().values / 3600
        r = dict(event=ph['event'], scene=ph['scene'], fire=ph['fire'], season=ph['season'], big=ph['big'], n_px=len(y), obs_frac=y.mean(),
                 before=int((tdet < th).sum() > 0), after=int((tdet > th).sum() > 0), n_viirs=len(d))
        for m, T in maps.items():
            pred = T <= th; r[f'acc_{m}'] = (pred == y).mean(); r[f'auc_{m}'] = auc(y, -T); r[f'frac_{m}'] = pred.mean()
        c = CS[CS.key == f"{ph['event']}|{ph['scene'][:40]}"]
        if len(c): r['acc_blend'] = float(c.acc_blend_walk_p4_clock.iloc[0]); r['auc_blend'] = float(c.auc_blend_walk_p4_clock.iloc[0]); r['frac_blend'] = float(c.frac_blend_walk_p4_clock.iloc[0])
        rows.append(r)
    X = pd.DataFrame(rows); X.to_csv(f'{OUT}/t6_photos_{name if len(name) < 40 else "cfg"}.csv', index=False)
    meth = [c[4:] for c in X.columns if c.startswith('acc_')]
    res = dict(config=name, photos=len(X), fires=int(X.fire.nunique()))
    for nm, g in [('all', X), ('look_before_and_after', X[(X.before == 1) & (X.after == 1)]), ('big', X[X.big]),
                  ('odd_seasons', X[X.season % 2 == 1]), ('even_seasons', X[X.season % 2 == 0])]:
        s = dict(n=len(g))
        for m in meth:
            s[m] = dict(acc=round(g[f'acc_{m}'].mean(), 4), auc=round(g[f'auc_{m}'].mean(), 4), burned_share_err=round((g[f'frac_{m}'] - g.obs_frac).mean(), 4))
        for b in [m for m in meth if m != 'inversion']:
            s[f'inversion_minus_{b}'] = dict(acc=boot(g, 'inversion', b, 'acc'), auc=boot(g, 'inversion', b, 'auc'))
        res[nm] = s
    json.dump(res, open(f'{OUT}/t6_photos_{name if len(name) < 40 else "cfg"}.json', 'w'), indent=1)
    print(json.dumps(res['all'], indent=1)); print(json.dumps(res['look_before_and_after'], indent=1))
