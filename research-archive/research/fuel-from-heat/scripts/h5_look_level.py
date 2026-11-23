"""Step 5: inside each of the 146 big fires, heat per BURNING area at each look (Akkshay's idea in its sharpest form).

Which ground was burning at look k: the fire-continuity blend map (same settings as its atlas, p=4, burning clock) gives
every 20 m pixel of the final scar an arrival time. Look k's ground = pixels whose arrival falls between the midpoints
(in fire-hours) to the previous and next look. First look also covers 6 fire-hours before it, last look 6 after.
How much heat: each VIIRS PASS inside look k is its own sample (S-NPP, NOAA-20, NOAA-21 never merged):
     fuel_kp (t/ha) = 10 x 0.368 x 3600 x [FRP_p / r(t_p)] x fire-hours(window_k) / area_k(m2)
The ground under look k: canopy, litter/grass (fuel map v3), teak, slope, tree share of the pixels in its window.
Out: results/look_fuel.csv (one row per pass x look)
"""
import os, sys, pickle
import numpy as np, pandas as pd
from multiprocessing import Pool
from rasterio import features
from rasterio.transform import Affine
sys.path.insert(0, '/mnt/project-files/research/fire-continuity/scripts')
import c0_lib as C
from h0_lib import RES, BF, SCRATCH, K_FRE, layers, r_clock, clock_hours

A = pd.read_csv(f'{BF}/fire_alerts.csv', parse_dates=['t']); A = A[A.sat != 'modis'].copy()
A['scan'] = A.scan.fillna(.375).clip(lower=.3); A['track'] = A.track.fillna(.375).clip(lower=.3)
SC = pickle.load(open(f'{SCRATCH}/fire_scars.pkl', 'rb'))
big = pd.read_csv(f'{BF}/big_fires_list.csv').fire.tolist()
V = pd.read_csv(f'{RES}/clusters.csv', parse_dates=['t']).dropna(subset=['fire']); V['fire'] = V.fire.astype(int)
L = layers()
LEAD = TAIL = 6.0

def one(fire):
    d = C.viirs_looks(A[A.fire == fire]); t0 = d.t.min(); d['th'] = (d.t - t0).dt.total_seconds() / 3600
    poly = SC[fire]
    xs = np.r_[poly.bounds[0], poly.bounds[2], d.x.min(), d.x.max()]; ys = np.r_[poly.bounds[1], poly.bounds[3], d.y.min(), d.y.max()]
    r0, c0 = C.rc_of(xs.min() - 800, ys.max() + 800); r1, c1 = C.rc_of(xs.max() + 800, ys.min() - 800)
    box = C.Box(int(r0), int(r1) + 1, int(c0), int(c1) + 1)
    tr = Affine(20, 0, C.X0 + box.c0 * 20, 0, -20, C.Y0 - box.r0 * 20)
    dom = features.rasterize([poly], out_shape=box.shape, transform=tr).astype(bool)
    clk = C.Clock(t0)
    T, lo, hi, idx, dmin = C.blend_map(box, dom, d, clock=clk, p=4)
    rr, cc = np.where(dom); gr, gc = rr + box.r0, cc + box.c0
    W = clk.W(T)                                     # pixel arrival in fire-hours
    looks = sorted(d.lk.unique()); tl = np.array([d[d.lk == k].th.min() for k in looks]); wl = clk.W(tl)
    edges = np.r_[-np.inf, (wl[1:] + wl[:-1]) / 2, np.inf]
    wlo = np.r_[wl[0] - LEAD, edges[1:-1]]; whi = np.r_[edges[1:-1], wl[-1] + TAIL]
    P = V[V.fire == fire].groupby(['sensor', 't']).agg(frp=('frp', 'sum'), n=('frp', 'size'),
                                                       pix_km2=('scan_m', lambda s: 0), night=('daynight', lambda s: (s == 'N').mean())).reset_index()
    P['pix_km2'] = V[V.fire == fire].groupby(['sensor', 't']).apply(lambda g: (g.scan_m * g.track_m).mean() / 1e6, include_groups=False).values
    P['th'] = (P.t - t0).dt.total_seconds() / 3600
    rows = []
    for i, k in enumerate(looks):
        sel = (W >= edges[i]) & (W < edges[i + 1])
        area = sel.sum() * 400.0; H = whi[i] - wlo[i]
        near = (dmin[sel] <= 600).mean() if sel.any() else np.nan
        cov = {n: np.nanmean(L[n][gr[sel], gc[sel]]) if sel.any() else np.nan for n in ['canopy', 'litter', 'grass', 'teak', 'slope', 'tree']}
        pk = P[(P.th >= tl[i] - 2.1) & (P.th <= tl[i] + 2.1)]
        for p in pk.itertuples():
            r = float(r_clock(p.t)[0])
            fuel = 10 * K_FRE * 3600 * (p.frp / r) * H / area if area > 0 else np.nan
            rows.append(dict(fire=fire, look=i, n_looks=len(looks), sensor=p.sensor, t=p.t, ist_hour=(p.t.hour + p.t.minute / 60 + 5.5) % 24,
                             frp=p.frp, n_det=p.n, pix_km2=p.pix_km2, night=p.night, clock_r=r, window_fire_h=H, area_ha=area / 1e4,
                             near600=near, fuel_tha=fuel, **cov))
    return rows

if __name__ == '__main__':
    with Pool(4) as pool:
        out = pool.map(one, big)
    R = pd.DataFrame([r for rs in out for r in rs])
    R.to_csv(f'{RES}/look_fuel.csv', index=False)
    print(len(R), 'pass x look rows,', R.fire.nunique(), 'fires; fuel t/ha median', R.fuel_tha.median().round(2), R.fuel_tha.quantile([.25, .75]).round(2).tolist())
