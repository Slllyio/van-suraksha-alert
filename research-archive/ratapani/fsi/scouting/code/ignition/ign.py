"""Ignition point and time for one burn scar from its satellite fire detections.

Three estimators:
  E0  'first'     centroid of the earliest pass's detection points (the GOES/FIRED-style rule)
  E1  'footprint' centroid of (earliest-pass pixel footprints  intersect  scar)  (Benali 2016's ignition area)
  E2  'kinematic' grid posterior over candidate points x inside the scar, ignition time t0 and spread rate v.
      A detection i at time t_i is consistent with (x, t0, v) when the front, travelling at v on a
      'burning clock' B (1 h per hour 09-18 IST, 0.3 h per hour otherwise), has reached the nearest part of
      footprint_i (inside the scar) but not left its farthest part more than RES hours earlier:
            dmin_i(x)/v  <=  B(t_i) - B(t0)  <=  dmax_i(x)/v + RES
      Shortfalls are penalised as Gaussian errors (SIG hours). Priors: ignition hour (late-morning human
      ignition, after the local GK2A diurnal curve), v lognormal (litter fire measurements), and one factor
      (1 - PDET) for every satellite pass between t0 and the first detection that saw nothing (after
      Farguell/Haley 2018: non-detections carry information). Optional per-candidate weights carry the
      optical burn-date evidence (pixels/cells that burned after the first detection cannot be the origin).
Distances are Euclidean inside the scar polygon (not geodesic) [simplification].
"""
import numpy as np, pandas as pd
from rasterio.features import rasterize
from rasterio.transform import from_origin

IST = 5.5
SIG = 0.75          # h, timing slop
RES = 2.0           # h, how long a footprint stays detectable after the front has crossed it (smoulder)
PDET = 0.35         # chance a polar pass detects a small litter fire that is burning in its footprint
V_GRID = np.array([20, 30, 45, 65, 95, 140, 200, 300.0])   # m per burning-hour
V_MED, V_SDLOG = 80.0, 0.6
T_STEP, T_MAX = 0.5, 48.0   # h grid back from the first detection
NIGHT_W = 0.3


def burn_clock(t_hours_utc):
    """Cumulative burning hours since an arbitrary origin, for times in hours (UTC, float)."""
    t = np.asarray(t_hours_utc, float)
    day = np.floor((t + IST) / 24.0)
    h = (t + IST) - day * 24.0          # IST hour of day
    per_day = 9.0 + NIGHT_W * 15.0
    # cumulative within the day
    c = np.where(h < 9, NIGHT_W * h, np.where(h < 18, NIGHT_W * 9 + (h - 9), NIGHT_W * 9 + 9 + NIGHT_W * (h - 18)))
    return day * per_day + c


def hour_prior(t_hours_utc):
    """Density (unnormalised) of ignition by IST hour: 85% N(11.0, 2.5 h), 15% flat."""
    h = np.mod(np.asarray(t_hours_utc, float) + IST, 24.0)
    d = np.minimum(np.abs(h - 11.0), 24 - np.abs(h - 11.0))
    return 0.85 * np.exp(-0.5 * (d / 2.5) ** 2) / (2.5 * np.sqrt(2 * np.pi)) + 0.15 / 24.0


def candidates(geom, res=40.0, max_n=3000):
    x0, y0, x1, y1 = geom.bounds
    while True:
        w, h = int(np.ceil((x1 - x0) / res)) + 1, int(np.ceil((y1 - y0) / res)) + 1
        tr = from_origin(x0, y1, res, res)
        m = rasterize([(geom, 1)], out_shape=(h, w), transform=tr, all_touched=False, dtype="uint8")
        if m.sum() == 0:
            m = rasterize([(geom, 1)], out_shape=(h, w), transform=tr, all_touched=True, dtype="uint8")
        if m.sum() <= max_n or res >= 200:
            break
        res *= 1.5
    r, c = np.nonzero(m)
    xs = x0 + (c + 0.5) * res
    ys = y1 - (r + 0.5) * res
    return xs, ys, res


