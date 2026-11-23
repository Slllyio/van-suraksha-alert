"""B step 3a: the fire-continuity blend map (its own code, read-only import of research/fire-continuity/scripts/c0_lib.py,
settings as chosen there: p = 4, burning clock) for the 845 tracking-run fires, to read its burned area at every VIIRS
look. Out (scratch r20_b/blend/<fire>.npz: arrival hours on the 20 m domain) and blend_area.parquet (fire, look time,
area burned by then in ha)."""
import sys, os, pickle
import numpy as np, pandas as pd
from multiprocessing import Pool
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from b_lib import *
sys.path.insert(0, f'{ROOT}/research/fire-continuity/scripts')
import c0_lib as C
from rasterio import features
from rasterio.transform import Affine
BF = f'{ROOT}/research/big-fires/results'
A = pd.read_csv(f'{BF}/fire_alerts.csv', parse_dates=['t']); A = A[A.sat != 'modis'].copy()
A['scan'] = A.scan.fillna(.375).clip(lower=.3); A['track'] = A.track.fillna(.375).clip(lower=.3)
S = pickle.load(open(f'{R17}/scars.pkl', 'rb'))
OD = f'{SC}/blend'; os.makedirs(OD, exist_ok=True)

def one(fire):
    try:
        g = A[A.fire == fire]
        if not len(g): return []
        d = C.viirs_looks(g); t0 = d.t.min(); d['th'] = (d.t - t0).dt.total_seconds() / 3600
        poly = S[fire]
        xs = np.r_[poly.bounds[0], poly.bounds[2], d.x.min(), d.x.max()]; ys = np.r_[poly.bounds[1], poly.bounds[3], d.y.min(), d.y.max()]
        r0, c0 = C.rc_of(xs.min() - 600, ys.max() + 600); r1, c1 = C.rc_of(xs.max() + 600, ys.min() - 600)
        box = C.Box(int(r0), int(r1) + 1, int(c0), int(c1) + 1)
        tr = Affine(20, 0, C.X0 + box.c0 * 20, 0, -20, C.Y0 - box.r0 * 20)
        dom = features.rasterize([poly], out_shape=box.shape, transform=tr).astype(bool)
        if dom.sum() < 2: return []
        T, lo, hi, idx, dmin = C.blend_map(box, dom, d, clock=C.Clock(t0), p=4)
        rr, cc = np.where(dom)
        np.savez_compressed(f'{OD}/{fire}.npz', T=T.astype(np.float32), x=box.X[rr, cc].astype(np.float32), y=box.Y[rr, cc].astype(np.float32), t0=str(t0))
        out = []
        for lk, gg in d.groupby('lk'):
            th = gg.th.min(); out.append(dict(fire=fire, lk=int(lk), t=gg.t.min(), th=th, area_ha=float((T <= th + 1e-6).sum() * 0.04), dom_ha=float(dom.sum() * 0.04)))
        return out
    except Exception as e:
        print('fail', fire, e, flush=True); return []

if __name__ == '__main__':
    fires = pd.read_csv(f'{V2}/tracking/results/fires_grid12.csv').fire.unique()
    with Pool(2) as p: rows = p.map(one, fires, chunksize=4)
    R = pd.DataFrame([r for rr in rows for r in rr]); R.to_parquet(f'{SC}/blend_area.parquet'); print(len(R), R.fire.nunique())
