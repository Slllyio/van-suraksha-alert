"""Run the spread model on Ratapani VIIRS fire events and score it against later VIIRS detections
and the 20 m burn scars."""
import numpy as np, pandas as pd, sys, json, time
from scipy import ndimage
from rothermel import rothermel, dead_moisture, FUELS
from engine import ros_fields, ros_fields_px, arrival, OFFS
from rothermel import rothermel_px, r0_px

import os
DATA = os.environ.get('SPREAD_DATA', '/tmp/claude-0/spread/data')   # set SPREAD_DATA to use another copy of the data files
G = np.load(f'{DATA}/grid20.npz')
TR = G['transform']; RES = TR[0]; X0, Y0 = TR[2], TR[5]
ELEV, SLOPE, UPAZ, WC = G['elev'], G['slope'], G['upslope_az'], G['wc']
TAN = np.tan(np.radians(SLOPE)).astype(np.float64)
NY, NX = WC.shape

# interim fuel map: WorldCover class -> fuel model (overridable by config)
DEFAULT_FUELMAP = {10: 'TL6', 20: 'GS2', 30: 'GR2', 60: 'GR1'}   # others non-burnable
CDAC_FUELMAP = {10: 'FM9', 20: 'FM2', 30: 'FM1', 60: 'FM1'}      # WRF-SFIRE Anderson-13 style


FUEL = np.load(f'{DATA}/fuel20.npz') if __import__('os').path.exists(f'{DATA}/fuel20.npz') else None
RFUEL = np.load(f'{DATA}/rfuel20.npz') if __import__('os').path.exists(f'{DATA}/rfuel20.npz') else None
LEAFFALL = np.load(f'{DATA}/leaffall20.npz')['lf'] if __import__('os').path.exists(f'{DATA}/leaffall20.npz') else None
BARRIER = np.load(f'{DATA}/barriers.npz')['road'] if __import__('os').path.exists(f'{DATA}/barriers.npz') else None
_B2 = {}
def bar2(k):
    """FSI thread's barrier layer on the grid (prep_barriers2.py: seg_id, seg_p_far, pstop_d, road_any, stream_big, recur_c_<s>, pday_<s>), cached per key."""
    if k not in _B2:
        _B2[k] = np.load(f'{DATA}/barriers2.npz')[k]
    return _B2[k]
LOAD_EDGES = np.array([1, 5, 9, 13, 17, 21, 25, 30, 36, 1e9])
LOAD_MID = np.array([3, 7, 11, 15, 19, 23, 27.5, 33, 40])


def litter_models(cfg):
    """Custom Rothermel beds from the fuel map: 1 h load = mapped g/ft2 (x cfg load_mult), litter depth,
    SAV and extinction moisture as C-DAC's Sikkim forest values unless overridden."""
    names = []
    for k, g in enumerate(LOAD_MID):
        nm = f'LIT{k}'
        tpa = g * cfg.get('load_mult', 1.0) * 0.1076 / 2.471
        FUELS[nm] = ((tpa, tpa * cfg.get('f10', 0.0), 0, 0, 0), (cfg.get('sav', 2000), 1800, 1500),
                     cfg.get('depth_ft', 0.2) * (g / 23.0) ** cfg.get('depth_exp', 0.0), cfg.get('mx', 30), False)
        names.append(nm)
    return names


def load_weather(season):
    d = pd.read_csv(f'/mnt/project-files/ratapani/ee/era5/era5land_hourly_{season}.csv', parse_dates=['datetime_utc'])
    from pyproj import Transformer
    tr = Transformer.from_crs(4326, 32643, always_xy=True)
    pts = d.groupby('point_id')[['longitude', 'latitude']].first()
    px, py = tr.transform(pts.longitude.values, pts.latitude.values)
    W = {}
    for pid, g in d.groupby('point_id'):
        g = g.sort_values('datetime_utc')
        T = g.temperature_2m.values - 273.15; Td = g.dewpoint_temperature_2m.values - 273.15
        es = lambda t: 6.112 * np.exp(17.67 * t / (t + 243.5))
        rh = np.clip(100 * es(Td) / es(T), 1, 100)
        sol = np.clip(g.surface_solar_radiation_downwards_hourly.values / 3600, 0, None)
        pr = np.clip(g.total_precipitation_hourly.values * 1000, 0, None)
        m = dead_moisture(T, rh, pr, sol)
        u, v = g.u_component_of_wind_10m.values, g.v_component_of_wind_10m.values
        W[pid] = pd.DataFrame(dict(T=T, rh=rh, ws=np.hypot(u, v), waz=np.degrees(np.arctan2(u, v)) % 360,
                                   m1=m[:, 0], m10=m[:, 1], m100=m[:, 2]), index=g.datetime_utc.values)
    return W, pd.DataFrame(dict(x=px, y=py), index=pts.index)


