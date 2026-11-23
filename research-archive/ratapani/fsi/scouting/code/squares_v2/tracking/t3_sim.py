"""Tracking step 3: synthetic-truth recovery test (does the inversion recover a known burning-time map?), and what the
VNP14IMG fire masks would add.

For a real fire's outline and its real pass schedule (times, sensors, pixel sizes, orientation):
  truth  : arrival time from one ignition cell by shortest-path walking at a patchy speed (lognormal, median v0 m/h,
           smooth on ~300 m) modulated by the burning clock (fast afternoon, ~10x slower at night; continuity diurnal.json).
  data   : each pass gets a random lattice phase and +-geolocation error (80 m); every node flags with the model probability;
           a share of passes (cloud) flags nothing. FIRMS-like: only flagged points are kept.
  fits   : (A) FIRMS mode: lattice rebuilt from the flagged points, passes with no flag enter phase-free, cloudy passes are
           read as clear (cloud unknown);
           (B) fire-mask mode (what VNP14IMG gives): true lattice for every pass, cloudy passes dropped, no geolocation
           error in the lattice of passes with no flag.
  scores : mean |T_est - T_true| (h) over cells burned during the observed window; "photo" accuracy at 10:30 IST times;
           compared with the start map (time of the nearest flagged pixel) and a blend map (inverse-distance^4 of flagged
           points' times).
Out: results/t3_sim.csv, results/t3_sim_summary.json
"""
import sys, os, json, copy
import numpy as np, pandas as pd
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import dijkstra
from scipy.spatial import cKDTree
from scipy.ndimage import gaussian_filter
sys.path.insert(0, '/mnt/project-files/ratapani/fsi/scouting/code/squares_v2/tracking')
from t2_lib import *
from t4_run import config
HYPF, EIKF = config(os.environ.get('SIM_CFG', 'grid12'))
import os

def clock_rate(t_utc):
    p = json.load(open(f'{ROOT}/research/fire-continuity/results/diurnal.json'))
    ist = (t_utc.hour + t_utc.minute / 60 + 5.5) % 24
    dh = (ist - p['peak_ist'] + 12) % 24 - 12
    r = p['base'] + (1 - p['base']) * np.exp(-dh ** 2 / (2 * p['width_h'] ** 2))
    return r

def truth_T(fr, rng, v0=25.0):
    """Fire-hours walking from a random ignition cell (within the first look's footprints) -> real hours with the clock."""
    z = rng.normal(0, 1, fr.shape); z = gaussian_filter(z, 300 / fr.cell / 2); z = z / (z.std() + 1e-9) * 0.6
    v = v0 * np.exp(z[fr.rr, fr.cc])
    a, b = fr.nb[:, 0], fr.nb[:, 1]; L = fr.cell / (.5 * (v[a] + v[b]))
    M = coo_matrix((np.r_[L, L], (np.r_[a, b], np.r_[b, a])), shape=(fr.n, fr.n)).tocsr()
    d0 = fr.det.sort_values('t'); ig = fr.ctree.query(d0[['xc', 'yc']].values[0])[1]
    W = dijkstra(M, indices=ig)            # fire-hours after ignition
    for _ in range(rng.integers(0, 3)):    # extra (spot / separate) ignitions
        j = rng.integers(fr.n); W = np.minimum(W, rng.uniform(6, 30) + dijkstra(M, indices=j))
    # convert fire-hours to clock hours: integrate rate from ignition time t_ig = first detection - 3 h
    tt = np.arange(-6, fr.thi + 48, 1 / 12); rate = np.array([clock_rate(fr.t0 + pd.Timedelta(hours=float(x))) for x in tt[::12]])
    rate = np.repeat(rate, 12)[:len(tt)]; rate = rate / rate.mean()
    cum = np.cumsum(rate) / 12; cum -= cum[0]
    T = np.interp(W, cum, tt) if np.isfinite(W).any() else W
    T[~np.isfinite(W)] = 1e3
    return T - 3.0

def simulate(fr, Ttrue, rng, cloud=0.1, geo=80.0, hyp=HYP):
    """Synthetic FIRMS points + the full-mask observation for every pass of fr.passes."""
    pts, mask = [], []
    for k, r in enumerate(fr.passes.itertuples()):
        us, ut = axes(r.heading); ds_, dt_ = r.scan_m, r.track_m * TRACK_SPACING
        ph = rng.uniform(0, 1, 2); cx, cy = fr.cx.mean(), fr.cy.mean()
        x0, y0, x1, y1 = fr.bounds; span = np.hypot(x1 - x0, y1 - y0) / 2 + 1500
        I = np.arange(-np.ceil(span / ds_), np.ceil(span / ds_) + 1) + ph[0]; J = np.arange(-np.ceil(span / dt_), np.ceil(span / dt_) + 1) + ph[1]
        II, JJ = np.meshgrid(I, J); II, JJ = II.ravel(), JJ.ravel()
        nx = cx + II * ds_ * us[0] + JJ * dt_ * ut[0]; ny = cy + II * ds_ * us[1] + JJ * dt_ * ut[1]
        g = rng.normal(0, geo, 2)          # true geolocation error of this pass (shifts the whole lattice)
        p = fr.p_flag_nodes(Ttrue, np.c_[nx + g[0], ny + g[1]], fr.tk[k], r.heading, ds_, dt_, r.kind, r.daynight)
        cloudy = rng.uniform() < cloud
        fl = (rng.uniform(size=len(p)) < p) & (not cloudy)
        mask.append(dict(k=k, nx=nx, ny=ny, flag=fl, cloudy=cloudy))
        for x, y in zip(nx[fl], ny[fl]):
            pts.append(dict(pass_key=r.pass_key, xc=x, yc=y, th=fr.tk[k], t=fr.t0 + pd.Timedelta(hours=float(fr.tk[k])), scan_m=r.scan_m, track_m=r.track_m))
    return pd.DataFrame(pts, columns=['pass_key', 'xc', 'yc', 'th', 't', 'scan_m', 'track_m']), mask

