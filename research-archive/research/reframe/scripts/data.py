"""Shared inputs for the reframe experiments (research thread 'Rethink the 2-day question').
Builds, into OUT (container scratch, regenerated on demand):
  cells.parquet   cell_id, x, y (UTM 43N centre), forest_frac, beat
  viirs.parquet   one row per VIIRS point (SNPP + NOAA-20, 2017-2026) inside the grid: date, cell_id, frp, daynight
  burns.parquet   every burned scar window 2017-2026: season, cell_id, ws, we, first, vday (first VIIRS date within 750 m in [ws-1, we+1], NaT if none)
  weather.parquet daily POWER drivers (research thread daily_drivers.csv, extended with the raw POWER file)
Inputs are read-only files owned by other threads."""
import json, os, glob, numpy as np, pandas as pd
from pyproj import Transformer
PF = '/mnt/project-files/'
OUT = os.environ.get('REFRAME_CACHE', '/tmp/claude-0/reframe_cache/'); os.makedirs(OUT, exist_ok=True)


def cells():
    p = OUT + 'cells.parquet'
    if os.path.exists(p): return pd.read_parquet(p)
    g = json.load(open(PF + 'ratapani/grid_500m.geojson'))
    c = pd.DataFrame([f['properties'] for f in g['features']])
    c['x'] = c.x0 + 250; c['y'] = c.y0 + 250
    b = pd.read_csv(PF + 'ratapani/beats/cell_beat.csv')
    c = c.merge(b, on='cell_id', how='left')[['cell_id', 'x', 'y', 'forest_frac', 'beat_uid']]
    c.to_parquet(p); return c


def viirs():
    p = OUT + 'viirs.parquet'
    if os.path.exists(p): return pd.read_parquet(p)
    c = cells(); key = {(int(x // 500), int(y // 500)): i for i, x, y in zip(c.cell_id, c.x, c.y)}
    fs = sorted(glob.glob(PF + 'fire-alert-scars/alerts/viirs-*_20*.csv'))
    a = pd.concat([pd.read_csv(f) for f in fs], ignore_index=True)
    tr = Transformer.from_crs(4326, 32643, always_xy=True); X, Y = tr.transform(a.longitude.values, a.latitude.values)
    a['cell_id'] = [key.get((int(x // 500), int(y // 500)), -1) for x, y in zip(X, Y)]
    a['x'], a['y'] = X, Y
    a = a[a.cell_id >= 0].copy(); a['date'] = pd.to_datetime(a.acq_date)
    a['dt'] = a.date + pd.to_timedelta(a.acq_time.astype(int) // 100, unit='h') + pd.to_timedelta(a.acq_time.astype(int) % 100, unit='m')
    a = a[['date', 'dt', 'cell_id', 'x', 'y', 'frp', 'daynight', 'satellite', 'confidence']].drop_duplicates()
    a.to_parquet(p); return a


def burns():
    p = OUT + 'burns.parquet'
    if os.path.exists(p): return pd.read_parquet(p)
    bw = pd.read_csv(PF + 'research/ratapani-burn-labels/burn_windows.csv', parse_dates=['window_start', 'window_end'])
    bw = bw[bw.burned == 1].sort_values(['season', 'cell_id', 'window_end']).rename(columns={'window_start': 'ws', 'window_end': 'we'})
    bw['first'] = ~bw.duplicated(['season', 'cell_id'])
    c = cells().set_index('cell_id'); v = viirs()
    # VIIRS points within 750 m of each cell centre, by day
    from scipy.spatial import cKDTree
    tree = cKDTree(v[['x', 'y']].values); cxy = c.loc[bw.cell_id, ['x', 'y']].values
    nb = tree.query_ball_point(cxy, r=750 + 250)   # centre-to-point; 750 m from cell edge ~ 1000 m from centre
    vd = v.date.values; vday = []
    for k, (ws, we) in enumerate(zip(bw.ws.values, bw.we.values)):
        d = vd[nb[k]]; d = d[(d >= ws - np.timedelta64(1, 'D')) & (d <= we + np.timedelta64(1, 'D'))]
        vday.append(d.min() if len(d) else np.datetime64('NaT'))
    bw['vday'] = pd.to_datetime(vday)
    bw[['season', 'cell_id', 'ws', 'we', 'burned_ha', 'first', 'vday']].to_parquet(p); return bw


def weather():
    p = OUT + 'weather.parquet'
    if os.path.exists(p): return pd.read_parquet(p)
    w = pd.read_csv(PF + 'research/ratapani-ignition/weather_power_2017_2026.csv', parse_dates=['date']).set_index('date').sort_index()
    w['rain'] = w.PRECTOTCORR
    wet = (w.rain > 1).astype(int); grp = wet.cumsum(); w['days_since_rain'] = w.groupby(grp).cumcount()
    w['rh_min7'] = w.RH2M.rolling(7).min(); w['rh7'] = w.RH2M.rolling(7).mean(); w['tmax7'] = w.T2M_MAX.rolling(7).mean()
    w['rain30'] = w.rain.rolling(30).sum(); w['vpd'] = 0.6108 * np.exp(17.27 * w.T2M / (w.T2M + 237.3)) * (1 - w.RH2M / 100)
    w['vpd7'] = w.vpd.rolling(7).mean()
    w = w[['T2M', 'T2M_MAX', 'RH2M', 'WS10M', 'rain', 'days_since_rain', 'rh_min7', 'rh7', 'tmax7', 'rain30', 'vpd', 'vpd7']]
    w.reset_index().to_parquet(p); return w.reset_index()


def lean_preds():
    a = pd.read_parquet(PF + 'ratapani/scoring/pipeline_lean_pred_loso_2017_24.parquet')
    b = pd.read_parquet(PF + 'ratapani/scoring/pipeline_lean_pred_2025_26.parquet')
    d = pd.concat([a, b], ignore_index=True); d['date'] = pd.to_datetime(d.date); return d


def season_days(Y):
    return pd.date_range(f'{Y}-02-01', f'{Y}-06-20')


SEASONS = list(range(2017, 2027))

if __name__ == '__main__':
    c = cells(); print('cells', len(c), c.beat_uid.nunique())
    v = viirs(); print('viirs', len(v), v.date.min(), v.date.max()); print(v.groupby(v.date.dt.year).size())
    b = burns(); print('burns', len(b), 'first', int(b['first'].sum()), 'dated share (first)', round(b[b['first']].vday.notna().mean(), 3))
    print(b[b['first']].groupby('season').vday.apply(lambda s: round(s.notna().mean(), 2)))
    w = weather(); print('weather', w.date.min(), w.date.max())
