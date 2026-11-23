"""Check the all-MP 10-day dryness against Ratapani's per-look S2/Landsat cell values (s2_cells.parquet): for each Ratapani cell
and step d, the mean of its clear looks in [d-15, d) vs the MP value. Usage: python3 scr/mp_dry_check.py <dir with mp_dry_YYYY.npz>"""
import sys, json, glob, numpy as np, pandas as pd
D = sys.argv[1]; W = 1829
G = json.load(open('/mnt/project-files/ratapani/grid_500m.geojson'))['features']
r = pd.DataFrame([f['properties'] for f in G])[['cell_id', 'x0', 'y0']]
r['cell'] = ((2996000 - (r.y0 + 500)) // 500 * W + (r.x0 - 399000) // 500).astype(int)
sc = pd.read_parquet('/mnt/project-files/research/ratapani-ignition/s2_cells.parquet'); sc['date'] = pd.to_datetime(sc['date'])
cc = pd.read_parquet('/mnt/project-files/research/ratapani-burn-labels/clear_calendar.parquet'); cc['date'] = pd.to_datetime(cc['date'])
sc = sc.merge(cc[cc.clear_frac >= 0.5][['cell_id', 'date']].drop_duplicates(), on=['cell_id', 'date'])
out = []
for f in sorted(glob.glob(D + '/mp_dry_*.npz')):
    z = np.load(f); pos = pd.Series(np.arange(len(z['cells'])), index=z['cells']); have = r.cell.isin(pos.index)
    idx = pos[r.cell[have]].values; cid = r.cell_id[have].values
    for k, s in enumerate(z['steps']):
        d = pd.Timestamp(str(s)); m = sc[(sc.date >= d - pd.Timedelta(days=15)) & (sc.date < d)].groupby('cell_id')[['ndvi', 'ndmi', 'nbr']].mean()
        if not len(m): continue
        X = z['X'][k][idx].astype(float); X[X == -9999] = np.nan
        a = pd.DataFrame(X[:, :3] / 1e4, columns=['ndvi_mp', 'ndmi_mp', 'nbr_mp'], index=cid).join(m, how='inner').dropna(); a['date'] = d
        out.append(a)
A = pd.concat(out); print('pairs', len(A), 'steps', A.date.nunique())
for v in ('ndvi', 'ndmi', 'nbr'):
    print(v, 'r =', round(A[v].corr(A[v + '_mp']), 3), '| mean diff', round((A[v + '_mp'] - A[v]).mean(), 3),
          '| within-step r (spatial) =', round(A.groupby('date').apply(lambda g: g[v].corr(g[v + '_mp'])).median(), 3))
