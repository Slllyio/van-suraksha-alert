"""Tracking library: forward detection model + multi-pass sub-square ("drizzle") inversion of one fire's burning-time map.

Unknown: arrival time T_c (hours from the fire's first detection) of every 40 m cell inside the fire outline (v2 scars,
+60 m). A cell is "burning" for about tau hours after T_c:  b_c(t) = sig((t - T_c)/s) * sig((T_c + tau - t)/s).

Observations, every satellite pass kept separate with its own time (no merging of near-time looks):
  * a pass that flagged pixels near the fire: its pixel lattice is rebuilt around the fire from the flagged pixels
    (nodes at scan_m spacing along scan and 1.024 x track_m along track, axes turned to the satellite track; spacing from
    t1_calib). Each lattice node is either FLAGGED (a FIRMS point snaps to it) or LOOKED-AND-NOT-FLAGGED.
  * a pass that viewed Ratapani but flagged nothing near the fire: phase unknown, so it enters as "no pixel anywhere over
    the fire flagged" (the sum over a tiling lattice of the pixel responses is ~1 for any phase).
Forward model of one pixel p at time t_k:
    eta_p = eps + lam_k * sum_c w_pc * b_c(t_k)        P(flag) = 1 - exp(-eta_p)
    w_pc  = pixel response: box of width scan_m along scan blurred by sqrt(geoloc^2 + (native sample/2)^2) (the trapezoid
            of the dragged, aggregated I-band samples), box of track_m along track blurred by the geolocation error.
    lam_k = lam_{day|night} * (375^2 / pixel area)^gamma   (same burning ground is a smaller share of a bigger pixel);
            MODIS gets its own factor lam_modis.
    Positions are first corrected for the per-satellite offsets measured on static industrial sources (t1_calib).
Prior: quadratic smoothness of T between 4-neighbour cells (alpha), weak pull (48 h sd) to a nearest-detection start map.
Fit: MAP by L-BFGS-B. Uncertainty: Laplace (Gauss-Newton diagonal) per cell, and pass-bootstrap ensembles for examples.
"""
import json, os, pickle
import numpy as np, pandas as pd
from scipy.optimize import minimize
from scipy.special import erf, expit
from scipy.spatial import cKDTree
from rasterio import features
from rasterio.transform import Affine
ROOT = '/mnt/project-files'
SC = os.environ.get('TR_SCRATCH', '/tmp/claude-0/-home-user/be9b8f54-cc26-52cb-bdbb-9c8008a24baf/scratchpad/r19_track')
R17 = '/tmp/claude-0/-home-user/be9b8f54-cc26-52cb-bdbb-9c8008a24baf/scratchpad/r17_exp_code'
CODE = f'{ROOT}/ratapani/fsi/scouting/code/squares_v2/tracking'; OUT = f'{CODE}/results'; os.makedirs(OUT, exist_ok=True)
CELL = 40.0
TRACK_SPACING = 1.024
HYP = dict(ring=0.0, tail_w=0.0, tail_tau=24.0, tau=3.0, s=0.5, lam_d=0.08, lam_n=0.05, lam_modis=0.3, gamma=1.0, q_d=0.6, q_n=0.45, eps=1e-5, w_neg=0.7, alpha=0.05,
           sd0=48.0, geo=80.0, use_modis=False, offsets=True,
           mask_dir=None, geo_mask=None, w_clear=1.0)   # real VIIRS fire masks (pull_fire_masks.py): crops folder; blur and clear-pixel weight with masks

# VIIRS 375 m fire-mask classes -> role in the likelihood (user guide classes 0-9)
MASK_FIRE = (7, 8, 9)            # low / nominal / high confidence fire  -> flagged
MASK_CLEAR = (3, 5)              # water, clear land                      -> looked, no fire (weight w_clear)
MASK_NOINFO = (2, 4, 6)          # glint, cloud, unclassified             -> no information (dropped)
MASK_MISSING = (0, 1)            # not processed, bow-tie deletion        -> missing data (dropped)
_tp_ll = None
def mask_crop(mask_dir, pass_key):
    """Load one pass's crop written by pull_fire_masks.py, or None. Returns list of parts (dict of arrays)."""
    fn = f"{mask_dir}/crops/{pass_key.replace('|', '_').replace(' ', '')}.npz"
    if not mask_dir or not os.path.exists(fn): return None
    z = np.load(fn, allow_pickle=False); n = int(z['n_parts'])
    return [{k[:-len(f'_{i}')]: z[k] for k in z.files if k.endswith(f'_{i}')} for i in range(n)]

def axes(h):
    h = np.radians(np.asarray(h, float))
    return np.stack([np.cos(h), -np.sin(h)], -1), np.stack([np.sin(h), np.cos(h)], -1)

