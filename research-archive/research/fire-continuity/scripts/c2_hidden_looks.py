"""Hidden-look test (uses detections only, never the photos). For every fire with >= 3 VIIRS looks, hide each middle look,
rebuild the growth map from the other looks, and read the map's arrival time at the hidden look's detection points.
A good map says those points burned shortly before the hidden look (they were seen burning then).
Scores per hidden look: median |T - t_hidden| (hours) and share of points with T <= t_hidden + 1 h.
This is where method choices (clock, far edge vs point, walking vs straight line, terrain) are made.
argv[1]: 'methods' (all fires, method variants) or 'terrain' (fires with >= 4 looks, terrain variants).
Out: results/hidden_<argv1>.parquet"""
import sys, os, pickle
import numpy as np, pandas as pd
from multiprocessing import Pool
from rasterio import features
from rasterio.transform import Affine
sys.path.insert(0, os.path.dirname(__file__))
from c0_lib import *

BF = f'{ROOT}/research/big-fires/results'; OUT = f'{ROOT}/research/fire-continuity/results'
MODE = sys.argv[1]
A = pd.read_csv(f'{BF}/fire_alerts.csv', parse_dates=['t']); A = A[A.sat != 'modis'].copy()
A['scan'] = A.scan.fillna(.375).clip(lower=.3); A['track'] = A.track.fillna(.375).clip(lower=.3)
F = pd.read_csv(f'{BF}/fires.csv'); F['big'] = (F.area_ha >= 200) & (F.n_looks >= 4) & (F.n_viirs >= 10) & ~F.still_at_edge
SC = pickle.load(open(f'{SCRATCH}/fire_scars.pkl', 'rb'))
TERRAIN = {'up+3': dict(up=3), 'up+6': dict(up=6), 'up-3': dict(up=-3), 'open+0.7': dict(open=.7), 'open-0.7': dict(open=-.7),
           'road_slow': dict(road=2), 'up+3_open-0.7': dict(up=3, open=-.7)}

def setup(fire):
    d = viirs_looks(A[A.fire == fire]); t0 = d.t.min().floor('h'); d['th'] = (d.t - t0).dt.total_seconds() / 3600
    poly = SC[fire]
    xs = np.r_[poly.bounds[0], poly.bounds[2], d.x.min(), d.x.max()]; ys = np.r_[poly.bounds[1], poly.bounds[3], d.y.min(), d.y.max()]
    r0, c0 = rc_of(xs.min() - 600, ys.max() + 600); r1, c1 = rc_of(xs.max() + 600, ys.min() - 600)
    box = Box(int(r0), int(r1) + 1, int(c0), int(c1) + 1)
    tr = Affine(20, 0, X0 + box.c0 * 20, 0, -20, Y0 - box.r0 * 20)
    dom = features.rasterize([poly], out_shape=box.shape, transform=tr).astype(bool)
    return d, t0, box, dom

def at_points(box, dom, idx, T, x, y):
    """Map value at the domain pixel nearest each point."""
    rr, cc = np.where(dom); k = cKDTree(np.c_[box.X[rr, cc], box.Y[rr, cc]]).query(np.c_[x, y])[1]
    return T[idx[rr[k], cc[k]]]

def one(fire):
    try:
        d, t0, box, dom = setup(fire)
    except Exception as e:
        return []
    if box.shape[0] * box.shape[1] > 400 * 400 or dom.sum() < 10: return []
    looks = sorted(d.lk.unique()); rows = []
    for k in looks[1:-1]:
        h = d[d.lk == k]; o = d[d.lk != k]; tk = h.th.min()
        T = {}
        E = eucl_footdist(h.x.values, h.y.values, o)    # base / nn read at the points directly
        T['base'] = (o.th.values[None] + E / 15).min(1)
        T['nn'] = o.th.values[np.argmin(E, 1)]
        clk = Clock(t0)
        if MODE == 'methods':
            for dist in ['line', 'walk']:
                for far in ['edge', 'centre']:
                    for cname, c in [('flat', None), ('clock', clk)]:
                        Tm, lo, hi, idx, vs = front_match(box, dom, o, clock=c, far_mode=far, dist=dist)
                        T[f'front_{dist}_{far}_{cname}'] = at_points(box, dom, idx, Tm, h.x.values, h.y.values)
        else:
            for nm, tp in [('none', None)] + list(TERRAIN.items()):
                Tm, lo, hi, idx, vs = front_match(box, dom, o, clock=clk, far_mode='edge', dist='walk', terrain=tp)
                T[f'terr_{nm}'] = at_points(box, dom, idx, Tm, h.x.values, h.y.values)
        r = dict(fire=fire, look=int(k), n_pts=len(h), big=bool(F.big[F.fire == fire].iloc[0]), season=int(F.season[F.fire == fire].iloc[0]),
                 gap_before=tk - o[o.th < tk].th.max(), gap_after=o[o.th > tk].th.min() - tk, ist_hour=(t0 + pd.Timedelta(hours=tk) + pd.Timedelta(hours=5.5)).hour)
        for nm, t in T.items():
            t = np.where(np.isfinite(t), t, T['base'])
            r[f'mae_{nm}'] = float(np.median(np.abs(t - tk))); r[f'ok_{nm}'] = float(np.mean(t <= tk + 1))
            r[f'bias_{nm}'] = float(np.median(t - tk))
        rows.append(r)
    return rows

if __name__ == '__main__':
    need = 3 if MODE == 'methods' else 4
    fires = F[F.n_looks >= need].fire.tolist()
    with Pool(4) as p: rows = [r for rs in p.imap_unordered(one, fires, chunksize=2) for r in rs]
    X = pd.DataFrame(rows); X.to_parquet(f'{OUT}/hidden_{MODE}.parquet')
    meth = [c[4:] for c in X.columns if c.startswith('mae_')]
    S = pd.DataFrame({m: [X['mae_' + m].mean(), X['ok_' + m].mean(), X['bias_' + m].median(), X[X.big]['mae_' + m].mean()] for m in meth},
                     index=['mean_abs_err_h', 'share_burned_by_then', 'median_bias_h', 'mae_big']).T.round(3)
    print(len(X), 'hidden looks,', X.fire.nunique(), 'fires'); print(S.sort_values('mean_abs_err_h'))
    S.to_csv(f'{OUT}/hidden_{MODE}_summary.csv')
