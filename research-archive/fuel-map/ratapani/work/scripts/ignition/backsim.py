"""Back-simulate ignition point and time for each fire with the spread thread's engine
(loose teak-litter bed, per-pixel leaf fall, ROS x2 == 3 t/ha, roads as barriers, no wind, hourly ERA5-Land moisture).
Observations per fire:
  VIIRS detections (S-NPP, NOAA-20, NOAA-21) as pixel FOOTPRINTS (FIRMS scan x track km) at their exact pass time:
     the model must have an active front (arrival within the 3 h before the pass) somewhere in the footprint;
  final scar (scar thread's grown polygons): share of scar pixels reached by the last detection + 24 h;
  mid-fire Sentinel-2/Landsat snapshot where one exists: burned / not yet burned at the scene minute.
Free per-fire speed factor k on the engine's rate (k x 3 t/ha equivalent load): 1, 1.7, 2.8, 4.5, 7.
Search: candidate ignition pixels on the scar (<= ~60), times from 36 h before the first detection to the first
detection, coarse 3 h then 30 min around the 3 best; cost = mean footprint miss (h) + 4 * unreached scar share + sum over VIIRS passes with NO detection of min(active front pixels / 10, 1)
+ 8 * snapshot misclassification share. Uncertainty: candidates within best cost + 0.25."""
import sys, os, glob, time, numpy as np, pandas as pd
sys.path.insert(0, '/tmp/claude-0/fuel/bsim/eng')
import sim
from engine import arrival, OFFS
from scipy import ndimage
CFG = {"fuel": "rfuel", "rfuel_file": "rfuel20_loose.npz", "leaffall": "interp", "ros_mult": 2, "ign_snap": False, "wind": False,
       "strict": 1, "barriers": True, "return_fields": True, "pad_m": 1200}
BACK = 48
ev_all = pd.read_parquet('/mnt/project-files/ratapani/spread/data_shared/events_viirs.parquet')
fr = []
for f in glob.glob('/mnt/project-files/fire-alert-scars/alerts/viirs-*.csv'):
    a = pd.read_csv(f)
    if 'latitude' in a: fr.append(a[['latitude', 'longitude', 'acq_date', 'acq_time', 'scan', 'track', 'satellite', 'daynight']])
a = pd.concat(fr); a['t'] = pd.to_datetime(a.acq_date + ' ' + a.acq_time.astype(str).str.zfill(4), format='%Y-%m-%d %H%M')
key = lambda d: d.latitude.round(5).astype(str) + d.longitude.round(5).astype(str) + d.t.astype(str)
a['k'] = key(a); ev_all['k'] = key(ev_all)
ev_all = ev_all.merge(a.drop_duplicates('k')[['k', 'scan', 'track']], on='k', how='left')
ev_all[['scan', 'track']] = ev_all[['scan', 'track']].fillna(0.4)
# VIIRS overpass times over Ratapani (detections anywhere in the region that day give the time; else the typical time)
a['sat'] = a.satellite if 'satellite' in a else None
snap = pd.read_parquet('/tmp/claude-0/fuel/timing/midscar.parquet'); snap = snap[(snap.status == 'ok') & (snap.ok_frac > 0.7)]
snapev = pd.read_parquet('/tmp/claude-0/fuel/inv/viirs_events_spread.parquet')  # snapshot events are S-NPP ids
WX = {}
_seen = a.groupby(['satellite', 'daynight', a.t.dt.date]).t.median()
_start = a.groupby('satellite').t.min()
def passes(t_lo, t_hi):
    out = []
    for day in pd.date_range(t_lo.normalize() - pd.Timedelta(days=1), t_hi.normalize(), freq='D'):
        for sat in ('N', 'N20', 'N21'):
            if day < _start[sat].normalize(): continue
            for dn, hh in (('D', 8.0), ('N', 20.47)):
                t = _seen.get((sat, dn, day.date()), day + pd.Timedelta(hours=hh))
                if t_lo <= t <= t_hi: out.append(t)
    return sorted(out)

import pickle
_PS = pickle.load(open('/tmp/claude-0/fuel/bsim/polyscars.pkl', 'rb'))
def scar_mask(o, ev):
    """Scar = union of the scar thread's grown polygons linked to this fire's alerts (Oct 15: the burn-label rasters
    are 2.4x smaller than the polygons for the same fires, spread README 4k)."""
    i0, i1, j0, j1 = o['win']; S = np.zeros((i1 - i0, j1 - j0), bool)
    for sid in _PS['link'].get(int(ev.event.iloc[0]), []):
        p = _PS['P'][sid]; m = p['m']; a, b = p['i0'] - i0, p['j0'] - j0
        ys, xs = max(a, 0), max(b, 0); ye, xe = min(a + m.shape[0], S.shape[0]), min(b + m.shape[1], S.shape[1])
        if ye > ys and xe > xs: S[ys:ye, xs:xe] |= m[ys - a:ye - a, xs - b:xe - b]
    return S