_D = {}
def data():
    if not _D:
        D = pd.read_parquet(f'{SC}/det.parquet'); D = D[D.type.fillna(0) != 2].reset_index(drop=True)
        P = pd.read_parquet(f'{SC}/passes.parquet')
        cal = json.load(open(f'{OUT}/t1_calib.json'))['offsets']
        off = {}
        for k, v in cal.items():   # apply an offset only where its 95% range excludes zero (else 0)
            e = v['east_m'] if (v['east_ci'][0] > 0 or v['east_ci'][1] < 0) else 0.0
            n = v['north_m'] if (v['north_ci'][0] > 0 or v['north_ci'][1] < 0) else 0.0
            off[k] = (e, n)
        key = D.sensor + '|' + D.daynight
        D['xc'] = D.x - key.map(lambda k: off.get(k, (0, 0))[0]); D['yc'] = D.y - key.map(lambda k: off.get(k, (0, 0))[1])
        S = pickle.load(open(f'{R17}/scars.pkl', 'rb'))
        _D.update(D=D, P=P, S=S, off=off, tree=cKDTree(D[['x', 'y']].values))
    return _D

def gbox(u, L, sig):
    """Box of width L blurred by a Gaussian (sd sig), evaluated at offset u (peak ~1 for L >> sig)."""
    r = np.sqrt(2) * sig
    return .5 * (erf((u + L / 2) / r) - erf((u - L / 2) / r))

def nagg(track_m):
    """VIIRS on-board aggregation (native samples per pixel along scan) from the along-track size [inference: zone limits
    31.6 and 44.7 deg correspond to track ~0.52 and ~0.66 km in our data]."""
    return np.where(track_m < 520, 3, np.where(track_m < 660, 2, 1))