def fp_dists(xs, ys, d, res):
    """dmin, dmax from each candidate to each detection footprint (rectangle), restricted to scar candidates."""
    n, k = len(xs), len(d)
    dmin = np.empty((n, k)); dmax = np.empty((n, k)); inside = np.zeros((n, k), bool)
    for j, (x, y, a, b) in enumerate(zip(d.x.values, d.y.values, d.hx.values, d.hy.values)):
        dx = np.maximum(np.abs(xs - x) - a, 0); dy = np.maximum(np.abs(ys - y) - b, 0)
        dmin[:, j] = np.hypot(dx, dy)
        ins = (np.abs(xs - x) <= a + res / 2) & (np.abs(ys - y) <= b + res / 2)
        inside[:, j] = ins
        if ins.any():
            px, py = xs[ins], ys[ins]
            # farthest scar candidate inside the footprint, from every candidate
            D2 = (xs[:, None] - px[None, :]) ** 2 + (ys[:, None] - py[None, :]) ** 2 if ins.sum() < 400 else None
            if D2 is not None:
                dmax[:, j] = np.sqrt(D2.max(1))
            else:
                ex = np.maximum(np.abs(xs - (x - a)), np.abs(xs - (x + a)))
                ey = np.maximum(np.abs(ys - (y - b)), np.abs(ys - (y + b)))
                dmax[:, j] = np.hypot(ex, ey)
        else:  # footprint touches the scar edge only: use the rectangle itself
            ex = np.maximum(np.abs(xs - (x - a)), np.abs(xs - (x + a)))
            ey = np.maximum(np.abs(ys - (y - b)), np.abs(ys - (y + b)))
            dmax[:, j] = np.hypot(ex, ey)
    return dmin, dmax, inside


PRE_SLACK, PRE_PEN = 8.0, np.log(0.3)   # the pre look often shows the fire burning before any scar is visible