def rc(x, y):
    return ((Y0 - y) / RES).astype(int), ((x - X0) / RES).astype(int)


def doy(ts):
    return ts.dayofyear


def run_event(ev, wx, cfg, hours=72, scar_fn=None):
    """ev: detections of one event (sorted by t). Returns dict of arrays for scoring."""
    t0 = ev.t.min().floor('h')
    pad = int(cfg.get('pad_m', 3000) / RES)
    r, c = rc(ev.x.values, ev.y.values)
    i0, i1 = max(r.min() - pad, 0), min(r.max() + pad, NY); j0, j1 = max(c.min() - pad, 0), min(c.max() + pad, NX)
    if cfg.get('win'):                      # caller's window (fair_table.py: the learned models' window)
        i0, i1, j0, j1 = cfg['win']
    season = int(ev.season.iloc[0]); d0 = doy(ev.t.min())
    wc = WC[i0:i1, j0:j1]
    if cfg.get('fuel') == 'rfuel':
        names, fidx = [], np.zeros(wc.shape, np.int64)
    elif cfg.get('fuel') == 'map':
        names = litter_models(cfg)
        ld = FUEL[f'load_{season}'][i0:i1, j0:j1].copy()
        outside = ~np.isfinite(ld) & np.isin(wc, [10, 20, 30])
        ld[outside] = cfg.get('outside_load', 21.0)
        fidx = np.digitize(np.nan_to_num(ld, nan=0.0), LOAD_EDGES) - 1
        fidx[(fidx < 0) | (fidx >= len(names))] = -1
        fidx = fidx.astype(np.int64)
    else:
        fmap = cfg.get('fuelmap', DEFAULT_FUELMAP)
        names = sorted(set(fmap.values()))
        fidx = np.full(wc.shape, -1, np.int64)
        for cls, nm in fmap.items():
            fidx[wc == cls] = names.index(nm)
    # fuel already consumed earlier this season
    be = G[f'burn_end_{season}'][i0:i1, j0:j1]
    if cfg.get('preburn', True):
        fidx[(be > -999) & (be < d0 - 26)] = -1
    # weather: nearest ERA5-Land point to the event
    W, P = wx
    pid = P.index[np.argmin(np.hypot(P.x - ev.x.mean(), P.y - ev.y.mean()))]
    w = W[pid].loc[t0: t0 + pd.Timedelta(hours=hours - 1)]
    nh = len(w)
    if cfg.get('fuel') == 'rfuel':
        return _run_px(ev, cfg, w, nh, t0, season, d0, wc, be, i0, i1, j0, j1, scar_fn, hours)
    R0 = np.zeros((len(names), nh)); phiw = np.zeros_like(R0)
    C = np.zeros(len(names)); Bc = np.zeros(len(names)); Ec = np.zeros(len(names)); rel = np.zeros(len(names)); beta = np.zeros(len(names))
    waf, mult = cfg.get('waf', 0.3), cfg.get('ros_mult', 1.0)
    for k, nm in enumerate(names):
        for h in range(nh):
            p = rothermel(nm, w.m1.iloc[h] + cfg.get('dm', 0.0), w.m10.iloc[h] + cfg.get('dm', 0.0), w.m100.iloc[h],
                          cfg.get('mherb', 0.6), cfg.get('mwood', 0.9), cfg.get('load_scale', 1.0))
            if p is None:
                continue
            R0[k, h] = p['R0'] * mult
            U = w.ws.iloc[h] / 1.15 * waf * 196.85 if cfg.get('wind', True) else 0.0   # 10 m -> 20 ft -> midflame, ft/min
            phiw[k, h] = p['C'] * U ** p['B'] * p['rel'] ** -p['E'] if U > 0 else 0.0
            C[k], Bc[k], Ec[k], rel[k], beta[k] = p['C'], p['B'], p['E'], p['rel'], p['beta']
    tan = TAN[i0:i1, j0:j1] if cfg.get('slope', True) else np.zeros(wc.shape)
    Rh, Dh, Eh = ros_fields(fidx, tan, UPAZ[i0:i1, j0:j1].astype(np.float64), R0, phiw,
                            w.waz.values.astype(np.float64), C, Bc, Ec, rel, beta, 8.0)
    burnable = fidx >= 0
    return _finish(ev, cfg, wc, fidx >= 0, Rh, Dh, Eh, i0, i1, j0, j1, t0, season, d0, fidx, nh, scar_fn, hours)