class Fire:
    """All observations of one fire, built once. t0 = first detection (UTC)."""
    def __init__(self, fire, hyp=HYP, drop_pass=None, tmax=None, pad_h=(36, 24)):
        dd = data(); D, P, S = dd['D'], dd['P'], dd['S']
        self.fire = fire; self.hyp = hyp
        g = D[D.fire == fire]
        if not hyp['use_modis']: g = g[g.kind == 'viirs']
        if not len(g): g = D[(D.fire == fire) & (D.kind == 'viirs')]
        self.t0 = g.t.min(); tA, tB = g.t.min() - pd.Timedelta(hours=pad_h[0]), g.t.max() + pd.Timedelta(hours=pad_h[1])
        poly = S[fire].buffer(60)
        x0, y0, x1, y1 = poly.bounds; x0 -= 200; y0 -= 200; x1 += 200; y1 += 200
        a_ha = poly.area / 1e4; CELL = self.cell = 40.0 if a_ha < 700 else (60.0 if a_ha < 2000 else 80.0)   # 40 m; coarser for the largest fires (speed)
        nc, nr = int(np.ceil((x1 - x0) / CELL)), int(np.ceil((y1 - y0) / CELL))
        self.tr = Affine(CELL, 0, x0, 0, -CELL, y1); self.shape = (nr, nc)
        dom = features.rasterize([poly], out_shape=(nr, nc), transform=self.tr, all_touched=False).astype(bool)
        if dom.sum() < 4: dom = features.rasterize([poly], out_shape=(nr, nc), transform=self.tr, all_touched=True).astype(bool)
        self.dom = dom; rr, cc = np.where(dom); self.rr, self.cc = rr, cc
        self.cx = x0 + (cc + .5) * CELL; self.cy = y1 - (rr + .5) * CELL; self.n = len(rr)
        idx = -np.ones(dom.shape, int); idx[rr, cc] = np.arange(self.n); self.idx = idx
        nb = []
        for dr, dc in [(0, 1), (1, 0)]:
            a = idx[:nr - dr, :nc - dc]; b = idx[dr:, dc:]; k = (a >= 0) & (b >= 0); nb.append(np.c_[a[k], b[k]])
        self.nb = np.concatenate(nb)
        from scipy.sparse import coo_matrix, diags
        a, b = self.nb[:, 0], self.nb[:, 1]
        A = coo_matrix((np.ones(2 * len(a)), (np.r_[a, b], np.r_[b, a])), shape=(self.n, self.n)).tocsr()
        self.Lap = (diags(np.asarray(A.sum(1)).ravel()) - A).tocsr()      # graph Laplacian (second differences)
        self.LtL = (self.Lap.T @ self.Lap).tocsr()
        self.ctree = cKDTree(np.c_[self.cx, self.cy])
        self.bounds = (x0, y0, x1, y1)
        # passes in the window
        kinds = ['viirs', 'modis'] if hyp['use_modis'] else ['viirs']
        pp = P[(P.t >= tA) & (P.t <= tB) & P.kind.isin(kinds)].copy()
        # detections of any fire id near the outline (so neighbouring flags are not read as "not flagged")
        near = D[(D.x > x0 - 1500) & (D.x < x1 + 1500) & (D.y > y0 - 1500) & (D.y < y1 + 1500) & (D.t >= tA) & (D.t <= tB) & D.kind.isin(kinds)]
        near = near[near.pass_key.isin(pp.pass_key) | (near.fire == fire)]
        extra = near[~near.pass_key.isin(pp.pass_key)].pass_key.unique()   # passes with detections but not in the viewing list
        if len(extra):
            e = near[near.pass_key.isin(extra)].groupby('pass_key').agg(sensor=('sensor', 'first'), kind=('kind', 'first'), t=('t', 'median'),
                    daynight=('daynight', 'first'), heading=('heading', 'first'), scan_m=('scan_m', 'median'), track_m=('track_m', 'median')).reset_index()
            pp = pd.concat([pp, e], ignore_index=True)
        if drop_pass is not None: pp = pp[~pp.pass_key.isin(np.atleast_1d(drop_pass))]
        if tmax is not None: pp = pp[pp.t <= tmax]; near = near[near.t <= tmax]
        pp = pp.sort_values('t').reset_index(drop=True)
        self.passes = pp; self.det = near[near.pass_key.isin(pp.pass_key)].copy()
        self.det['th'] = (self.det.t - self.t0).dt.total_seconds() / 3600
        self.tk = ((pp.t - self.t0).dt.total_seconds() / 3600).values
        self.build_obs()
        self.tlo = min(self.tk.min() if len(self.tk) else 0, 0) - 12; self.thi = max(self.tk.max() if len(self.tk) else 0, 0) + 12

    def lattice(self, r, dk):
        """Pixel lattice nodes for pass r around the fire (anchor = first flagged pixel). Returns node xy, flag, size."""
        h = self.hyp; us, ut = axes(r.heading)
        ds_, dt_ = (float(np.median(dk.scan_m)), float(np.median(dk.track_m)) * TRACK_SPACING) if len(dk) else (r.scan_m, r.track_m * TRACK_SPACING)
        ax, ay = dk.xc.values[0], dk.yc.values[0]
        x0, y0, x1, y1 = self.bounds
        cor = np.array([[x0, y0], [x1, y0], [x1, y1], [x0, y1]]) - [ax, ay]
        ps, pt = cor @ us, cor @ ut
        I = np.arange(np.floor(ps.min() / ds_) - 2, np.ceil(ps.max() / ds_) + 3); J = np.arange(np.floor(pt.min() / dt_) - 2, np.ceil(pt.max() / dt_) + 3)
        II, JJ = np.meshgrid(I, J); II, JJ = II.ravel(), JJ.ravel()
        nx = ax + II * ds_ * us[0] + JJ * dt_ * ut[0]; ny = ay + II * ds_ * us[1] + JJ * dt_ * ut[1]
        flag = np.zeros(len(nx), bool)
        o = np.c_[dk.xc.values - ax, dk.yc.values - ay]; i = np.round(o @ us / ds_); j = np.round(o @ ut / dt_)
        resid = np.hypot(o @ us / ds_ - i, o @ ut / dt_ - j)
        key = {(a, b): q for q, (a, b) in enumerate(zip(II, JJ))}
        extra = []
        for a, b, rs, xx, yy in zip(i, j, resid, dk.xc.values, dk.yc.values):
            q = key.get((a, b))
            if q is not None and rs < .35: flag[q] = True
            else: extra.append((xx, yy))     # off-lattice point (bow-tie / other scan): its own flagged node
        if extra:   # drop same-pass near-duplicates (overlapping scans / bow-tie): within 0.6 pixel of a flagged node
            ex = np.array(extra); fx, fy = nx[flag], ny[flag]
            if len(fx):
                dmin = np.hypot(ex[:, 0][:, None] - fx[None], ex[:, 1][:, None] - fy[None]).min(1)
                ex = ex[dmin > 0.6 * min(ds_, dt_)]
            self.n_dupes += len(extra) - len(ex)
            extra = list(ex)
        if len(extra):
            ex = np.array(extra); nx = np.r_[nx, ex[:, 0]]; ny = np.r_[ny, ex[:, 1]]; flag = np.r_[flag, np.ones(len(ex), bool)]
        self.n_offlattice += len(extra); self.n_flag_det += len(dk)
        return nx, ny, flag, ds_, dt_

    def mask_nodes(self, r):
        """Nodes of pass r from its real fire-mask crop: every pixel centre inside the fire box (+1 pixel), its class
        role, and the local pixel spacing and heading measured from the crop's own lat/lon grid. None if no usable crop."""
        global _tp_ll
        parts = mask_crop(self.hyp['mask_dir'], r.pass_key)
        if not parts: return None
        if _tp_ll is None:
            import pyproj; _tp_ll = pyproj.Transformer.from_crs(4326, 32643, always_xy=True).transform
        e, n = data()['off'].get(f'{r.sensor}|{r.daynight}', (0.0, 0.0))     # same per-satellite offsets as FIRMS points
        X, Y, F, Wt, geom = [], [], [], [], []
        x0, y0, x1, y1 = self.bounds
        for p in parts:
            if 'lat' not in p or p['lat'].ndim != 2: continue
            fm = p['fire_mask']; x, y = _tp_ll(p['lon'].astype(float), p['lat'].astype(float)); x = x - e; y = y - n
            ok = np.isfinite(x) & np.isfinite(y)
            if ok.sum() < 4: continue
            # local geometry: rows = along track, columns = along scan
            dsx, dsy = np.nanmedian(np.diff(x, axis=1)), np.nanmedian(np.diff(y, axis=1))
            dtx, dty = np.nanmedian(np.diff(x, axis=0)), np.nanmedian(np.diff(y, axis=0))
            ds_, dt_ = float(np.hypot(dsx, dsy)), float(np.hypot(dtx, dty))
            hd = float(np.degrees(np.arctan2(dtx, dty)) % 360)       # track direction, clockwise from north
            if np.cos(np.radians(hd - r.heading)) < 0: hd = (hd + 180) % 360   # keep the FIRMS convention's sense
            pad = max(ds_, dt_)
            inb = ok & (x > x0 - pad) & (x < x1 + pad) & (y > y0 - pad) & (y < y1 + pad)
            role = np.isin(fm, MASK_FIRE) * 1 + np.isin(fm, MASK_CLEAR) * 2      # 1 flagged, 2 clear, 0 dropped
            k = inb & (role > 0)
            X.append(x[k]); Y.append(y[k]); F.append(role[k] == 1); Wt.append(np.where(role[k] == 1, 1.0, self.hyp['w_clear'])); geom.append((ds_, dt_, hd))
        if not X or not sum(len(a) for a in X): return None
        ds_, dt_, hd = geom[0]
        return np.concatenate(X), np.concatenate(Y), np.concatenate(F), np.concatenate(Wt), ds_, dt_, hd

    def psf(self, nx, ny, heading, ds_, dt_, kind, geo=None):
        """Sparse responses of nodes to cells: rows (node), cols (cell), w. geo: blur override (real-mask passes)."""
        h = self.hyp; us, ut = axes(heading); gsd = h['geo'] if geo is None else geo
        if kind == 'viirs':
            ss = np.sqrt(gsd ** 2 + (ds_ / nagg(dt_ / TRACK_SPACING) / 2) ** 2); st = gsd
        else:   # MODIS: triangular along scan (~0.3 pixel blur), geolocation ~50 m (MODIS C6)
            ss = np.sqrt(50 ** 2 + (0.3 * ds_) ** 2); st = np.sqrt(50 ** 2 + (0.15 * dt_) ** 2)
        rad = np.hypot(.625 * ds_ + 3 * ss, .625 * dt_ + 3 * st)
        lst = self.ctree.query_ball_point(np.c_[nx, ny], rad)
        R = np.repeat(np.arange(len(nx)), [len(l) for l in lst]); C = np.fromiter((c for l in lst for c in l), int, len(R))
        if not len(R): return R, C, np.zeros(0)
        dx, dy = self.cx[C] - nx[R], self.cy[C] - ny[R]
        a_, b_ = dx * us[0] + dy * us[1], dx * ut[0] + dy * ut[1]
        if h.get('ring', 0) > 0 and kind == 'viirs':
            # edge-weighted ring (big-fires 14c: hot pixels sit at the block edge or just outside): a 1.25x box minus a
            # centre box of half size, weight 'ring'; for two adjacent flagged blocks the product favours their shared edge
            w = gbox(a_, 1.25 * ds_, ss) * gbox(b_, 1.25 * dt_, st) - h['ring'] * gbox(a_, .5 * ds_, ss) * gbox(b_, .5 * dt_, st)
            w = np.clip(w, 0, None)
        else:
            w = gbox(a_, ds_, ss) * gbox(b_, dt_, st)
        k = w > 2e-3
        return R[k], C[k], w[k]

    def build_obs(self):
        h = self.hyp; rows, cols, ws, node_pass, node_flag, node_xy, node_w = [], [], [], [], [], [], []
        self.n_mask_pass = 0
        self.q_pass = np.where(self.passes.daynight.values == 'D', self.hyp['q_d'], self.hyp['q_n']) if len(self.passes) else np.zeros(0)
        lam_pass = np.zeros(len(self.passes)); free = np.zeros(len(self.passes), bool); nn = 0
        self.n_offlattice = 0; self.n_flag_det = 0; self.n_dupes = 0
        self.node_pass_size = []
        for k, r in enumerate(self.passes.itertuples()):
            dk = self.det[self.det.pass_key == r.pass_key]
            lam = h['lam_d'] if r.daynight == 'D' else h['lam_n']
            if r.kind == 'modis': lam *= h['lam_modis']
            area = (np.median(dk.scan_m) * np.median(dk.track_m)) if len(dk) else r.scan_m * r.track_m
            if r.kind == 'viirs': lam *= (375.0 ** 2 / area) ** h['gamma']
            else: lam *= (1000.0 ** 2 / area) ** h['gamma']
            lam_pass[k] = lam * (self.cell / 40.0) ** 2      # lambda is per 40 m cell of burning ground
            mk = self.mask_nodes(r) if (h.get('mask_dir') and r.kind == 'viirs') else None
            if mk is not None:            # real fire mask: true pixel grid; clear = looked, cloud/bow-tie = dropped
                nx, ny, fl, wn, ds_, dt_, hd = mk; self.n_mask_pass += 1
                R, C, W = self.psf(nx, ny, hd, ds_, dt_, r.kind, geo=h.get('geo_mask'))
            elif not len(dk):
                free[k] = True; continue
            else:
                nx, ny, fl, ds_, dt_ = self.lattice(r, dk); wn = np.full(len(nx), h['w_neg'])
                R, C, W = self.psf(nx, ny, r.heading, ds_, dt_, r.kind)
            used = np.unique(R); keep = np.isin(np.arange(len(nx)), used) | fl
            remap = -np.ones(len(nx), int); remap[keep] = np.arange(keep.sum()) + nn
            m = keep[R]; rows.append(remap[R[m]]); cols.append(C[m]); ws.append(W[m])
            node_pass.append(np.full(keep.sum(), k)); node_flag.append(fl[keep]); node_xy.append(np.c_[nx[keep], ny[keep]]); node_w.append(wn[keep])
            nn += keep.sum()
        cat = lambda L, dt=float: np.concatenate(L) if L else np.zeros(0, dt)
        self.R, self.C, self.W = cat(rows, int), cat(cols, int), cat(ws)
        self.node_pass, self.node_flag = cat(node_pass, int), cat(node_flag, bool); self.node_w = cat(node_w)
        self.node_xy = np.concatenate(node_xy) if node_xy else np.zeros((0, 2))
        self.lam_pass, self.free = lam_pass, free; self.nn = nn
        self.lamR = lam_pass[self.node_pass[self.R]] if nn else np.zeros(0)
        self.Rpass = self.node_pass[self.R] if nn else np.zeros(0, int)

    # ---------------- model
    def burn(self, T, t):
        """b and db/dT for cells (T: n) at pass times t (m) -> (n, m). Main burning window tau after arrival; optional long
        tail (weight tail_w, e-folding tail_tau h) for smouldering / re-flaring ground that stays detectable."""
        h = self.hyp; s = h['s']; a = (t[None] - T[:, None]) / s; c = (T[:, None] + h['tau'] - t[None]) / s
        sa, sc = expit(a), expit(c); w = h.get('tail_w', 0.0)
        if w <= 0: return sa * sc, (-sc * sa * (1 - sa) + sa * sc * (1 - sc)) / s
        dd = s * np.logaddexp(0, a); eL = np.exp(-dd / h['tail_tau']); G = (1 - w) * sc + w * eL
        db = -sa * (1 - sa) / s * G + sa * ((1 - w) * sc * (1 - sc) / s + w * eL * sa / h['tail_tau'])
        return sa * G, db

    def eta(self, T):
        B, dB = self.burn(T, self.tk)
        contrib = self.W * B[self.C, self.Rpass]
        e = np.bincount(self.R, self.lamR * contrib, minlength=self.nn)
        return e, B, dB

    def init_T(self):
        """Start: time of the nearest flagged pixel centre (each detection separate), soft-clipped to the window."""
        d = self.det
        if not len(d): return np.zeros(self.n)
        t = cKDTree(d[['xc', 'yc']].values); _, j = t.query(np.c_[self.cx, self.cy])
        return d.th.values[j] - 0.5 * self.hyp['tau']

    def datall(self, T):
        """-log likelihood of all passes given T, and its gradient in T.
        P(flag) = eps + (1-eps) * q * (1 - exp(-eta)): q < 1 is the ceiling (a fully burning pixel is still missed sometimes:
        smoke, sub-threshold heat, background test); passes with no flag on the fire: P(no pixel flags) = 1 - q(1 - exp(-H)),
        H = lam * sum_c b_c (phase-free)."""
        h = self.hyp; eps = h['eps']
        e, B, dB = self.eta(T); ll = 0.0; gT = np.zeros(self.n)
        if self.nn:
            q = self.q_pass[self.node_pass]; ex = np.exp(-e)
            P = eps + (1 - eps) * q * (1 - ex); dP = (1 - eps) * q * ex
            f = self.node_flag
            wn = self.node_w
            ll = np.where(f, np.log(P), wn * np.log1p(-P)).sum()
            g_e = np.where(f, dP / P, -wn * dP / (1 - P))
            gT = np.bincount(self.C, g_e[self.R] * self.lamR * self.W * dB[self.C, self.Rpass], minlength=self.n)
        fr = np.where(self.free)[0]
        if len(fr):
            H = (self.lam_pass[fr][None] * B[:, fr]).sum(0); q = self.q_pass[fr]; ex = np.exp(-H)
            P = q * (1 - ex); ll += h['w_neg'] * np.log1p(-P).sum()
            gT += ((-h['w_neg'] * q * ex / (1 - P))[None] * self.lam_pass[fr][None] * dB[:, fr]).sum(1)
        return -ll, -gT

    def negloglik(self, T, T0, grad=True):
        h = self.hyp; nl, gT = self.datall(T)
        LT = self.Lap @ T
        pen = h['alpha'] * (LT ** 2).sum() + ((T - T0) ** 2).sum() / (2 * h['sd0'] ** 2)
        gp = 2 * h['alpha'] * (self.LtL @ T) + (T - T0) / h['sd0'] ** 2
        return nl + pen, gT + gp

    def fit(self, T_start=None, maxiter=400):
        T0 = self.init_T(); x0 = T0.copy() if T_start is None else T_start
        bnd = [(self.tlo, self.thi)] * self.n
        r = minimize(self.negloglik, x0, args=(T0,), jac=True, method='L-BFGS-B', bounds=bnd, options=dict(maxiter=maxiter))
        self.T = r.x; self.T0 = T0; self.opt = r
        return r.x

    def laplace_sd(self, T):
        """Gauss-Newton diagonal: Fisher information of each node's Bernoulli in eta, chained to T; plus the prior."""
        h = self.hyp; eps = h['eps']; e, B, dB = self.eta(T); info = np.zeros(self.n)
        if self.nn:
            q = self.q_pass[self.node_pass]; ex = np.exp(-e); P = eps + (1 - eps) * q * (1 - ex); dP = (1 - eps) * q * ex
            fi = dP ** 2 / (P * (1 - P)); J2 = (self.lamR * self.W * dB[self.C, self.Rpass]) ** 2
            info = np.bincount(self.C, fi[self.R] * J2, minlength=self.n)
        fr = np.where(self.free)[0]
        if len(fr):
            H = (self.lam_pass[fr][None] * B[:, fr]).sum(0); q = self.q_pass[fr]; ex = np.exp(-H); P = np.clip(q * (1 - ex), 1e-6, 1 - 1e-6)
            ff = (q * ex) ** 2 / (P * (1 - P)); info += ((self.lam_pass[fr][None] * dB[:, fr]) ** 2 * ff[None]).sum(1)
        info += 2 * h['alpha'] * np.asarray(self.LtL.diagonal()) * 0.1 + 1 / h['sd0'] ** 2
        return 1 / np.sqrt(info)

    def p_flag_nodes(self, T, nodes_xy, t, heading, ds_, dt_, kind, daynight):
        """Predicted P(flag) for arbitrary lattice nodes of a (hidden) pass at time t (hours)."""
        h = self.hyp; R, C, W = self.psf(nodes_xy[:, 0], nodes_xy[:, 1], heading, ds_, dt_, kind)
        lam = (h['lam_d'] if daynight == 'D' else h['lam_n']) * (h['lam_modis'] if kind == 'modis' else 1)
        lam *= ((375.0 if kind == 'viirs' else 1000.0) ** 2 / (ds_ * dt_ / TRACK_SPACING)) ** h['gamma']
        lam *= (self.cell / 40.0) ** 2
        B, _ = self.burn(T, np.array([t]))
        e = lam * np.bincount(R, W * B[C, 0], minlength=len(nodes_xy)); q = h['q_d'] if daynight == 'D' else h['q_n']
        return h['eps'] + (1 - h['eps']) * q * (-np.expm1(-e))

    def T_at(self, X, Y):
        """Arrival time at arbitrary points (nearest cell; outside the outline -> nearest outline cell)."""
        _, j = self.ctree.query(np.c_[X, Y]); return self.T[j]


