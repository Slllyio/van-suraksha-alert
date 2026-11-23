"""Summarise the smoke-plume wind vane (plume.py output). Usage: plume_stats.py plume_0.parquet,plume_1.parquet"""
import numpy as np, pandas as pd, sys
import sim
d = pd.concat([pd.read_parquet(f) for f in sys.argv[1].split(',')], ignore_index=True)
v = pd.read_parquet(f'{sim.DATA}/viirs_events.parquet')
def dang(a, b):
    return np.abs(((a - b) + 180) % 360 - 180)
# next VIIRS pass after the scene (within 30 h): direction from the hot pixels to those detections
nxt_az, nxt_d, prv_az = [], [], []
for _, r in d.iterrows():
    ev = v[v.event == r.event]; ts = pd.Timestamp(r.date) + pd.Timedelta(hours=5.25)
    after = ev[(ev.t > ts) & (ev.t <= ts + pd.Timedelta(hours=30))]; before = ev[(ev.t < ts) & (ev.t >= ts - pd.Timedelta(hours=30))]
    hx = None
    if len(after):
        a = after[after.overpass == after.overpass.min()]
        # hot-pixel centroid is not stored; use hot_az/hot_d from the first pass centroid
        f = ev[ev.overpass == ev.overpass.min()]; hx = f.x.mean() + r.hot_d * np.sin(np.radians(r.hot_az)); hy = f.y.mean() + r.hot_d * np.cos(np.radians(r.hot_az))
        nxt_az.append((np.degrees(np.arctan2(a.x.mean() - hx, a.y.mean() - hy)) + 360) % 360); nxt_d.append(np.hypot(a.x.mean() - hx, a.y.mean() - hy))
    else:
        nxt_az.append(np.nan); nxt_d.append(np.nan)
    if len(before):
        b = before[before.overpass == before.overpass.max()]
        f = ev[ev.overpass == ev.overpass.min()]; hx = f.x.mean() + r.hot_d * np.sin(np.radians(r.hot_az)); hy = f.y.mean() + r.hot_d * np.cos(np.radians(r.hot_az))
        prv_az.append((np.degrees(np.arctan2(hx - b.x.mean(), hy - b.y.mean())) + 360) % 360)
    else:
        prv_az.append(np.nan)
d['nxt_az'] = nxt_az; d['nxt_d'] = nxt_d; d['prv_az'] = prv_az
d['front_az'] = (d.ahead_az + 180) % 360        # from the scar centroid to the active front (where the fire had got to)
print('scenes', len(d), 'fires', d.event.nunique(), '; cloud share median', d.cloud.median().round(2))
for thr in [0, 2, 3]:
    g = d[(d.strength >= thr) & (d.cloud < 0.3)]
    print(f'\n--- plume strength >= {thr}, cloud < 30%: {len(g)} scenes ---')
    rows = []
    for name, a in [('ERA5 wind at scene hour', g.wind_az), ('scar centre -> active front (where the fire had got to)', g.front_az),
                    ('front -> next VIIRS pass (where it went next, <=30 h)', g.nxt_az), ('previous pass -> front (VIIRS momentum)', g.prv_az),
                    ('first detection -> scar centre (run, 4f)', g.run_az), ('VIIRS pass 1 -> 2 momentum (4f)', g.mom_az)]:
        x = dang(g.plume_az, a); m = x.notna()
        rows.append(dict(relation=name, n=int(m.sum()), within45=round(float((x[m] <= 45).mean()), 3), opposite=round(float((x[m] >= 135).mean()), 3), mean_cos=round(float(np.cos(np.radians(x[m])).mean()), 3)))
    print(pd.DataFrame(rows).to_string(index=False))
    # ERA5 vs the scar front relations for the same scenes (is the problem the wind data or the fire?)
    rows = []
    for name, a in [('scar centre -> front', g.front_az), ('front -> next pass', g.nxt_az), ('run', g.run_az)]:
        x = dang(g.wind_az, a); m = x.notna()
        rows.append(dict(relation='ERA5 vs ' + name, n=int(m.sum()), within45=round(float((x[m] <= 45).mean()), 3), opposite=round(float((x[m] >= 135).mean()), 3), mean_cos=round(float(np.cos(np.radians(x[m])).mean()), 3)))
    print(pd.DataFrame(rows).to_string(index=False))
    # scar beyond the front: downwind vs upwind of the plume (pixels > 300 m from the hot pixels)
    tot = g.scar_far.replace(0, np.nan)
    print('share of the scar (>300 m from the front) downwind of the plume: median', round(float((g.scar_dw / tot).median()), 3), ' upwind:', round(float((g.scar_uw / tot).median()), 3))
print('\nERA5 speed vs plume strength: corr', round(float(d[['wind_ms', 'strength']].corr().iloc[0, 1]), 3), '; ERA5 vs plume within 45 deg by wind speed:')
for lo, hi in [(0, 1.5), (1.5, 3), (3, 99)]:
    g = d[(d.wind_ms >= lo) & (d.wind_ms < hi) & (d.strength >= 2) & (d.cloud < 0.3)]; x = dang(g.plume_az, g.wind_az)
    print(f'  {lo}-{hi} m/s: n={len(g)} within45={(x <= 45).mean():.3f}')
d.to_parquet(f'{sim.DATA}/plume_all.parquet')
