"""Test 2a. Add Terra/Aqua MODIS looks to the continuity thread's arrival maps and score on the mid-fire photos.
Reuses research/fire-continuity/scripts/c0_lib.py read-only (imported) and copies the photo/fire matching of c1_photos.py.
Each MODIS pass on the fire (one satellite within 15 min, from m1b) is one extra look; its footprint is the real
scan x track box ('real') or a 375 m box at the pixel centre ('small').
Reconstruction maps use every VIIRS look (before and after the photo), as in c1. MODIS filters:
  a  : MODIS looks at least 3 h before the photo (up to the night before)    -> honest about the photo minute
  a2 : all MODIS except within 3 h of the photo (adds later Aqua/Terra looks)
  b  : all MODIS, including Terra-day at the photo minute (near-simultaneous: "what is burning now")
Forecast maps (only what was seen before the photo): VIIRS >= 1 h before; + MODIS (a) >= 3 h before; (b) up to +1 h.
Methods: blend (walk, p4, burning clock: the continuity choice), nearest look (straight line), base forecast
(t_j + distance/15 m/h), closest footprint (ranking of the spread review's honest distance table).
Out: results/photo_modis.parquet (one row per photo), printed summary."""
import sys, glob, os, pickle
sys.path.insert(0, '/mnt/project-files/research/fire-continuity/scripts')
import numpy as np, pandas as pd
from multiprocessing import Pool
from rasterio import features
from rasterio.transform import Affine
from sklearn.metrics import roc_auc_score
from c0_lib import *          # needs FC_SCRATCH = folder holding fire_scars.pkl
MS = os.environ['ML_SCRATCH']; OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'results')
BF = f'{ROOT}/research/big-fires/results'; TD = f'{ROOT}/fuel-map/ratapani/timing/'
A = pd.read_csv(f'{BF}/fire_alerts.csv', parse_dates=['t']); A = A[A.sat != 'modis'].copy()
A['scan'] = A.scan.fillna(.375).clip(lower=.3); A['track'] = A.track.fillna(.375).clip(lower=.3)
F = pd.read_csv(f'{BF}/fires.csv'); F['big'] = (F.area_ha >= 200) & (F.n_looks >= 4) & (F.n_viirs >= 10) & ~F.still_at_edge
SC = pickle.load(open(f'{SCRATCH}/fire_scars.pkl', 'rb'))
ms = pd.read_parquet(TD + 'midscar.parquet'); ms = ms[ms.status == 'ok']
tree = cKDTree(A[['x', 'y']].values)
RM = pd.read_parquet(f'{MS}/rat_modis.parquet')
RM['pid'] = RM['pass'].astype(int)
def auc(y, s): return roc_auc_score(y, s) if 0 < y.sum() < len(y) else np.nan

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
    mo = RM[RM.fire == fire].copy(); mo['th'] = (mo.t - T).dt.total_seconds() / 3600
    poly = SC[fire]
    xs = np.r_[poly.bounds[0], poly.bounds[2], px.min(), px.max(), d.x.min(), d.x.max()]
    ys = np.r_[poly.bounds[1], poly.bounds[3], py.min(), py.max(), d.y.min(), d.y.max()]
    r0, c0 = rc_of(xs.min() - 600, ys.max() + 600); r1, c1 = rc_of(xs.max() + 600, ys.min() - 600)
    box = Box(int(r0), int(r1) + 1, int(c0), int(c1) + 1)
    tr = Affine(20, 0, X0 + box.c0 * 20, 0, -20, Y0 - box.r0 * 20)
    dom = features.rasterize([poly], out_shape=box.shape, transform=tr).astype(bool)
    ri, ci = rr + i0 - box.r0, cc + j0 - box.c0
    sr, scc = np.where(Sm); dom[sr + i0 - box.r0, scc + j0 - box.c0] = True
    y = bym[rr, cc].astype(int)
    M_, idx_, _, _ = box.graph(dom)
    # per-look distances (straight line and walking) from chip pixels to each look's footprints
    looks = []   # (kind, th, Eline, Ewalk)
    def add(kind, g):
        Eline = eucl_footdist(px, py, g).min(1)
        fp = np.any([box.footprint(det, dom) for det in g.itertuples()], 0)
        Ew = walk(M_, idx_, fp)[idx_[ri, ci]]
        looks.append((kind, g.th.min(), Eline, np.where(np.isfinite(Ew), Ew, Eline)))
    for k in sorted(d.lk.unique()): add('V', d[d.lk == k])
    for p, g in mo.groupby('pid'):
        add(g.kind.iloc[0], g); add(g.kind.iloc[0] + '_small', g.assign(scan=.375, track=.375))
    kinds = np.array([l[0] for l in looks]); th = np.array([l[1] for l in looks])
    EL = np.stack([l[2] for l in looks], 1); EW = np.stack([l[3] for l in looks], 1)
    isV = kinds == 'V'; isM = ~isV; small = np.char.endswith(kinds.astype(str), '_small'); terra = np.char.startswith(kinds.astype(str), 'Terra')
    clk = Clock(T)
    res = dict(event=ev, scene=sc, T=T, season=T.year, fire=fire, big=bool(F.big[F.fire == fire].iloc[0]), n_px=len(rr), obs_frac=y.mean(),
               n_looks=int(isV.sum()), looks_before=int((isV & (th < 0)).sum()), looks_after=int((isV & (th > 0)).sum()))
    sets = {'V': isV}
    for fp_name, fpm in [('real', isM & ~small), ('small', isM & small)]:
        sets[f'a_T_{fp_name}'] = isV | (fpm & terra & (th <= -3))
        sets[f'a_M_{fp_name}'] = isV | (fpm & (th <= -3))
        sets[f'a2_M_{fp_name}'] = isV | (fpm & (np.abs(th) > 3))
        sets[f'b_M_{fp_name}'] = isV | fpm
        sets[f'b_T_{fp_name}'] = isV | (fpm & terra)
    for nm, s in sets.items():
        res[f'nM_{nm}'] = int((s & isM).sum())
        tl = th[s]
        w = 1 / (EW[:, s] + 50.0) ** 4; w /= w.sum(1, keepdims=True)
        Tb = clk.Winv((w * clk.W(tl)[None]).sum(1))
        Tn = tl[np.argmin(EL[:, s], 1)]
        for meth, t in [('blend', Tb), ('nn', Tn)]:
            res[f'acc_{meth}_{nm}'] = ((t <= 0) == y).mean(); res[f'auc_{meth}_{nm}'] = auc(y, -t); res[f'frac_{meth}_{nm}'] = (t <= 0).mean()
    # forecasts: only looks before the photo
    fsets = {'fcV': isV & (th <= -1)}
    for fp_name, fpm in [('real', isM & ~small), ('small', isM & small)]:
        fsets[f'fc_a_{fp_name}'] = fsets['fcV'] | (fpm & (th <= -3))
        fsets[f'fc_b_{fp_name}'] = fsets['fcV'] | (fpm & (th <= 1))
    for nm, s in fsets.items():
        res[f'nM_{nm}'] = int((s & isM).sum())
        if not s.any(): continue
        Tf = (th[s][None] + EL[:, s] / 15).min(1); Dm = EL[:, s].min(1)
        res[f'acc_base_{nm}'] = ((Tf <= 0) == y).mean(); res[f'auc_base_{nm}'] = auc(y, -Tf); res[f'auc_dist_{nm}'] = auc(y, -Dm)
        res[f'frac_base_{nm}'] = (Tf <= 0).mean()
    # burned share inside MODIS footprints (real), outside every VIIRS footprint seen before the photo
    preV = isV & (th < 0)
    outV = (EL[:, preV].min(1) > 0) if preV.any() else np.ones(len(y), bool)
    res['inV_n'] = int((~outV).sum()); res['inV_b'] = int(y[~outV].sum())
    for nm, s in [('TN_before', (kinds == 'Terra_N') & (th <= -3) & (th >= -16)), ('TD_now', (kinds == 'Terra_D') & (np.abs(th) <= 1.5)),
                  ('AQ_before', np.char.startswith(kinds.astype(str), 'Aqua') & ~small & (th <= -3) & (th >= -16))]:
        if s.any():
            inside = EL[:, s].min(1) == 0
            res[f'{nm}_n'] = int((inside & outV).sum()); res[f'{nm}_b'] = int(y[inside & outV].sum())
            res[f'{nm}_nall'] = int(inside.sum()); res[f'{nm}_ball'] = int(y[inside].sum())
    res['out_n'] = int(outV.sum()); res['out_b'] = int(y[outV].sum())
    return res

if __name__ == '__main__':
    files = sorted(glob.glob(TD + 'chips/*.npz'))
    with Pool(4) as p: rows = [r for r in p.map(one, files, chunksize=4) if r]
    X = pd.DataFrame(rows); X.to_parquet(f'{OUT}/photo_modis.parquet'); print(len(X), 'photos')
