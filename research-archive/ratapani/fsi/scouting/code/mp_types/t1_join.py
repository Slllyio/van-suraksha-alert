"""Join all-MP VIIRS points (Jan-Jun) to forest beats; write one parquet with division, beat, local date, DOY.
Inputs: /mnt/project-files/fire-alert-scars/alerts_mp/viirs-*.csv, /mnt/project-files/ratapani/beats/mp_beats.geojson
Output: out/viirs_mp_beats.parquet (only points inside a beat polygon)."""
import glob, os, pandas as pd, geopandas as gpd, numpy as np
D = '/mnt/project-files/fire-alert-scars/alerts_mp/'
os.makedirs('out', exist_ok=True)
beats = gpd.read_file('/mnt/project-files/ratapani/beats/mp_beats.geojson')[['beat_uid', 'Division', 'Range', 'Beat', 'Beat_Ar', 'geometry']]
beats = beats.to_crs(4326)
beats['geometry'] = beats.geometry.buffer(0)
parts = []
for f in sorted(glob.glob(D + 'viirs-*.csv')):
    sat = os.path.basename(f).split('_')[0].replace('viirs-', '')
    df = pd.read_csv(f, usecols=['latitude', 'longitude', 'acq_date', 'acq_time', 'confidence', 'frp', 'daynight', 'type'])
    df['sat'] = sat
    g = gpd.GeoDataFrame(df, geometry=gpd.points_from_xy(df.longitude, df.latitude), crs=4326)
    j = gpd.sjoin(g, beats[['beat_uid', 'Division', 'geometry']], predicate='within', how='inner')
    j = j[~j.index.duplicated()]
    parts.append(pd.DataFrame(j.drop(columns=['geometry', 'index_right'])))
    print(f, len(df), 'in beats', len(j), flush=True)
a = pd.concat(parts, ignore_index=True)
# local time IST = UTC + 5:30
t = pd.to_datetime(a.acq_date) + pd.to_timedelta(a.acq_time // 100, unit='h') + pd.to_timedelta(a.acq_time % 100, unit='m') + pd.Timedelta(minutes=330)
a['t_ist'] = t
a['date_ist'] = t.dt.normalize()
a['season'] = t.dt.year
a['doy'] = t.dt.dayofyear
a.to_parquet('out/viirs_mp_beats.parquet')
area = beats.groupby('Division').Beat_Ar.agg(['sum', 'count']).rename(columns={'sum': 'forest_km2', 'count': 'n_beats'})
area.to_csv('out/division_area.csv')
print(len(a)); print(area.sum())
