"""Two more first-pass direction cues on the polygon truth (Akkshay: "try"):
(1) a back-fitted start point: the hot front seen at the first pass bows outward in the direction of travel, so for a
    first pass of 3+ pixels that are not in a line, fit a circle through the pixel centres; the centre of that circle is
    the start estimate and the direction from it to the cluster is the heading. Also the physics-free version: the
    cluster's convex side (sign of the arc). (2) pixel far sides for the pass-to-pass bearing: each pass-2 point is moved to
    the edge of its scan x track footprint that is farthest from the pass-1 centroid; bearing from the pass-1 centroid to
    those points against the polygon run direction, compared with the centre-based bearing. -> data/direction_cues2.json"""
import numpy as np, pandas as pd, json
import sim, grown
def az(vx, vy): return (np.degrees(np.arctan2(vx, vy)) + 360) % 360
def dang(a, b): return np.abs((a - b + 180) % 360 - 180)
v = pd.read_parquet(f'{sim.DATA}/viirs_events.parquet'); st = grown.load()
dc = pd.read_parquet(f'{sim.DATA}/direction_cues.parquet').set_index('event')   # polygon run direction and distance
def circfit(x, y):
    """algebraic circle fit; returns centre, radius, rms residual"""
    A = np.c_[2 * x, 2 * y, np.ones_like(x)]; b = x ** 2 + y ** 2
    sol, *_ = np.linalg.lstsq(A, b, rcond=None); cx, cy = sol[0], sol[1]; r = np.sqrt(max(sol[2] + cx ** 2 + cy ** 2, 1e-9))
    return cx, cy, r, float(np.sqrt(np.mean((np.hypot(x - cx, y - cy) - r) ** 2)))
rows = []
for e, ev in v.groupby('event'):
    if e not in dc.index: continue
    ev = ev.sort_values('t'); passes = sorted(ev.overpass.unique()); first = ev[ev.overpass == passes[0]]
    X, Y = first.x.values, first.y.values; mx, my = X.mean(), Y.mean()
    row = dict(event=e, n_first=len(first), run_az=dc.run_az_poly[e], run_m=dc.run_m_poly[e])
    # (1) start point by circle fit, only for 3+ pixels that are not nearly collinear and whose arc is not tiny
    if len(first) >= 3:
        cov = np.cov(np.c_[X - mx, Y - my].T); w_, _ = np.linalg.eigh(cov); width = np.sqrt(max(w_[0], 0)); length = np.sqrt(w_[1])
        if width > 60 and length > 150:
            cx, cy, r, rms = circfit(X, Y)
            if 150 < r < 5000 and rms < 150:
                row.update(start_az=az(mx - cx, my - cy), start_r=r, start_rms=rms)
    # (2) far side for pass 1 -> pass 2
    if len(passes) >= 2:
        sec = ev[ev.overpass == passes[1]]
        sx, sy = sec.x.values, sec.y.values
        row['mom_az_centre'] = az(sx.mean() - mx, sy.mean() - my)
        hs, ht = sec.scan.values * 500.0, sec.track.values * 500.0   # half footprint across (east-west) and along (north-south) track
        fx = sx + np.sign(sx - mx) * hs; fy = sy + np.sign(sy - my) * ht
        row['mom_az_far'] = az(fx.mean() - mx, fy.mean() - my)
        # near side (the edge nearest the pass-1 centroid), as a control
        nx = sx - np.sign(sx - mx) * hs; ny = sy - np.sign(sy - my) * ht
        row['mom_az_near'] = az(nx.mean() - mx, ny.mean() - my)
        row['mom_lead_h'] = (sec.t.min() - first.t.min()).total_seconds() / 3600; row['mom_d'] = float(np.hypot(sx.mean() - mx, sy.mean() - my))
    rows.append(row)
d = pd.DataFrame(rows); d.to_parquet(f'{sim.DATA}/direction_cues2.parquet')
far = d[d.run_m >= 300]; out = dict(n=len(d), n_far=len(far))
q = far.dropna(subset=['start_az']); dd = dang(q.start_az, q.run_az)
out['start_point_circle_fit'] = dict(n=len(q), within45=round(float((dd <= 45).mean()), 3), within90=round(float((dd <= 90).mean()), 3), mean_cos=round(float(np.cos(np.radians(dd)).mean()), 3), radius_median_m=float(q.start_r.median()))
for k in ['mom_az_centre', 'mom_az_far', 'mom_az_near']:
    q = far.dropna(subset=[k]); dd = dang(q[k], q.run_az)
    out[k] = dict(n=len(q), within45=round(float((dd <= 45).mean()), 3), within90=round(float((dd <= 90).mean()), 3), mean_cos=round(float(np.cos(np.radians(dd)).mean()), 3))
    for lo, hi in [(0, 300), (300, 800), (800, 1e9)]:
        qq = q[(q.mom_d >= lo) & (q.mom_d < hi)]; ddq = dang(qq[k], qq.run_az)
        out[k][f'move_{lo:.0f}_{hi:.0f}m'] = dict(n=len(qq), within45=round(float((ddq <= 45).mean()), 3)) if len(qq) else None
json.dump(out, open(f'{sim.DATA}/direction_cues2.json', 'w'), indent=1); print(json.dumps(out, indent=1))
