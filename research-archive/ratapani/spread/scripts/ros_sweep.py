"""Audit item 1 follow-up (Oct 15): refit the spread-rate multiplier (= litter load, ROS is linear in load for this bed) against the grown
outlines with an HONEST start: a 100 m disc at each first-pass alert point (no scar snapping), roads as barriers, no wind, ERA5-Land hindcast
weather. For every scarred S-NPP fire with an outline and multipliers 1, 1.5, 2, 2.5, 3 (1.5 to 4.5 t/ha of loose litter): Sorensen at the
outline's area (shape only), the hour at which the free run reaches the outline's area, free-run area and Sorensen at 26 h and 48 h,
later-pass hits (240 m) at the outline's area and at 26 h.
  python3 ros_sweep.py k/n out.parquet
"""
import os; os.environ['SCAR_GROWN'] = '1'
import numpy as np, pandas as pd, sys, time
import sim, score, grown, footprint
score.scar_footprint = grown.scar_footprint
BASE = dict(footprint.CFG, ign_snap=False, barriers='ms')
MULTS = [1.0, 1.5, 2.0, 2.5, 3.0]


def main(k_n, out):
    v, ids = footprint.events(k_n); wx = {}; rows = []; tt = time.time()
    for k, e in enumerate(ids):
        ev = v[v.event == e].sort_values('t'); s = int(ev.season.iloc[0])
        if s not in wx:
            wx.clear(); wx[s] = sim.load_weather(s)
        first = ev[ev.overpass == ev.overpass.min()]
        later = ev[(ev.t >= ev.t.min() + pd.Timedelta(hours=6)) & (ev.t <= ev.t.min() + pd.Timedelta(hours=72))]
        for m in MULTS:
            o = sim.run_event(ev, wx[s], dict(BASE, ros_mult=m), hours=48, scar_fn=score.scar_footprint)
            S, B, (i0, i1, j0, j1) = o['S'], o['burnable'], o['win']
            tfirst = (ev.t.min() - o['t0']).total_seconds() / 60; tph = (o['T'] - tfirst) / 60.0; tph = np.where(np.isfinite(tph), tph, 96.0)
            yy, xx = np.mgrid[i0:i1, j0:j1]; px = sim.X0 + xx * sim.RES + sim.RES / 2; py = sim.Y0 - yy * sim.RES - sim.RES / 2
            d_near = np.full(px.shape, np.inf)
            for a, b in zip(first.x.values, first.y.values):
                d_near = np.minimum(d_near, np.hypot(px - a, py - b))
            mask = np.isin(sim.WC[i0:i1, j0:j1], [10, 20, 30]) & (d_near <= footprint.R_MAX)
            n = int(S.sum()); Pp = score.topn(tph, mask, n); Pc = score.topn(d_near, mask, n)
            tv = np.sort(tph[mask]); t_reach = float(tv[n - 1]) if n <= len(tv) and tv[n - 1] < 96 else np.nan
            P26 = mask & (tph <= 26); P48 = mask & (tph <= 48)
            row = dict(event=int(e), season=s, ros_mult=m, scar_px=n, sor=score.soren(Pp, S), sor_circle=score.soren(Pc, S), t_reach_h=t_reach,
                       area26=int(P26.sum()), sor26=score.soren(P26, S), area48=int(P48.sum()), sor48=score.soren(P48, S))
            if len(later):
                r, c = sim.rc(later.x.values, later.y.values); r -= i0; c -= j0; h = h26 = hc = 0
                for a, b in zip(r, c):
                    sl = (slice(max(a - 12, 0), a + 13), slice(max(b - 12, 0), b + 13))
                    h += bool(Pp[sl].any()); h26 += bool(P26[sl].any()); hc += bool(Pc[sl].any())
                row.update(n_later=len(later), hit=h, hit26=h26, hit_circle=hc)
            rows.append(row)
        if k % 25 == 0:
            print(k, len(ids), f'{time.time() - tt:.0f}s', flush=True)
    pd.DataFrame(rows).to_parquet(out)


if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2])
