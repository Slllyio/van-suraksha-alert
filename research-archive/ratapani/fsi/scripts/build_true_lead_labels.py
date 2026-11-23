"""True-lead labels (SCORING.md 'True-lead variant'): scar windows say where, VIIRS says which day.
Fire day d = first VIIRS (nominal/high confidence) within 750 m of the cell centre on [ws, we+1] of the cell's
first-burn window (ws, we], clipped to (ws, we]. Positives t = d-2, d-1; rest of [ws-1, we-1] masked.
strict: undated windows masked entirely; lenient: undated windows keep the main rule. Seasons 2017-2024 (VIIRS file ends 2024).
Out: true_lead_labels.parquet (season, date, cell_id, pos_main, pos, valid_strict, valid_lenient, dated, fire_day)."""
import json, importlib.util, numpy as np, pandas as pd
from scipy.spatial import cKDTree
P = '/mnt/project-files/'
spec = importlib.util.spec_from_file_location('ps', P + 'research/ratapani-ignition/scripts/pipeline_score.py'); ps = importlib.util.module_from_spec(spec); spec.loader.exec_module(ps)
SEAS = list(range(2017, 2025))
lab = ps.labels(SEAS)
G = json.load(open(P + 'ratapani/grid_500m.geojson'))['features']
xy = np.zeros((3614, 2))
for f in G: p = f['properties']; xy[p['cell_id']] = (p['x0'] + 250, p['y0'] + 250)   # EPSG:32643 cell centres
v = pd.read_parquet(P + 'ratapani/viirs_snpp_2013_2024.parquet')
v = v[v.confidence.astype(str).str.lower().isin(['n', 'h', 'nominal', 'high'])].copy()
v['date'] = pd.to_datetime(v.acq_date)
# lon/lat -> UTM 43N (no pyproj here): fit an affine map from the grid's WGS84 corners to its UTM corners
ll, ut = [], []
for f in G:
    p = f['properties']; c = np.array(f['geometry']['coordinates'][0][:4])
    ll.append(c.mean(0)); ut.append((p['x0'] + 250, p['y0'] + 250))
ll, ut = np.array(ll), np.array(ut)
Aff, *_ = np.linalg.lstsq(np.c_[ll, ll[:, :1] ** 2, ll[:, 1:] ** 2, ll[:, :1] * ll[:, 1:], np.ones(len(ll))], ut, rcond=None)
L = np.c_[v.longitude, v.latitude]; vxy = np.c_[L, L[:, :1] ** 2, L[:, 1:] ** 2, L[:, :1] * L[:, 1:], np.ones(len(L))] @ Aff
tree = cKDTree(xy)
pairs = [(c, v.date.iloc[k]) for k, nb in enumerate(tree.query_ball_point(vxy, r=750)) for c in nb]
vp = pd.DataFrame(pairs, columns=['cell_id', 'vd']).drop_duplicates()
bw = pd.read_csv(P + 'research/ratapani-burn-labels/burn_windows.csv', parse_dates=['window_start', 'window_end'])
bw = bw[(bw.burned == 1) & bw.season.isin(SEAS)].sort_values(['season', 'cell_id', 'window_end']).drop_duplicates(['season', 'cell_id'])
x = bw.merge(vp, on='cell_id')
x = x[(x.vd >= x.window_start) & (x.vd <= x.window_end + pd.Timedelta('1D'))].sort_values('vd').drop_duplicates(['season', 'cell_id'])
x['fire_day'] = x.vd.clip(lower=x.window_start + pd.Timedelta('1D'), upper=x.window_end)
bw = bw.merge(x[['season', 'cell_id', 'fire_day']], on=['season', 'cell_id'], how='left')
print('first burns', len(bw), 'dated', int(bw.fire_day.notna().sum()))
o = lab.rename(columns={'pos': 'pos_main'}).merge(bw[['season', 'cell_id', 'window_start', 'window_end', 'fire_day']], on=['season', 'cell_id'], how='left')
inwin = o.window_start.notna() & (o.date >= o.window_start - pd.Timedelta('1D')) & (o.date <= o.window_end - pd.Timedelta('1D'))
dated = o.fire_day.notna()
lead = (o.fire_day - o.date).dt.days
tl = dated & inwin & lead.isin([1, 2])
o['pos'] = np.where(inwin & dated, tl, np.where(inwin, o.pos_main, False))
o['dated'] = dated
o['valid_lenient'] = ~(inwin & dated & ~tl)
o['valid_strict'] = o.valid_lenient & ~(inwin & ~dated)
o['pos'] = o.pos.astype(bool)
out = o[['season', 'date', 'cell_id', 'pos_main', 'pos', 'valid_strict', 'valid_lenient', 'dated', 'fire_day']]
out.to_parquet(P + 'ratapani/fsi/true_lead_labels.parquet', index=False)
for k in ('strict', 'lenient'):
    s = out[out['valid_' + k]]; print(k, 'valid cell-days', len(s), 'positives', int(s.pos.sum()), 'base rate', round(s.pos.mean(), 4))
print('main rule positives', int(out.pos_main.sum()))