def scar_mask_raster(o, ev):
    i0, i1, j0, j1 = o['win']; s = o['season']
    be = sim.G[f'burn_end_{s}'][i0:i1, j0:j1]; bs = sim.G[f'burn_start_{s}'][i0:i1, j0:j1]
    d0, d1 = ev.t.min().dayofyear, ev.t.max().dayofyear
    m = (be > -999) & (be >= d0 - 2) & (bs <= d1 + 2)
    lab, n = ndimage.label(m, structure=np.ones((3, 3)))
    r, c = sim.rc(ev.x.values, ev.y.values); r -= i0; c -= j0
    near = np.zeros(m.shape, bool); near[np.clip(r, 0, m.shape[0] - 1), np.clip(c, 0, m.shape[1] - 1)] = True
    near = ndimage.binary_dilation(near, iterations=20)
    k = np.unique(lab[near & m]); k = k[k > 0]
    return np.isin(lab, k)

def snapshot_for(ev, win):
    """Match a mid-fire snapshot to this fire: S-NPP event whose detections overlap in time and space."""
    if not len(snap): return None
    t0, t1 = ev.t.min() - pd.Timedelta(hours=2), ev.t.max() + pd.Timedelta(hours=2)
    cand = snap[(snap['T'] >= t0 - pd.Timedelta(days=2)) & (snap['T'] <= t1 + pd.Timedelta(days=2))]
    for _, r in cand.iterrows():
        se = snapev[snapev.event == r.event]
        if len(se) and np.min(np.hypot(se.x.values[:, None] - ev.x.values[None], se.y.values[:, None] - ev.y.values[None])) < 600:
            z = np.load(f"/tmp/claude-0/fuel/timing/chips/{r.event}_{r.scene[:40]}.npz")
            i0, i1, j0, j1 = win; a0, b0 = int(z['i0']) + 100, int(z['j0']) + 100  # label grid -> engine grid (origin 2 km further NW)
            B = np.zeros((i1 - i0, j1 - j0), bool); OK = np.zeros_like(B)
            h, w = z['S'].shape; ys, xs = a0 - i0, b0 - j0
            if ys < 0 or xs < 0 or ys + h > B.shape[0] or xs + w > B.shape[1]: continue
            B[ys:ys + h, xs:xs + w] = z['bym']; OK[ys:ys + h, xs:xs + w] = z['ok']
            return dict(T=r['T'], B=B, OK=OK, scene=r.scene)
    return None

