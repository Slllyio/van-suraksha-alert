"""Fire continuity: turn time-stamped VIIRS detections of one fire into a continuous 20 m arrival-time map.

Everything runs on the 20 m UTM 43N grid of ratapani/spread/data_shared/grid20.npz (elevation, slope, land cover).
The burn-label rasters (photo chips) sit on the same grid, offset by 100 rows / 100 columns.

Methods (all give T(x) = hour the fire reached pixel x):
  base   : spread review arrival map. T = min_j [t_j + straight-line distance to footprint j / 15 m/h].
  nn     : time of the nearest footprint (straight line). Uses looks before AND after.
  geo    : like base, but distance is walked inside the final scar (fire can't cross unburned ground).
  front  : FRONT MATCHING (main). Looks in time order. Between look k-1 and look k the front walks out of everything
           seen so far, inside the scar, at the one speed that makes it reach the far side of look k's new footprints
           exactly at t_k (speed clipped 5-150 m/h). Ground still unreached after the last look keeps going at 15 m/h.
           Each pixel also gets a bracket [earliest, latest] = the two looks it lies between.
  front + terrain : same, but walking cost depends on terrain (uphill/downhill, open vs tree cover, roads).
"""
import numpy as np, pandas as pd
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import dijkstra
from scipy.spatial import cKDTree

ROOT = '/mnt/project-files'
import os
SCRATCH = os.environ.get('FC_SCRATCH', '/tmp')   # big intermediate files stay out of the shared folder
G = np.load(f'{ROOT}/ratapani/spread/data_shared/grid20.npz')
GT = G['transform']; X0, Y0 = GT[2], GT[5]
ELEV = G['elev']; WC = G['wc']
ROAD = np.load(f'{ROOT}/ratapani/spread/data_shared/barriers.npz')['road']
NR, NC = ELEV.shape

def rc_of(x, y):
    return np.floor((Y0 - np.asarray(y)) / 20).astype(int), np.floor((np.asarray(x) - X0) / 20).astype(int)
def xy_of(r, c):
    return X0 + (np.asarray(c) + .5) * 20, Y0 - (np.asarray(r) + .5) * 20

def viirs_looks(d):
    """d: detections of one fire (t, x, y, scan, track). Adds 'lk' = VIIRS look index (gap > 2 h starts a new look)."""
    d = d.sort_values('t').copy()
    d['lk'] = (d.t.diff().dt.total_seconds().fillna(1e9) > 2 * 3600).cumsum() - 1
    return d

class Box:
    """A window of the 20 m grid around one fire: domain mask (pixels the fire may cross) and terrain layers."""
    def __init__(self, r0, r1, c0, c1):
        self.r0, self.r1, self.c0, self.c1 = max(r0, 0), min(r1, NR), max(c0, 0), min(c1, NC)
        sl = (slice(self.r0, self.r1), slice(self.c0, self.c1))
        self.elev = ELEV[sl].astype(float); self.wc = WC[sl]; self.road = ROAD[sl]
        self.shape = self.elev.shape
        rr, cc = np.mgrid[self.r0:self.r1, self.c0:self.c1]
        self.X, self.Y = xy_of(rr, cc)

    def footprint(self, det, dom):
        """Boolean mask of the VIIRS pixel footprint (scan x track box around the point) inside the domain.
        If it misses the domain, the domain pixel nearest the point."""
        hx, hy = det.scan * 500, det.track * 500
        m = (np.abs(self.X - det.x) <= hx) & (np.abs(self.Y - det.y) <= hy) & dom
        if not m.any():
            rr, cc = np.where(dom)
            if not len(rr): return m
            k = np.argmin((self.X[rr, cc] - det.x) ** 2 + (self.Y[rr, cc] - det.y) ** 2)
            m[rr[k], cc[k]] = True
        return m

    def graph(self, dom, terrain=None):
        """8-neighbour walking graph over domain pixels. Edge cost = metres / speed multiplier.
        terrain = dict(up=a, open=b, road=c): multiplier = exp(a * tan(slope along the step) + b * open_ground) / (1 + c*road)."""
        idx = -np.ones(self.shape, int); rr, cc = np.where(dom); idx[rr, cc] = np.arange(len(rr))
        I, J, W = [], [], []
        openg = (self.wc != 10).astype(float)   # WorldCover 10 = trees
        for dr, dc in [(0, 1), (1, 0), (1, 1), (1, -1)]:
            r2, c2 = rr + dr, cc + dc
            ok = (r2 >= 0) & (r2 < self.shape[0]) & (c2 >= 0) & (c2 < self.shape[1])
            a, r2, c2, r1, c1 = idx[rr[ok], cc[ok]], r2[ok], c2[ok], rr[ok], cc[ok]
            b = idx[r2, c2]; k = b >= 0
            a, b, r1, c1, r2, c2 = a[k], b[k], r1[k], c1[k], r2[k], c2[k]
            L = 20 * np.hypot(dr, dc)
            for (p, q, ra, ca, rb, cb) in [(a, b, r1, c1, r2, c2), (b, a, r2, c2, r1, c1)]:
                w = np.full(len(p), L)
                if terrain:
                    tan = (self.elev[rb, cb] - self.elev[ra, ca]) / L
                    mult = np.exp(terrain.get('up', 0) * tan + terrain.get('open', 0) * .5 * (openg[ra, ca] + openg[rb, cb]))
                    mult = mult / (1 + terrain.get('road', 0) * (self.road[ra, ca] | self.road[rb, cb]))
                    w = w / mult
                I.append(p); J.append(q); W.append(w)
        n = len(rr)
        M = coo_matrix((np.concatenate(W), (np.concatenate(I), np.concatenate(J))), shape=(n + 1, n + 1)).tocsr()
        return M, idx, rr, cc

