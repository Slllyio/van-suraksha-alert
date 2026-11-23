"""Start point -> first detection as a direction cue, from the fuel thread's ignition back-fits (fuel-map/ratapani/ignition/).
Usage: ignition_cue.py fits.csv label   (events keyed by events_viirs ids; truth = polygon run direction from direction_cues.parquet, S-NPP ids)"""
import numpy as np, pandas as pd, sys, json
import sim
def az(vx, vy): return (np.degrees(np.arctan2(vx, vy)) + 360) % 360
def dang(a, b): return np.abs((a - b + 180) % 360 - 180)
fits = pd.read_csv(sys.argv[1]); label = sys.argv[2]
a = pd.read_parquet(f'{sim.DATA}/viirs_events.parquet'); b = pd.read_parquet(f'{sim.DATA}/events_viirs.parquet')
key = lambda d: d.latitude.round(5).astype(str) + '_' + d.longitude.round(5).astype(str) + '_' + d.t.astype(str)
a['key'] = key(a); b['key'] = key(b)
mp = b[['event', 'key']].merge(a[['key', 'event']], on='key', suffixes=('_v', '_s')).drop_duplicates('event_v')[['event_v', 'event_s']]
dc = pd.read_parquet(f'{sim.DATA}/direction_cues.parquet')[['event', 'run_az_poly', 'run_m_poly', 'n_first']].rename(columns={'event': 'event_s'})
f = fits.merge(mp, left_on='event', right_on='event_v').merge(dc, on='event_s')
# first-pass centroid of the all-sensor event
first = b.sort_values('t').groupby('event').apply(lambda g: g[g.overpass == g.overpass.min()][['x', 'y']].mean()).reset_index().rename(columns={'event': 'event_v', 'x': 'fx', 'y': 'fy'})
f = f.merge(first, on='event_v')
f['ign_d'] = np.hypot(f.fx - f.ign_x, f.fy - f.ign_y); f['ign_az'] = az(f.fx - f.ign_x, f.fy - f.ign_y)
far = f[f.run_m_poly >= 300]
out = dict(label=label, n_fits=len(fits), n_matched=len(f), n_far=len(far), ign_d_median_m=float(far.ign_d.median()), lead_h_median=float(far.lead_h.median()) if 'lead_h' in far else None)
for nm, q in [('all', far), ('start >= 200 m from first pass', far[far.ign_d >= 200]), ('start >= 200 m and spread < 500 m', far[(far.ign_d >= 200) & (far.ign_spread_m < 500)] if 'ign_spread_m' in far else far.iloc[0:0])]:
    if len(q):
        dd = dang(q.ign_az, q.run_az_poly); out[nm] = dict(n=len(q), within45=round(float((dd <= 45).mean()), 3), within90=round(float((dd <= 90).mean()), 3), mean_cos=round(float(np.cos(np.radians(dd)).mean()), 3))
json.dump(out, open(f'{sim.DATA}/ignition_cue_{label}.json', 'w'), indent=1); print(json.dumps(out, indent=1))
