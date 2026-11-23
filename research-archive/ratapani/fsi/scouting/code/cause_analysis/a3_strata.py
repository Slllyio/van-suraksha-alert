"""Recall@5 of the lean LOSO model (2017-2024) split by cause-proxy strata of the positive (first-burn) cell-seasons."""
import importlib.util, json, numpy as np, pandas as pd
from scipy.spatial import cKDTree
RS = '/mnt/project-files/research/'; SC = '/mnt/project-files/ratapani/scoring/'; OUT = '/tmp/claude-0/-home-user/be9b8f54-cc26-52cb-bdbb-9c8008a24baf/scratchpad/cause_an/'
spec = importlib.util.spec_from_file_location('ps', RS + 'ratapani-ignition/scripts/pipeline_score.py'); ps = importlib.util.module_from_spec(spec); spec.loader.exec_module(ps)
S = list(range(2017, 2025))
lab = ps.labels(S)
pred = pd.read_parquet(SC + 'pipeline_lean_pred_loso_2017_24.parquet')
pb = pd.read_csv(SC + 'pseudo_beats_pipeline.csv').set_index('cell_id').pseudo_beat
m = lab.merge(pred, on=['season', 'date', 'cell_id'], how='left'); m['pb'] = m.cell_id.map(pb)
m['r'] = m.pipeline_lean.fillna(-np.inf).groupby([m.season, m.date, m.pb]).rank('first', ascending=False)
m['hit'] = m.pos & (m.r <= 5)
print('overall recall@5', round(m.hit.sum() / m.pos.sum(), 4), ' positives', int(m.pos.sum()))
P = m[m.pos].copy()
# cell-season attributes
bw = pd.read_csv(RS + 'ratapani-burn-labels/burn_windows.csv', parse_dates=['window_start', 'window_end'])
fb = bw[bw.burned == 1].sort_values(['season', 'cell_id', 'window_end']).drop_duplicates(['season', 'cell_id']).set_index(['season', 'cell_id'])
G = json.load(open('/mnt/project-files/ratapani/grid_500m.geojson'))['features']; n = len(G)
xy = np.zeros((n, 2))
for f in G: p = f['properties']; xy[p['cell_id']] = (p['x0'] + 250, p['y0'] + 250)
v = pd.read_parquet(OUT + 'viirs_cells.parquet')
# VIIRS lon/lat -> approx UTM via cell centre of assigned cell plus offset is overkill; use assigned cell and its 8 neighbours (<=750 m)
tr = cKDTree(xy); nb = tr.query_ball_point(xy, 760)
v['d'] = v.dt_ist.dt.normalize()
vg = {c: g for c, g in v.groupby('cell_id')}
rows = []
for (Y, c), r in fb.iterrows():
    if Y not in S: continue
    pts = pd.concat([vg[k] for k in nb[c] if k in vg]) if any(k in vg for k in nb[c]) else None
    if pts is not None:
        pts = pts[(pts.d > r.window_start - pd.Timedelta('1D')) & (pts.d <= r.window_end + pd.Timedelta('1D'))]
    has = pts is not None and len(pts) > 0
    rows.append(dict(season=Y, cell_id=c, ws=r.window_start, we=r.window_end, ha=r.burned_ha, viirs=has,
                     night=bool(has and (pts.daynight == 'N').any()), vdays=(pts.d.nunique() if has else 0), frpmax=(pts.frp.max() if has else np.nan)))
A = pd.DataFrame(rows)
# patch geometry: largest patch with this end date in the cell
Pt = pd.read_parquet(OUT + 'patches.parquet')
Pt['pid'] = np.arange(len(Pt)); Pt = Pt.drop(columns='cell_id').merge(pd.read_parquet(OUT + 'patch_cells.parquet')[['pid', 'cell_id']], on='pid')
Pt['we'] = pd.to_datetime(Pt.season.astype(str) + '-01-01') + pd.to_timedelta(Pt.end_doy, 'D')
big = Pt.sort_values('ha', ascending=False).drop_duplicates(['season', 'cell_id', 'we'])[['season', 'cell_id', 'we', 'ha', 'elong', 'width_m', 'len_m']].rename(columns={'ha': 'patch_ha'})
A = A.merge(big, on=['season', 'cell_id', 'we'], how='left')
px = pd.read_csv('/mnt/project-files/ratapani/ee/proximity.csv').set_index('cell_id'); wc = pd.read_csv('/mnt/project-files/ratapani/ee/worldcover.csv').set_index('cell_id')
A = A.join(px[['dist_crop_cell', 'dist_village', 'depth_in_forest', 'dist_road']], on='cell_id').join(wc[['wc_40']], on='cell_id')
# repeat: seasons burned among the other 7
B = fb.reset_index(); burned = {Y: set(B[B.season == Y].cell_id) for Y in S}
A['n_other'] = [sum(c in burned[y] for y in S if y != Y) for Y, c in zip(A.season, A.cell_id)]
# spread proxy: a neighbour (<=1 km) had its first-burn window end within 7 days before this cell's window start
fbd = {(Y, c): we for (Y, c), we in fb.window_end.items()}
nb1 = tr.query_ball_point(xy, 1010)
A['spread'] = [any(((Y, k) in fbd) and (pd.Timedelta(0) <= ws - fbd[(Y, k)] <= pd.Timedelta('7D')) for k in nb1[c] if k != c) for Y, c, ws in zip(A.season, A.cell_id, A.ws)]
A['month'] = A.we.dt.month
A['managed_proxy'] = (A.we <= pd.to_datetime(A.season.astype(str) + '-02-20')) & A.viirs & ~A.night & (A.vdays <= 1)
A['linear'] = (A.elong >= 4) & (A.width_m <= 80) & (A.len_m >= 300)
A['cropedge'] = (A.wc_40 >= 0.2) | (A.dist_crop_cell <= 500)
A['late'] = A.we >= pd.to_datetime(A.season.astype(str) + '-04-15')
A.to_parquet(OUT + 'pos_attrs.parquet')
P = P.merge(A, on=['season', 'cell_id'], how='left')
def rep(col, bins=None, labels=None):
    x = P[col] if bins is None else pd.cut(P[col], bins, labels=labels)
    g = P.groupby(x, observed=True)
    t = pd.DataFrame({'pos_celldays': g.size(), 'share': g.size() / len(P), 'recall@5': g.hit.mean()}).round(3)
    print(f'\n-- {col} --\n{t.to_string()}')
for c in ['viirs', 'night', 'managed_proxy', 'linear', 'cropedge', 'late', 'spread', 'month']: rep(c)
rep('ha', [0, 2, 5, 10, 25, 1e4]); rep('n_other', [-1, 0, 1, 3, 7]); rep('dist_village', [0, 1000, 2000, 4000, 1e5]); rep('frpmax', [0, 3, 6, 12, 1e4])
print('\ncell-season counts: total', len(A), 'managed_proxy', int(A.managed_proxy.sum()), 'linear', int(A.linear.sum()), 'cropedge', int(A.cropedge.sum()), 'late', int(A.late.sum()), 'spread', int(A.spread.sum()))
