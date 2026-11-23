"""Can the run direction be read from the FIRST VIIRS pass? Truth = direction from the first-pass centroid to the grown
polygon's centroid (4k truth). Cues known at the first pass: FRP-weighted and brightness-weighted centroid shifts, the
hottest pixel, the cluster axis (undirected), and the static cues of rundir.py (fuel mass, away from village / earlier
burns / roads / non-fuel, downslope, ERA5 wind); for reference the pass 1->2 move. -> data/direction_cues.parquet + json"""
import numpy as np, pandas as pd, json
import sim, grown
def az(vx, vy):
    return (np.degrees(np.arctan2(vx, vy)) + 360) % 360 if np.isfinite(vx) else np.nan
def dang(a, b):
    d = np.abs((a - b + 180) % 360 - 180); return d
v = pd.read_parquet(f'{sim.DATA}/viirs_events.parquet'); st = grown.load(); rd = pd.read_parquet(f'{sim.DATA}/rundir.parquet').set_index('event')
rows = []; pad = int(2600 / sim.RES)
for e, ev in v.groupby('event'):
    if e not in st or e not in rd.index:
        continue
    ev = ev.sort_values('t'); first = ev[ev.overpass == ev.overpass.min()]
    r, c = sim.rc(ev.x.values, ev.y.values)
    i0, i1 = max(r.min() - pad, 0), min(r.max() + pad, sim.NY); j0, j1 = max(c.min() - pad, 0), min(c.max() + pad, sim.NX)
    G, _ = grown.scar_footprint(dict(win=(i0, i1, j0, j1)), ev)
    if G.sum() < 125:
        continue
    ys, xs = np.nonzero(G); px, py = xs.astype(float), -ys.astype(float)
    rf, cf = sim.rc(first.x.values, first.y.values); fx, fy = (cf - j0).mean(), -(rf - i0).mean()
    cx, cy = px.mean(), py.mean(); run_m = np.hypot(cx - fx, cy - fy) * sim.RES
    cov = np.cov(np.c_[px - cx, py - cy].T); w_, V = np.linalg.eigh(cov); axv = V[:, 1]; elong = np.sqrt(w_[1]) / np.sqrt(max(w_[0], 1e-9))
    proj = (px - cx) * axv[0] + (py - cy) * axv[1]; lo, hi = np.percentile(proj, [2, 98])
    u = ((fx - cx) * axv[0] + (fy - cy) * axv[1] - lo) / max(hi - lo, 1e-9); u = float(np.clip(u, 0, 1)); u = min(u, 1 - u)
    # first-pass cues in metres (east, north)
    X, Y = first.x.values, first.y.values; mx, my = X.mean(), Y.mean()
    def wshift(w):
        if len(first) < 2 or w.sum() <= 0: return np.nan, np.nan
        sx, sy = (w * X).sum() / w.sum() - mx, (w * Y).sum() / w.sum() - my; d = np.hypot(sx, sy)
        return (az(sx, sy) if d >= 50 else np.nan), d
    az_frp, d_frp = wshift(first.frp.values.astype(float)); az_bt, d_bt = wshift(np.clip(first.bright_ti4.values.astype(float) - 300, 0, None))
    k = int(np.argmax(first.frp.values)); dh = np.hypot(X[k] - mx, Y[k] - my); az_hot = az(X[k] - mx, Y[k] - my) if (len(first) >= 2 and dh >= 100) else np.nan
    rr = rd.loc[e]
    rows.append(dict(event=e, season=int(ev.season.iloc[0]), n_first=len(first), n_pass=ev.overpass.nunique(), poly_px=int(G.sum()), run_az_poly=az(cx - fx, cy - fy), run_m_poly=run_m,
                     elong_poly=float(elong), u_poly=u, run_az_raster=float(rr.run_az), az_frp=az_frp, d_frp=d_frp, az_bt=az_bt, az_hot=az_hot, front_az=float(rr.front_az),
                     fuel_az=float(rr.fuel_az), vill_az=float(rr.vill_az), burn_az=float(rr.burn_az), road_az=float(rr.road_az), lc_az=float(rr.lc_az), edge_az=float(rr.edge_az),
                     down_az=float(rr.down_az), wind_az=float(rr.wind_az), mom_az=float(rr.mom_az), load_az=float(rr.load_az), night_first=float(rr.night_first)))
d = pd.DataFrame(rows); d.to_parquet(f'{sim.DATA}/direction_cues.parquet')
out = dict(n=len(d), run_m_median=float(d.run_m_poly.median()), elong_median=float(d.elong_poly.median()), u_median=float(d.u_poly.median()),
           raster_vs_poly_within45=round(float((dang(d.run_az_raster, d.run_az_poly) <= 45).mean()), 3))
far = d[d.run_m_poly >= 300]   # fires whose polygon centroid is at least 300 m from the first pass: a direction exists
out['n_far'] = len(far)
for cue in ['az_frp', 'az_bt', 'az_hot', 'fuel_az', 'vill_az', 'burn_az', 'road_az', 'lc_az', 'edge_az', 'down_az', 'wind_az', 'load_az', 'mom_az']:
    q = far.dropna(subset=[cue]); dd = dang(q[cue], q.run_az_poly)
    out[cue] = dict(n=len(q), within45=round(float((dd <= 45).mean()), 3), within90=round(float((dd <= 90).mean()), 3), mean_cos=round(float(np.cos(np.radians(dd)).mean()), 3))
q = far.dropna(subset=['front_az']); dd = np.minimum(dang(q.front_az, q.run_az_poly), dang(q.front_az + 180, q.run_az_poly))
out['front_axis'] = dict(n=len(q), within45_either_end=round(float((dd <= 45).mean()), 3), random=0.5)
# does the cluster axis align with the scar's long axis?
q = far.dropna(subset=['front_az']); 
json.dump(out, open(f'{sim.DATA}/direction_cues.json', 'w'), indent=1); print(json.dumps(out, indent=1))
