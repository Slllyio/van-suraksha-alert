"""Section 15 detail on the statewide ECOSTRESS clips (from b17b): fire-level bootstrap CIs for the 14c measures, the 14c
"between the two block centres" measure for 2-block passes (hot pixel projects onto the segment joining the centres, 0<s<1),
and splits by satellite, scan angle (block width) and time of day.
Output: results/mp_between_blocks_detail.json"""
import os, json, numpy as np, pandas as pd
from pyproj import Transformer
R = '/mnt/project-files/research/big-fires/results'; M = '/mnt/project-files/fire-alert-scars/mp/out'
CL = os.environ.get('MP_ECO_SCRATCH', '/tmp/claude-0/mp_eco') + '/clips'
D = pd.read_csv(f'{R}/mp_ecostress_passes.csv', parse_dates=['t0']); V = D[D.visible == True].copy()
A = pd.read_csv(f'{M}/mp_alert_event.csv', usecols=['latitude', 'longitude', 'acq_date', 'acq_time', 'satellite', 'instrument', 'scan', 'track', 'event_id'])
A = A[(A.instrument == 'VIIRS') & A.event_id.isin(V.event_id)]
A['t'] = pd.to_datetime(A.acq_date + ' ' + A.acq_time.astype(int).astype(str).str.zfill(4), format='%Y-%m-%d %H%M')
to43 = Transformer.from_crs('EPSG:4326', 'EPSG:32643', always_xy=True); A['x'], A['y'] = to43.transform(A.longitude.values, A.latitude.values)
rows = []
for r in V.itertuples():
    z = np.load(f'{CL}/{r.event_id}_{r.granule}.npz'); lst = z['lst'].astype(float); clear = np.isfinite(lst) & (lst > 250) & (z['cloud'] == 0)
    g = A[(A.event_id == r.event_id) & (A.satellite == r.sensor) & ((A.t - r.t0).abs() <= pd.Timedelta(hours=1))]
    if g.empty: continue
    v = A[(A.event_id == r.event_id) & ((A.t - r.t0).abs() <= pd.Timedelta(hours=1))]
    dmin = np.hypot(z['x'][:, None] - v.x.values[None], z['y'][:, None] - v.y.values[None]).min(1)
    near, ring = dmin <= 600, (dmin >= 1500) & (dmin <= 3000)
    bg = np.median(lst[clear & ring]); hot = (lst - bg > 10) & clear & near
    hx, hy = z['x'][hot], z['y'][hot]
    bx, by, bw, bh = g.x.values, g.y.values, g.scan.values * 1000, g.track.values * 1000
    d = np.hypot(hx[:, None] - bx[None], hy[:, None] - by[None]); i = d.argmin(1)
    u = np.maximum(np.abs(hx - bx[i]) / (bw[i] / 2), np.abs(hy - by[i]) / (bh[i] / 2))
    rec = dict(event_id=r.event_id, t0=r.t0, sensor=r.sensor, n_blocks=len(g), scan_km=float(g.scan.mean()), hour_utc=r.t0.hour,
               outer=float((u > 0.5).mean()), inside=float((u <= 1).mean()), dnear=float(np.median(d.min(1))))
    if len(g) == 2:
        p, q = np.array([bx[0], by[0]]), np.array([bx[1], by[1]]); sep = float(np.hypot(*(q - p)))
        s = ((hx - p[0]) * (q - p)[0] + (hy - p[1]) * (q - p)[1]) / max(sep ** 2, 1.0)
        rec.update(sep=sep, between=float(((s > 0) & (s < 1)).mean()))
    rows.append(rec)
X = pd.DataFrame(rows); rng = np.random.default_rng(0)


def boot(df, col, n=1000):
    ev = df.event_id.unique(); g = {e: df[df.event_id == e][col].values for e in ev}
    vals = [np.mean(np.concatenate([g[e] for e in rng.choice(ev, len(ev))])) for _ in range(n)]
    return [round(float(df[col].mean()), 3), round(float(np.percentile(vals, 2.5)), 3), round(float(np.percentile(vals, 97.5)), 3)]


X['kind'] = np.where(X.n_blocks == 1, 'single block', np.where(X.n_blocks == 2, '2 blocks', '3+ blocks'))
out = dict(passes=int(len(X)), fires=int(X.event_id.nunique()),
           note='mean share per pass [estimate, 95% CI by fire bootstrap]; random-in-block reference: outer half 0.75', by_kind={})
for k, g in X.groupby('kind'):
    out['by_kind'][k] = dict(passes=int(len(g)), share_outer_half=boot(g, 'outer'), share_inside_block=boot(g, 'inside'),
                             hot_to_nearest_centre_m=round(float(g.dnear.median())))
two = X[X.n_blocks == 2]
out['two_blocks_between_centres'] = {'adjacent_<500m': dict(passes=int((two.sep < 500).sum()), share_between=boot(two[two.sep < 500], 'between')),
                                     'far_>=500m': dict(passes=int((two.sep >= 500).sum()), share_between=boot(two[two.sep >= 500], 'between')),
                                     'ratapani_30m_reference': dict(adjacent=0.37, far=0.88)}
out['by_satellite'] = {s: dict(passes=int(len(g)), share_outer_half=boot(g, 'outer')) for s, g in X.groupby('sensor')}
X['scan_band'] = pd.cut(X.scan_km, [0, 0.45, 0.6, 9], labels=['near nadir (<0.45 km)', 'mid (0.45-0.6)', 'edge (>0.6)'])
out['by_scan'] = {str(s): dict(passes=int(len(g)), share_outer_half=boot(g, 'outer'), share_inside_block=boot(g, 'inside')) for s, g in X.groupby('scan_band', observed=True)}
X['tod'] = np.where((X.hour_utc >= 1) & (X.hour_utc <= 13), 'day', 'night')
out['by_time'] = {s: dict(passes=int(len(g)), share_outer_half=boot(g, 'outer')) for s, g in X.groupby('tod')}
json.dump(out, open(f'{R}/mp_between_blocks_detail.json', 'w'), indent=1); print(json.dumps(out, indent=1))
