"""Small tables from the VIIRS 375 m fire-mask crops (pull_fire_masks_fast.py), for the spread and continuity threads.

Inputs : <crops>/index.csv + <crops>/crops/*.npz (scratch), results/fire_mask_pull_plan.csv and _unseen.csv (pass -> fires),
         research/big-fires/results/fire_alerts.csv (alerts of every fire, same fire ids).
Outputs (results/, next to this script):
  mask_pixels_near_fires.parquet  one row per fire x pass x mask pixel within 2 km of any alert of that fire:
      fire, pass_key, sensor, t_pass (UTC, granule start), lat, lon, cls (0-9, below), vza (sensor zenith deg),
      d_alert_m (distance to the fire's nearest alert, any time), d_prior_m (to its nearest alert BEFORE this pass; NaN if none),
      unseen (True = one of the spread thread's 818 unseen fires)
  mask_fire_pass_summary.csv      one row per fire x pass: pixel counts by class within 750 m of the fire's prior alerts
      ("front zone"), n_fire (7-9), n_clear (3,5), n_cloud (4), n_noinfo (2,6), n_missing (0,1), seen_later (any alert of
      the fire after this pass), hours_since_last_alert, unseen
Mask classes (VIIRS 375 m user guide): 0 not processed, 1 bow-tie deletion, 2 glint, 3 water, 4 cloud, 5 clear land no fire,
      6 unclassified land, 7/8/9 low/nominal/high-confidence fire. "Looked, saw no fire" = 3 or 5.
"""
import os, sys, glob, numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__)); RES = f'{HERE}/results'
CROPS = sys.argv[1] if len(sys.argv) > 1 else '/tmp/claude-0/fire_masks'
PF = '/mnt/project-files'
plan = pd.concat([pd.read_csv(f'{RES}/fire_mask_pull_plan.csv'), pd.read_csv(f'{RES}/fire_mask_pull_plan_unseen.csv')], ignore_index=True)
unseen_ids = set(pd.read_csv(f'{PF}/ratapani/spread/unseen_validation/unseen_fires_not_in_mask_plan.csv').fire)
try:
    import json; s = json.load(open(f'{PF}/ratapani/spread/unseen_validation/summary.json'))
except Exception: s = {}
A = pd.read_csv(f'{PF}/research/big-fires/results/fire_alerts.csv', usecols=['fire', 't', 'latitude', 'longitude'], parse_dates=['t'])
A = A[A.fire.isin(plan.fire)]
AL = {f: g for f, g in A.groupby('fire')}
IDX = pd.read_csv(f'{CROPS}/index.csv'); IDX = IDX[IDX.status == 'ok'].drop_duplicates('pass_key', keep='last')
fires_of = plan.groupby('pass_key').fire.apply(lambda x: sorted(set(x))).to_dict()


def dist_m(lat, lon, alat, alon):
    k = np.cos(np.radians(lat.mean())) if len(lat) else 1.0
    return np.sqrt(((lat[:, None] - alat[None]) * 111195) ** 2 + ((lon[:, None] - alon[None]) * 111195 * k) ** 2).min(1)


pix, summ = [], []
for r in IDX.itertuples():
    fn = f'{CROPS}/crops/{r.file}'
    if not os.path.exists(fn): continue
    z = np.load(fn, allow_pickle=True)
    for i in range(int(z['n_parts'])):
        if f'lat_{i}' not in z: continue
        lat, lon, cls = z[f'lat_{i}'].ravel(), z[f'lon_{i}'].ravel(), z[f'fire_mask_{i}'].ravel()
        vza = z[f'sensor_zenith_{i}'].ravel() if f'sensor_zenith_{i}' in z else np.full(lat.shape, np.nan, np.float32)
        tp = pd.Timestamp(str(z[f'granule_start_{i}']))
        ok = np.isfinite(lat) & np.isfinite(lon)
        lat, lon, cls, vza = lat[ok], lon[ok], cls[ok], vza[ok]
        for f in fires_of.get(r.pass_key, []):
            a = AL.get(f)
            if a is None or not len(lat): continue
            d_all = dist_m(lat, lon, a.latitude.values, a.longitude.values); near = d_all <= 2000
            if not near.any(): continue
            pr = a[a.t < tp - pd.Timedelta(minutes=10)]
            d_pr = dist_m(lat[near], lon[near], pr.latitude.values, pr.longitude.values) if len(pr) else np.full(near.sum(), np.nan)
            pix.append(pd.DataFrame(dict(fire=f, pass_key=r.pass_key, sensor=r.sensor, t_pass=tp, lat=lat[near], lon=lon[near], cls=cls[near],
                                         vza=vza[near].astype(np.float32), d_alert_m=d_all[near].astype(np.float32), d_prior_m=d_pr.astype(np.float32),
                                         unseen=f in unseen_ids)))
            fz = cls[near][np.isfinite(d_pr) & (d_pr <= 750)]
            summ.append(dict(fire=f, pass_key=r.pass_key, sensor=r.sensor, t_pass=tp, unseen=f in unseen_ids, n_front=len(fz),
                             n_fire=int((fz >= 7).sum()), n_clear=int(np.isin(fz, [3, 5]).sum()), n_cloud=int((fz == 4).sum()),
                             n_noinfo=int(np.isin(fz, [2, 6]).sum()), n_missing=int(np.isin(fz, [0, 1]).sum()),
                             vza_med=float(np.nanmedian(vza[near])) if near.any() else np.nan,
                             seen_later=bool((a.t > tp + pd.Timedelta(minutes=10)).any()),
                             hours_since_last_alert=float((tp - pr.t.max()).total_seconds() / 3600) if len(pr) else np.nan))
P = pd.concat(pix, ignore_index=True) if pix else pd.DataFrame()
S = pd.DataFrame(summ).sort_values(['fire', 't_pass']).drop_duplicates(['fire', 't_pass', 'sensor'], keep='first')
P.to_parquet(f'{RES}/mask_pixels_near_fires.parquet', index=False)
S.to_csv(f'{RES}/mask_fire_pass_summary.csv', index=False)
print(len(P), 'pixel rows;', len(S), 'fire-pass rows;', S.fire.nunique(), 'fires')
