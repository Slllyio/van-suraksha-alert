"""Tracking step 4: fit every fire of the run set and keep its burning-time map (scratch: maps/<config>/<fire>.npz).
Run set = fires with a mid-fire photo, fires with same-day Sentinel-2/Landsat hot pixels, and the 146 big fires.
Usage: python3 t4_run.py <config> [n_boot]
  config: 'base' (VIIRS only, the main result), 'modis' (+Terra/Aqua MODIS as weaker pixels; MODIS passes within 2 h of any
          photo of the fire are left out so the photo test stays independent), or a JSON dict of HYP/EIK overrides.
  n_boot: pass-bootstrap refits for the spread of arrival times (default 0)."""
import sys, os, json, glob, pickle, time
import numpy as np, pandas as pd
from multiprocessing import Pool
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from t2_lib import *

def run_set():
    fn = f'{SC}/run_set.json'
    if os.path.exists(fn): return json.load(open(fn))
    PH = pickle.load(open(f'{R17}/photos.pkl', 'rb'))
    ph = sorted(set(int(p['fire']) for p in PH))
    F = pd.read_csv(f'{ROOT}/research/big-fires/results/fires.csv')
    big = F[(F.area_ha >= 200) & (F.n_looks >= 4) & (F.n_viirs >= 10) & ~F.still_at_edge].fire.astype(int).tolist()
    import pyproj
    tp = pyproj.Transformer.from_crs(4326, 32643, always_xy=True).transform
    H = pd.concat([pd.read_csv(f, usecols=['date', 'time_utc', 'lon', 'lat']) for f in glob.glob(f'{ROOT}/fire-alert-scars/out/af/af_20*.csv')])
    H['x'], H['y'] = tp(H.lon.values, H.lat.values); H['t'] = pd.to_datetime(H.date + ' ' + H.time_utc)
    D = data()['D']; V = D[(D.fire >= 0) & (D.kind == 'viirs')]
    from scipy.spatial import cKDTree
    tr = cKDTree(V[['x', 'y']].values); hot = set()
    for (d, tt), g in H.groupby(['date', 't']):
        for lst in tr.query_ball_point(g[['x', 'y']].values[::3], 800):
            for j in lst:
                if abs((V.t.iloc[j] - tt).total_seconds()) < 36 * 3600: hot.add(int(V.fire.iloc[j]))
    rs = dict(photo=ph, big=big, hot=sorted(hot), all=sorted(set(ph) | set(big) | hot))
    json.dump(rs, open(fn, 'w')); return rs

def config(name):
    hyp, eik = dict(HYP), dict(EIK)
    FINAL = dict(geo=250.0, lam_d=0.02, lam_n=0.0125, tau=1.5)          # chosen on even-season hidden passes (t5 tune waves)
    if name.startswith('grid'):          # free-grid MAP: Laplacian smoothness + pull to the nearest-flag start map
        hyp.update(FINAL); eik['clock'] = False; eik['grid'] = True
        hyp['sd0'] = {'grid': 12.0, 'grid6': 6.0, 'grid24': 24.0}.get(name, 12.0)
    elif name.startswith('ring'):        # edge-ring pixel response (coordinator, big-fires 14c prior) on the chosen grid12 fitter;
        hyp.update(FINAL); eik['clock'] = False; eik['grid'] = True; hyp['sd0'] = 12.0   # geo blur reduced as the ring carries part of the spread
        hyp['ring'] = 0.7; hyp['geo'] = {'ring': 120.0, 'ring250': 250.0}.get(name, 120.0)
    elif name in ('final', 'final_modis'):
        hyp.update(FINAL); eik['clock'] = False
        if name == 'final_modis': hyp['use_modis'] = True
    elif name == 'modis': hyp['use_modis'] = True
    elif name not in ('base',):
        o = json.loads(name); [hyp.update({k: v}) if k in hyp else eik.update({k: v}) for k, v in o.items()]
    return hyp, eik

def photo_times():
    PH = pickle.load(open(f'{R17}/photos.pkl', 'rb')); out = {}
    for p in PH: out.setdefault(int(p['fire']), []).append(pd.Timestamp(p['T']))
    return out

