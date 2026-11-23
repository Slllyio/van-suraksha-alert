"""Tracking step 7b: Terra MODIS as an unseen sensor (never an input of the VIIRS-only maps). Terra passes ~10:30 and
~22:30 IST, hours VIIRS never sees. For each fire map and each Terra pass that flagged the fire: rebuild Terra's 1 km
pixel lattice from its points, and rank its flagged vs not-flagged nodes by
  inversion : forward-model P(flag) from the fitted burning-time map at the Terra minute (MODIS pixel response)
  nearest   : the same forward model on the nearest-flag start map
  kernel    : sum over VIIRS detections exp(-d/400 m) exp(-|dt|/12 h)
Also pass level: P(Terra flags anything) for Terra passes that did / did not flag the fire.
Usage: python3 t7b_terra.py <config> -> results/t7b_terra_<config>.json"""
import sys, os, json, glob
os.environ.setdefault('OMP_NUM_THREADS', '1')
import numpy as np, pandas as pd
from sklearn.metrics import roc_auc_score
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from t2_lib import *
from t4_run import config
from t6_photos import load_map, mapdir
name = sys.argv[1] if len(sys.argv) > 1 else 'grid12'; hyp, eik = config(name)
hm = dict(hyp); hm['use_modis'] = True
dd = data(); D, P = dd['D'], dd['P']; rows, prow = [], []
rng = np.random.default_rng(0)
for fn in sorted(glob.glob(f'{mapdir(name)}/*.npz')):
    fire = int(os.path.basename(fn)[:-4]); z = load_map(name, fire)
    fr = Fire(fire, hyp=hm)
    if not len(fr.passes): continue
    tp = fr.passes[fr.passes.sensor == 'Terra MODIS']
    if not len(tp): continue
    T = np.minimum(z['T'].astype(float), 1e4) + (z['t0'] - fr.t0).total_seconds() / 3600   # map clock -> this Fire's clock
    if len(T) != fr.n: continue
    vd = fr.det[fr.det.kind == 'viirs']
    T0 = cKDTree(vd[['xc', 'yc']].values).query(np.c_[fr.cx, fr.cy])[1] if len(vd) else None
    Tn = vd.th.values[T0] - .5 * hyp['tau'] if T0 is not None else np.zeros(fr.n)
    for r in tp.itertuples():
        dk = fr.det[fr.det.pass_key == r.pass_key]; tk = (r.t - fr.t0).total_seconds() / 3600
        B, _ = fr.burn(T, np.array([tk])); lam = (hyp['lam_d'] if r.daynight == 'D' else hyp['lam_n']) * hyp['lam_modis'] * (fr.cell / 40) ** 2
        q = hyp['q_d'] if r.daynight == 'D' else hyp['q_n']
        Bn, _ = fr.burn(Tn, np.array([tk]))
        prow.append(dict(fire=fire, flagged=len(dk) > 0, p_inv=q * (1 - np.exp(-lam * B[:, 0].sum())), p_nn=q * (1 - np.exp(-lam * Bn[:, 0].sum()))))
        if not len(dk): continue
        nx, ny, fl, ds_, dt_ = fr.lattice(r, dk)
        R, C, W = fr.psf(nx, ny, r.heading, ds_, dt_, 'modis'); keep = np.isin(np.arange(len(nx)), np.unique(R)) | fl
        nx, ny, fl = nx[keep], ny[keep], fl[keep]
        if not (0 < fl.sum() < len(fl)): continue
        p = fr.p_flag_nodes(T, np.c_[nx, ny], tk, r.heading, ds_, dt_, 'modis', r.daynight)
        pn = fr.p_flag_nodes(Tn, np.c_[nx, ny], tk, r.heading, ds_, dt_, 'modis', r.daynight)
        kern = np.zeros(len(nx))
        for t_, x_, y_ in zip(vd.th.values, vd.xc.values, vd.yc.values): kern += np.exp(-np.hypot(nx - x_, ny - y_) / 400) * np.exp(-abs(t_ - tk) / 12)
        rows.append(dict(fire=fire, dn=r.daynight, n_nodes=len(fl), n_flag=int(fl.sum()), auc_inversion=roc_auc_score(fl, p), auc_nearest=roc_auc_score(fl, pn), auc_kernel=roc_auc_score(fl, kern)))
X, Pp = pd.DataFrame(rows), pd.DataFrame(prow)
def bt(a, b):
    g = X.groupby('fire')[[a, b]].mean(); d = (g[a] - g[b]).values; bs = [rng.choice(d, len(d)).mean() for _ in range(2000)]
    return [round(float(d.mean()), 4), round(float(np.quantile(bs, .025)), 4), round(float(np.quantile(bs, .975)), 4)]
res = dict(config=name, terra_flagged_passes=len(X), fires=int(X.fire.nunique()) if len(X) else 0, auc_mean={m: round(X[f'auc_{m}'].mean(), 4) for m in ['inversion', 'nearest', 'kernel']},
           inversion_minus_nearest=bt('auc_inversion', 'auc_nearest'), inversion_minus_kernel=bt('auc_inversion', 'auc_kernel'),
           by_daynight={dn: dict(n=len(g), **{m: round(g[f'auc_{m}'].mean(), 4) for m in ['inversion', 'nearest', 'kernel']}) for dn, g in X.groupby('dn')},
           pass_level=dict(passes=len(Pp), flagged_share=round(Pp.flagged.mean(), 3), auc_inversion=round(roc_auc_score(Pp.flagged, Pp.p_inv), 4), auc_nearest=round(roc_auc_score(Pp.flagged, Pp.p_nn), 4)))
json.dump(res, open(f'{OUT}/t7b_terra_{name}.json', 'w'), indent=1); print(json.dumps(res, indent=1))