# ======================================================================================================================
# Eikonal ("fast-marching") inversion: T = earliest arrival from a few ignition seeds walking at a smooth speed field,
# on the burning clock. Burn once, monotone front by construction. Parameters: log-speed on a 200 m control grid + seed
# times. Gradient through the shortest-path tree (each cell's arrival = seed time + sum of edge costs on its path).
# ======================================================================================================================
from scipy.sparse import coo_matrix as _coo, identity as _eye
from scipy.sparse.csgraph import dijkstra as _dijkstra
from scipy.sparse.linalg import spsolve as _spsolve
EIK = dict(ctrl=200.0, v0=20.0, sd_logv=1.2, sd_dlogv=0.5, jump_m=1200.0, clock=True, max_seeds=20)

class Clock:
    """Burning clock from research/fire-continuity/results/diurnal.json (MODIS counts; never fitted on photos)."""
    def __init__(self, t0, flat=False):
        self.flat = flat
        if flat: return
        p = json.load(open(f'{ROOT}/research/fire-continuity/results/diurnal.json'))
        th = np.arange(-400, 400, 1 / 30); ist = (t0.hour + t0.minute / 60 + 5.5 + th) % 24
        dh = (ist - p['peak_ist'] + 12) % 24 - 12
        r = p['base'] + (1 - p['base']) * np.exp(-dh ** 2 / (2 * p['width_h'] ** 2)); r = r / r.mean()
        w = np.concatenate([[0], np.cumsum(r[:-1] / 30)]); w -= np.interp(0, th, w)
        self.th, self.w, self.r = th, w, r
    def W(self, t): return np.asarray(t, float) if self.flat else np.interp(t, self.th, self.w)
    def Winv(self, w): return np.asarray(w, float) if self.flat else np.interp(w, self.w, self.th)
    def rate(self, t): return np.ones_like(np.asarray(t, float)) if self.flat else np.interp(t, self.th, self.r)

