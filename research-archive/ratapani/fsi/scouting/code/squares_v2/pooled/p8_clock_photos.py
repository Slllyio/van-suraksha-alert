"""Step 8a: does the displacement-derived diurnal rate curve improve the continuity thread's blend map on the 340 mid-fire
photos (independent truth)? Same set-up as research/fire-continuity/scripts/c1_photos.py (blend: every VIIRS look pulls a
pixel's time with weight 1/(walking distance + 50 m)^4, averaged on a burning clock); only the clock changes:
  flat    : ordinary time
  modis   : the current clock (MODIS detection counts, peak 15:00, width 4.3 h, night floor 8%)
  pooled  : this thread's curve from pooled outward speeds, fitted on all-MP pairs OUTSIDE Ratapani (spatially held out):
            forest curve peak 14:00, width 3.75 h, floor 6.3 / 36.2 = 17% of peak
Nothing is fitted on the photos. Also the time-of-nearest-look rule for reference. Read-only use of the continuity code.
Out: results/photo_clock.csv, results/photo_clock_summary.json"""
import sys, glob, os, json, pickle
os.environ.setdefault('FC_SCRATCH', '/tmp/claude-0/-home-user/be9b8f54-cc26-52cb-bdbb-9c8008a24baf/scratchpad/r19_pool')
import numpy as np, pandas as pd
from multiprocessing import Pool
from rasterio import features
from rasterio.transform import Affine
from sklearn.metrics import roc_auc_score
sys.path.insert(0, '/mnt/project-files/research/fire-continuity/scripts')
from c0_lib import *
HERE = os.path.dirname(os.path.abspath(__file__)); OUT = f'{HERE}/results'
BF = f'{ROOT}/research/big-fires/results'; TD = f'{ROOT}/fuel-map/ratapani/timing/'
FIT = json.load(open(f'{OUT}/diurnal_fit_noratapani.json'))['forest']
class CurveClock(Clock):
    def __init__(self, t0, base_rel, pk, s, th_range=(-200, 200)):
        self.flat = False
        th = np.arange(th_range[0], th_range[1], 1 / 30)
        ist = (pd.Timestamp(t0).hour + pd.Timestamp(t0).minute / 60 + 5.5 + th) % 24
        dh = (ist - pk + 12) % 24 - 12
        r = base_rel + (1 - base_rel) * np.exp(-dh ** 2 / (2 * s ** 2)); r = r / r.mean()
        w = np.concatenate([[0], np.cumsum(r[:-1] / 30)]); w -= np.interp(0, th, w)
        self.th, self.w = th, w
