"""Do VIIRS 'looked, clear, no fire' pixels (VNP14IMG/VJ114IMG classes 3/5; VIIRS fire masks thread,
ratapani/fsi/scouting/code/squares_v2/tracking/results/mask_pixels_near_fires.parquet) tighten the growth map?
A clear no-fire look at time tn says the ground there was probably not burning at tn. The blend map (block seed, p=4, clock)
contradicts it only where it puts arrival within D hours before tn (still burning at the pass). Correction: those pixels get the
time of the next VIIRS fire look after tn (the fire arrived later). Same 340 photos and scoring as c1/c13.
Variants: D = 1.5 / 3 / 6 h; footprint match radius 200 m around the mask pixel centre (375 m pixel, position error).
Out: results/nofire.json, results/nofire.parquet"""
import sys, glob, os, json, pickle
import numpy as np, pandas as pd
from multiprocessing import Pool
from rasterio import features
from rasterio.transform import Affine
from scipy.spatial import cKDTree
import pyproj
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from c0_lib import *
BF = f'{ROOT}/research/big-fires/results'; TD = f'{ROOT}/fuel-map/ratapani/timing/'; OUT = f'{ROOT}/research/fire-continuity/results'
A = pd.read_csv(f'{BF}/fire_alerts.csv', parse_dates=['t']); A = A[A.sat != 'modis'].copy()
A['scan'] = A.scan.fillna(.375).clip(lower=.3); A['track'] = A.track.fillna(.375).clip(lower=.3)
SC = pickle.load(open(f'{SCRATCH}/fire_scars.pkl', 'rb'))
ms = pd.read_parquet(TD + 'midscar.parquet'); ms = ms[ms.status == 'ok']
tree = cKDTree(A[['x', 'y']].values)
M = pd.read_parquet(f'{ROOT}/ratapani/fsi/scouting/code/squares_v2/tracking/results/mask_pixels_near_fires.parquet',
                    columns=['fire', 't_pass', 'lat', 'lon', 'cls'])
M = M[M.cls.isin([3, 5])].copy()
M['x'], M['y'] = pyproj.Transformer.from_crs(4326, 32643, always_xy=True).transform(M.lon.values, M.lat.values)
MF = {f: g for f, g in M.groupby('fire')}
DS = [1.5, 3.0, 6.0]; RAD = 200.0

