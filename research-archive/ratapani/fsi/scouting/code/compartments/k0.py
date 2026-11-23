"""Shared settings and kernels for round r27 (internal compartment lines inside repeat-burn patches).
Reuses round-26 fires/patches (scratch r26: fires_<div>.pkl built from read_hist_geom() + tiger reserves + Ratapani v2, clipped to
VTM forest; patches_<div>.npz repeat-burn counts and labels; rings_tr3.pkl patch rings and edge segments) and round-25 code/scratch
(candidate ridge/valley/track chains cand_<div>.pkl, corridor plan lines sel_<div>.pkl).
Scoring rule (same for every line strategy): each fire spreads again from its round-25 start cells (within 400 m of the first VIIRS
look), 4-connected, only inside its own outline. Line cells can be crossed, but each crossing (entering a line cell from a non-line
cell) is stopped with chance p. A cell that needs k crossings to reach is burnt with chance (1-p)^k, so its expected saving is
1-(1-p)^k (k = fewest crossings, by 0-1 BFS). p = 0.35 (road odds, round 25) and p = 1.0 (upper bound). A line is treated as a
zero-width barrier: its own 60 m cell counts as part of the side the fire reaches it from (so a new line never 'loses' ground). Saved ground is reported three ways: 'patch' = repeat-patch forest, 'forest' = all VTM forest/scrub,
'ground' = all outline cells (round-25/26 'all ground')."""
import sys, os
import numpy as np
from numba import njit
sys.path.insert(0, '/mnt/project-files/ratapani/fsi/scouting/code/fire_lines/')
sys.path.insert(0, '/mnt/project-files/ratapani/fsi/scouting/code/repeat_patch_lines/')
import common as C25   # noqa: E402
import c26 as C26      # noqa: E402

SCR = '/tmp/claude-0/-home-user/be9b8f54-cc26-52cb-bdbb-9c8008a24baf/scratchpad/'
SC = SCR + 'r27/'; SC26 = SCR + 'r26/'; SC25 = SCR + 'r25/'
HERE = '/mnt/project-files/ratapani/fsi/scouting/code/compartments/'
OUT = HERE + 'out/'
CONF = '/mnt/project-files/ratapani/fsi/scouting/conference/'
RES = 60.0; CELL_HA = 0.36; AGG = 2
TRAIN = (2017, 2018, 2019, 2020, 2021); TEST = (2022, 2023, 2024, 2025); ALL = TRAIN + TEST
P_STOP = 0.35; PS = (0.35, 1.0)
EXT = 2               # a cut runs on up to 2 cells (120 m) beyond the patch edge, to tie into the surrounding ground
MIN_PIECE_HA = 2.0    # a cut must leave at least two pieces of >= 2 ha each
MAX_CUTS = 20         # per patch
ANGLES = np.arange(0, 180, 22.5)
BUDGETS = (100, 250, 500, 1000)
CORE = C25.CORE; slug = C25.slug
for d in (SC, OUT, CONF + 'figs/'): os.makedirs(d, exist_ok=True)


@njit(cache=True)
def bfs01(Mf, H, W, src, LMf, dist, dq):
    """0-1 BFS inside the fire crop (Mf flat bool), from start cells src. Entering a line cell (LMf) from a non-line cell costs 1.
    dist (int32, size n) filled; unreached = 9999. dq: int64 work array of size 4n+4 (each cell is pushed at most twice)."""
    n = H * W
    for i in range(n): dist[i] = 9999
    head = 2 * n + 2; tail = 2 * n + 2
    for s in src:
        if Mf[s] and dist[s] > 0:
            dist[s] = 0; dq[tail] = s; tail += 1
    while head < tail:
        i = dq[head]; head += 1; r = i // W; c = i % W; di = dist[i]
        for k in range(4):
            if k == 0: rr = r - 1; cc = c
            elif k == 1: rr = r + 1; cc = c
            elif k == 2: rr = r; cc = c - 1
            else: rr = r; cc = c + 1
            if rr < 0 or rr >= H or cc < 0 or cc >= W: continue
            j = rr * W + cc
            if not Mf[j]: continue
            w = 1 if (LMf[j] and not LMf[i]) else 0
            if di + w < dist[j]:
                dist[j] = di + w
                if w == 0:
                    head -= 1; dq[head] = j
                else:
                    dq[tail] = j; tail += 1
    return dist