BREL = FIT['base_m_h'] / (FIT['base_m_h'] + FIT['amp_m_h'])
A = pd.read_csv(f'{BF}/fire_alerts.csv', parse_dates=['t']); A = A[A.sat != 'modis'].copy()
A['scan'] = A.scan.fillna(.375).clip(lower=.3); A['track'] = A.track.fillna(.375).clip(lower=.3)
F = pd.read_csv(f'{BF}/fires.csv'); F['big'] = (F.area_ha >= 200) & (F.n_looks >= 4) & (F.n_viirs >= 10) & ~F.still_at_edge
SCR = pickle.load(open(f'{SCRATCH}/fire_scars.pkl', 'rb'))
ms = pd.read_parquet(TD + 'midscar.parquet'); ms = ms[ms.status == 'ok']
tree = cKDTree(A[['x', 'y']].values)
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
    poly = SCR[fire]
    xs = np.r_[poly.bounds[0], poly.bounds[2], px.min(), px.max(), d.x.min(), d.x.max()]
    ys = np.r_[poly.bounds[1], poly.bounds[3], py.min(), py.max(), d.y.min(), d.y.max()]
    r0, c0 = rc_of(xs.min() - 600, ys.max() + 600); r1, c1 = rc_of(xs.max() + 600, ys.min() - 600)
    box = Box(int(r0), int(r1) + 1, int(c0), int(c1) + 1)
    tr = Affine(20, 0, X0 + box.c0 * 20, 0, -20, Y0 - box.r0 * 20)
    dom = features.rasterize([poly], out_shape=box.shape, transform=tr).astype(bool)
    ri, ci = rr + i0 - box.r0, cc + j0 - box.c0
    sr, scc = np.where(Sm); dom[sr + i0 - box.r0, scc + j0 - box.c0] = True
    y = bym[rr, cc].astype(int)
    res = dict(event=ev, scene=sc, T=T, season=T.year, fire=fire, big=bool(F.big[F.fire == fire].iloc[0]), n_px=len(rr),
               looks_before=int((d.groupby('lk').th.min() < 0).sum()), looks_after=int((d.groupby('lk').th.min() > 0).sum()))
    E = eucl_footdist(px, py, d)
    Tm = {'nn': d.th.values[np.argmin(E, 1)]}
    looks = sorted(d.lk.unique()); tlk = np.array([d[d.lk == k].th.min() for k in looks])
    Eline = np.stack([E[:, (d.lk == k).values].min(1) for k in looks], 1)
    M_, idx_, rr_, cc_ = box.graph(dom)
    Ewalk = np.stack([walk(M_, idx_, np.any([box.footprint(det, dom) for det in d[d.lk == k].itertuples()], 0))[idx_[ri, ci]] for k in looks], 1)
    Ewalk = np.where(np.isfinite(Ewalk), Ewalk, Eline)
    clocks = {'flat': Clock(T, flat=True), 'modis': Clock(T), 'pooled': CurveClock(T, BREL, FIT['peak_ist'], FIT['width_h'])}
    w = 1 / (Ewalk + 50.0) ** 4; w /= w.sum(1, keepdims=True)
    for cname, c in clocks.items():
        Tm[f'blend_{cname}'] = c.Winv((w * c.W(tlk)[None]).sum(1))
    for k, t in Tm.items():
        pred = t <= 0
        res[f'acc_{k}'] = (pred == y).mean(); res[f'frac_{k}'] = pred.mean(); res[f'auc_{k}'] = auc(y, -t)
    res['obs_frac'] = y.mean()
    return res
if __name__ == '__main__':
    files = sorted(glob.glob(TD + 'chips/*.npz'))
    with Pool(3) as p: rows = [r for r in p.map(one, files, chunksize=4) if r]
    X = pd.DataFrame(rows); X.to_csv(f'{OUT}/photo_clock.csv', index=False)
    rng = np.random.default_rng(8); out = {'photos': len(X), 'fires': int(X.fire.nunique())}
    for nm, g in [('all', X), ('look before and after', X[(X.looks_before > 0) & (X.looks_after > 0)]), ('big fires', X[X.big])]:
        r = {k: dict(acc=round(g['acc_' + k].mean(), 4), auc=round(g['auc_' + k].mean(), 4), burned_share_error=round((g['frac_' + k] - g.obs_frac).mean(), 3)) for k in ['nn', 'blend_flat', 'blend_modis', 'blend_pooled']}
        for a, b in [('blend_pooled', 'blend_modis'), ('blend_pooled', 'blend_flat'), ('blend_modis', 'blend_flat')]:
            for met in ['acc', 'auc']:
                dfr = (g[f'{met}_{a}'] - g[f'{met}_{b}']).groupby(g.fire).mean(); bs = [dfr.sample(frac=1, replace=True, random_state=i).mean() for i in range(1000)]
                r[f'{a} - {b} ({met})'] = f'{dfr.mean():+.4f} ({np.quantile(bs, .025):+.4f} to {np.quantile(bs, .975):+.4f})'
        out[nm] = dict(n=len(g), **r)
    json.dump(out, open(f'{OUT}/photo_clock_summary.json', 'w'), indent=1); print(json.dumps(out, indent=1))
