"""Numba kernels: D8 drainage (valleys; ridges = drainage of the flipped surface), chain tracing, spread-flow (BFS tree
subtree size from the start cells) and reach (4-connected flood from the start cells with line cells removed).
Fires spread 4-connected; lines are 8-connected cell chains, so a 4-connected flood cannot slip through a diagonal step."""
import numpy as np
from numba import njit

DR = np.array([-1, -1, -1, 0, 0, 1, 1, 1]); DC = np.array([-1, 0, 1, -1, 1, -1, 0, 1])
DD = np.array([1.4142, 1, 1.4142, 1, 1, 1.4142, 1, 1.4142])


@njit(cache=True)
def d8(z):
    H, W = z.shape; rec = -np.ones(H * W, np.int64)
    for r in range(1, H - 1):
        for c in range(1, W - 1):
            best = 0.0; bi = -1
            for k in range(8):
                rr = r + DR[k]; cc = c + DC[k]
                s = (z[r, c] - z[rr, cc]) / DD[k]
                if s > best: best = s; bi = rr * W + cc
            rec[r * W + c] = bi
    return rec


@njit(cache=True)
def accum(z, rec):
    order = np.argsort(-z.ravel()); acc = np.ones(z.size, np.float64)
    for i in order:
        j = rec[i]
        if j >= 0: acc[j] += acc[i]
    return acc


@njit(cache=True)
def trace(chan, rec, W):
    """Partition the channel network into chains: start at every channel cell with no channel donor, go downstream until
    a visited cell (junction, which is included to keep the chain joined) or the end. Returns flat cells and chain starts."""
    n = chan.size; donor = np.zeros(n, np.int32)
    for i in range(n):
        if chan[i] and rec[i] >= 0 and chan[rec[i]]: donor[rec[i]] += 1
    vis = np.zeros(n, np.bool_); out = []; starts = [0]
    for i in range(n):
        if chan[i] and donor[i] == 0:
            j = i
            while j >= 0 and chan[j]:
                out.append(j)
                if vis[j]: break
                vis[j] = True; j = rec[j]
            starts.append(len(out))
    return np.array(out, np.int64), np.array(starts, np.int64)


@njit(cache=True)
def flow(M, ign):
    """M: bool crop mask (H,W) ravelled; ign: flat start cells. BFS tree from all starts (4-conn); returns subtree size per cell
    (= cells whose shortest burn path passes through it) and the reached flag."""
    H, W = M.shape; Mf = M.ravel(); n = Mf.size
    par = -np.ones(n, np.int64); q = np.empty(n, np.int64); seen = np.zeros(n, np.bool_); h = 0; t = 0
    for s in ign:
        if Mf[s] and not seen[s]: seen[s] = True; q[t] = s; t += 1
    while h < t:
        i = q[h]; h += 1; r = i // W; c = i % W
        for k in (1, 3, 4, 6):
            rr = r + DR[k]; cc = c + DC[k]
            if rr < 0 or rr >= H or cc < 0 or cc >= W: continue
            j = rr * W + cc
            if Mf[j] and not seen[j]: seen[j] = True; par[j] = i; q[t] = j; t += 1
    sub = np.zeros(n, np.float64)
    for k in range(t - 1, -1, -1):
        i = q[k]; sub[i] += 1.0
        if par[i] >= 0: sub[par[i]] += sub[i]
    return sub.reshape(H, W), seen.reshape(H, W)


@njit(cache=True)
def reach(Mf, H, W, ign, block):
    """4-conn flood from starts within mask Mf (flat bool), not entering block (flat bool). Start cells are never blocked."""
    n = Mf.size; seen = np.zeros(n, np.bool_); q = np.empty(n, np.int64); h = 0; t = 0
    for s in ign:
        if Mf[s] and not seen[s]: seen[s] = True; q[t] = s; t += 1
    while h < t:
        i = q[h]; h += 1; r = i // W; c = i % W
        for k in (1, 3, 4, 6):
            rr = r + DR[k]; cc = c + DC[k]
            if rr < 0 or rr >= H or cc < 0 or cc >= W: continue
            j = rr * W + cc
            if Mf[j] and not seen[j] and not block[j]: seen[j] = True; q[t] = j; t += 1
    return seen


@njit(cache=True)
def _cut(D, off, Hs, Ws, r0s, c0s, srcp, srcs, ptr, cells, WL, f, k, block, seen, q):
    """One (line k, fire f) pair: returns number of protected cells; leaves 'seen' filled for the crop, block cleared later."""
    o = off[f]; H = Hs[f]; W = Ws[f]; n = H * W
    nb = 0
    for t in range(ptr[k], ptr[k + 1]):
        g = cells[t]; r = g // WL - r0s[f]; c = g % WL - c0s[f]
        if r >= 0 and r < H and c >= 0 and c < W and D[o + r * W + c]:
            block[r * W + c] = True; nb += 1
    if nb == 0: return 0, 0
    for i in range(n): seen[i] = False
    h = 0; tt = 0
    for s in range(srcp[f], srcp[f + 1]):
        i = srcs[s]
        if D[o + i] and not seen[i]: seen[i] = True; q[tt] = i; tt += 1
    while h < tt:
        i = q[h]; h += 1; r = i // W; c = i % W
        for kk in (1, 3, 4, 6):
            rr = r + DR[kk]; cc = c + DC[kk]
            if rr < 0 or rr >= H or cc < 0 or cc >= W: continue
            j = rr * W + cc
            if D[o + j] and not seen[j] and not block[j]: seen[j] = True; q[tt] = j; tt += 1
    return nb, tt


@njit(cache=True)
def pair_counts(D, off, Hs, Ws, r0s, c0s, base, srcp, srcs, ptr, cells, WL, pk, pf, maxn):
    """protected cells for each pair (pk[i] line, pf[i] fire): base-reached cells neither re-reached nor under the line."""
    block = np.zeros(maxn, np.bool_); seen = np.zeros(maxn, np.bool_); q = np.empty(maxn, np.int64)
    out = np.zeros(len(pk), np.int64); onl = np.zeros(len(pk), np.int64)
    for i in range(len(pk)):
        f = pf[i]; k = pk[i]
        nb, tt = _cut(D, off, Hs, Ws, r0s, c0s, srcp, srcs, ptr, cells, WL, f, k, block, seen, q)
        if nb > 0:
            # block cells that are start cells were reached anyway; count block cells actually reached
            o = off[f]; W = Ws[f]; nbr = 0
            for j in range(Hs[f] * W):
                if block[j]:
                    if seen[j]: nbr += 1
                    block[j] = False
            out[i] = base[f] - tt - (nb - nbr); onl[i] = nb
    return out, onl


@njit(cache=True)
def pair_cells(D, off, Hs, Ws, r0s, c0s, srcp, srcs, ptr, cells, WL, pk, pf, maxn, outp, total):
    """Protected local cell indices for each pair, written at outp[i]:outp[i+1]."""
    block = np.zeros(maxn, np.bool_); seen = np.zeros(maxn, np.bool_); q = np.empty(maxn, np.int64)
    res = np.empty(total, np.int32)
    for i in range(len(pk)):
        f = pf[i]; k = pk[i]
        nb, tt = _cut(D, off, Hs, Ws, r0s, c0s, srcp, srcs, ptr, cells, WL, f, k, block, seen, q)
        o = off[f]; W = Ws[f]; w = outp[i]
        for j in range(Hs[f] * W):
            if nb > 0 and D[o + j] and not seen[j] and not block[j] and w < outp[i + 1]:
                res[w] = j; w += 1
            block[j] = False
    return res
