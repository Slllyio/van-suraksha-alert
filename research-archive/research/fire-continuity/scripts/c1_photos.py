"""Score continuity methods on the mid-fire Sentinel-2/Landsat photos (independent truth: burned-so-far at the photo minute,
fuel-map/ratapani/timing/chips; chip grid = burn-label raster grid = grid20 shifted by 100 rows / 100 cols).

Methods use ALL VIIRS detections of the fire (before and after the photo): this is a reconstruction ("how did it grow"),
not a forecast. No method is fitted on the photos: speeds are fixed (15 m/h tail) or come from the detections themselves.
Variants (clock, far edge vs point, walking vs straight, terrain) are all scored; c4_choose.py picks with seasons held out.
Out: results/photo_scores.parquet
"""
import sys, glob, os, json, pickle
import numpy as np, pandas as pd
from multiprocessing import Pool
from rasterio import features
from rasterio.transform import Affine
from sklearn.metrics import roc_auc_score
sys.path.insert(0, os.path.dirname(__file__))
from c0_lib import *

BF = f'{ROOT}/research/big-fires/results'; TD = f'{ROOT}/fuel-map/ratapani/timing/'
OUT = f'{ROOT}/research/fire-continuity/results'
TERRAIN = {'up+3': dict(up=3), 'up+6': dict(up=6), 'up-3': dict(up=-3), 'open+0.7': dict(open=.7), 'open-0.7': dict(open=-.7),
           'road_slow': dict(road=2), 'up+3_open-0.7': dict(up=3, open=-.7)}
A = pd.read_csv(f'{BF}/fire_alerts.csv', parse_dates=['t']); A = A[A.sat != 'modis'].copy()
A['scan'] = A.scan.fillna(.375).clip(lower=.3); A['track'] = A.track.fillna(.375).clip(lower=.3)
F = pd.read_csv(f'{BF}/fires.csv'); F['big'] = (F.area_ha >= 200) & (F.n_looks >= 4) & (F.n_viirs >= 10) & ~F.still_at_edge
SC = pickle.load(open(f'{SCRATCH}/fire_scars.pkl', 'rb'))
ms = pd.read_parquet(TD + 'midscar.parquet'); ms = ms[ms.status == 'ok']
tree = cKDTree(A[['x', 'y']].values)
DET = pd.read_csv(f'{BF}/detections.csv', parse_dates=['t'])   # every pass of every sensor, kept separate (big-fires thread)

