"""Tracking step 5: hidden-pass test (hide one satellite pass, refit on all other passes, predict that pass).
Used (i) to choose the few model settings, on fires of EVEN seasons only, and (ii) to score on ODD seasons (held out).
Photos and hot pixels are never used for any choice.

Per fire: up to 2 hidden passes that flagged pixels on the fire + 1 viewing pass that flagged nothing there.
Scores:
  node level (passes that flagged): the hidden pass's pixel lattice is rebuilt from its own points (so the lattice phase is
      known; same for every method); each node's predicted P(flag) ranks flagged vs not-flagged nodes (AUC; log-loss).
  pass level: P(the pass flags anything on the fire) for flagged vs not-flagged hidden passes (AUC, Brier).
Methods: the inversion; baselines through the SAME forward model: nearest flagged pixel time (each detection separate),
  inverse-distance weighted mean of detection times p=2 (Parks-type) and p=4 (blend-type); plus a dot kernel score
  (sum exp(-d/400 m) exp(-|dt|/12 h), ranking only).
Usage: python3 t5_hidden.py tune|test  -> results/t5_hidden_<mode>.csv / .json"""
import sys, os, json
os.environ.setdefault('OMP_NUM_THREADS', '1'); os.environ.setdefault('OPENBLAS_NUM_THREADS', '1')
import numpy as np, pandas as pd
from multiprocessing import Pool
from sklearn.metrics import roc_auc_score
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from t2_lib import *
from t4_run import run_set, config

CONFIGS = ['base', '{"lam_d": 0.02, "lam_n": 0.0125}', '{"lam_d": 0.3, "lam_n": 0.18}', '{"tau": 1.5}', '{"tau": 6.0}',
           '{"q_d": 0.85, "q_n": 0.7}', '{"q_d": 0.45, "q_n": 0.3}', '{"w_neg": 0.3}', '{"clock": false}', '{"geo": 160.0}', '{"v0": 8.0}']

def pick(mode, nf=60, seed=0):
    rs = run_set(); D = data()['D']; rng = np.random.default_rng(seed); out = []
    for f in rs['all']:
        g = D[(D.fire == f) & (D.kind == 'viirs')]
        if g.pass_key.nunique() < 3: continue
        yr = g.t.min().year
        if (mode == 'tune') != (yr % 2 == 0): continue
        if mode == 'tune' and data()['S'][f].area > 1500e4: continue      # tuning on fires up to 1,500 ha (run time)
        out.append(f)
    out = list(rng.choice(out, min(nf, len(out)), replace=False))
    return [int(f) for f in out]

def idw(fr, p):
    d = fr.det
    if not len(d): return np.zeros(fr.n)
    dd = np.hypot(fr.cx[:, None] - d.xc.values[None], fr.cy[:, None] - d.yc.values[None])
    w = 1 / (dd + 50) ** p; return (w * d.th.values[None]).sum(1) / w.sum(1) - 0.5 * fr.hyp['tau']

