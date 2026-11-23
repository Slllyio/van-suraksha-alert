"""Build tables for the jump / nearby-new-start analysis.
ign.parquet : one row per new fire (fire_group), earliest first-day event: x,y (UTM43N m), t (IST), beat, month, year
det.parquet : FIRMS detections (v2 lookup) with fire_group, x,y, t (IST)
"""
import pandas as pd, numpy as np
from pyproj import Transformer
OUT = '/tmp/claude-0/-home-user/be9b8f54-cc26-52cb-bdbb-9c8008a24baf/scratchpad/r13_jump_code/'
TR = Transformer.from_crs(4326, 32643, always_xy=True)
I = pd.read_csv('/mnt/project-files/ratapani/fsi/scouting/data/ignition_points.csv')
L = pd.read_csv('/mnt/project-files/fire-alert-scars/reference/v2_2026-10-16/firms_alert_scar_lookup.csv')
I = I[I.status == 'ok'].copy()
for c in ['t_ign_med_ist', 't_first_ist', 't_ign_05_ist', 't_ign_95_ist']: I[c] = pd.to_datetime(I[c])
# beat of event = beat of its first alert
L['t'] = pd.to_datetime(L.acq_date) + pd.to_timedelta((L.acq_time // 100) * 60 + L.acq_time % 100, unit='min') + pd.Timedelta(minutes=330)
eb = L.sort_values('t').groupby('event_id')[['beat_uid', 'division', 'range', 'beat']].first()
I = I.join(eb, on='event_id')
F = I[I.event_role == 'first_day_of_fire'].sort_values('t_ign_med_ist').groupby('fire_group').first().reset_index()
F['x'], F['y'] = TR.transform(F.ign_lon.values, F.ign_lat.values)
F['t'] = F.t_ign_med_ist; F['yr'] = F.t.dt.year; F['mon'] = F.t.dt.month; F['hr'] = F.t.dt.hour + F.t.dt.minute / 60
F['hr_first'] = F.t_first_ist.dt.hour + F.t_first_ist.dt.minute / 60
F = F[['fire_group', 'event_id', 'x', 'y', 't', 't_first_ist', 't_ign_05_ist', 't_ign_95_ist', 'yr', 'mon', 'hr', 'hr_first', 'first_sensor',
       'scar_ha', 'n_rival_fires', 'ignitions_flag', 'ign_r90_cal_m', 'beat_uid', 'division', 'range', 'beat']]
F.to_parquet(OUT + 'ign.parquet'); print('new fires', len(F), F.yr.value_counts().sort_index().to_dict())
g = I.set_index('event_id').fire_group
L['fire_group'] = L.event_id.map(g)
L['x'], L['y'] = TR.transform(L.longitude.values, L.latitude.values)
D = L[['alert_id', 'event_id', 'fire_group', 'x', 'y', 't', 'sensor', 'frp', 'beat_uid']].dropna(subset=['fire_group'])
D.to_parquet(OUT + 'det.parquet'); print('detections', len(D), 'unlinked', L.fire_group.isna().sum())