def fit_firms(fr, pts):
    f = copy.copy(fr); f.det = pts; f.build_obs(); f.T0 = f.init_T(); (f.fit() if EIKF.get('grid') else fit_robust(Eikonal(f, EIKF))); return f

def fit_mask(fr, mask):
    """Full fire mask: true lattice for every non-cloudy pass (flags and clear nodes); cloudy passes dropped."""
    f = copy.copy(fr); rows, cols, ws, npass, nflag = [], [], [], [], []; nn = 0
    for m in mask:
        if m['cloudy']: continue
        r = fr.passes.iloc[m['k']]
        R, C, W = f.psf(m['nx'], m['ny'], r.heading, r.scan_m, r.track_m * TRACK_SPACING, r.kind)
        used = np.unique(R); keep = np.isin(np.arange(len(m['nx'])), used)
        remap = -np.ones(len(m['nx']), int); remap[keep] = np.arange(keep.sum()) + nn
        rows.append(remap[R]); cols.append(C); ws.append(W); npass.append(np.full(keep.sum(), m['k'])); nflag.append(m['flag'][keep]); nn += keep.sum()
    f.R, f.C, f.W = np.concatenate(rows), np.concatenate(cols), np.concatenate(ws)
    f.node_pass, f.node_flag = np.concatenate(npass), np.concatenate(nflag); f.nn = nn
    f.lamR = f.lam_pass[f.node_pass[f.R]]; f.Rpass = f.node_pass[f.R]; f.free = np.zeros(len(f.passes), bool)
    pts = pd.DataFrame([dict(xc=x, yc=y, th=fr.tk[m['k']]) for m in mask for x, y in zip(m['nx'][m['flag']], m['ny'][m['flag']])])
    f.det = pts if len(pts) else fr.det
    f.T0 = f.init_T(); (f.fit() if EIKF.get('grid') else fit_robust(Eikonal(f, EIKF))); return f

def blend(fr, pts, p=4):
    if not len(pts): return np.zeros(fr.n)
    d = np.hypot(fr.cx[:, None] - pts.xc.values[None], fr.cy[:, None] - pts.yc.values[None])
    w = 1 / (d + 50) ** p; return (w * pts.th.values[None]).sum(1) / w.sum(1)

if __name__ == '__main__':
    rng = np.random.default_rng(int(sys.argv[2]) if len(sys.argv) > 2 else 0)
    F = pd.read_csv(f'{ROOT}/research/big-fires/results/fires.csv')
    cand = F[(F.area_ha.between(60, 900)) & (F.n_viirs >= 6)].fire.values
    nf = int(sys.argv[1]) if len(sys.argv) > 1 else 20
    rows = []
    for fire in rng.choice(cand, nf, replace=False):
        fr = Fire(int(fire), hyp=HYPF)
        if fr.n < 30 or len(fr.passes) < 4: continue
        Tt = truth_T(fr, rng)
        pts, mask = simulate(fr, Tt, rng)
        if len(pts) < 3: continue
        fa = fit_firms(fr, pts); fm = fit_mask(fr, mask)
        T0 = fa.T0; Tb = blend(fr, pts)
        obs = (Tt >= fr.tk.min() - 1) & (Tt <= fr.tk.max())
        r = dict(fire=int(fire), cells=fr.n, passes=len(fr.passes), flags=len(pts), obs_cells=int(obs.sum()))
        for nm, T in [('start_nearest', T0), ('blend', Tb), ('inv_firms', fa.T), ('inv_mask', fm.T)]:
            r[f'mae_{nm}'] = float(np.abs(T - Tt)[obs].mean()) if obs.any() else np.nan
            # photo-like accuracy: burned-by-t at the 10:30 IST times inside the observed window
            accs = []
            for th in np.arange(np.ceil(fr.tk.min()), fr.tk.max(), 1.0):
                tu = fr.t0 + pd.Timedelta(hours=float(th))
                if abs(((tu.hour + tu.minute / 60 + 5.5) % 24) - 10.5) > .5: continue
                y = Tt <= th
                if 0.05 < y.mean() < 0.95: accs.append(((T <= th) == y).mean())
            r[f'acc_{nm}'] = float(np.mean(accs)) if accs else np.nan
        rows.append(r); print(r, flush=True)
    X = pd.DataFrame(rows); X.to_csv(f'{OUT}/t3_sim.csv', index=False)
    res = {c: round(float(X[c].mean()), 3) for c in X.columns if c.startswith(('mae_', 'acc_'))}; res['fires'] = len(X)
    rb = np.random.default_rng(0)
    for a, b in [('inv_firms', 'start_nearest'), ('inv_firms', 'blend'), ('inv_mask', 'inv_firms')]:
        for m in ['mae', 'acc']:
            dlt = (X[f'{m}_{a}'] - X[f'{m}_{b}']).dropna().values; bs = [rb.choice(dlt, len(dlt)).mean() for _ in range(2000)]
            res[f'{m}_{a}_minus_{b}'] = [round(float(dlt.mean()), 3), round(float(np.quantile(bs, .025)), 3), round(float(np.quantile(bs, .975)), 3)]
    json.dump(res, open(f'{OUT}/t3_sim_summary.json', 'w'), indent=1); print(json.dumps(res, indent=1))
    print(X.mean(numeric_only=True))
