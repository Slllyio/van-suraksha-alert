"""Tracking step 9: per-fire products from the fitted maps.
  results/fires_<config>.csv      one row per fire: cells, passes, flags, active seeds, burned area by each flagged pass,
                                  median local speed (m/h, from |grad T|), day / night speeds, arrival spread (bootstrap sd)
  results/fronts_<config>.csv     per fire and per pass time: burned area so far (ha), equivalent front radius growth,
                                  its bootstrap range when available
  results/subsquare_<config>.csv  per VIIRS detection: where inside its own footprint the fit puts the burning at that
                                  minute (offset along scan / track in half-pixel units, share of the footprint burning)
Local speed = 1 / |grad T| on the 40 m grid (real hours, includes the burning clock if the config uses it);
day = arrival 10:00-18:00 IST, night = 22:00-06:00 IST. Speeds are kept only where T lies inside the observed window.
Usage: python3 t9_tracks.py <config>"""
import sys, os, json, glob
import numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from t2_lib import *
from t6_photos import load_map, mapdir
from t4_run import config

def raster(z, key='T'):
    nr, nc = z['shape']; A = np.full((nr, nc), np.nan); A[z['rr'], z['cc']] = z[key]; return A

def speed(z):
    A = raster(z); A[A > 1e3] = np.nan
    gy, gx = np.gradient(A, z['tr'][0]); g = np.hypot(gx, gy)
    v = 1 / np.where(g > 0, g, np.nan); return np.clip(v[z['rr'], z['cc']], 0.5, 2000)

if __name__ == '__main__':
    name = sys.argv[1] if len(sys.argv) > 1 else 'base'; hyp, eik = config(name); tag = name if len(name) < 40 else 'cfg'
    D = data()['D']; rows, fronts, subs = [], [], []
    for fn in sorted(glob.glob(f'{mapdir(name)}/*.npz')):
        fire = int(os.path.basename(fn)[:-4]); z = load_map(name, fire); t0 = z['t0']; T = z['T'].astype(float)
        d = D[(D.fire == fire) & (D.kind == 'viirs')]; tdet = (d.t - t0).dt.total_seconds().values / 3600
        win = (T >= tdet.min() - 2) & (T <= tdet.max()) & (T < 1e3)
        v = speed(z); ist = ((t0 + pd.to_timedelta(np.where(T < 1e3, T, 0), 'h')).hour.values + 5) % 24   # IST hour (UTC+5:30, rounded)
        day = win & (ist >= 10) & (ist < 18); night = win & ((ist >= 22) | (ist < 6))
        r = dict(fire=fire, season=t0.year, t0=str(t0), cells=len(T), area_ha=len(T) * z['tr'][0] ** 2 / 1e4, n_pass=int(z['n_pass']), n_flagpass=int(z['n_flagpass']),
                 n_det=int(z['n_det']), n_flags=int(z['n_flags']), n_dupes=int(z['n_dupes']), n_offlattice=int(z['n_off']),
                 seeds_active=int((z['seed_w'] < np.max(z['seed_w']) - 1).sum()) if len(z['seed_w']) > 1 else 1,
                 share_burned_in_window=float(win.mean()), speed_med=float(np.nanmedian(v[win])) if win.any() else np.nan,
                 speed_day=float(np.nanmedian(v[day])) if day.sum() > 10 else np.nan, speed_night=float(np.nanmedian(v[night])) if night.sum() > 10 else np.nan,
                 cells_day=int(day.sum()), cells_night=int(night.sum()), sd_laplace_med=float(np.median(z['sd_laplace'][win])) if win.any() else np.nan)
        if 'T_boot_sd' in z: r['sd_boot_med'] = float(np.median(z['T_boot_sd'][win])) if win.any() else np.nan
        rows.append(r)
        for pk, g in d.groupby('pass_key'):
            tk = (g.t.iloc[0] - t0).total_seconds() / 3600; a = (T <= tk).sum() * z['tr'][0] ** 2 / 1e4
            fr_ = dict(fire=fire, pass_key=pk, sensor=g.sensor.iloc[0], t=str(g.t.iloc[0]), th=tk, n_pts=len(g), burned_ha=a, radius_m=np.sqrt(a * 1e4 / np.pi))
            if 'T_boot_sd' in z:
                Tm, Ts = z['T_boot_med'], z['T_boot_sd']
                fr_['burned_ha_lo'] = float(((Tm + 2 * Ts) <= tk).sum() * z['tr'][0] ** 2 / 1e4); fr_['burned_ha_hi'] = float(((Tm - 2 * Ts) <= tk).sum() * z['tr'][0] ** 2 / 1e4)
            fronts.append(fr_)
            tr = z['tr']; cx = tr[2] + (z['cc'] + .5) * z['tr'][0]; cy = tr[5] - (z['rr'] + .5) * z['tr'][0]
            b = expit((tk - T) / hyp['s']) * expit((T + hyp['tau'] - tk) / hyp['s'])
            us, ut = axes(g.heading.iloc[0])
            for q in g.itertuples():
                o = np.c_[cx - q.xc, cy - q.yc]; a_ = o @ us; b_ = o @ ut
                inside = (np.abs(a_) <= q.scan_m / 2) & (np.abs(b_) <= q.track_m / 2)
                w = b * inside; s = w.sum()
                subs.append(dict(fire=fire, pass_key=pk, t=str(q.t), x=q.xc, y=q.yc, scan_m=q.scan_m, track_m=q.track_m, frp=q.frp,
                                 cells_in_footprint=int(inside.sum()), burning_share=float(s / max(inside.sum(), 1)),
                                 off_scan=float((a_ * w).sum() / s / (q.scan_m / 2)) if s > 1e-3 else np.nan,
                                 off_track=float((b_ * w).sum() / s / (q.track_m / 2)) if s > 1e-3 else np.nan))
    R = pd.DataFrame(rows); R.to_csv(f'{OUT}/fires_{tag}.csv', index=False)
    pd.DataFrame(fronts).to_csv(f'{OUT}/fronts_{tag}.csv', index=False); S = pd.DataFrame(subs); S.to_csv(f'{OUT}/subsquare_{tag}.csv', index=False)
    big = R[R.area_ha >= 200]
    res = dict(fires=len(R), speed_med_all=round(R.speed_med.median(), 1), speed_med_big=round(big.speed_med.median(), 1),
               day_over_night_ratio_median=round(float((R.speed_day / R.speed_night).median()), 2), n_fires_day_and_night=int(R[['speed_day', 'speed_night']].dropna().shape[0]),
               speed_day_med=round(R.speed_day.median(), 1), speed_night_med=round(R.speed_night.median(), 1),
               seeds_active_med=float(R.seeds_active.median()), share_fires_multi_start=round(float((R.seeds_active > 1).mean()), 3),
               dupes_removed=int(R.n_dupes.sum()), offlattice=int(R.n_offlattice.sum()), detections=int(R.n_det.sum()),
               subsquare_with_burning=int(S.off_scan.notna().sum()), subsquare_abs_offset_scan_med=round(float(S.off_scan.abs().median()), 3),
               subsquare_abs_offset_track_med=round(float(S.off_track.abs().median()), 3), burning_share_of_footprint_med=round(float(S.burning_share.median()), 3))
    if 'sd_boot_med' in R: res['arrival_sd_boot_median_h'] = round(R.sd_boot_med.median(), 2)
    res['arrival_sd_laplace_median_h'] = round(R.sd_laplace_med.median(), 2)
    json.dump(res, open(f'{OUT}/tracks_{tag}.json', 'w'), indent=1); print(json.dumps(res, indent=1))
