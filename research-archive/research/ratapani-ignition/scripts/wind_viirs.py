"""Wind test with VIIRS-dated fronts (day resolution) instead of 5-day scar windows.
Issue day t: front = VIIRS detections (confidence n/h) on day t within 3 km of a cell. Outcome = the cell's VIIRS-dated
first-burn day is t+1 (true_lead_labels, dated). Candidates = cells valid_strict on t. Wind = afternoon (06-12 UTC) mean
direction on t ('m1', the spread afternoon) and on t+1 ('d0'), from POWER (one series) and ERA5-Land nearest point. downwind = cos(bearing front->cell - (wd+180)).
"""
import json, numpy as np, pandas as pd
from scipy.spatial import cKDTree
P = '/mnt/project-files/'; IGN = P + 'research/ratapani-ignition/'
gj = json.load(open(P + 'ratapani/grid_500m.geojson'))
xy = pd.DataFrame([(f['properties']['cell_id'], f['properties']['x0'] + 250, f['properties']['y0'] + 250) for f in gj['features']], columns=['cell_id', 'x', 'y']).set_index('cell_id')
v = pd.read_parquet(P + 'ratapani/viirs_snpp_2013_2024.parquet'); v = v[v.confidence.isin(['n', 'h'])].copy(); v['date'] = pd.to_datetime(v.date)
# lon/lat -> UTM 43N (simple pyproj-free approx via affine fit on the grid corners)
import math
def to_utm(lon, lat):
    # fit from grid: use first/last feature lon/lat vs x/y (linear fit good enough over 40 km)
    return A @ np.c_[lon, lat, np.ones(len(lon))].T
pts = np.array([(np.mean([c[0] for c in f['geometry']['coordinates'][0][:4]]), np.mean([c[1] for c in f['geometry']['coordinates'][0][:4]])) for f in gj['features']])
X = np.c_[pts, np.ones(len(pts))]; A = np.linalg.lstsq(X, xy[['x', 'y']].values, rcond=None)[0].T
vu = to_utm(v.longitude.values, v.latitude.values); v['x'], v['y'] = vu[0], vu[1]
TL = pd.read_parquet(P + 'ratapani/fsi/true_lead_labels.parquet'); TL['date'] = pd.to_datetime(TL.date); TL['fire_day'] = pd.to_datetime(TL.fire_day)
fires = TL[TL.dated == True][['season', 'cell_id', 'fire_day']].drop_duplicates()
fire_set = set(zip(fires.season, fires.cell_id, fires.fire_day))
cand = TL[TL.valid_strict][['season', 'date', 'cell_id']]
pw = pd.read_csv(IGN + 'weather_power_2017_2026.csv', parse_dates=['date']).set_index('date')
e5 = pd.read_parquet(IGN + 'era5_daily_points.parquet'); e5['date'] = pd.to_datetime(e5.date); e5 = e5.set_index(['date', 'point_id'])
cp = pd.read_csv(IGN + 'cell_point.csv').set_index('cell_id').point_id
rows = []
for (y, d), g in cand.groupby(['season', 'date']):
    f = v[v.date == d]
    if len(f) == 0: continue
    tree = cKDTree(f[['x', 'y']].values)
    cx = xy.loc[g.cell_id.values, ['x', 'y']].values
    dist, j = tree.query(cx, k=1, distance_upper_bound=3000)
    ok = np.isfinite(dist)
    if not ok.any(): continue
    fx = f[['x', 'y']].values[j[ok]]
    bearing = np.degrees(np.arctan2(cx[ok, 0] - fx[:, 0], cx[ok, 1] - fx[:, 1])) % 360
    n_front = np.array([len(n_) for n_ in tree.query_ball_point(cx[ok], 2000)])
    cells = g.cell_id.values[ok]
    burn = np.array([(y, c, d + pd.Timedelta(days=1)) in fire_set for c in cells])
    r = pd.DataFrame(dict(season=y, date=d, cell_id=cells, dist=dist[ok], bearing=bearing, n_front_2km=n_front, burn=burn))
    for lag, tag in [(0, 'm1'), (-1, 'd0')]:
        dd = d - pd.Timedelta(days=lag)
        r[f'wd_pw_{tag}'] = pw.wd_pm.get(dd, np.nan); r[f'ws_pw_{tag}'] = pw.ws_pm.get(dd, np.nan)
        pid = cp.reindex(cells).values
        idx = pd.MultiIndex.from_arrays([np.repeat(dd, len(cells)), pid])
        r[f'wd_e5_{tag}'] = e5.wd_pm.reindex(idx).values; r[f'ws_e5_{tag}'] = e5.ws_pm.reindex(idx).values
    rows.append(r)
