"""Test 2b. Hidden-look test (continuity c2_hidden_looks.py idea, detections only): for every Ratapani fire with >= 3 VIIRS
looks, hide each middle VIIRS look and predict the arrival time at its detection points from the other VIIRS looks,
without and with MODIS looks. MODIS looks within 2 h of the hidden look are always dropped (Aqua passes with VIIRS, so it
would hand over the answer). Variants: + Terra only, + Terra and Aqua; footprints real or 375 m at the pixel centre.
Methods: blend (walk, p4, burning clock) and nearest look (straight line). Error = median |T - t_hidden| over the points.
Out: results/hidden_modis.parquet"""
import sys, os, pickle
sys.path.insert(0, '/mnt/project-files/research/fire-continuity/scripts')
import numpy as np, pandas as pd
from multiprocessing import Pool
from rasterio import features
from rasterio.transform import Affine
from c0_lib import *
MS = os.environ['ML_SCRATCH']; OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'results')
BF = f'{ROOT}/research/big-fires/results'
A = pd.read_csv(f'{BF}/fire_alerts.csv', parse_dates=['t']); A = A[A.sat != 'modis'].copy()
A['scan'] = A.scan.fillna(.375).clip(lower=.3); A['track'] = A.track.fillna(.375).clip(lower=.3)
F = pd.read_csv(f'{BF}/fires.csv'); F['big'] = (F.area_ha >= 200) & (F.n_looks >= 4) & (F.n_viirs >= 10) & ~F.still_at_edge
SC = pickle.load(open(f'{SCRATCH}/fire_scars.pkl', 'rb'))
RM = pd.read_parquet(f'{MS}/rat_modis.parquet')

def one(fire):
    d = viirs_looks(A[A.fire == fire])
    if d.lk.nunique() < 3: return []
    t0 = d.t.min().floor('h'); d['th'] = (d.t - t0).dt.total_seconds() / 3600
    mo = RM[RM.fire == fire].copy(); mo['th'] = (mo.t - t0).dt.total_seconds() / 3600
    poly = SC[fire]
    xs = np.r_[poly.bounds[0], poly.bounds[2], d.x.min(), d.x.max()]; ys = np.r_[poly.bounds[1], poly.bounds[3], d.y.min(), d.y.max()]
    r0, c0 = rc_of(xs.min() - 600, ys.max() + 600); r1, c1 = rc_of(xs.max() + 600, ys.min() - 600)
    box = Box(int(r0), int(r1) + 1, int(c0), int(c1) + 1)
    if box.shape[0] * box.shape[1] > 400 * 400: return []
    tr = Affine(20, 0, X0 + box.c0 * 20, 0, -20, Y0 - box.r0 * 20)
    dom = features.rasterize([poly], out_shape=box.shape, transform=tr).astype(bool)
    if dom.sum() < 10: return []
    M_, idx, rr, cc = box.graph(dom)
    looks = []   # kind, th, walk array over domain, detections frame
    def add(kind, g):
        fp = np.any([box.footprint(det, dom) for det in g.itertuples()], 0)
        looks.append((kind, g.th.min(), walk(M_, idx, fp), g))
    vl = sorted(d.lk.unique())
    for k in vl: add('V%d' % k, d[d.lk == k])
    for p, g in mo.groupby('pass'):
        add(g.kind.iloc[0], g); add(g.kind.iloc[0] + '_small', g.assign(scan=.375, track=.375))
    kinds = np.array([l[0] for l in looks]); th = np.array([l[1] for l in looks]); W_ = np.stack([l[2] for l in looks], 1)
    W_ = np.where(np.isfinite(W_), W_, 1e7)
    isV = np.char.startswith(kinds, 'V'); small = np.char.endswith(kinds, '_small'); terra = np.char.startswith(kinds, 'Terra'); isM = ~isV
    kd = cKDTree(np.c_[box.X[rr, cc], box.Y[rr, cc]])
    clk = Clock(t0); rows = []
    for k in vl[1:-1]:
        h = d[d.lk == k]; tk = h.th.min(); hid = kinds == 'V%d' % k
        pi = kd.query(np.c_[h.x, h.y])[1]
        far = np.abs(th - tk) > 2
        base = isV & ~hid
        sets = {'V': base}
        for fpn, fpm in [('real', isM & ~small), ('small', isM & small)]:
            sets[f'T_{fpn}'] = base | (fpm & terra & far); sets[f'M_{fpn}'] = base | (fpm & far)
        tprev = th[base & (th < tk)].max() if (base & (th < tk)).any() else np.nan; tnext = th[base & (th > tk)].min() if (base & (th > tk)).any() else np.nan
        inside = isM & ~small & far & (th > tprev) & (th < tnext)
        r = dict(fire=fire, look=int(k), n_pts=len(h), big=bool(F.big[F.fire == fire].iloc[0]), season=int(t0.year), gap_before=tk - tprev, gap_after=tnext - tk,
                 ist_hour=(t0 + pd.Timedelta(hours=tk + 5.5)).hour, modis_in_gaps=int(inside.sum()), terra_in_gaps=int((inside & terra).sum()))
        for nm, s in sets.items():
            r[f'nM_{nm}'] = int((s & isM).sum())
            Wk = W_[pi][:, s]; tl = th[s]
            w = 1 / (Wk + 50.0) ** 4; w /= w.sum(1, keepdims=True)
            Tb = clk.Winv((w * clk.W(tl)[None]).sum(1))
            gl = [looks[i][3] for i in np.where(s)[0]]
            EL = np.stack([eucl_footdist(h.x.values, h.y.values, g).min(1) for g in gl], 1)
            Tn = tl[np.argmin(EL, 1)]
            for meth, t in [('blend', Tb), ('nn', Tn)]:
                r[f'mae_{meth}_{nm}'] = float(np.median(np.abs(t - tk))); r[f'bias_{meth}_{nm}'] = float(np.median(t - tk))
        rows.append(r)
    return rows

if __name__ == '__main__':
    fires = sorted(A.groupby('fire').filter(lambda g: True).fire.unique())
    nl = {f: viirs_looks(g).lk.nunique() for f, g in A.groupby('fire')}
    fires = [f for f in fires if nl[f] >= 3]
    with Pool(4) as p: rows = [r for rs in p.imap_unordered(one, fires, chunksize=2) for r in rs]
    X = pd.DataFrame(rows); X.to_parquet(f'{OUT}/hidden_modis.parquet'); print(len(X), 'hidden looks', X.fire.nunique(), 'fires')
