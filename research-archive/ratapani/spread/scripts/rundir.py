"""Where does the real scar lie relative to the first detection, and what predicts that direction?
For every scarred fire: scar principal axis, elongation, position of the first-pass detections along the axis,
run vector (first-detection centroid -> scar centroid), and candidate predictors of the run direction measured
at the first detections: away from the nearest non-fuel (non-forest, earlier burn), toward the most burnable
fuel within 1 km, away from the nearest road, away from built-up, downslope, ERA5 wind, and the direction from the
first pass to the second pass (momentum). Usage: rundir.py out.parquet"""
import numpy as np, pandas as pd, sys
from scipy import ndimage
import sim, score
v = pd.read_parquet(f'{sim.DATA}/viirs_events.parquet'); v = v[v.t.dt.month <= 6]
wc_all = sim.WC; rows = []; wx = {}
ROAD = sim.BARRIER
def unit(vx, vy):
    n = np.hypot(vx, vy); return (vx / n, vy / n) if n > 0 else (np.nan, np.nan)
def az(vx, vy):   # compass bearing of a (east, north) vector
    return (np.degrees(np.arctan2(vx, vy)) + 360) % 360 if np.isfinite(vx) else np.nan
for e, ev in v.groupby('event'):
    ev = ev.sort_values('t'); s = int(ev.season.iloc[0])
    if s not in wx:
        wx.clear(); wx[s] = sim.load_weather(s)
    cfg = dict(fuel='rfuel', wind=False, pad_m=4000)
    o = sim.run_event(ev, wx[s], cfg, hours=1, scar_fn=score.scar_footprint)   # 1 h run: we only need the masks
    S, B, (i0, i1, j0, j1), t0 = o['S'], o['burnable'], o['win'], o['t0']
    if S.sum() < 125:    # >= 5 ha
        continue
    first = ev[ev.overpass == ev.overpass.min()]
    r, c = sim.rc(first.x.values, first.y.values); r = r - i0; c = c - j0
    # pixel coordinates: x east = c, y north = -r
    ys, xs = np.nonzero(S); px, py = xs.astype(float), -ys.astype(float)
    cx, cy = px.mean(), py.mean(); fx, fy = c.mean(), -r.mean()
    # principal axis of the scar
    cov = np.cov(np.c_[px - cx, py - cy].T); w_, V = np.linalg.eigh(cov); ax = V[:, 1]; L = np.sqrt(w_[1]); W_ = np.sqrt(max(w_[0], 1e-9))
    proj = (px - cx) * ax[0] + (py - cy) * ax[1]; lo, hi = np.percentile(proj, [2, 98])
    u = ((fx - cx) * ax[0] + (fy - cy) * ax[1] - lo) / max(hi - lo, 1e-9); u = float(np.clip(u, 0, 1)); u = min(u, 1 - u)   # 0 = at an end, 0.5 = centre
    run = (cx - fx, cy - fy); run_m = np.hypot(*run) * sim.RES; rx, ry = unit(*run)
    # how far the scar extends from the first detections, in metres (95th percentile distance), and the share of
    # scar pixels more than 1 km from every detection of the event (later passes included)
    d_first = np.hypot(px - fx, py - fy) * sim.RES
    ra, ca = sim.rc(ev.x.values, ev.y.values); ra -= i0; ca -= j0
    dm = np.zeros(S.shape, bool); dm[np.clip(ra, 0, S.shape[0] - 1), np.clip(ca, 0, S.shape[1] - 1)] = True
    d_any = ndimage.distance_transform_edt(~dm) * sim.RES
    far = float((d_any[S] > 1000).mean())
    # predictors at the first detections (mean position)
    ri, ci = int(round(r.mean())), int(round(c.mean())); R = 50   # 1 km
    sl = (slice(max(ri - R, 0), ri + R + 1), slice(max(ci - R, 0), ci + R + 1))
    yy, xx = np.mgrid[sl[0], sl[1]]; dx, dy = (xx - ci).astype(float), -(yy - ri).astype(float); dd = np.hypot(dx, dy)
    disc = dd <= R
    def away_from(mask, rmax=25):   # unit vector from the centroid of mask pixels within rmax (500 m) to the point
        m = mask[sl] & (dd <= rmax)
        if not m.any(): return (np.nan, np.nan), np.nan
        return unit(-dx[m].mean(), -dy[m].mean()), float(np.hypot(dx[m].mean(), dy[m].mean())) * sim.RES
    nonfuel = ~B
    (ex, ey), edge_d = away_from(nonfuel)                       # away from non-fuel (non-forest, water, built, earlier burn, road)
    wcw = wc_all[i0:i1, j0:j1]
    (gx, gy), _ = away_from(~np.isin(wcw, [10, 20, 30]))        # away from non-vegetation land cover only
    be = sim.G[f'burn_end_{s}'][i0:i1, j0:j1]; d0 = ev.t.min().dayofyear
    (bx, by), burn_d = away_from((be > -999) & (be < d0 - 1))   # away from this season's earlier burns
    (qx, qy), road_d = away_from(ROAD[i0:i1, j0:j1]) if ROAD is not None else ((np.nan, np.nan), np.nan)
    (vx, vy), vill_d = away_from(wcw == 50, 50)                   # away from built-up within 1 km
    m = B[sl] & disc; (ux, uy) = unit(dx[m].sum(), dy[m].sum()) if m.any() else (np.nan, np.nan)   # toward the fuel mass within 1 km
    fuel_frac = float(m.sum() / disc.sum())
    el = sim.ELEV[i0:i1, j0:j1][sl]; gy_, gx_ = np.gradient(el.astype(float), sim.RES)
    (sx, sy) = unit(-gx_[ri - sl[0].start, ci - sl[1].start], gy_[ri - sl[0].start, ci - sl[1].start])   # downslope (north = -row)
    slope_deg = float(sim.SLOPE[i0 + ri, j0 + ci])
    Wd, P = wx[s]; pid = P.index[np.argmin(np.hypot(P.x - ev.x.mean(), P.y - ev.y.mean()))]
    ww = Wd[pid][(Wd[pid].index >= ev.t.min()) & (Wd[pid].index <= ev.t.min() + pd.Timedelta(hours=24))]
    wu, wv = (ww.ws * np.sin(np.radians(ww.waz))).mean(), (ww.ws * np.cos(np.radians(ww.waz))).mean(); (wx_, wy_) = unit(wu, wv); wsp = float(np.hypot(wu, wv))
    passes = sorted(ev.overpass.unique()); mx_ = my_ = np.nan
    if len(passes) > 1:
        sec = ev[ev.overpass == passes[1]]; (mx_, my_) = unit(sec.x.mean() - first.x.mean(), sec.y.mean() - first.y.mean())
    # orientation of the first-pass cluster (front line), as an axis (0-180)
    front_az = np.nan
    if len(first) >= 2:
        cc = np.cov(np.c_[first.x - first.x.mean(), first.y - first.y.mean()].T); _, VV = np.linalg.eigh(cc); front_az = az(VV[0, 1], VV[1, 1]) % 180
    rows.append(dict(event=e, season=s, scar_px=int(S.sum()), n_first=len(first), n_pass=len(passes), elong=L / W_, u_first=u, run_m=run_m,
                     ext95_m=float(np.percentile(d_first, 95)), far_frac=far, run_az=az(rx, ry), scar_axis_az=az(ax[0], ax[1]) % 180,
                     edge_az=az(ex, ey), edge_d=edge_d, lc_az=az(gx, gy), burn_az=az(bx, by), burn_d=burn_d, road_az=az(qx, qy), road_d=road_d,
                     vill_az=az(vx, vy), vill_d=vill_d, fuel_az=az(ux, uy), fuel_frac=fuel_frac, down_az=az(sx, sy), slope_deg=slope_deg,
                     wind_az=az(wx_, wy_), wind_ms=wsp, mom_az=az(mx_, my_), front_az=front_az,
                     night_first=int(first.t.dt.hour.iloc[0] >= 15 or first.t.dt.hour.iloc[0] < 5)))
d = pd.DataFrame(rows); d.to_parquet(sys.argv[1]); print('fires', len(d))
