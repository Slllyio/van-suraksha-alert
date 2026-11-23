"""Step 3: per fire, total radiated energy / final scar area = fuel burnt per hectare (FRE method, Wooster et al. 2005).

Each VIIRS pass is its own sample of FRP at its own time (never merged). Between passes the fire's FRP is assumed to follow
the burning clock: pass i stands for the time from the midpoint (in fire-hours) to the previous pass to the midpoint to the
next pass, and its FRP is scaled by the clock inside that window.
   E_i = FRP_i / r(t_i) x fire-hours(window_i)          (MW x h)
   fuel (t/ha) = 10 x 0.368 kg/MJ x 3600 x sum(E_i) / scar area (m2)
Ends: the first pass also covers LEAD fire-hours before it, the last pass TAIL fire-hours after it (default 6 / 6;
sensitivity 3 / 3 and 12 / 12). Gap cap: no pass stands for more than CAP fire-hours on either side (default 12) - a
long gap means passes that saw nothing, so the fire was probably weak then.
Independent repeats: the same sum using only S-NPP passes, only NOAA-20 passes. If the two satellites rank fires the same
way, the number is a property of the fire, not of the sensor.
Out: results/fire_fuel.csv
"""
import numpy as np, pandas as pd
from h0_lib import RES, BF, K_FRE, r_clock, clock_hours

v = pd.read_csv(f'{RES}/clusters.csv', parse_dates=['t']).dropna(subset=['fire'])
v['fire'] = v.fire.astype(int)
P = v.groupby(['fire', 'sensor', 't']).agg(frp=('frp', 'sum'), n=('frp', 'size'), pix_km2=('scan_m', 'mean'),
                                            night=('daynight', lambda s: (s == 'N').mean())).reset_index().sort_values(['fire', 't'])
P['pix_km2'] = v.groupby(['fire', 'sensor', 't']).apply(lambda g: (g.scan_m * g.track_m).mean() / 1e6, include_groups=False).values
P['r'] = r_clock(P.t)
F = pd.read_csv(f'{BF}/ml/fires_ml.csv')
area = pd.read_csv(f'{BF}/fires.csv').set_index('fire').area_ha

def energy(g, lead=6, tail=6, cap=12):
    """MW-hours for one fire's passes g (sorted by time)."""
    t = list(g.t); E = 0.0
    for i in range(len(g)):
        a = lead if i == 0 else min(clock_hours(t[i - 1], t[i]) / 2, cap)
        b = tail if i == len(g) - 1 else min(clock_hours(t[i], t[i + 1]) / 2, cap)
        E += g.frp.iloc[i] / g.r.iloc[i] * (a + b)
    return E

rows = []
for fire, g in P.groupby('fire'):
    A = area[fire] * 1e4
    to_tha = 10 * K_FRE * 3600 / A
    rec = dict(fire=fire, scar_ha=area[fire], n_pass=len(g), n_det=g.n.sum(), frp_sum=g.frp.sum(),
               pix_km2=np.average(g.pix_km2, weights=g.n), night_share=np.average(g.night, weights=g.n),
               fuel_tha=energy(g) * to_tha, fuel_tha_short=energy(g, 3, 3, 6) * to_tha, fuel_tha_long=energy(g, 12, 12, 24) * to_tha,
               hours=(g.t.max() - g.t.min()).total_seconds() / 3600)
    for s, k in [('S-NPP', 'snpp'), ('NOAA-20', 'n20')]:
        h = g[g.sensor == s]
        rec[f'fuel_tha_{k}'] = energy(h) * to_tha if len(h) else np.nan
        rec[f'n_pass_{k}'] = len(h)
    rows.append(rec)
R = pd.DataFrame(rows)
keep = ['fire', 'big', 'season', 'doy_start', 'canopy_mean', 'teak_mean', 'litter_v3_mean', 'grass_v3_mean', 'fuel_total_v3_mean',
        'burn_prior_mean', 'slope_mean', 'elev_relief', 'wc_tree', 'd_building_first_m', 'wx_tmax', 'wx_rh', 'wx_wind', 'wx_soilw', 'wx_rain30',
        'rate_median_m_per_h', 'first_look_night']
R = R.merge(F[[c for c in keep if c in F.columns]], on='fire', how='left')
R.to_csv(f'{RES}/fire_fuel.csv', index=False)
m = R[R.n_pass >= 2]
print('fires', len(R), '| with >=2 VIIRS passes', len(m))
print('fuel burnt (t/ha) median [IQR]:', m.fuel_tha.median().round(2), m.fuel_tha.quantile([.25, .75]).round(2).tolist(),
      '| short ends', m.fuel_tha_short.median().round(2), '| long ends', m.fuel_tha_long.median().round(2))