def fit(e):
    ev = ev_all[ev_all.event == e].sort_values('t')
    season = int(ev.season.iloc[0])
    if season not in WX: WX[season] = sim.load_weather(season)
    tf = ev.t.min()
    dummy = ev.iloc[[0]].copy(); dummy['t'] = tf - pd.Timedelta(hours=BACK); dummy['overpass'] = dummy['t'].iloc[0] if not pd.api.types.is_numeric_dtype(ev.overpass) else ev.overpass.min() - 1
    evx = pd.concat([dummy, ev])
    dur_h = (ev.t.max() - tf).total_seconds() / 3600
    hours = int(min(BACK + dur_h + 14, 144))
    o = sim.run_event(evx, WX[season], CFG, hours=hours, scar_fn=None)
    t0 = o['t0']; win = o['win']; burn = o['burnable']; Rh, Dh, Eh = o['Rh'], o['Dh'], o['Eh']
    S = scar_mask(o, ev) & burn
    if S.sum() < 25: return dict(event=e, status='small_or_no_scar')
    i0, i1, j0, j1 = win
    yy, xx = np.mgrid[i0:i1, j0:j1]; px, py = xx * sim.RES + sim.X0 + 10, sim.Y0 - yy * sim.RES - 10
    tm = lambda t: (t - t0).total_seconds() / 60
    # footprints per detection
    fps, tks = [], []
    for _, d in ev.iterrows():
        m = (np.abs(px - d.x) <= d.scan * 500) & (np.abs(py - d.y) <= d.track * 500) & burn
        if m.any(): fps.append(np.flatnonzero(m)); tks.append(tm(d.t))
    tks = np.array(tks); tend = tm(ev.t.max()) + 1440
    # restrict the simulation to the scar and footprints plus 600 m (the fire is there; speeds things up a lot)
    zone = S.copy()
    for f in fps: zone.ravel()[f] = True
    burn = burn & ndimage.binary_dilation(zone, iterations=30)
    sn = snapshot_for(ev, win)
    # candidate ignition pixels: scar pixels on a grid, plus first-pass footprint pixels inside the scar
    si, sj = np.nonzero(S); step = max(1, int(np.sqrt(len(si) / 50)))
    sel = (si % step == 0) & (sj % step == 0); ci, cj = si[sel], sj[sel]
    if len(ci) > 12: k = np.linspace(0, len(ci) - 1, 12).astype(int); ci, cj = ci[k], cj[k]
    # plus burnable pixels inside the first-pass footprints (the fire may have started outside the mapped scar patch)
    f1 = np.unique(np.concatenate([f for f, tk in zip(fps, tks) if tk <= tks.min() + 60])) if len(fps) else np.array([], int)
    if len(f1):
        f1 = f1[np.linspace(0, len(f1) - 1, min(6, len(f1))).astype(int)]
        fi, fj = np.unravel_index(f1, S.shape); ci, cj = np.r_[ci, fi], np.r_[cj, fj]
    tfm = tm(tf)
    dt_all = ev.t.values
    nps = [tm(p) for p in passes(tf - pd.Timedelta(hours=BACK), ev.t.max() + pd.Timedelta(hours=24))
           if np.min(np.abs((dt_all - np.datetime64(p)).astype('timedelta64[m]').astype(float))) > 30]
    KS = (1.0, 1.7, 2.8, 4.5, 7.0, 11.0)
    RK = {k: Rh * k for k in KS}
    def cost(i, j, tig, k=1.0):
        T = arrival(RK[k], Dh, Eh, burn, np.array([i], np.int64), np.array([j], np.int64), np.array([tig], np.float64), sim.RES, float(tend + 60), OFFS, 1)
        Tf = T.ravel()
        miss = []
        for f, tk in zip(fps, tks):
            at = Tf[f]; act = (at <= tk) & (at >= tk - 180)
            if act.any(): miss.append(0.0)
            else:
                d = np.where(at > tk, at - tk, tk - 180 - at); miss.append(min(np.min(d) / 60, 24))
        un = 1 - (T[S] <= tend).mean()
        nd = 0.0
        for p in nps:
            n_act = int(((Tf <= p) & (Tf >= p - 60)).sum()); nd += min(n_act / 10, 1.0)
        sc = 0.0
        if sn is not None:
            ok = sn['OK'] & S
            if ok.sum() > 10: sc = ((T[ok] <= tm(sn['T'])) != sn['B'][ok]).mean()
        return float(np.mean(miss)) + 4 * un + 8 * sc + nd, float(np.mean(miss)), un, sc, T
    res = []
    for kk in KS:
        for i, j in zip(ci, cj):
            for tig in np.arange(tfm - BACK * 60, tfm + 1, 180):
                c, m, u, s_, _ = cost(i, j, tig, kk); res.append((c, m, u, s_, i, j, tig, kk))
    res.sort(key=lambda r: r[0])
    fine = []
    for c0 in res[:3]:
        for tig in np.arange(c0[6] - 150, c0[6] + 151, 30):
            if tig > tfm or tig < tfm - BACK * 60: continue
            c, m, u, s_, _ = cost(c0[4], c0[5], tig, c0[7]); fine.append((c, m, u, s_, c0[4], c0[5], tig, c0[7]))
    allr = sorted(res + fine, key=lambda r: r[0]); best = allr[0]
    good = [r for r in allr if r[0] <= best[0] + 0.25]
    gt = np.array([r[6] for r in good]); gx = np.array([r[5] for r in good]); gy = np.array([r[4] for r in good])
    bi, bj = best[4], best[5]
    _, _, _, _, Tb = cost(bi, bj, best[6], best[7])
    kgood = sorted(set(r[7] for r in good))
    np.savez_compressed(f'out/arr_{e}.npz', T=np.where(np.isfinite(Tb), Tb, -1).astype(np.float32), S=S, win=np.array(win), t0=str(t0))
    return dict(event=e, season=season, status='ok', n_det=len(ev), n_fp=len(fps), n_pass=ev.overpass.nunique(), scar_ha=S.sum() * 0.04,
                t_first=tf, ign_t=t0 + pd.Timedelta(minutes=best[6]), lead_h=(tfm - best[6]) / 60,
                lead_lo_h=(tfm - gt.max()) / 60, at_bound=bool(best[6] <= tfm - BACK * 60 + 1), lead_hi_h=(tfm - gt.min()) / 60,
                ign_x=sim.X0 + (j0 + bj) * sim.RES + 10, ign_y=sim.Y0 - (i0 + bi) * sim.RES - 10,
                ign_spread_m=float(np.hypot(gx - bj, gy - bi).max() * sim.RES) if len(good) else 0.0,
                speed_k=best[7], k_lo=min(kgood), k_hi=max(kgood), cost=best[0], fp_miss_h=best[1], unreached=best[2], snap_err=best[3] if sn is not None else np.nan,
                has_snap=sn is not None, first_daynight=ev.daynight.iloc[0], n_cand=len(ci), n_runs=len(allr))

if __name__ == '__main__':
    os.makedirs('out', exist_ok=True)
    n = ev_all[ev_all.t.dt.month <= 6].groupby('event').overpass.nunique()
    ids = n[n >= int(sys.argv[2] if len(sys.argv) > 2 else 2)].index.tolist()
    part, nparts = map(int, sys.argv[1].split('/'))
    ids = ids[part::nparts]
    if len(sys.argv) > 3: ids = ids[:int(sys.argv[3])]
    rows = []
    for k, e in enumerate(ids):
        t = time.time()
        try: r = fit(e)
        except Exception as ex: r = dict(event=e, status=f'err {ex}'[:150])
        r['sec'] = time.time() - t; rows.append(r)
        if k % 10 == 0: pd.DataFrame(rows).to_parquet(f'out/fit_{part}.parquet'); print(k, len(ids), r.get('status'), round(r['sec'], 1), flush=True)
    pd.DataFrame(rows).to_parquet(f'out/fit_{part}.parquet')
