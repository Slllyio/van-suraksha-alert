"""Every satellite pass as its own timed row (Akkshay 16 Oct 20:06Z: "take all detections from the various sensors as
different rows; even a small time difference between sensors gives rate and direction of spread").

A pass = detections from ONE satellite within 15 min (S-NPP, NOAA-20, NOAA-21, Terra MODIS, Aqua MODIS, one Sentinel-2
or Landsat scene of hot pixels). Nothing is merged across satellites.

Short-gap test (every pair of consecutive passes on the same fire less than 3 h apart):
  shift      = centre of the later pass minus centre of the earlier pass (m), and its bearing
  new edge   = later-pass detections outside every block (real footprint) of the earlier pass: their direction
  reference  = where the fire really went next: bearing of the new burning at the next VIIRS pass at least 6 h later,
               measured from everything seen up to the pair (independent detections)
  If the short-gap move is fire spread, it should point the same way as the reference more than half the time, and the
  shift should grow with the gap. If it is position noise (pixel ~375-800 m, error ~290 m), 50% and flat.
Out: results/passes.csv (one row per pass), results/short_pairs.csv, results/short_gap_summary.json
"""
import glob, json, pickle
import numpy as np, pandas as pd, pyproj
from scipy.spatial import cKDTree
from shapely.geometry import Point
ROOT = '/mnt/project-files'; R = f'{ROOT}/research/big-fires/results'
F = pd.read_csv(f'{R}/fires.csv'); A = pd.read_csv(f'{R}/fire_alerts.csv', parse_dates=['t'])
F['big'] = (F.area_ha >= 200) & (F.n_looks >= 4) & (F.n_viirs >= 10) & ~F.still_at_edge
tp = pyproj.Transformer.from_crs(4326, 32643, always_xy=True).transform
# MODIS Terra / Aqua names
M = pd.concat([pd.read_csv(f) for f in glob.glob(f'{ROOT}/fire-alert-scars/alerts/modis_*.csv')], ignore_index=True).dropna(subset=['acq_time'])
M['t'] = pd.to_datetime(M.acq_date) + pd.to_timedelta(M.acq_time.astype(int) // 100, 'h') + pd.to_timedelta(M.acq_time.astype(int) % 100, 'min')
M['k'] = M.latitude.round(4).astype(str) + M.longitude.round(4).astype(str) + M.t.astype(str)
A['k'] = A.latitude.round(4).astype(str) + A.longitude.round(4).astype(str) + A.t.astype(str)
A = A.merge(M[['k', 'satellite']].drop_duplicates('k'), on='k', how='left')
NAME = {'viirs-snpp': 'S-NPP', 'viirs-jpss1': 'NOAA-20', 'viirs-noaa21': 'NOAA-21'}
A['sensor'] = [NAME.get(s, ('Terra MODIS' if m == 'Terra' else 'Aqua MODIS' if m == 'Aqua' else 'MODIS')) for s, m in zip(A.sat, A.satellite)]
md = A.sat == 'modis'
A['hw'] = A.scan.fillna(pd.Series(np.where(md, 1.0, 0.375), index=A.index)) * 500
A['hh'] = A.track.fillna(pd.Series(np.where(md, 1.0, 0.375), index=A.index)) * 500
# hot pixels on each fire's scar
import os
SP = f'{R}/fire_scars.pkl' if os.path.exists(f'{R}/fire_scars.pkl') else '/tmp/claude-0/-home-user/408de539-c392-557a-989b-ab3e8eea191b/scratchpad/bigfires_cache/fire_scars.pkl'
S = pickle.load(open(SP, 'rb'))
h = pd.concat([pd.read_csv(f) for f in glob.glob(f'{ROOT}/fire-alert-scars/out/af/af_*.csv')], ignore_index=True)
h['t'] = pd.to_datetime(h.date + ' ' + h.time_utc); h['x'], h['y'] = tp(h.lon.values, h.lat.values)
h['sensor'] = np.where(h.sensor == 's2', 'Sentinel-2', 'Landsat')
rows = []
for _, f in F[F.n_looks >= 1].iterrows():
    a = A[A.fire == f.fire]
    if not len(a): continue
    poly = S[f.fire]; x0, y0, x1, y1 = poly.bounds; zb = poly.buffer(100)
    hh = h[(h.x > x0 - 100) & (h.x < x1 + 100) & (h.y > y0 - 100) & (h.y < y1 + 100) & (h.t >= a.t.min() - pd.Timedelta(days=1)) & (h.t <= a.t.max() + pd.Timedelta(days=1))]
    if len(hh): hh = hh[np.array([zb.contains(Point(p)) for p in zip(hh.x, hh.y)], dtype=bool)]
    d = pd.concat([a[['t', 'x', 'y', 'sensor', 'frp', 'hw', 'hh', 'daynight']].assign(fire=f.fire),
                   hh[['t', 'x', 'y', 'sensor']].assign(fire=f.fire, frp=np.nan, hw=15.0, hh=15.0, daynight='D')], ignore_index=True)
    rows.append(d)
D = pd.concat(rows, ignore_index=True).sort_values(['fire', 'sensor', 't'])
D['pass_id'] = ((D.fire != D.fire.shift()) | (D.sensor != D.sensor.shift()) | (D.t.diff() > pd.Timedelta(minutes=15))).cumsum()
inv = pyproj.Transformer.from_crs(32643, 4326, always_xy=True).transform
D['lon'], D['lat'] = inv(D.x.values, D.y.values)
D.assign(t_ist=D.t + pd.Timedelta(hours=5, minutes=30), pix_w_m=2 * D.hw, pix_h_m=2 * D.hh).round({'lat': 5, 'lon': 5, 'x': 1, 'y': 1})[
    ['fire', 'pass_id', 'sensor', 't', 't_ist', 'lat', 'lon', 'x', 'y', 'frp', 'pix_w_m', 'pix_h_m', 'daynight']].to_csv(f'{R}/detections.csv', index=False)
P = D.groupby('pass_id').agg(fire=('fire', 'first'), sensor=('sensor', 'first'), t=('t', 'min'), n=('x', 'size'), x=('x', 'mean'), y=('y', 'mean'),
                             frp_sum=('frp', 'sum'), pix_w_m=('hw', lambda s: 2 * s.mean()), pix_h_m=('hh', lambda s: 2 * s.mean())).reset_index()
P = P.sort_values(['fire', 't']); P['n_in_fire'] = P.groupby('fire').cumcount() + 1
P['t_ist'] = P.t + pd.Timedelta(hours=5, minutes=30)
P['gap_from_prev_min'] = P.groupby('fire').t.diff().dt.total_seconds() / 60
P.merge(F[['fire', 'big']], on='fire').to_csv(f'{R}/passes.csv', index=False)
print('passes', len(P), 'in', P.fire.nunique(), 'fires; by sensor:', P.sensor.value_counts().to_dict())

# ---- short-gap pairs
def comp(dx, dy): return np.degrees(np.arctan2(dx, dy)) % 360
pairs = []
V = D[~D.sensor.isin(['Sentinel-2', 'Landsat'])]
for fid, g in P.groupby('fire'):
    g = g.reset_index(drop=True)
    dd = D[D.fire == fid]; vv = V[V.fire == fid]
    for i in range(1, len(g)):
        p0, p1 = g.iloc[i - 1], g.iloc[i]
        gap = (p1.t - p0.t).total_seconds() / 60
        if gap <= 0 or gap > 180: continue
        a0 = dd[dd.pass_id == p0.pass_id]; a1 = dd[dd.pass_id == p1.pass_id]
        sx, sy = p1.x - p0.x, p1.y - p0.y
        out = (np.abs(a1.x.values[:, None] - a0.x.values[None]) > a0.hw.values[None] + 0) | (np.abs(a1.y.values[:, None] - a0.y.values[None]) > a0.hh.values[None])
        outside = a1[out.all(1)]
        # reference: next VIIRS pass >= 6 h after p1, new burning (> 400 m from all earlier) vs everything seen up to p1
        seen = vv[vv.t <= p1.t + pd.Timedelta(minutes=1)]
        later = vv[vv.t >= p1.t + pd.Timedelta(hours=6)]
        ref = np.nan; ref_d = np.nan
        if len(later) and len(seen):
            tn = later.t.min(); nxt = later[later.t <= tn + pd.Timedelta(hours=2)]
            dn = cKDTree(seen[['x', 'y']].values).query(nxt[['x', 'y']].values)[0]; new = nxt[dn > 400]
            if len(new):
                c0 = seen[['x', 'y']].values.mean(0); ref = comp(new.x.mean() - c0[0], new.y.mean() - c0[1]); ref_d = np.hypot(new.x.mean() - c0[0], new.y.mean() - c0[1])
        pairs.append(dict(fire=fid, big=bool(F.loc[F.fire == fid, 'big'].iloc[0]), s0=p0.sensor, s1=p1.sensor, t0=p0.t, gap_min=gap, n0=p0.n, n1=p1.n,
                          shift_m=np.hypot(sx, sy), shift_deg=comp(sx, sy) if np.hypot(sx, sy) > 0 else np.nan,
                          n_outside=len(outside), out_deg=comp(outside.x.mean() - p0.x, outside.y.mean() - p0.y) if len(outside) else np.nan,
                          out_m=np.hypot(outside.x.mean() - p0.x, outside.y.mean() - p0.y) if len(outside) else np.nan,
                          pix0=p0.pix_w_m, pix1=p1.pix_w_m, ref_deg=ref, ref_m=ref_d))
Q = pd.DataFrame(pairs); Q.to_csv(f'{R}/short_pairs.csv', index=False)
cosd = lambda a, b: np.cos(np.radians(a - b))
summ = {}
Q['kind'] = Q.s0 + ' -> ' + Q.s1
for name, q in [('all pairs < 3 h', Q), ('VIIRS to VIIRS', Q[~Q.s0.str.contains('MODIS|Sentinel|Landsat') & ~Q.s1.str.contains('MODIS|Sentinel|Landsat')]),
                ('involving MODIS', Q[Q.kind.str.contains('MODIS')]), ('involving Sentinel-2/Landsat', Q[Q.kind.str.contains('Sentinel|Landsat')]),
                ('big fires only', Q[Q.big])]:
    r = q.dropna(subset=['ref_deg'])
    c_shift = cosd(r.shift_deg, r.ref_deg).dropna(); ro = r.dropna(subset=['out_deg']); c_out = cosd(ro.out_deg, ro.ref_deg)
    summ[name] = dict(pairs=len(q), median_gap_min=round(q.gap_min.median()), median_shift_m=round(q.shift_m.median()),
                      implied_rate_m_per_h=round((q.shift_m / (q.gap_min / 60)).median()),
                      shift_same_way_as_next_growth_pct=round(100 * (c_shift > 0).mean(), 1), n_with_reference=len(c_shift),
                      shift_mean_cos=round(c_shift.mean(), 3),
                      new_edge_same_way_pct=round(100 * (c_out > 0).mean(), 1) if len(c_out) else None, n_new_edge=len(c_out),
                      shift_m_by_gap={f'{a}-{b} min': round(q[(q.gap_min >= a) & (q.gap_min < b)].shift_m.median()) if ((q.gap_min >= a) & (q.gap_min < b)).sum() else None
                                      for a, b in [(0, 30), (30, 60), (60, 90), (90, 180)]})
# bootstrap CI over fires for the main number
r = Q.dropna(subset=['ref_deg', 'shift_deg']); fires_ = r.fire.unique(); rng = np.random.default_rng(0)
bs = [np.mean(np.concatenate([(cosd(r[r.fire == f_].shift_deg, r[r.fire == f_].ref_deg) > 0).values for f_ in rng.choice(fires_, len(fires_))])) for _ in range(500)]
summ['all pairs < 3 h']['same_way_95pct_range'] = [round(100 * np.quantile(bs, .025), 1), round(100 * np.quantile(bs, .975), 1)]
# compare: 12 h steps (from b3) for scale
print(json.dumps(summ, indent=1)); json.dump(summ, open(f'{R}/short_gap_summary.json', 'w'), indent=1)
print(Q.kind.value_counts().head(12))
