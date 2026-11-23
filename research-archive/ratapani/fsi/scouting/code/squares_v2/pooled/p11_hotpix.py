"""Step 9: independent truth for pooled outward motion -- Sentinel-2 / Landsat 30 m hot pixels (Ratapani, ~10:45 IST).
For each hot-pixel pass of a fire (>= 3 hot pixels): H = hot-pixel centre (placed to ~30 m), E = centre of the fire's VIIRS
detections 13-48 h before (so never one of the looks tested), outward unit u = (H - E)/|H - E| (H is precise, so u carries almost no noise from the looks
being tested). Then for every look L of the same fire near that time, p = (L centre - H) . u:
  Terra MODIS within 30 min of H : same moment -> p should be ~0 (a real-fire null for the whole method)
  VIIRS day pass 1-4 h after H   : p / gap = outward speed over 10:45 -> 13:30
  VIIRS night pass 6-12 h before : p should be negative (fire was behind the 10:45 line)
Pooled over passes, 95% CI by fire bootstrap. Out: results/hotpix_outward.csv/json"""
import json, os
import numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__)); OUT = f'{HERE}/results'
rng = np.random.default_rng(11)
D = pd.read_csv('/mnt/project-files/research/big-fires/results/detections.csv', parse_dates=['t'])
D['kind'] = D.sensor.map({'Sentinel-2': 'hot', 'Landsat': 'hot', 'S-NPP': 'viirs', 'NOAA-20': 'viirs', 'NOAA-21': 'viirs', 'Terra MODIS': 'terra', 'Aqua MODIS': 'aqua'})
rows = []
for fire, g in D.groupby('fire'):
    hp = g[g.kind == 'hot']
    if not len(hp): continue
    V = g[g.kind == 'viirs']
    for pid, h in hp.groupby('pass_id'):
        if len(h) < 3: continue
        tH = h.t.min(); Hx, Hy = h.x.mean(), h.y.mean()
        e = V[(V.t >= tH - pd.Timedelta(hours=48)) & (V.t <= tH - pd.Timedelta(hours=13))]   # 13-48 h: never the looks tested
        if not len(e): continue
        ux, uy = Hx - e.x.mean(), Hy - e.y.mean(); L = np.hypot(ux, uy)
        if L < 100: continue
        ux, uy = ux / L, uy / L
        for kind, lo, hi, lab in [('terra', -0.5, 0.5, 'Terra MODIS within 30 min (null)'), ('viirs', 1, 4.5, 'VIIRS day pass 1-4.5 h after'),
                                  ('viirs', -12.5, -6, 'VIIRS night pass 6-12.5 h before'), ('aqua', 1, 4.5, 'Aqua MODIS 1-4.5 h after')]:
            c = g[(g.kind == kind) & (g.t >= tH + pd.Timedelta(hours=lo)) & (g.t <= tH + pd.Timedelta(hours=hi))]
            for qid, q in c.groupby('pass_id'):
                dt = (q.t.min() - tH).total_seconds() / 3600
                rows.append(dict(fire=fire, season=tH.year, test=lab, dt_h=dt, n=len(q), nH=len(h), u_len=L,
                                 p=(q.x.mean() - Hx) * ux + (q.y.mean() - Hy) * uy, perp=-(q.x.mean() - Hx) * uy + (q.y.mean() - Hy) * ux,
                                 dx=q.x.mean() - Hx, dy=q.y.mean() - Hy, ux=ux, uy=uy))
P = pd.DataFrame(rows); P.to_csv(f'{OUT}/hotpix_outward.csv', index=False)
res = {}
for lab, g in P.groupby('test'):
    v = g.p.clip(-2000, 2000).values; fr = pd.factorize(g.fire)[0]; nf = fr.max() + 1
    s = np.bincount(fr, v, nf); c = np.bincount(fr, minlength=nf).astype(float)
    bs = np.array([s[k].sum() / c[k].sum() for k in (rng.integers(0, nf, nf) for _ in range(1000))])
    m = v.mean(); dt = g.dt_h.mean()
    pp = g.perp.clip(-2000, 2000).mean()
    res[lab] = dict(passes=len(g), fires=int(nf), mean_dt_h=round(dt, 2), outward_m=round(m, 1), ci_m=f'{np.quantile(bs, .025):.1f} to {np.quantile(bs, .975):.1f}',
                    speed_m_h=round(m / dt, 1) if abs(dt) > 0.6 else None,
                    speed_ci=(f'{np.quantile(bs, .025) / dt:.1f} to {np.quantile(bs, .975) / dt:.1f}' if abs(dt) > 0.6 else None),
                    perpendicular_m=round(pp, 1), mean_vector_m=[round(g.dx.clip(-2000, 2000).mean()), round(g.dy.clip(-2000, 2000).mean())],
                    mean_u=[round(g.ux.mean(), 2), round(g.uy.mean(), 2)])
json.dump(res, open(f'{OUT}/hotpix_outward.json', 'w'), indent=1); print(json.dumps(res, indent=1))