def one(f):
    b = os.path.basename(f); ev = int(b.split('_')[0]); sc = b[len(str(ev)) + 1:-4]
    m = ms[(ms.event == ev) & (ms.scene.str[:40] == sc)]
    if not len(m): return None
    m = m.iloc[0]; z = np.load(f); Sm, bym, ok = z['S'], z['bym'], z['ok']; i0, j0 = int(z['i0']) + 100, int(z['j0']) + 100
    rr, cc = np.where(Sm & ok)
    if len(rr) < 20: return None
    px, py = xy_of(rr + i0, cc + j0)
    near = np.unique(np.concatenate(tree.query_ball_point(np.c_[px[::5], py[::5]], 1000)))
    if not len(near): return None
    dd = A.iloc[near]; dd = dd[(dd.t >= m.t_first - pd.Timedelta(hours=26)) & (dd.t <= m.t_last + pd.Timedelta(hours=26))]
    if not len(dd): return None
    fire = int(dd.fire.value_counts().index[0]); d = viirs_looks(A[A.fire == fire])
    T = pd.Timestamp(m['T']); d['th'] = (d.t - T).dt.total_seconds() / 3600
    poly = SC[fire]
    xs = np.r_[poly.bounds[0], poly.bounds[2], px.min(), px.max(), d.x.min(), d.x.max()]
    ys = np.r_[poly.bounds[1], poly.bounds[3], py.min(), py.max(), d.y.min(), d.y.max()]
    r0, c0 = rc_of(xs.min() - 900, ys.max() + 900); r1, c1 = rc_of(xs.max() + 900, ys.min() - 900)
    box = Box(int(r0), int(r1) + 1, int(c0), int(c1) + 1)
    tr = Affine(20, 0, X0 + box.c0 * 20, 0, -20, Y0 - box.r0 * 20)
    dom = features.rasterize([poly], out_shape=box.shape, transform=tr).astype(bool)
    ri, ci = rr + i0 - box.r0, cc + j0 - box.c0
    sr, scc = np.where(Sm); dom[sr + i0 - box.r0, scc + j0 - box.c0] = True
    y = bym[rr, cc].astype(int)
    M_, idx_, _, _ = box.graph(dom); clk = Clock(T)
    looks = sorted(d.lk.unique()); tlk = np.array([d[d.lk == k].th.min() for k in looks])
    Ek = np.stack([walk(M_, idx_, np.any([box.footprint(det, dom) for det in d[d.lk == k].itertuples()], 0))[idx_[ri, ci]] for k in looks], 1)
    Ek[~np.isfinite(Ek)] = 1e6
    w = 1 / (Ek + 50.0) ** 4; w /= w.sum(1, keepdims=True)
    t = clk.Winv((w * clk.W(tlk)[None]).sum(1))
    res = dict(event=ev, scene=sc, season=T.year, fire=fire, n_px=len(rr), acc_base=((t <= 0) == y).mean())
    g = MF.get(fire)
    if g is None or not len(g):
        for D in DS: res[f'acc_D{D}'] = res['acc_base']; res[f'n_conf_D{D}'] = 0; res[f'conf_right_base_D{D}'] = np.nan; res[f'conf_right_new_D{D}'] = np.nan
        res['has_mask'] = False; return res
    res['has_mask'] = True
    tn = ((g.t_pass - T).dt.total_seconds() / 3600).values
    # only passes that are not also fire looks of this fire within 1 h (those times already have fire elsewhere = fine, keep all)
    kd = cKDTree(g[['x', 'y']].values); hits = kd.query_ball_point(np.c_[px, py], RAD)
    for D in DS:
        tnew = t.copy(); conf = np.zeros(len(t), bool)
        for i, h in enumerate(hits):
            if not h: continue
            tt = tn[h]; bad = tt[(t[i] <= tt) & (t[i] >= tt - D)]   # map says burning at a clear no-fire look
            if len(bad):
                conf[i] = True; nxt = tlk[tlk > bad.max()]; tnew[i] = nxt.min() if len(nxt) else 1e6
        res[f'acc_D{D}'] = ((tnew <= 0) == y).mean(); res[f'n_conf_D{D}'] = int(conf.sum())
        res[f'conf_right_base_D{D}'] = ((t[conf] <= 0) == y[conf]).mean() if conf.any() else np.nan
        res[f'conf_right_new_D{D}'] = ((tnew[conf] <= 0) == y[conf]).mean() if conf.any() else np.nan
        res[f'flip_D{D}'] = int(((t <= 0) != (tnew <= 0)).sum())
    return res

if __name__ == '__main__':
    files = sorted(glob.glob(TD + 'chips/*.npz'))
    with Pool(8) as p: rows = [r for r in p.map(one, files, chunksize=4) if r]
    X = pd.DataFrame(rows); X.to_parquet(f'{OUT}/nofire.parquet')
    rng = np.random.default_rng(0); out = dict(n_photos=len(X), photos_with_mask=int(X.has_mask.sum()), acc_base=round(X.acc_base.mean(), 4))
    fr = X.fire.values; u = np.unique(fr)
    for D in DS:
        dl = (X[f'acc_D{D}'] - X.acc_base).values; bs = []
        for _ in range(1000):
            s = rng.choice(u, len(u)); mm = np.concatenate([np.where(fr == f)[0] for f in s]); bs.append(dl[mm].mean())
        n = X[f'n_conf_D{D}'].sum(); wb = (X[f'conf_right_base_D{D}'] * X[f'n_conf_D{D}']).sum() / max(n, 1); wn = (X[f'conf_right_new_D{D}'] * X[f'n_conf_D{D}']).sum() / max(n, 1)
        out[f'D{D}h'] = dict(acc=round(X[f'acc_D{D}'].mean(), 4), gain=[round(dl.mean(), 4), round(float(np.quantile(bs, .025)), 4), round(float(np.quantile(bs, .975)), 4)],
                            conflicted_pixels=int(n), share_of_pixels=round(n / X.n_px.sum(), 4), flipped=int(X[f'flip_D{D}'].sum()),
                            conflicted_right_before=round(float(wb), 3), conflicted_right_after=round(float(wn), 3))
    print(json.dumps(out, indent=1)); json.dump(out, open(f'{OUT}/nofire.json', 'w'), indent=1)
