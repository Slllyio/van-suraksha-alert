"""Teak-litter cue for the run direction: from the first-pass detections, the direction toward the heavier 1-h litter
load (fuel-map layer, kg/m2) within 1 km, and the load contrast between the run side and the opposite side.
Adds load_az, load_ratio to rundir.parquet (in place). Usage: teakcue.py rundir.parquet"""
import numpy as np, pandas as pd, sys
import sim
rd = pd.read_parquet(sys.argv[1]).set_index('event')
v = pd.read_parquet(f'{sim.DATA}/viirs_events.parquet')
R = 50; yy, xx = np.mgrid[-R:R + 1, -R:R + 1]; dx, dy = xx.astype(float), -yy.astype(float); dd = np.hypot(dx, dy); disc = dd <= R
out = {}; cache = {}
for e in sorted(rd.index, key=lambda e: rd.loc[e, 'season']):
    ev = v[v.event == e]; s = int(ev.season.iloc[0]); first = ev[ev.overpass == ev.overpass.min()]
    r, c = sim.rc(first.x.values, first.y.values); ri, ci = int(round(r.mean())), int(round(c.mean()))
    if ri - R < 0 or ci - R < 0 or ri + R + 1 > sim.NY or ci + R + 1 > sim.NX:
        continue
    if s not in cache:
        cache.clear(); cache[s] = sim.RFUEL[f'rf_{s}'][0]   # the npz decompresses the whole layer on every access
    w1 = cache[s][ri - R:ri + R + 1, ci - R:ci + R + 1].astype(float)
    w1 = np.where(np.isfinite(w1), w1, 0.0) * disc
    if w1.sum() <= 0:
        continue
    vx, vy = (w1 * dx).sum(), (w1 * dy).sum(); n = np.hypot(vx, vy)
    az = (np.degrees(np.arctan2(vx, vy)) + 360) % 360 if n > 0 else np.nan
    ra = np.radians(rd.loc[e, 'run_az'])
    along = dx * np.sin(ra) + dy * np.cos(ra)
    front, back = w1[along > 0].mean(), w1[along < 0].mean()
    out[e] = dict(load_az=az, load_ratio=front / back if back > 0 else np.nan, load_mean=w1[disc].mean())
o = pd.DataFrame(out).T
rd = rd.join(o); rd.reset_index().to_parquet(sys.argv[1])
m = rd[(rd.run_m > 300)].dropna(subset=['load_az'])
diff = np.abs((m.load_az - m.run_az + 180) % 360 - 180)
print(f'toward heavier teak litter within 1 km (n={len(m)}): mean cos {np.cos(np.radians(diff)).mean():+.2f}, within 45 deg {(diff <= 45).mean():.0%}, within 90 deg {(diff <= 90).mean():.0%}')
print(f'litter load on the run side / opposite side, median {m.load_ratio.median():.2f} (q25-q75 {m.load_ratio.quantile(.25):.2f}-{m.load_ratio.quantile(.75):.2f}); > 1 in {(m.load_ratio > 1).mean():.0%} of fires')
big = m[m.scar_px >= 500]; d2 = np.abs((big.load_az - big.run_az + 180) % 360 - 180)
print(f'  scars >= 20 ha (n={len(big)}): cos {np.cos(np.radians(d2)).mean():+.2f}, within 45 deg {(d2 <= 45).mean():.0%}; load ratio median {big.load_ratio.median():.2f}')