_RFC = {}
def _rf_cache(name):
    if name not in _RFC:
        _RFC[name] = np.load(f'{DATA}/{name}')
    return _RFC[name]


def _run_px(ev, cfg, w, nh, t0, season, d0, wc, be, i0, i1, j0, j1, scar_fn, hours):
    src = RFUEL if not cfg.get('rfuel_file') else _rf_cache(cfg['rfuel_file'])
    rf = src[f'rf_{season}'][:, i0:i1, j0:j1].astype(np.float64).copy()
    out = ~np.isfinite(rf[0]) & np.isin(wc, [10, 20, 30])
    for b, v in enumerate((0.19, 0.03, 0.036, 0.235)):
        rf[b][out] = v
    rf = np.nan_to_num(rf, nan=0.0)
    sav1 = np.full(wc.shape, 2000.0)
    if cfg.get('cdac_params'):
        # Kale et al. 2024 (C-DAC, Sikkim) Table 2-3: load kg/m2, depth m, mx, SAV 1/ft per class
        rf[:] = 0
        for cls, (ld, dp, mx, sv) in {10: (0.270, 0.061, 0.30, 1224), 20: (0.234, 0.61, 0.15, 1371),
                                      30: (0.160, 0.305, 0.12, 1631), 60: (0.160, 0.305, 0.12, 1631)}.items():
            m = wc == cls; rf[0][m], rf[2][m], rf[3][m], sav1[m] = ld, dp, mx, sv
    if cfg.get('leaffall') and not cfg.get('cdac_params'):
        # per-pixel share of the leaf-off drop done by the end of the previous month (fuel-map thread's layer)
        mo = ev.t.min().month; band = {12: 0, 1: 0, 2: 1, 3: 2, 4: 3}.get(mo, None)   # fire in Jan -> Dec band, Feb -> Jan, ...
        mf = LEAFFALL[band, i0:i1, j0:j1].astype(np.float64) if band is not None else np.ones(wc.shape)
        if cfg.get('leaffall') == 'interp' and band is not None and band < 4:
            # share done by the end of the previous month, moved toward the end of this month by the day of the month
            nxt = LEAFFALL[band + 1, i0:i1, j0:j1].astype(np.float64); frac = min(ev.t.min().day / 30.0, 1.0)
            mf = mf + (nxt - mf) * frac
        mf = np.where(np.isfinite(mf), mf, {1: 0.5, 2: 0.70, 3: 0.88}.get(mo, 1.0))
    else:
        mf = 1.0 if cfg.get('cdac_params') else {1: 0.5, 2: 0.70, 3: 0.88}.get(ev.t.min().month, 1.0)   # fuel v2 month factor
    rf[0] *= mf; rf[1] *= mf; rf[2] *= mf
    w1, w10 = rf[0] * cfg.get('load_mult', 1.0), rf[1] * cfg.get('load_mult', 1.0)
    p = rothermel_px(w1.ravel(), w10.ravel(), rf[2].ravel() * cfg.get('depth_mult', 1.0), rf[3].ravel() + cfg.get('dmx', 0.0), sav1.ravel())
    ok = p['ok'].reshape(wc.shape)
    if cfg.get('preburn', True):
        ok &= ~((be > -999) & (be < d0 - 26))
    R0h = np.zeros((nh,) + wc.shape)
    for h in range(nh):
        R0h[h] = r0_px(p, w.m1.iloc[h] + cfg.get('dm', 0.0), w.m10.iloc[h] + cfg.get('dm', 0.0)).reshape(wc.shape) * ok * cfg.get('ros_mult', 1.0)
    U = (w.ws.values / 1.15 * cfg.get('waf', 0.3) * 196.85) if cfg.get('wind', True) else np.zeros(nh)
    tan = TAN[i0:i1, j0:j1] if cfg.get('slope', True) else np.zeros(wc.shape)
    sh = lambda k: p[k].reshape(wc.shape).astype(np.float64)
    Rh, Dh, Eh = ros_fields_px(R0h, tan, UPAZ[i0:i1, j0:j1].astype(np.float64), U.astype(np.float64),
                               w.waz.values.astype(np.float64), sh('C'), sh('B'), sh('E'), sh('rel'), sh('beta'), 8.0)
    return _finish(ev, cfg, wc, ok, Rh, Dh, Eh, i0, i1, j0, j1, t0, season, d0, ok.astype(np.int64) - 1, nh, scar_fn, hours)