def walk(M, idx, seeds_mask, offsets=None):
    """Walking cost from a set of seed pixels (super-source trick). offsets: per-pixel start cost (same shape)."""
    n = M.shape[0] - 1
    s = idx[seeds_mask]; s = s[s >= 0]
    if not len(s): return np.full(n, np.inf)
    off = np.full(len(s), 1e-6) if offsets is None else offsets[seeds_mask][idx[seeds_mask] >= 0] + 1e-6
    S = coo_matrix((off, (np.full(len(s), n), s)), shape=(n + 1, n + 1)).tocsr()
    return dijkstra(M + S, indices=n)[:n]

def eucl_footdist(X, Y, d):
    """Straight-line distance from points (X, Y) to every footprint box in d. Returns (npts, ndet)."""
    hx, hy = d.scan.values * 500, d.track.values * 500
    dx = np.maximum(np.abs(X[:, None] - d.x.values[None]) - hx[None], 0)
    dy = np.maximum(np.abs(Y[:, None] - d.y.values[None]) - hy[None], 0)
    return np.hypot(dx, dy)

V_TAIL = 15.0; VMIN, VMAX = 5.0, 150.0

class Clock:
    """Burning clock. 'Fire time' runs fast in the afternoon and slow at night (results/diurnal.json, from MODIS counts).
    W(th) = fire-hours elapsed since th=0 (th in hours from t0, a UTC timestamp); Winv is its inverse.
    With flat=True it is ordinary time."""
    def __init__(self, t0, flat=False, th_range=(-200, 200)):
        import json
        self.flat = flat
        if flat: return
        p = json.load(open(f'{ROOT}/research/fire-continuity/results/diurnal.json'))
        b, pk, s = p['base'], p['peak_ist'], p['width_h']
        th = np.arange(th_range[0], th_range[1], 1 / 30)
        ist = (pd.Timestamp(t0).hour + pd.Timestamp(t0).minute / 60 + 5.5 + th) % 24
        dh = (ist - pk + 12) % 24 - 12
        r = b + (1 - b) * np.exp(-dh ** 2 / (2 * s ** 2))
        r = r / r.mean()                      # one fire-hour per hour on average over the day
        w = np.concatenate([[0], np.cumsum(r[:-1] / 30)]); w -= np.interp(0, th, w)
        self.th, self.w = th, w
    def W(self, t):
        return np.asarray(t, float) if self.flat else np.interp(t, self.th, self.w)
    def Winv(self, w):
        return np.asarray(w, float) if self.flat else np.interp(w, self.w, self.th)

