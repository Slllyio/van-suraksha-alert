"""Big-fires 14c test: real hot pixels sit at the edge of their VIIRS block or just outside it, not at the centre.
Does seeding the growth map at block edges / the cluster's outer boundary beat the current seeding (whole scan x track block)?
Same 340 mid-fire photos and scoring as c1 (chosen method: blend, walking distance, p=4, burning clock). Seed variants:
  block     : current, whole block (distance to a block = distance to its nearest edge)
  centre    : the dot only (20 m)
  grow125 / grow250 : block widened by 125 / 250 m each side (hot pixels just outside; ~250 m position error)
  ring      : only the outer 100 m band of each look's union of blocks (cluster boundary; interior is not a seed)
  ring_grow125 : ring of the widened union
Out: results/edge_seed.parquet, results/edge_seed.json"""
import sys, glob, os, json, pickle
import numpy as np, pandas as pd
from multiprocessing import Pool
from rasterio import features
from rasterio.transform import Affine
from scipy.ndimage import binary_erosion
from sklearn.metrics import roc_auc_score
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from c0_lib import *
BF = f'{ROOT}/research/big-fires/results'; TD = f'{ROOT}/fuel-map/ratapani/timing/'; OUT = f'{ROOT}/research/fire-continuity/results'
A = pd.read_csv(f'{BF}/fire_alerts.csv', parse_dates=['t']); A = A[A.sat != 'modis'].copy()
A['scan'] = A.scan.fillna(.375).clip(lower=.3); A['track'] = A.track.fillna(.375).clip(lower=.3)
SC = pickle.load(open(f'{SCRATCH}/fire_scars.pkl', 'rb'))
ms = pd.read_parquet(TD + 'midscar.parquet'); ms = ms[ms.status == 'ok']
tree = cKDTree(A[['x', 'y']].values)
VAR = {'block': (0, False), 'centre': (None, False), 'grow125': (125, False), 'grow250': (250, False), 'ring': (0, True), 'ring_grow125': (125, True)}

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
    fire = int(dd.fire.value_counts().index[0]); d0 = viirs_looks(A[A.fire == fire])
    T = pd.Timestamp(m['T']); d0['th'] = (d0.t - T).dt.total_seconds() / 3600
    poly = SC[fire]
    xs = np.r_[poly.bounds[0], poly.bounds[2], px.min(), px.max(), d0.x.min(), d0.x.max()]
    ys = np.r_[poly.bounds[1], poly.bounds[3], py.min(), py.max(), d0.y.min(), d0.y.max()]
    r0, c0 = rc_of(xs.min() - 900, ys.max() + 900); r1, c1 = rc_of(xs.max() + 900, ys.min() - 900)
    box = Box(int(r0), int(r1) + 1, int(c0), int(c1) + 1)
    tr = Affine(20, 0, X0 + box.c0 * 20, 0, -20, Y0 - box.r0 * 20)
    dom = features.rasterize([poly], out_shape=box.shape, transform=tr).astype(bool)
    ri, ci = rr + i0 - box.r0, cc + j0 - box.c0
    sr, scc = np.where(Sm); dom[sr + i0 - box.r0, scc + j0 - box.c0] = True
    y = bym[rr, cc].astype(int)
    res = dict(event=ev, scene=sc, T=T, season=T.year, fire=fire, n_px=len(rr), obs_frac=y.mean(),
               looks_before=int((d0.groupby('lk').th.min() < 0).sum()), looks_after=int((d0.groupby('lk').th.min() > 0).sum()))
    M_, idx_, _, _ = box.graph(dom); clk = Clock(T)
    looks = sorted(d0.lk.unique()); tlk = np.array([d0[d0.lk == k].th.min() for k in looks])
    for name, (g, ring) in VAR.items():
        d = d0.copy()
        if g is None: d['scan'] = d['track'] = .02
        else: d['scan'] = d.scan + 2 * g / 1000; d['track'] = d.track + 2 * g / 1000
        Ek = []
        for k in looks:
            fp = np.any([box.footprint(det, dom) for det in d[d.lk == k].itertuples()], 0)
            if ring:
                inner = binary_erosion(fp, iterations=5) & dom
                if (fp & ~inner).any(): fp = fp & ~inner
            Ek.append(walk(M_, idx_, fp)[idx_[ri, ci]])
        Ek = np.stack(Ek, 1); Ek[~np.isfinite(Ek)] = 1e6
        w = 1 / (Ek + 50.0) ** 4; w /= w.sum(1, keepdims=True)
        t = clk.Winv((w * clk.W(tlk)[None]).sum(1)); pred = t <= 0
        res[f'acc_{name}'] = (pred == y).mean(); res[f'auc_{name}'] = roc_auc_score(y, -t) if 0 < y.sum() < len(y) else np.nan
    return res

if __name__ == '__main__':
    files = sorted(glob.glob(TD + 'chips/*.npz'))
    with Pool(8) as p: rows = [r for r in p.map(one, files, chunksize=4) if r]
    X = pd.DataFrame(rows); X.to_parquet(f'{OUT}/edge_seed.parquet')
    rng = np.random.default_rng(0); fires = X.fire.values; uf = np.unique(fires); out = dict(n_photos=len(X))
    for setn, g in [('all', X), ('look before and after', X[(X.looks_before > 0) & (X.looks_after > 0)])]:
        o = {}
        fr = g.fire.values; u = np.unique(fr)
        for v in VAR:
            dlt = (g[f'acc_{v}'] - g.acc_block).values; bs = []
            for _ in range(1000):
                s = rng.choice(u, len(u)); mm = np.concatenate([np.where(fr == f)[0] for f in s]); bs.append(dlt[mm].mean())
            o[v] = dict(acc=round(float(g[f'acc_{v}'].mean()), 4), auc=round(float(g[f'auc_{v}'].mean()), 4),
                        acc_vs_block=[round(float(dlt.mean()), 4), round(float(np.quantile(bs, .025)), 4), round(float(np.quantile(bs, .975)), 4)])
        out[setn] = dict(n=len(g), variants=o)
    print(json.dumps(out, indent=1)); json.dump(out, open(f'{OUT}/edge_seed.json', 'w'), indent=1)
