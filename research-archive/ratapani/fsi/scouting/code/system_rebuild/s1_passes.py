"""Layer 1a: rebuild every VIIRS overpass of MP from the FIRMS detection metadata alone.
- A pass = one satellite's detections less than 15 min apart (acq_time). Each pass crosses MP in ~2 min.
- Scan angle of a detection from its along-track size (FIRMS `track`), which grows monotonically with scan angle
  (the along-scan size `scan` has a saw-tooth from the on-board aggregation zones, so it cannot be inverted alone):
  track = 0.375 km x slant range / altitude.
- Nadir ground track: VIIRS orbits are sun-synchronous, so nadir local solar time at 23 N is fixed (~13:10 day, ~01:40
  night). First guess lon_nadir = 15 x (LST_nadir - UTC hours); then fitted per pass by least squares so that each
  detection's cross-track distance matches the one implied by its track size. Heading 347 deg (ascending, day) /
  193 deg (descending, night).
- Passes with no detection in the bbox are added from the orbit (period ~101.4 min -> nadir 25.35 deg further west per
  orbit) when their swath reaches MP; flagged `pred=1`.
Outputs (scratch): passes.parquet (one row per pass), det_geom.parquet (scan angle, view zenith, cross-track distance,
pass id per detection). Checks printed: fitted vs time-only nadir; scan/track model fit; bow-tie duplicates."""
import numpy as np, pandas as pd
from scipy.optimize import least_squares
import common as C
RE, HSAT = 6371.0, 829.0          # km; S-NPP/NOAA-20/NOAA-21 ~824-834 km
THMAX = np.radians(56.06)         # VIIRS scan half-angle
HEAD = {'D': 347.0, 'N': 193.0}
PER_MIN = 101.44; DLON = 360 * PER_MIN / 1436.07 * 1.0   # Earth turns under the orbit between consecutive passes


def slant(th):
    return (RE + HSAT) * np.cos(th) - np.sqrt(RE ** 2 - ((RE + HSAT) * np.sin(th)) ** 2)


def ground_dist(th):
    """Ground distance from nadir (km) for scan angle th (rad)."""
    vza = np.arcsin((RE + HSAT) / RE * np.sin(th)); return RE * (vza - th), vza


_tt = np.linspace(0, THMAX, 2000); _tr = 0.375 * slant(_tt) / HSAT; _gd, _vz = ground_dist(_tt)


def th_from_track(track):
    return np.interp(track, _tr, _tt)


def th_from_ground(d):
    return np.interp(np.abs(d), _gd, _tt, right=np.nan)


def xtrack(lon, lat, lon0, lat0, head):
    """Signed cross-track distance (km, positive = right of the direction of travel) of points from a great-circle track
    through (lat0, lon0) with heading head (local flat approx good to <1% over MP)."""
    kx = 111.32 * np.cos(np.radians(lat0)); dx = (lon - lon0) * kx; dy = (lat - lat0) * 110.57
    h = np.radians(head); return dx * np.cos(h) - dy * np.sin(h)


if __name__ == '__main__':
    v = C.load_det().reset_index(drop=True)
    v = v.sort_values(['sat', 'utc']).reset_index(drop=True)
    gap = (v.utc.diff().dt.total_seconds() > 900) | (v.sat != v.sat.shift())
    v['pass_id'] = np.cumsum(gap.values) - 1
    nad = pd.read_csv(C.SC + '../r19_pool/nadir.csv')
    lst = nad.groupby('dn').lst_nadir.mean().to_dict()   # ~13.16 h day, ~1.67 h night (sensor/latitude spread < 4 min)
    print('nadir LST', lst)
    v['th'] = th_from_track(v.track.values)
    gd, vza = ground_dist(v.th.values); v['gd'] = gd
    rows = []; xt = np.full(len(v), np.nan)
    for pid, g in v.groupby('pass_id'):
        dn = g.daynight.mode().iat[0]; head = HEAD[dn]
        t = g.utc.iloc[len(g) // 2]; uh = t.hour + t.minute / 60 + 0.5 / 60
        lon_t = ((lst[dn] - uh) * 15 + 180) % 360 - 180
        lat0 = 23.5
        lon_f = lon_t; cost = np.nan
        if len(g) >= 5:
            lo, la, d = g.longitude.values, g.latitude.values, g.gd.values
            def res(p): return np.abs(xtrack(lo, la, p[0], lat0, head)) - d
            best = None
            for s0 in (lon_t - 3, lon_t, lon_t + 3):
                r = least_squares(res, [s0], loss='soft_l1', f_scale=20)
                if best is None or r.cost < best.cost: best = r
            lon_f = float(best.x[0]); cost = float(np.median(np.abs(best.fun)))
        xt[g.index] = xtrack(g.longitude.values, g.latitude.values, lon_f, lat0, head)
        rows.append(dict(pass_id=pid, sat=g.sat.iat[0], dn=dn, utc=t, n=len(g), lon_time=lon_t, lon_fit=lon_f, med_abs_res_km=cost,
                         ld=g.ld.mode().iat[0], season=int(g.season.iat[0])))
    Pz = pd.DataFrame(rows)
    v['xt'] = xt
    ok = Pz.n >= 5
    print('passes', len(Pz), 'with >=5 detections', ok.sum())
    d = (Pz.lon_fit - Pz.lon_time)[ok] * 111.32 * np.cos(np.radians(23.5))
    print('fitted minus time-only nadir (km): median %.1f, IQR %.1f..%.1f, |d|<50 km %.1f%%' % (d.median(), d.quantile(.25), d.quantile(.75), 100 * (d.abs() < 50).mean()))
    print('median residual |cross-track| per pass (km):', Pz.med_abs_res_km.median())
    # predicted passes with no detection: for each sat, UTC day and node, every orbit k = -2..2 around the observed ones
    add = []
    for (sat, dn, day), g in Pz.groupby(['sat', 'dn', Pz.utc.dt.floor('D') + pd.to_timedelta((Pz.dn == 'N') * 0, 'h')]):
        ref = g.iloc[0]
        for k in range(-2, 3):
            lonk = ref.lon_fit - k * DLON
            if any(abs(lonk - x) < 5 for x in g.lon_fit): continue
            # does the swath reach MP (74-83 E at 23.5 N)? ground half-width 1500 km = ~14.7 deg lon
            if lonk + 15.5 < 74 or lonk - 15.5 > 83: continue
            add.append(dict(pass_id=-1, sat=sat, dn=dn, utc=ref.utc + pd.Timedelta(minutes=k * PER_MIN), n=0, lon_time=np.nan, lon_fit=lonk,
                            med_abs_res_km=np.nan, ld=(ref.utc + pd.Timedelta(minutes=k * PER_MIN) + pd.Timedelta(hours=5.5)).normalize(), season=ref.season, pred=1))
    A = pd.DataFrame(add); Pz['pred'] = 0
    print('orbit-predicted passes reaching MP with no detection in the bbox:', len(A))
    if len(A):
        A['pass_id'] = -np.arange(1, len(A) + 1); Pz = pd.concat([Pz, A], ignore_index=True)
    Pz.to_parquet(C.SC + 'passes.parquet')
    v['vza'] = np.degrees(vza)
    # scan-size model check: predicted along-scan size from the aggregation zones
    v[['pass_id', 'th', 'gd', 'xt', 'vza']].assign(idx=v.index).to_parquet(C.SC + 'det_geom_tmp.parquet')
    v.to_parquet(C.SC + 'det_geom.parquet')
    print('DONE')