class Eikonal:
    def __init__(self, fr, eik=EIK):
        self.fr, self.e = fr, eik; n = fr.n; self.clock = Clock(fr.t0, flat=not eik['clock'])
        # 8-neighbour graph
        I, J, L = [], [], []
        for dr, dc in [(0, 1), (1, 0), (1, 1), (1, -1)]:
            r2, c2 = fr.rr + dr, fr.cc + dc; ok = (r2 >= 0) & (r2 < fr.shape[0]) & (c2 >= 0) & (c2 < fr.shape[1])
            a = np.arange(n)[ok]; b = fr.idx[r2[ok], c2[ok]]; k = b >= 0
            I.append(a[k]); J.append(b[k]); L.append(np.full(k.sum(), fr.cell * np.hypot(dr, dc)))
        self.ea, self.eb, self.eL = np.concatenate(I), np.concatenate(J), np.concatenate(L)
        # control grid (bilinear)
        x0, y0, x1, y1 = fr.bounds; s = eik['ctrl']
        gx = np.arange(x0, x1 + s, s); gy = np.arange(y0, y1 + s, s); self.gshape = (len(gy), len(gx))
        fx = (fr.cx - x0) / s; fy = (fr.cy - y0) / s; ix = np.clip(np.floor(fx).astype(int), 0, len(gx) - 2); iy = np.clip(np.floor(fy).astype(int), 0, len(gy) - 2)
        ax, ay = fx - ix, fy - iy; m = len(gx) * len(gy); rows = np.repeat(np.arange(n), 4)
        cols = np.c_[iy * len(gx) + ix, iy * len(gx) + ix + 1, (iy + 1) * len(gx) + ix, (iy + 1) * len(gx) + ix + 1].ravel()
        vals = np.c_[(1 - ax) * (1 - ay), ax * (1 - ay), (1 - ax) * ay, ax * ay].ravel()
        self.Bm = _coo((vals, (rows, cols)), shape=(n, m)).tocsr(); self.m = m
        used = np.unique(cols); self.cuse = used
        cn = []
        G = np.arange(m).reshape(self.gshape)
        for a_, b_ in [(G[:, :-1], G[:, 1:]), (G[:-1], G[1:])]: cn.append(np.c_[a_.ravel(), b_.ravel()])
        cn = np.concatenate(cn); self.cn = cn[np.isin(cn[:, 0], used) & np.isin(cn[:, 1], used)]
        # seeds: cells under the first flagged pass, and under any later flag > jump_m from all earlier flags
        d = fr.det.sort_values('th') if len(fr.det) else fr.det
        seeds = []
        if len(d):
            P = d[['xc', 'yc']].values; th = d.th.values; first = th <= th.min() + 0.25
            for i in range(len(d)):
                if first[i] or np.hypot(*(P[:i][th[:i] < th[i] - 0.25] - P[i]).T).min(initial=1e9) > eik['jump_m']:
                    seeds.append((fr.ctree.query(P[i])[1], th[i]))
        if not seeds: seeds = [(0, 0.0)]
        sd = {}
        for c, t in seeds:
            if c not in sd or t < sd[c]: sd[c] = t
        it = sorted(sd.items(), key=lambda q: q[1])[:eik['max_seeds']]
        self.seed_cell = np.array([c for c, _ in it]); self.seed_t = np.array([t for _, t in it])
        self.ns = len(it)

    def unpack(self, x): return x[:self.m], x[self.m:]

    def forward(self, x, need_tree=False):
        z, ws = self.unpack(x); n = self.fr.n
        u = np.exp(-(self.Bm @ z))                    # fire-hours per metre
        cost = self.eL * .5 * (u[self.ea] + u[self.eb])
        wmin = ws.min()
        M = _coo((np.r_[cost, cost, ws - wmin + 1e-6], (np.r_[self.ea, self.eb, np.full(self.ns, n)], np.r_[self.eb, self.ea, self.seed_cell])), shape=(n + 1, n + 1)).tocsr()
        D, pred = _dijkstra(M, directed=True, indices=n, return_predecessors=True)
        D = D[:n] + wmin - 1e-6; pred = pred[:n]
        T = self.clock.Winv(np.where(np.isfinite(D), D, 1e9)); T[~np.isfinite(D)] = 1e4
        return T, D, pred, u

    def objective(self, x):
        fr, e = self.fr, self.e; n = fr.n
        T, D, pred, u = self.forward(x)
        nl, gT = fr.datall(T)
        gD = np.where(T < 1e3, gT / np.clip(self.clock.rate(T), 1e-3, None), 0)
        # subtree sums on the shortest-path tree: S_c = gD_c + sum over children S_k
        child = np.where((pred >= 0) & (pred < n))[0]
        A = (_eye(n, format='csr') - _coo((np.ones(len(child)), (pred[child], child)), shape=(n, n)).tocsr()).tocsc()
        S = _spsolve(A, gD) if np.any(gD) else np.zeros(n)
        S = np.asarray(S).ravel()
        # edge pred->c of length L: L/2 * S_c to u_c and u_pred
        Lc = np.zeros(n); pc = pred[child]
        Lc[child] = fr.cell * np.hypot(fr.rr[child] - fr.rr[pc], fr.cc[child] - fr.cc[pc])
        gu = np.zeros(n); np.add.at(gu, child, .5 * Lc[child] * S[child]); np.add.at(gu, pc, .5 * Lc[child] * S[child])
        gz = self.Bm.T @ (gu * (-u))
        z, ws = self.unpack(x)
        gw = np.zeros(self.ns); act = pred[self.seed_cell] == n
        # seed cell rooted at the super node: d(D_c)/d(w_i) = 1 for its subtree
        gw[act] = S[self.seed_cell[act]]
        # prior
        mu = np.log(e['v0']); zu = z[self.cuse]
        pen = ((zu - mu) ** 2).sum() / (2 * e['sd_logv'] ** 2)
        dz = z[self.cn[:, 0]] - z[self.cn[:, 1]]; pen += (dz ** 2).sum() / (2 * e['sd_dlogv'] ** 2)
        gp = np.zeros(self.m); gp[self.cuse] += (zu - mu) / e['sd_logv'] ** 2
        np.add.at(gp, self.cn[:, 0], dz / e['sd_dlogv'] ** 2); np.add.at(gp, self.cn[:, 1], -dz / e['sd_dlogv'] ** 2)
        return nl + pen, np.r_[gz + gp, gw]

    def fit(self, maxiter=200, x0=None):
        if x0 is None:
            x0 = np.r_[np.full(self.m, np.log(self.e['v0'])), self.clock.W(self.seed_t - 1.0)]
        lo_w = self.clock.W(self.seed_t - 72); hi_w = self.clock.W(np.full(self.ns, self.fr.thi + 300.0))   # a seed may switch off (false alarm)
        bnd = [(np.log(1.0), np.log(600.0))] * self.m + list(zip(lo_w, hi_w))
        r = minimize(self.objective, x0, jac=True, method='L-BFGS-B', bounds=bnd, options=dict(maxiter=maxiter))
        self.x = r.x; self.opt = r
        self.T, self.D, self.pred, u = self.forward(r.x); self.v = 1 / u      # m per fire-hour
        self.fr.T = self.T
        return self.T

def fit_robust(ek, maxiter=200, trial_iter=60, max_trials=12):
    """Fit, then greedy seed pruning: switch each active seed off in turn (time order) and keep the change if the
    posterior objective improves (isolated early flags otherwise anchor a false early start: a local optimum)."""
    ek.fit(maxiter=maxiter); best, x = ek.opt.fun, ek.x.copy(); off = ek.clock.W(ek.fr.thi + 300.0)
    act = [i for i in np.argsort(ek.seed_t) if x[ek.m + i] < off - 1][:max_trials]
    for i in act:
        x2 = x.copy(); x2[ek.m + i] = off; ek.fit(x0=x2, maxiter=trial_iter)
        if ek.opt.fun < best - 0.5: best, x = ek.opt.fun, ek.x.copy()
    ek.fit(x0=x, maxiter=maxiter)
    if ek.opt.fun > best + 1e-6:
        ek.x = x; ek.T, ek.D, ek.pred, u = ek.forward(x); ek.v = 1 / u; ek.fr.T = ek.T
    return ek.T