def fit_one(fire, hyp, eik, drop=None, boot=0, seed=0):
    fr = Fire(fire, hyp=hyp, drop_pass=drop)
    if not len(fr.det) or fr.n < 2: return None
    if eik.get('grid'):
        fr.fit(); ek = type('G', (), {})(); ek.T = fr.T; ek.v = np.zeros(fr.n); ek.seed_cell = np.zeros(1, int); ek.x = np.zeros(1); ek.m = 0
        ek.opt = fr.opt
    else:
        ek = Eikonal(fr, eik); fit_robust(ek)
    out = dict(fire=fire, t0=str(fr.t0), T=ek.T.astype(np.float32), v=ek.v.astype(np.float32), rr=fr.rr.astype(np.int32), cc=fr.cc.astype(np.int32),
               tr=np.array(fr.tr)[:6], shape=np.array(fr.shape), seed_cell=ek.seed_cell, seed_w=ek.x[ek.m:], n_pass=len(fr.passes),
               n_flagpass=int((~fr.free).sum()), n_det=len(fr.det), n_nodes=fr.nn, n_flags=int(fr.node_flag.sum()), n_dupes=fr.n_dupes,
               n_off=fr.n_offlattice, obj=ek.opt.fun, sd_laplace=fr.laplace_sd(np.minimum(ek.T, 1e3)).astype(np.float32))
    if boot:
        rng = np.random.default_rng(seed); Ts = []
        for b in range(boot):
            keep = rng.choice(len(fr.passes), len(fr.passes), replace=True)
            drop_b = fr.passes.pass_key.values[np.setdiff1d(np.arange(len(fr.passes)), keep)]
            fb = Fire(fire, hyp=hyp, drop_pass=list(drop_b) + (list(np.atleast_1d(drop)) if drop is not None else []))
            if not len(fb.det): continue
            if eik.get('grid'): fb.fit(); Ts.append(np.minimum(fb.T, 1e3))
            else: eb = Eikonal(fb, eik); fit_robust(eb, max_trials=10); Ts.append(np.minimum(eb.T, 1e3))
        if Ts: Ts = np.array(Ts); out['T_boot_sd'] = Ts.std(0).astype(np.float32); out['T_boot_med'] = np.median(Ts, 0).astype(np.float32)
    return out

def work(args):
    fire, name, boot = args
    od = f'{SC}/maps/{name if len(name) < 40 else __import__('hashlib').md5(name.encode()).hexdigest()[:10]}'; fn = f'{od}/{fire}.npz'
    if os.path.exists(fn): return fire
    hyp, eik = config(name); drop = None
    try:
        if hyp['use_modis']:
            pt = photo_times().get(fire, [])
            if pt:
                P = data()['P']; m = P[(P.kind == 'modis')]
                drop = [k for k, t in zip(m.pass_key, m.t) if min(abs((t - q).total_seconds()) for q in pt) < 7200]
        t = time.time(); o = fit_one(fire, hyp, eik, drop=drop, boot=boot)
        if o is None: return None
        o['secs'] = time.time() - t; np.savez_compressed(fn, **{k: np.asarray(v) for k, v in o.items()})
    except Exception as ex:
        print('fail', fire, repr(ex), flush=True); return None
    return fire

if __name__ == '__main__':
    name = sys.argv[1] if len(sys.argv) > 1 else 'base'; boot = int(sys.argv[2]) if len(sys.argv) > 2 else 0
    which = sys.argv[3] if len(sys.argv) > 3 else 'all'
    rs = run_set(); print({k: len(v) for k, v in rs.items()})
    od = f'{SC}/maps/{name if len(name) < 40 else __import__('hashlib').md5(name.encode()).hexdigest()[:10]}'; os.makedirs(od, exist_ok=True)
    fires = rs[which] if which in rs else [int(f) for f in which.split(',')]
    F = pd.read_csv(f'{ROOT}/research/big-fires/results/fires.csv').set_index('fire')
    fires = sorted(fires, key=lambda f: -F.area_ha.get(f, 0))     # biggest first (load balance)
    with Pool(4) as p:
        for i, r in enumerate(p.imap_unordered(work, [(f, name, boot) for f in fires])):
            if i % 25 == 0: print(i, r, flush=True)
    print('done', len(glob.glob(f'{od}/*.npz')))