df = pd.concat(rows, ignore_index=True)
for k in ['pw_m1', 'pw_d0', 'e5_m1', 'e5_d0']:
    df[f'down_{k}'] = np.cos(np.radians(df.bearing - (df[f'wd_{k}'] + 180)))
print('exposed cell-days', len(df), 'burns', int(df.burn.sum()), 'rate', round(df.burn.mean(), 4), flush=True)
res = {'exposed_cell_days': int(len(df)), 'burns': int(df.burn.sum())}
def tab(col, bins):
    g = df.groupby(pd.cut(df[col], bins), observed=True).burn.agg(['mean', 'size'])
    return {str(k): [round(float(m), 4), int(n)] for k, (m, n) in g.iterrows()}
res['by_dist'] = tab('dist', [0, 500, 1000, 1500, 2000, 3000])
for k in ['pw_m1', 'pw_d0', 'e5_m1', 'e5_d0']:
    res[f'by_down_{k}'] = tab(f'down_{k}', [-1, -0.5, 0, 0.5, 1.01])
    # within 1 km only, where wind should matter most
    sub = df[df.dist <= 1000]; g = sub.groupby(pd.cut(sub[f'down_{k}'], [-1, -0.5, 0, 0.5, 1.01]), observed=True).burn.agg(['mean', 'size'])
    res[f'by_down_{k}_within1km'] = {str(a): [round(float(m), 4), int(n)] for a, (m, n) in g.iterrows()}
    # strong wind days only (ws > 75th pct)
    ws = df[f'ws_{k}']; strong = df[ws > ws.quantile(0.75)]
    g = strong.groupby(pd.cut(strong[f'down_{k}'], [-1, -0.5, 0, 0.5, 1.01]), observed=True).burn.agg(['mean', 'size'])
    res[f'by_down_{k}_strongwind'] = {str(a): [round(float(m), 4), int(n)] for a, (m, n) in g.iterrows()}
# model with and without wind: LightGBM AUC, season-grouped CV
import lightgbm as lgb
from sklearn.metrics import roc_auc_score
base = ['dist', 'n_front_2km']
for name, feats in [('no_wind', base), ('wind_pw_m1', base + ['down_pw_m1', 'ws_pw_m1']), ('wind_e5_m1', base + ['down_e5_m1', 'ws_e5_m1']), ('wind_e5_both', base + ['down_e5_m1', 'ws_e5_m1', 'down_e5_d0', 'ws_e5_d0'])]:
    aucs = []
    for y in sorted(df.season.unique()):
        tr, te = df[df.season != y], df[df.season == y]
        if te.burn.sum() < 20: continue
        m = lgb.train(dict(objective='binary', learning_rate=0.05, num_leaves=15, min_data_in_leaf=100, verbose=-1, seed=0), lgb.Dataset(tr[feats], label=tr.burn), 300)
        aucs.append(roc_auc_score(te.burn, m.predict(te[feats])))
    res[f'auc_{name}'] = round(float(np.mean(aucs)), 4)
    print(name, res[f'auc_{name}'], flush=True)
json.dump(res, open(IGN + 'results/wind_viirs.json', 'w'), indent=1); print(json.dumps(res, indent=1))