def front_match(box, dom, d, terrain=None, vtail=V_TAIL, lead=0.0, clock=None, far_mode='edge', dist='walk'):
    """Front matching. d: detections with lk (look index) and th (hours from clock's t0). Returns per-domain-pixel arrays
    T (hours), lo, hi (bracket: the two looks the pixel lies between), the domain index and the interval speeds.
    clock   : Clock (burning clock); None = ordinary time.
    far_mode: 'edge' = the front reaches the far side of the new footprints at t_k; 'centre' = it reaches the detection points.
    dist    : 'walk' = walking distance inside the outline (terrain cost optional); 'line' = straight line.
    lead    : hours the first look's ground is taken to have burned before t_1."""
    from scipy.ndimage import distance_transform_edt
    clock = clock or Clock(None, flat=True)
    if dist == 'walk':
        M, idx, rr, cc = box.graph(dom, terrain)
        D_of = lambda reg: walk(M, idx, reg)
    else:
        idx = -np.ones(box.shape, int); rr, cc = np.where(dom); idx[rr, cc] = np.arange(len(rr))
        D_of = lambda reg: (distance_transform_edt(~reg) * 20)[rr, cc] if reg.any() else np.full(len(rr), np.inf)
    n = len(rr); T = np.full(n, np.inf); lo = np.full(n, -np.inf); hi = np.full(n, np.inf)
    looks = sorted(d.lk.unique()); tl = [d[d.lk == k].th.min() for k in looks]; wl = clock.W(np.array(tl))
    region = np.zeros(box.shape, bool)
    vs = []
    for i, k in enumerate(looks):
        dk = d[d.lk == k]
        fp = np.zeros(box.shape, bool)
        for det in dk.itertuples(): fp |= box.footprint(det, dom)
        new = fp & ~region
        newi = idx[new]; newi = newi[newi >= 0]
        if i == 0:
            T[newi] = tl[0] - lead; hi[newi] = tl[0]
        else:
            D = D_of(region)
            dW = max(wl[i] - wl[i - 1], 0.25)
            if far_mode == 'edge':
                cand = D[newi]
            else:   # the detection points themselves
                pr, pc = rc_of(dk.x.values, dk.y.values); pr, pc = pr - box.r0, pc - box.c0
                okp = (pr >= 0) & (pr < box.shape[0]) & (pc >= 0) & (pc < box.shape[1])
                ii = idx[pr[okp], pc[okp]]; cand = D[ii[ii >= 0]]
            cand = cand[np.isfinite(cand)] if len(cand) else cand
            far = cand.max() if len(cand) else 0
            v = float(np.clip(far / dW, VMIN, VMAX)) if far > 0 else VMIN     # metres per fire-hour
            vs.append(v)
            reach = np.isinf(T) & (D <= v * dW)
            T[reach] = clock.Winv(wl[i - 1] + D[reach] / v); lo[reach] = tl[i - 1]; hi[reach] = tl[i]
            jump = np.isinf(T[newi]); T[newi[jump]] = tl[i]; lo[newi[jump]] = tl[i - 1]; hi[newi[jump]] = tl[i]
        region |= fp
    rest = np.isinf(T)
    if rest.any():
        D = D_of(region)
        T[rest] = clock.Winv(wl[-1] + D[rest] / vtail); lo[rest] = tl[-1]
    return T, lo, hi, idx, vs

def forward(box, dom, d, v=V_TAIL, terrain=None):
    """'geo': T = min_j [t_j + walking distance inside domain from footprint j / v]."""
    M, idx, rr, cc = box.graph(dom, terrain)
    off = np.full(box.shape, np.inf); seeds = np.zeros(box.shape, bool)
    for det in d.itertuples():
        fp = box.footprint(det, dom)
        off[fp] = np.minimum(off[fp], det.th * v); seeds |= fp
    mn = np.nanmin(off[seeds]) if seeds.any() else 0
    D = walk(M, idx, seeds, np.where(seeds, off - mn, 0))
    return (D + mn) / v, idx

def blend_map(box, dom, d, clock=None, p=4, soft=50.0, terrain=None):
    """BLEND (the method the photos chose). Each VIIRS look pulls a pixel's arrival time toward its own time, with weight
    1 / (walking distance inside the outline to that look's footprints + 50 m)^p, averaged on the burning clock.
    Returns per-domain-pixel T (hours), the two looks pulling hardest (their times, for a 'between' bracket), idx, and the
    walking distance to the nearest footprint (m)."""
    clock = clock or Clock(None, flat=True)
    M, idx, rr, cc = box.graph(dom, terrain)
    looks = sorted(d.lk.unique()); tl = np.array([d[d.lk == k].th.min() for k in looks])
    Ek = []
    for k in looks:
        fp = np.zeros(box.shape, bool)
        for det in d[d.lk == k].itertuples(): fp |= box.footprint(det, dom)
        Ek.append(walk(M, idx, fp))
    Ek = np.stack(Ek, 1)
    far = ~np.isfinite(Ek); Ek[far] = 1e7
    w = 1 / (Ek + soft) ** p; w /= w.sum(1, keepdims=True)
    T = clock.Winv((w * clock.W(tl)[None]).sum(1))
    top2 = np.argsort(-w, 1)[:, :2]; ta, tb = tl[top2[:, 0]], tl[top2[:, 1]]
    return T, np.minimum(ta, tb), np.maximum(ta, tb), idx, Ek.min(1)