def auc(y, s):
    return roc_auc_score(y, s) if 0 < y.sum() < len(y) else np.nan

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
    # window: fire outline + chip + detections, 600 m margin
    xs = np.r_[poly.bounds[0], poly.bounds[2], px.min(), px.max(), d.x.min(), d.x.max()]
    ys = np.r_[poly.bounds[1], poly.bounds[3], py.min(), py.max(), d.y.min(), d.y.max()]
    r0, c0 = rc_of(xs.min() - 600, ys.max() + 600); r1, c1 = rc_of(xs.max() + 600, ys.min() - 600)
    box = Box(int(r0), int(r1) + 1, int(c0), int(c1) + 1)
    tr = Affine(20, 0, X0 + box.c0 * 20, 0, -20, Y0 - box.r0 * 20)
    dom = features.rasterize([poly], out_shape=box.shape, transform=tr).astype(bool)
    ri, ci = rr + i0 - box.r0, cc + j0 - box.c0
    sr, scc = np.where(Sm); dom[sr + i0 - box.r0, scc + j0 - box.c0] = True
    y = bym[rr, cc].astype(int)
    res = dict(event=ev, scene=sc, T=T, season=T.year, fire=fire, big=bool(F.big[F.fire == fire].iloc[0]),
               n_px=len(rr), obs_frac=y.mean(), n_looks=int(d.lk.nunique()),
               looks_before=int((d.groupby('lk').th.min() < 0).sum()), looks_after=int((d.groupby('lk').th.min() > 0).sum()),
               h_after_first=-d.th.min())
    Tm = {}
    E = eucl_footdist(px, py, d)
    Tm['base'] = (d.th.values[None] + E / 15).min(1)
    Tm['nn'] = d.th.values[np.argmin(E, 1)]
    Tg, idx = forward(box, dom, d); Tm['geo'] = Tg[idx[ri, ci]]
    clk = Clock(T)
    Tf, lo, hi, idx, vs = front_match(box, dom, d, clock=clk); k = idx[ri, ci]
    Tm['front_walk_edge_clock'] = Tf[k]; LO, HI = lo[k], hi[k]
    for dist in ['line', 'walk']:
        for far in ['edge', 'centre']:
            for cname, c in [('flat', None), ('clock', clk)]:
                nm = f'front_{dist}_{far}_{cname}'
                if nm in Tm: continue
                Tt, *_ = front_match(box, dom, d, clock=c, far_mode=far, dist=dist); Tm[nm] = Tt[idx[ri, ci]] if dist == 'walk' else Tt[_[2][ri, ci]]
    # BLEND: each look pulls the pixel's time toward its own, weighted 1/distance^p (in burning-clock time). p large = nearest look.
    looks = sorted(d.lk.unique()); tlk = np.array([d[d.lk == k].th.min() for k in looks])
    Eline = np.stack([E[:, (d.lk == k).values].min(1) for k in looks], 1)
    M_, idx_, rr_, cc_ = box.graph(dom)
    Ewalk = np.stack([walk(M_, idx_, np.any([box.footprint(det, dom) for det in d[d.lk == k].itertuples()], 0))[idx_[ri, ci]] for k in looks], 1)
    Ewalk = np.where(np.isfinite(Ewalk), Ewalk, Eline)
    for dname, Ek in [('line', Eline), ('walk', Ewalk)]:
        for pw in [1, 2, 4]:
            w = 1 / (Ek + 50.0) ** pw; w /= w.sum(1, keepdims=True)
            for cname, c in [('flat', Clock(T, flat=True)), ('clock', clk)]:
                Tm[f'blend_{dname}_p{pw}_{cname}'] = c.Winv((w * c.W(tlk)[None]).sum(1))
    # JOINT: one speed per fire through every pass of every sensor (VIIRS, MODIS, S2/Landsat hot pixels; anything within
    # 2 h of the photo dropped, so the photo's own scene is never used). Front distance of a pass = 90th percentile of the
    # walking distance of its detections from the first VIIRS look; fit front = c + v * (time since first look) through all
    # passes at once; T(x) = when that front reaches x.
    P = DET[(DET.fire == fire) & ((DET.t - T).abs() > pd.Timedelta(hours=2))].copy()
    P['th'] = (P.t - T).dt.total_seconds() / 3600
    first = d[d.lk == d.lk.min()]; seed = np.any([box.footprint(det, dom) for det in first.itertuples()], 0)
    D0 = walk(M_, idx_, seed)
    rr_all, cc_all = np.where(dom); q = cKDTree(np.c_[box.X[rr_all, cc_all], box.Y[rr_all, cc_all]]).query(np.c_[P.x, P.y])[1]
    P['D'] = D0[idx_[rr_all[q], cc_all[q]]]
    t1 = first.th.min(); P = P[(P.th > t1 + 0.5) & np.isfinite(P.D)]
    Dx = D0[idx_[ri, ci]]; Dx = np.where(np.isfinite(Dx), Dx, E.min(1))
    for cname, c in [('flat', Clock(T, flat=True)), ('clock', clk)]:
        v, c0 = 25.0, 0.0
        if P.pass_id.nunique() >= 2:
            g = P.groupby('pass_id').agg(f=('D', lambda u: np.quantile(u, .9)), th=('th', 'min'))
            xw = c.W(g.th.values) - c.W(t1)
            if np.ptp(xw) > 1:
                v1, c1_ = np.polyfit(xw, g.f.values, 1)
                if v1 > 1: v, c0 = v1, max(c1_, 0)
        Tm[f'joint_{cname}'] = c.Winv(c.W(t1) + np.maximum(Dx - c0, 0) / v)
        res[f'joint_v_{cname}'] = v
    for name, tp in TERRAIN.items():
        Tt, *_ = front_match(box, dom, d, clock=clk, terrain=tp); Tm['terr_' + name] = Tt[idx[ri, ci]]
    for kname in Tm:   # pixels the walk can't reach (cut off from the rest of the outline): straight-line arrival map
        Tm[kname] = np.where(np.isfinite(Tm[kname]), Tm[kname], Tm['base'])
    LO, HI = np.where(np.isfinite(LO) | np.isfinite(HI), LO, -np.inf), HI
    for kname, t in Tm.items():
        pred = t <= 0
        res[f'acc_{kname}'] = (pred == y).mean(); res[f'frac_{kname}'] = pred.mean(); res[f'auc_{kname}'] = auc(y, -t)
    und = (LO <= 0) & (HI > 0)          # pixels the looks alone cannot decide (fire was between two looks there)
    res['n_undecided'] = int(und.sum()); res['undecided_share'] = und.mean()
    for kname, t in Tm.items():
        res[f'accU_{kname}'] = ((t[und] <= 0) == y[und]).mean() if und.sum() >= 20 else np.nan
    res['bracket_right'] = np.mean(np.where(HI <= 0, y == 1, np.where(LO > 0, y == 0, True)))
    res['v_med'] = float(np.median(vs)) if vs else np.nan
    return res

if __name__ == '__main__':
    files = sorted(glob.glob(TD + 'chips/*.npz'))
    with Pool(8) as p: rows = [r for r in p.map(one, files, chunksize=4) if r]
    X = pd.DataFrame(rows); X.to_parquet(f'{OUT}/photo_scores.parquet'); print(len(X), 'photos')
    meth = [c[4:] for c in X.columns if c.startswith('acc_')]
    for nm, g in [('all', X), ('both sides', X[(X.looks_before > 0) & (X.looks_after > 0)]), ('big', X[X.big])]:
        print(nm, len(g), {k: (round(g['acc_' + k].mean(), 3), round(g['auc_' + k].mean(), 3)) for k in meth})
