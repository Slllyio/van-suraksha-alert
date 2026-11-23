"""Step 12a. 2026 burn-scar event set, same method as fire-alert-scars/mp 2017-25 history (clip_mp.py + mp_events.py):
FIRMS 2026 MODIS, S-NPP, NOAA-20 (no NOAA-21, to match the history), 15 Feb-15 Jun, inside MP beats, events = same day
within 1 km, forest >= 10% tree+shrub within 375 m. Out (scratch): scars2026/set_2026.csv, alert_event_2026.csv.
Then: python fire-alert-scars/mp/scripts/mp_run.py set_2026.csv scars_2026.csv 16"""
import sys
sys.path.insert(0, "/mnt/project-files/fire-alert-scars/scripts"); sys.path.insert(0, "/mnt/project-files/field-system/app")
import pandas as pd, geopandas as gpd, numpy as np
from run_all import build_events
from landcover import WorldCover
import lf_common as L
O = L.SC + 'scars2026/'; A = '/mnt/project-files/fire-alert-scars/alerts_mp/'
D = pd.concat([pd.read_csv(A + f'{s}_2026.csv').assign(sensor=s) for s in ('modis', 'viirs-snpp', 'viirs-jpss1')], ignore_index=True)
md = D.acq_date.str[5:]; D = D[(md >= '02-15') & (md <= '06-15')]
B = gpd.read_file('/mnt/project-files/ratapani/beats/mp_beats.geojson').to_crs(4326)
P = gpd.GeoDataFrame(D, geometry=gpd.points_from_xy(D.longitude, D.latitude), crs=4326)
J = gpd.sjoin(P, B[['geometry']], predicate='within', how='inner'); J = J[~J.index.duplicated()].drop(columns=['geometry', 'index_right'])
J['acq_time'] = J.acq_time.astype(str).str.zfill(4)
print('season alerts in beats', len(J), J.groupby('sensor').size().to_dict(), flush=True)
R, E = build_events(J)
P = gpd.GeoDataFrame(E, geometry=gpd.points_from_xy(E.longitude, E.latitude), crs=4326)
P = gpd.sjoin(P, B[['beat_uid', 'Division', 'Range', 'Beat', 'geometry']], predicate='within', how='left')
P = P[~P.index.duplicated()].drop(columns=['index_right', 'geometry'])
wc = WorldCover(max_blocks=3000); fs = []
for k, (la, lo) in enumerate(zip(P.latitude, P.longitude)):
    try: fs.append(wc.share(la, lo, 0.375)[1])
    except Exception: fs.append(np.nan)
    if k % 5000 == 0: print(k, len(P), flush=True)
P['forest_share'] = fs; P['forest'] = P.forest_share >= 0.10
R.to_csv(O + 'alert_event_2026.csv', index=False)
P[P.forest].sort_values('acq_date', ascending=False).to_csv(O + 'set_2026.csv', index=False)
print('events', len(P), 'forest', int(P.forest.sum()), flush=True)
