"""Stage 4: does the fixed bias from the static sources also explain the fire results, once fire movement is accounted for?
For each statewide 30 m fire pass (b18, scene ~10:30 IST): VIIRS day pass AFTER the scene (~13:30 IST, gap ~3 h) and VIIRS night
pass BEFORE it (~01:30 IST, gap ~9 h), same fire. Measured: hot-pixel centroid minus VIIRS block centroid (east, north).
Model: after:  H - V = -bias_day   - movement(10:30->13:30)
       before: H - V = -bias_night + movement(01:30->10:30)
With the static-site biases plugged in, the remaining part is fire movement; if it points the same way in both and its size
matches the known front speed, the decomposition holds. Out: results/fire_bias_movement.json"""
import glob, json, numpy as np, pandas as pd
R = '/mnt/project-files/research/big-fires/results'; M = '/mnt/project-files/fire-alert-scars/mp/out'
SC = '/tmp/claude-0/-home-user/408de539-c392-557a-989b-ab3e8eea191b/scratchpad/mp_hotpix'
D = pd.read_csv(f'{R}/mp_hotpix_passes.csv'); V = D[D.visible == True].copy()
PR = pd.read_csv(f'{R}/mp_hotpix_pairs.csv', parse_dates=['t', 't_scene'])
V = V.merge(PR[['pass_id', 'scene', 't_scene', 't']].drop_duplicates('pass_id'), on='pass_id', how='left')
A = pd.read_csv(f'{M}/mp_alert_event.csv', usecols=['latitude', 'longitude', 'acq_date', 'acq_time', 'satellite', 'instrument', 'event_id', 'daynight'])
A = A[(A.instrument == 'VIIRS') & A.event_id.isin(V.event_id)].copy()
A['t'] = pd.to_datetime(A.acq_date + ' ' + A.acq_time.astype(int).astype(str).str.zfill(4), format='%Y-%m-%d %H%M')
SATN = {'N': 'S-NPP', 'N20': 'NOAA-20', '1': 'NOAA-20'}
def lonlat_to_xy(lon, lat):
    from pyproj import Transformer
    return Transformer.from_crs('EPSG:4326', 'EPSG:32643', always_xy=True).transform(lon, lat)
A['x'], A['y'] = lonlat_to_xy(A.longitude.values, A.latitude.values)
rows = []
for _, r in V.iterrows():
    f = glob.glob(f"{SC}/{r.pass_id.replace('|', '_').replace(':', '')}_*.npz")
    if not f: continue
    z = np.load(f[0]); hx, hy = z['x'].astype(float), z['y'].astype(float)
    a = A[A.event_id == r.event_id]
    for kind, sel in [('after (day, ~3 h)', (a.t > r.t_scene) & (a.t - r.t_scene <= pd.Timedelta(hours=4)) & (a.daynight == 'D')),
                      ('before (night, ~9 h)', (a.t < r.t_scene) & (r.t_scene - a.t <= pd.Timedelta(hours=12)) & (a.daynight == 'N'))]:
        for sat, b in a[sel].groupby('satellite'):
            near = np.hypot(hx[:, None] - b.x.values[None], hy[:, None] - b.y.values[None]).min(1) <= 600
            if near.sum() < 3: continue
            # local east/north from UTM 43N: rotate by grid convergence at the fire
            lon0 = b.longitude.mean(); lat0 = b.latitude.mean(); gamma = np.radians((lon0 - 75) * np.sin(np.radians(lat0)))
            dx, dy = hx[near].mean() - b.x.mean(), hy[near].mean() - b.y.mean()
            dE = dx * np.cos(gamma) - dy * np.sin(gamma); dN = dx * np.sin(gamma) + dy * np.cos(gamma)
            gap = abs((b.t.mean() - r.t_scene).total_seconds()) / 3600
            rows.append(dict(event_id=r.event_id, kind=kind, sat=SATN.get(str(sat), str(sat)), gap_h=gap, n_blocks=len(b), dE=dE, dN=dN))
F = pd.DataFrame(rows); F.to_csv(f'{R}/fire_bias_movement_rows.csv', index=False)
S = json.load(open(f'{R}/static_offsets.json'))['by_group']
rng = np.random.default_rng(0)
def ci(g, c):
    m = g.groupby('event_id')[c].mean().values; bs = [rng.choice(m, len(m)).mean() for _ in range(1000)]
    return [round(float(m.mean()), 1), round(float(np.percentile(bs, 2.5)), 1), round(float(np.percentile(bs, 97.5)), 1)]
out = {}
for (k, s), g in F.groupby(['kind', 'sat']):
    key = f'{s} {"day" if k.startswith("after") else "night"}'
    if key not in S or len(g) < 30: continue
    bE, bN = S[key]['east_m'][0], S[key]['north_m'][0]
    E, N = ci(g, 'dE'), ci(g, 'dN')
    sign = -1 if k.startswith('after') else 1      # movement = sign * (measured + bias)
    mE, mN = sign * (E[0] + bE), sign * (N[0] + bN)
    out[f'{k} | {s}'] = dict(passes=int(len(g)), fires=int(g.event_id.nunique()), gap_h_median=round(float(g.gap_h.median()), 1),
                             measured_hot_minus_viirs_east=E, measured_hot_minus_viirs_north=N, static_bias_east_north=[bE, bN],
                             implied_movement_east_north_m=[round(mE), round(mN)], implied_speed_m_per_h=round(float(np.hypot(mE, mN) / g.gap_h.median()), 1),
                             implied_direction_deg_from_north=round(float(np.degrees(np.arctan2(mE, mN)) % 360)))
json.dump(out, open(f'{R}/fire_bias_movement.json', 'w'), indent=1); print(json.dumps(out, indent=1))
