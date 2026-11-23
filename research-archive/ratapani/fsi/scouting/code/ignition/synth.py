"""Synthetic test of the ignition estimators on real Ratapani scar shapes.

For each sampled scar: put a known ignition (point, time), grow the fire across the scar at a known
direction-dependent rate on the burning clock, fly a realistic polar-orbiter schedule over it (S-NPP, NOAA-20
VIIRS 375 m; Aqua, Terra MODIS 1 km), detect burning footprints with low probability (small litter fires),
add geolocation noise, then run the estimators and score them against the truth.
Two-ignition scars (second fire lit 0-30 h later elsewhere in the same scar) test the 'merged' flag.

Usage: python -I synth.py <prepdir> <out.csv> [n_scars] [mode: uniform|edge]
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np, pandas as pd
from concurrent.futures import ProcessPoolExecutor
import ign

PREP, OUTF = sys.argv[1], sys.argv[2]
N = int(sys.argv[3]) if len(sys.argv) > 3 else 400
MODE = sys.argv[4] if len(sys.argv) > 4 else "uniform"
S = pd.read_pickle(PREP + "/scars.pkl")
S = S[(S.scar_ha >= 2) & (S.scar_ha <= 400)].reset_index(drop=True)
IST = 5.5
# (name, IST hour, footprint half-size m, detection probability, geolocation sd m)
PASSES = [("npp_d", 13.5, 210, 0.35, 70), ("npp_n", 1.5, 210, 0.30, 70), ("n20_d", 12.7, 210, 0.35, 70),
          ("n20_n", 0.7, 210, 0.30, 70), ("aqua_d", 13.6, 550, 0.12, 300), ("aqua_n", 1.6, 550, 0.10, 300),
          ("terra_d", 10.6, 550, 0.10, 300), ("terra_n", 22.6, 550, 0.08, 300)]
RES_T = 1.5   # clock hours a footprint stays detectable after the front passed


def inv_clock(Btarget, t_start):
    """Clock time (h UTC) at which the burning clock reaches Btarget, searching forward from t_start."""
    tt = t_start + np.arange(0, 24 * 12, 0.05)
    Bt = ign.burn_clock(tt)
    return np.interp(Btarget, Bt, tt)


def sample_hour(rng):
    while True:
        h = rng.uniform(0, 24)
        if rng.uniform() < ign.hour_prior(h - IST) / ign.hour_prior(11.0 - IST):
            return h


def one(args):
    k, seed, two = args
    rng = np.random.default_rng(seed)
    s = S.iloc[k]
    xs, ys, res = ign.candidates(s.geometry, 40.0)
    if len(xs) < 5:
        return None
    if MODE == "edge":
        # ignition within 120 m of the scar boundary (people lighting from a path or the forest edge)
        bd = s.geometry.boundary
        from shapely.geometry import Point
        dist = np.array([bd.distance(Point(a, b)) for a, b in zip(xs, ys)])
        pool = np.nonzero(dist <= 120)[0]
        pool = pool if len(pool) else np.arange(len(xs))
        j0 = rng.choice(pool)
    else:
        j0 = rng.integers(len(xs))
    day0 = 2000 * 24 + rng.integers(0, 60) * 24.0          # arbitrary day, hours UTC
    h = sample_hour(rng)
    t0 = day0 + h - IST
    v = float(np.clip(rng.lognormal(np.log(80), 0.6), 15, 300))
    theta = rng.uniform(0, 2 * np.pi); ecc = rng.uniform(0, 0.6)
    fires = [(j0, t0, v, theta, ecc)]
    if two:
        far = np.hypot(xs - xs[j0], ys - ys[j0])
        cand = np.nonzero(far > max(400, np.percentile(far, 60)))[0]
        if len(cand) == 0:
            return None
        j1 = rng.choice(cand)
        fires.append((j1, t0 + rng.uniform(0, 30), float(np.clip(rng.lognormal(np.log(80), 0.6), 15, 300)),
                      rng.uniform(0, 2 * np.pi), rng.uniform(0, 0.6)))
    arr = np.full(len(xs), np.inf)
    for (j, ta, vv, th, e) in fires:
        dx, dy = xs - xs[j], ys - ys[j]
        dd = np.hypot(dx, dy)
        ang = np.arctan2(dy, dx)
        vdir = vv * (1 + e * np.cos(ang - th)) / (1 + e / 2)      # direction-dependent speed (misspecified)
        Bt = ign.burn_clock(ta) + dd / vdir
        arr = np.minimum(arr, inv_clock(Bt, ta))
    t_end = arr.max()
    # optical bracket: last S2/Landsat look (10:45 IST) before ignition, every 5 days with random phase
    look0 = day0 - 24 * rng.integers(0, 5) + 10.75 - IST
    if look0 > t0:
        look0 -= 24 * 5
    t_pre = look0
    # passes
    dets, pass_t = [], []
    for dday in range(-6, int((t_end - day0) / 24) + 3):
        for (nm, hh, half, p, geo) in PASSES:
            tp = day0 + dday * 24 + hh - IST + rng.normal(0, 0.4)
            if tp < t_pre - ign.PRE_SLACK or tp > t_end + RES_T + 6:
                continue
            pass_t.append(tp)
            if tp < t0:
                continue
            burning = (arr <= tp) & (arr > tp - RES_T * 1.0)
            if not burning.any():
                continue
            # sensor grid with random phase; scan/track stretch for off-nadir
            sc = rng.uniform(1.0, 1.6) if half < 300 else rng.uniform(1.0, 2.0)
            hx, hy = half * sc, half * (1 + (sc - 1) * 0.6)
            ox, oy = rng.uniform(0, 2 * hx), rng.uniform(0, 2 * hy)
            ci = np.floor((xs[burning] - ox) / (2 * hx)).astype(int); cj = np.floor((ys[burning] - oy) / (2 * hy)).astype(int)
            for (a, b) in set(zip(ci, cj)):
                if rng.uniform() < p:
                    cx, cy = ox + (a + 0.5) * 2 * hx + rng.normal(0, geo), oy + (b + 0.5) * 2 * hy + rng.normal(0, geo)
                    dets.append((cx, cy, hx, hy, tp, nm))
    out = dict(k=k, event_id=s.event_id, scar_ha=s.scar_ha, two=two, v_true=v, ecc=ecc, n_det=len(dets),
               hour_true=h)
    if not dets:
        out.update(detected=False)
        return out
    d = pd.DataFrame(dets, columns=["x", "y", "hx", "hy", "th", "nm"])
    d["src"] = "firms"
    d = d.sort_values("th").reset_index(drop=True)
    t1 = d.th.iloc[0]
    pt = np.array(sorted(pass_t))
    prev = pt[(pt > t_pre - ign.PRE_SLACK) & (pt < t1 - 0.5)]
    t_lo_soft = prev.max() if len(prev) else t_pre
    o = ign.estimate(s.geometry, d.iloc[:60], t_pre, pt[(pt >= t_pre - ign.PRE_SLACK) & (pt <= t1)], return_post=True)
    pxs, pys, px = o.pop("post")
    x0, y0 = xs[j0], ys[j0]
    first = d[d.th <= t1 + 1.0]
    in_fp = bool(((np.abs(first.x - x0) <= first.hx) & (np.abs(first.y - y0) <= first.hy)).any())
    jt = np.argmin((pxs - x0) ** 2 + (pys - y0) ** 2)
    # posterior mass closer to the estimate than the truth (for calibration of radii)
    rr = np.hypot(pxs - o["e2_x"], pys - o["e2_y"])
    out.update(detected=True, t_first_lag=t1 - t0, err_e0=np.hypot(o["e0_x"] - x0, o["e0_y"] - y0),
               err_e1=np.hypot(o["e1_x"] - x0, o["e1_y"] - y0), err_e2=np.hypot(o["e2_x"] - x0, o["e2_y"] - y0),
               err_e2map=np.hypot(o["e2_map_x"] - x0, o["e2_map_y"] - y0), e1_r=o["e1_r"],
               e2_r50=o["e2_r50"], e2_r90=o["e2_r90"], p_in_first_fp=o["p_in_first_fp"], truth_in_first_fp=in_fp,
               err_rand=float(np.median(np.hypot(xs - x0, ys - y0))),
               terr=o["t_ign_med"] - t0, tcov=(o["t_ign_05"] <= t0 + 0.25) and (t0 - 0.25 <= o["t_ign_95"]),
               t_naive_err=t1 - t0, n_first=len(first),
               n_ign_v150=ign.min_ignitions(d, t_lo_soft, 150.0), n_ign_v60=ign.min_ignitions(d, t_lo_soft, 60.0),
               max_resid_h=o["max_resid_h"], n_days=int(np.ptp(np.floor((d.th.values + IST) / 24)) + 1))
    return out


if __name__ == "__main__":
    rng = np.random.default_rng(7)
    ks = rng.choice(len(S), size=N, replace=False)
    jobs = [(int(k), 1000 + i, False) for i, k in enumerate(ks)] + \
           [(int(k), 5000 + i, True) for i, k in enumerate(ks[: N // 2])]
    with ProcessPoolExecutor(4) as ex:
        res = [r for r in ex.map(one, jobs, chunksize=4) if r is not None]
    R = pd.DataFrame(res)
    R.to_csv(OUTF, index=False)
    print(R.groupby("two").detected.mean())