def one(args):
    fire, name, seed = args
    hyp, eik = config(name); rng = np.random.default_rng(fire + seed)
    full = Fire(fire, hyp=hyp)
    flagged = [k for k in range(len(full.passes)) if not full.free[k]]; free = [k for k in range(len(full.passes)) if full.free[k]]
    hid = list(rng.choice(flagged, min(2, len(flagged)), replace=False)) + (list(rng.choice(free, 1)) if free else [])
    rows = []
    for k in hid:
        r = full.passes.iloc[k]; dk = full.det[full.det.pass_key == r.pass_key]
        fr = Fire(fire, hyp=hyp, drop_pass=r.pass_key)
        if not len(fr.det): continue
        if eik.get('grid'): fr.fit(); ek = type('G', (), {})(); ek.T = fr.T
        else: ek = Eikonal(fr, eik); fit_robust(ek)
        tk = (r.t - fr.t0).total_seconds() / 3600
        maps = {'inversion': ek.T, 'nearest': fr.init_T(), 'idw2': idw(fr, 2), 'idw4': idw(fr, 4)}
        lam = (hyp['lam_d'] if r.daynight == 'D' else hyp['lam_n'])
        base = dict(fire=fire, season=fr.t0.year, pass_key=r.pass_key, flagged=len(dk) > 0, n_pts=len(dk), dn=r.daynight, gap_h=float(np.min(np.abs(fr.tk - tk))) if len(fr.tk) else np.nan)
        if len(dk):
            nx, ny, fl, ds_, dt_ = full.lattice(r, dk)
            # keep nodes that see the outline
            R, C, W = fr.psf(nx, ny, r.heading, ds_, dt_, r.kind); keep = np.isin(np.arange(len(nx)), np.unique(R)) | fl
            nx, ny, fl = nx[keep], ny[keep], fl[keep]
            kern = np.zeros(len(nx))
            for t_, x_, y_ in zip(fr.det.th.values, fr.det.xc.values, fr.det.yc.values):
                kern += np.exp(-np.hypot(nx - x_, ny - y_) / 400) * np.exp(-abs(t_ - tk) / 12)
        for m, T in maps.items():
            row = dict(base, method=m)
            B, _ = fr.burn(np.minimum(T, 1e4), np.array([tk]))
            area = (np.median(dk.scan_m) * np.median(dk.track_m)) if len(dk) else r.scan_m * r.track_m
            lamk = lam * (375.0 ** 2 / area) ** hyp['gamma'] * (fr.cell / 40.0) ** 2
            qk = hyp['q_d'] if r.daynight == 'D' else hyp['q_n']; row['p_any'] = float(hyp['eps'] + qk * -np.expm1(-lamk * B[:, 0].sum()))
            if len(dk):
                p = fr.p_flag_nodes(np.minimum(T, 1e4), np.c_[nx, ny], tk, r.heading, ds_, dt_, r.kind, r.daynight)
                row['auc_node'] = roc_auc_score(fl, p) if 0 < fl.sum() < len(fl) else np.nan
                pc = np.clip(p, 1e-4, 1 - 1e-4); row['logloss_node'] = float(-(fl * np.log(pc) + (~fl) * np.log(1 - pc)).mean())
                row['n_nodes'] = len(fl); row['n_flag_nodes'] = int(fl.sum())
                row['p_flagged_nodes_mean'] = float(p[fl].mean()); row['p_other_nodes_mean'] = float(p[~fl].mean())
                if m == 'inversion':
                    rows.append(dict(base, method='kernel', auc_node=roc_auc_score(fl, kern) if 0 < fl.sum() < len(fl) else np.nan, n_nodes=len(fl)))
            rows.append(row)
    return rows

def summarize(X):
    out = {}
    for (cfg, m), g in X.groupby(['config', 'method']):
        f = g[g.flagged]; pa = g.dropna(subset=['p_any'])
        r = dict(hidden_passes=len(g), fires=int(g.fire.nunique()), auc_node_mean=round(f.auc_node.mean(), 4), logloss_node=round(f.logloss_node.mean(), 4) if 'logloss_node' in f else None)
        if pa.flagged.nunique() == 2:
            r['auc_pass'] = round(roc_auc_score(pa.flagged, pa.p_any), 4); r['brier_pass'] = round(((pa.p_any - pa.flagged) ** 2).mean(), 4)
        out[f'{cfg} | {m}'] = r
    return out

if __name__ == '__main__':
    mode = sys.argv[1]; cfgs = CONFIGS if mode == 'tune' else [sys.argv[2] if len(sys.argv) > 2 else 'base']
    tag = mode if mode != 'test' else f'test_{cfgs[0]}'
    if mode == 'tune2': mode, tag, cfgs = 'tune', 'tune2', json.loads(sys.argv[2])     # second wave: list of configs
    fires = pick(mode, nf=32 if mode == 'tune' else 80)
    rows = []
    with Pool(4) as p:
        for cfg in cfgs:
            for rr in p.imap_unordered(one, [(f, cfg, 0) for f in fires]):
                for r in rr: r['config'] = cfg; rows.append(r)
            X = pd.DataFrame(rows); X.to_csv(f'{OUT}/t5_hidden_{tag}.csv', index=False)
            print(json.dumps({k: v for k, v in summarize(X).items() if k.startswith(cfg + ' |')}), flush=True)
    json.dump(summarize(X), open(f'{OUT}/t5_hidden_{tag}.json', 'w'), indent=1)