def ignition_mask(dets, S, burnable, win, cfg, t0):
    """Ignition pixels for a set of detections: burnable pixels within ign_r of each detection (nearest
    burnable within 400 m if none); with ign_snap, the nearest observed-scar pixel instead. Returns the
    mask and a grid of ignition times (minutes since t0, inf elsewhere; earliest detection wins)."""
    i0, i1, j0, j1 = win
    yy, xx = np.mgrid[i0:i1, j0:j1]
    px, py = xx * RES + X0 + RES / 2, Y0 - yy * RES - RES / 2
    ig = np.zeros(burnable.shape, bool); tg = np.full(burnable.shape, np.inf)
    for x, y, tt in zip(dets.x, dets.y, dets.t):
        tm = (tt - t0).total_seconds() / 60
        d = np.hypot(px - x, py - y); m = None
        if cfg.get('ign_snap') and S is not None and S.any():
            dd = np.where(S & burnable, d, np.inf)
            if np.isfinite(dd.min()) and dd.min() < 750:
                m = dd <= dd.min() + 1e-6
        if m is None and cfg.get('ign_fp') and 'scan' in dets:
            # the whole VIIRS pixel footprint (scan x track km, axis-aligned) rather than the centre point
            sc, tr_ = float(dets.loc[dets.x == x, 'scan'].iloc[0]), float(dets.loc[dets.x == x, 'track'].iloc[0])
            m = (np.abs(px - x) <= sc * 500) & (np.abs(py - y) <= tr_ * 500) & burnable
            if not m.any():
                m = None
        if m is None:
            m = (d <= cfg.get('ign_r', 100)) & burnable
            if not m.any():
                dd = np.where(burnable, d, np.inf)
                if np.isfinite(dd.min()) and dd.min() < 400:
                    m = dd == dd.min()
        ig |= m; tg[m] = np.minimum(tg[m], tm)
    return ig, tg


def _finish(ev, cfg, wc, burnable, Rh, Dh, Eh, i0, i1, j0, j1, t0, season, d0, fidx, nh, scar_fn, hours):
    S, scar_win = scar_fn(dict(win=(i0, i1, j0, j1), season=season), ev) if scar_fn else (None, 0)
    bm = cfg.get('barriers')
    if bm in (True, 'ms') and BARRIER is not None:
        burnable = burnable & ~BARRIER[i0:i1, j0:j1]
    elif bm in ('all', 'p50', 'draw'):
        # FSI thread's leaky lines (roads, rail, DEM streams) with a stop probability per segment (fires that started > 1 km away):
        # all = every mapped line holds; p50 = segments with stop probability >= 0.5 hold; draw = each segment holds with its probability (cfg seed)
        sid = bar2('seg_id')[i0:i1, j0:j1]; pf = bar2('seg_p_far')
        if bm == 'all':
            held = sid >= 0
        elif bm == 'p50':
            held = (sid >= 0) & (pf[np.maximum(sid, 0)] >= 0.5)
        else:
            rng = np.random.default_rng(int(cfg.get('seed', 0))); hold = rng.random(len(pf)) < pf
            held = (sid >= 0) & hold[np.maximum(sid, 0)]
        burnable = burnable & ~held
    if cfg.get('preburn_poly'):
        # ground burned earlier this season inside the scar thread's event polygons counts as consumed fuel (the label rasters miss most of it)
        pdy = bar2(f'pday_{season}')[i0:i1, j0:j1]
        burnable = burnable & ~((pdy > -999) & (pdy < d0 - 2))
    first = ev if cfg.get('ign_all') else ev[ev.overpass == ev.overpass.min()]   # ign_all: restart from every detection given, each at its time
    ig, tig_grid = ignition_mask(first, S, burnable, (i0, i1, j0, j1), cfg, t0)
    ii, jj = np.nonzero(ig)
    tig = tig_grid[ii, jj]
    T = arrival(Rh, Dh, Eh, burnable, ii.astype(np.int64), jj.astype(np.int64), tig, RES, hours * 60.0, OFFS, int(cfg.get('strict', 0))) if len(ii) else np.full(wc.shape, np.inf)
    # isotropic baseline: distance from ignition pixels over burnable pixels
    dist = ndimage.distance_transform_edt(~ig) * RES if len(ii) else np.full(wc.shape, np.inf)
    extra = dict(Rh=Rh, Dh=Dh, Eh=Eh) if cfg.get('return_fields') else {}
    return dict(T=T, dist=dist, burnable=burnable, ig=ig, win=(i0, i1, j0, j1), t0=t0, season=season, d0=d0, **extra,
                fidx=fidx, nh=nh, S=S if S is not None else np.zeros(wc.shape, bool), scar_win=scar_win)