def estimate(geom, d, t_lo_hard, pass_times, cand_w=None, return_post=False, res=40.0):
    """geom: scar polygon (UTM). d: detections (x, y, hx, hy, th = hours UTC since epoch, src).
    t_lo_hard: hours UTC of the last clear optical look before the fire (scar absent).
    pass_times: array of satellite pass times (hours UTC) near the window."""
    xs, ys, res = candidates(geom, res)
    if cand_w is not None:
        cand_w = cand_w(xs, ys)
    d = d.sort_values("th").reset_index(drop=True)
    t1 = d.th.iloc[0]
    first = d[d.th <= t1 + 1.0]            # earliest pass (sensors within 1 h of each other)
    out = {}
    # E0
    e0x, e0y = first.x.mean(), first.y.mean()
    out.update(e0_x=e0x, e0_y=e0y)
    # E1: earliest-pass footprints intersect scar
    dmin, dmax, inside = fp_dists(xs, ys, d, res)
    fi = np.arange(len(first))
    in_first = inside[:, fi].any(1)
    if in_first.any():
        e1x, e1y = xs[in_first].mean(), ys[in_first].mean()
        a1 = in_first.sum() * res * res
    else:
        j = np.argmin(dmin[:, fi].min(1)); e1x, e1y = xs[j], ys[j]; a1 = res * res
    out.update(e1_x=e1x, e1_y=e1y, e1_r=np.sqrt(a1 / np.pi), e1_area_ha=a1 / 1e4)
    # E2
    # t_lo_hard is the last clear optical look without a scar. Fires burning at that look are common
    # (93% of fire pixels seen before the first FIRMS point are on that very image), so allow ignition up to
    # PRE_SLACK hours earlier at a penalty.
    t_pre = t_lo_hard
    t_lo = max(t_pre - PRE_SLACK, t1 - T_MAX)
    tg = np.arange(t1, t_lo - 1e-9, -T_STEP)
    if len(tg) == 0:
        tg = np.array([t1])
    Bt0 = burn_clock(tg)                          # (T,)
    Bdet = burn_clock(d.th.values)                # (K,)
    tau = Bdet[None, :] - Bt0[:, None]            # (T,K) burning hours from t0 to t_i
    lp_t = np.log(hour_prior(tg))
    pt = np.asarray(pass_times)
    nmiss = np.array([((pt > t0 + 0.2) & (pt < t1 - 0.2)).sum() for t0 in tg])
    lp_t = lp_t + nmiss * np.log(1 - PDET) + np.where(tg < t_pre, PRE_PEN, 0.0)
    lp_v = -0.5 * ((np.log(V_GRID) - np.log(V_MED)) / V_SDLOG) ** 2
    n = len(xs)
    logpost = np.full(n, -np.inf)
    post_t = np.zeros(len(tg)); post_v = np.zeros(len(V_GRID))
    LP = np.empty((len(V_GRID), len(tg), n))
    for iv, v in enumerate(V_GRID):
        lo = dmin / v; hi = dmax / v + RES                        # (n,K)
        for it in range(len(tg)):
            ta = tau[it][None, :]
            short = np.maximum(lo - ta, 0) + np.maximum(ta - hi, 0)
            LP[iv, it] = -0.5 * ((short / SIG) ** 2).sum(1) + lp_t[it] + lp_v[iv]
    if cand_w is not None:
        LP = LP + np.log(np.clip(cand_w, 1e-3, None))[None, None, :]
    m = LP.max()
    P = np.exp(LP - m)
    Z = P.sum()
    px = P.sum((0, 1)) / Z
    pt_ = P.sum((0, 2)) / Z
    pv = P.sum((1, 2)) / Z
    mx, my = (px * xs).sum(), (px * ys).sum()
    jmap = np.argmax(px)
    # snap mean to a candidate inside the scar
    js = np.argmin((xs - mx) ** 2 + (ys - my) ** 2)
    dd = np.hypot(xs - xs[js], ys - ys[js])
    o = np.argsort(dd); cm = np.cumsum(px[o])
    r50 = dd[o][np.searchsorted(cm, 0.5)]; r90 = dd[o][min(np.searchsorted(cm, 0.9), len(o) - 1)]
    # time
    ot = np.argsort(tg); ct = np.cumsum(pt_[ot])
    t_med = tg[ot][np.searchsorted(ct, 0.5)]
    t05 = tg[ot][np.searchsorted(ct, 0.05)]; t95 = tg[ot][min(np.searchsorted(ct, 0.95), len(ot) - 1)]
    best = LP.reshape(-1, n).max(0)
    # residual of the best single-ignition fit, per detection (h)
    iv, it, jx = np.unravel_index(np.argmax(LP), LP.shape)
    v = V_GRID[iv]
    ta = tau[it]
    short = np.maximum(dmin[jx] / v - ta, 0) + np.maximum(ta - (dmax[jx] / v + RES), 0)
    out.update(e2_x=xs[js], e2_y=ys[js], e2_map_x=xs[jmap], e2_map_y=ys[jmap], e2_r50=r50, e2_r90=r90,
               p_in_first_fp=float(px[in_first].sum()), t_first=t1, t_ign_med=t_med, t_ign_05=t05,
               t_ign_95=t95, v_med=float(V_GRID[np.searchsorted(np.cumsum(pv), 0.5)]),
               max_resid_h=float(short.max()), n_resid_gt2h=int((short > 2).sum()),
               n_cand=n, cand_res=res, n_det=len(d), n_first=len(first))
    if return_post:
        out["post"] = (xs, ys, px)
    return out


def min_ignitions(d, t_lo_soft, vmax=150.0):
    """Smallest number of ignitions that can explain the detections, if a front cannot move faster than
    vmax per burning-hour (the upper end of measured litter-fire spread). Pairs are linked when the gap between
    footprints can be crossed in the burning time between them; detections of the same pass are linked when
    a fire lit after the last empty pass could have reached both."""
    d = d.reset_index(drop=True)
    k = len(d)
    if k <= 1:
        return k
    B = burn_clock(d.th.values)
    gx = np.maximum(np.abs(d.x.values[:, None] - d.x.values[None, :]) - d.hx.values[:, None] - d.hx.values[None, :], 0)
    gy = np.maximum(np.abs(d.y.values[:, None] - d.y.values[None, :]) - d.hy.values[:, None] - d.hy.values[None, :], 0)
    gap = np.hypot(gx, gy)
    dt = np.abs(B[:, None] - B[None, :])
    t1 = d.th.min()
    Bavail = np.where(d.th.values <= t1 + 12, B - burn_clock(t_lo_soft), 0.0)
    reach = vmax * np.maximum(dt, Bavail[:, None] + Bavail[None, :])
    A = gap <= reach
    par = np.arange(k)
    def find(i):
        while par[i] != i:
            par[i] = par[par[i]]; i = par[i]
        return i
    ii, jj = np.nonzero(np.triu(A, 1))
    for i, j in zip(ii, jj):
        a, b = find(i), find(j)
        if a != b:
            par[a] = b
    return len({find(i) for i in range(k)})