@njit(cache=True)
def eval_fires(fids, D, off, Hs, Ws, r0s, c0s, srcp, srcs, WL, LM, LAB, FORg, pid, p, out):
    """Expected saved cells per fire for the current line mask LM (global flat bool of the division window).
    out[i, :] = (patch cells saved [LAB == pid, or LAB > 0 if pid == 0] & forest, forest cells saved, all cells saved, same three at p=1).
    Only line cells inside the fire's base reach matter; fires with none get zeros quickly."""
    maxn = 0
    for f in fids:
        if Hs[f] * Ws[f] > maxn: maxn = Hs[f] * Ws[f]
    dist = np.empty(maxn, np.int32); dq = np.empty(4 * maxn + 8, np.int64); lmf = np.zeros(maxn, np.bool_)
    q = 1.0 - p
    for ii in range(len(fids)):
        f = fids[ii]; o = off[f]; H = Hs[f]; W = Ws[f]; n = H * W
        any_line = False
        for j in range(n):
            if D[o + j]:
                g = (r0s[f] + j // W) * WL + (c0s[f] + j % W)
                lmf[j] = LM[g]
                if LM[g]: any_line = True
            else:
                lmf[j] = False
        for k in range(6): out[ii, k] = 0.0
        if not any_line: continue
        bfs01(D[o:o + n], H, W, srcs[srcp[f]:srcp[f + 1]], lmf[:n], dist, dq)
        for j in range(n):
            if not D[o + j]: continue
            k = dist[j]
            if lmf[j] and k > 0: k -= 1      # the line itself is a zero-width barrier: its cell burns as the side it is reached from
            if k == 0 or k >= 9999: continue
            s = 1.0 - q ** k
            g = (r0s[f] + j // W) * WL + (c0s[f] + j % W)
            out[ii, 2] += s; out[ii, 5] += 1.0
            if FORg[g]:
                out[ii, 1] += s; out[ii, 4] += 1.0
                if (pid == 0 and LAB[g] > 0) or (pid > 0 and LAB[g] == pid):
                    out[ii, 0] += s; out[ii, 3] += 1.0
    return out


@njit(cache=True)
def eval_fires_bypatch(fids, D, off, Hs, Ws, r0s, c0s, srcp, srcs, WL, LM, LAB, FORg, p, npatch):
    """As eval_fires with pid = 0, but also returns saved patch-forest cells per patch label (p and p=1)."""
    maxn = 0
    for f in fids:
        if Hs[f] * Ws[f] > maxn: maxn = Hs[f] * Ws[f]
    dist = np.empty(maxn, np.int32); dq = np.empty(4 * maxn + 8, np.int64); lmf = np.zeros(maxn, np.bool_)
    out = np.zeros((len(fids), 6)); byp = np.zeros((npatch + 1, 2)); q = 1.0 - p
    for ii in range(len(fids)):
        f = fids[ii]; o = off[f]; H = Hs[f]; W = Ws[f]; n = H * W
        any_line = False
        for j in range(n):
            if D[o + j]:
                g = (r0s[f] + j // W) * WL + (c0s[f] + j % W)
                lmf[j] = LM[g]
                if LM[g]: any_line = True
            else:
                lmf[j] = False
        if not any_line: continue
        bfs01(D[o:o + n], H, W, srcs[srcp[f]:srcp[f + 1]], lmf[:n], dist, dq)
        for j in range(n):
            if not D[o + j]: continue
            k = dist[j]
            if lmf[j] and k > 0: k -= 1      # the line itself is a zero-width barrier: its cell burns as the side it is reached from
            if k == 0 or k >= 9999: continue
            s = 1.0 - q ** k
            g = (r0s[f] + j // W) * WL + (c0s[f] + j % W)
            out[ii, 2] += s; out[ii, 5] += 1.0
            if FORg[g]:
                out[ii, 1] += s; out[ii, 4] += 1.0
                if LAB[g] > 0:
                    out[ii, 0] += s; out[ii, 3] += 1.0; byp[LAB[g], 0] += s; byp[LAB[g], 1] += 1.0
    return out, byp


def fronts(f, gap=750.0):
    """Conservative start rule (round 25 'fronts'): first-look start cells plus the footprint cell of every later VIIRS/MODIS dot that is
    more than 750 m from all earlier dots (a new front, possibly a second ignition or a spot fire)."""
    d = f['dots']; w = f['shape'][1]; cell = d[:, 0].astype(np.int64); t = d[:, 1]
    ok = cell >= 0; cell, t = cell[ok], t[ok]
    if len(cell) == 0: return f['ign'].astype(np.int64)
    o = np.argsort(t, kind='stable'); cell, t = cell[o], t[o]
    xy = np.c_[cell % w, cell // w].astype(float) * RES
    first = t <= t.min() + 2.0
    seen = list(xy[first]); new = []
    for tt in np.unique(t[~first]):
        m = t == tt; P = xy[m]
        S = np.array(seen); dmin = np.sqrt(((P[:, None, :] - S[None, :, :]) ** 2).sum(-1)).min(1)
        new += list(cell[m][dmin > gap]); seen += list(P)
    return np.union1d(f['ign'], np.array(new, np.int64)).astype(np.int64)


class Fires:
    """Fires of one division for a set of seasons: base reach D (cells reachable from the start inside the outline), crops."""
    def __init__(self, L, idx, src='ign'):
        from fl_lib import reach
        fs = [L['fires'][i] for i in idx]; self.idx = np.asarray(idx)
        self.year = np.array([f['year'] for f in fs], int); self.ha = np.array([f['ha'] for f in fs]); self.forest_ha = np.array([f['forest_ha'] for f in fs])
        Ds, offs, srcs, srcp = [], [0], [], [0]
        for f in fs:
            M = np.unpackbits(f['M'])[:f['shape'][0] * f['shape'][1]].astype(bool)
            s = f['ign'].astype(np.int64) if src == 'ign' else fronts(f)
            seen = reach(M, f['shape'][0], f['shape'][1], s, np.zeros(M.size, np.bool_))
            Ds.append(seen); offs.append(offs[-1] + seen.size); srcs.append(s); srcp.append(srcp[-1] + len(s))
        self.D = np.concatenate(Ds) if Ds else np.zeros(0, bool); self.off = np.array(offs[:-1], np.int64)
        self.H = np.array([f['shape'][0] for f in fs], np.int64); self.W = np.array([f['shape'][1] for f in fs], np.int64)
        self.r0 = np.array([f['r0'] for f in fs], np.int64); self.c0 = np.array([f['c0'] for f in fs], np.int64)
        self.srcs = np.concatenate(srcs).astype(np.int64) if srcs else np.zeros(0, np.int64); self.srcp = np.array(srcp, np.int64)
        self.n = len(fs)

    def args(self):
        return self.D, self.off, self.H, self.W, self.r0, self.c0, self.srcp, self.srcs


def load_div(key):
    import pickle
    L = pickle.load(open(SC26 + f'fires_{key}.pkl', 'rb')); H, W = L['H'], L['W']
    FOR = np.unpackbits(L['forest'])[:H * W].astype(bool)
    Z = np.load(SC26 + f'patches_{key}.npz')
    return L, FOR, Z


def lab60(Z, name, H, W):
    lab = Z['lab_' + name]
    return np.kron(lab, np.ones((AGG, AGG), np.int32))[:H, :W]
