"""New question 6. Does the forest come back greener or weaker the monsoon after a fire, and does the fire's date matter?
Only one season can be tested from what we hold: MODIS 8-day composites (field-system cloud series, 500 m) cover Sep-Oct 2024
(before) and Sep-Oct 2025 (after) around the 2025 fire season. Per 500 m forest cell: peak NDVI and NDMI (max of the Sep-Oct
composites) 2025 minus 2024, for cells burnt in 2025 (by burn date, scar rasters at 60 m -> burnt share of the cell's forest)
against unburnt forest cells of the same division. Out: out/n6_cells.parquet (scratch), out/n6_recovery.csv"""
import os, sys, numpy as np, pandas as pd
sys.path.insert(0, '/mnt/project-files/ratapani/fsi/scouting/code/control_burn/'); import cb0 as B
HERE = os.path.dirname(os.path.abspath(__file__)); OUT = HERE + '/out/'; CS = '/mnt/project-files/field-system/pc_models/cloud_series/'
W500 = 1829
def peak(npz, m0, m1):
    Z = np.load(npz, allow_pickle=True); d = pd.to_datetime(Z['dates']); m = (d.month >= m0) & (d.month <= m1)
    nd = Z['ndvi'][m].astype(float); nd[nd == -32768] = np.nan; nm = Z['ndmi'][m].astype(float); nm[nm == -32768] = np.nan
    return pd.DataFrame({'cell': Z['cells'], 'ndvi': np.nanmax(nd, 0) / 1e4, 'ndmi': np.nanmax(nm, 0) / 1e4, 'n': np.isfinite(nd).sum(0)})
A = peak(CS + 'modis_2025.npz', 9, 10).rename(columns={'ndvi': 'ndvi24', 'ndmi': 'ndmi24', 'n': 'n24'}); Bp = peak(CS + 'modis_2026.npz', 9, 10).rename(columns={'ndvi': 'ndvi25', 'ndmi': 'ndmi25', 'n': 'n25'})
M = A.merge(Bp, on='cell'); print('cells with both years', len(M), 'composites Sep-Oct', A.n24.max(), Bp.n25.max())
# burnt cells 2025 at 500 m from the 60 m scar rasters
rows = []
for key in B.KEYS:
    L, FOR = B.load_div(key); H, W = L['H'], L['W']; D = B.burn_day(L, 2025)
    rr, cc = np.nonzero(FOR); x = L['x0'] + (cc + 0.5) * B.RES; y = L['y1'] - (rr + 0.5) * B.RES
    c500 = ((2996000 - y) // 500).astype(int) * W500 + ((x - 399000) // 500).astype(int)
    d = D[rr, cc]; burnt = d < 9999
    g = pd.DataFrame({'cell': c500, 'burnt': burnt, 'doy': np.where(burnt, d, np.nan)}).groupby('cell').agg(forest_cells=('burnt', 'size'), burnt_cells=('burnt', 'sum'), doy=('doy', 'median')).reset_index()
    g['key'] = key; rows.append(g); print(key, flush=True)
G = pd.concat(rows).drop_duplicates('cell'); G['share'] = G.burnt_cells / G.forest_cells; G['forest_ha'] = G.forest_cells * B.CELL_HA
C = G[G.forest_ha >= 12.5].merge(M, on='cell', how='inner')          # at least half the 25 ha cell is forest
C['cls'] = np.where(C.share == 0, 'unburnt', np.where(C.share < 0.5, 'part-burnt', pd.cut(C.doy, [0, 59, 74, 90, 400], labels=['burnt 15-28 Feb or earlier', 'burnt 1-15 Mar', 'burnt 16-31 Mar', 'burnt Apr+']).astype(str)))
C['dndvi'] = C.ndvi25 - C.ndvi24; C['dndmi'] = C.ndmi25 - C.ndmi24
for v in ('dndvi', 'dndmi', 'ndvi24', 'ndmi24'): C[v + '_w'] = C[v] - C.groupby('key')[v].transform('mean')   # within-division
C.to_parquet(B.SCR + 'n6_cells.parquet', index=False)
res = []
rng = np.random.default_rng(0); keys = C.key.unique()
for cls, d in C.groupby('cls'):
    bs = []
    for _ in range(300):
        pick = rng.choice(keys, len(keys)); m = d[d.key.isin(pick)]; bs.append(m.dndvi_w.mean())
    res.append(dict(cls=cls, cells=len(d), ndvi_2024_peak=d.ndvi24.mean(), ndvi_2025_peak=d.ndvi25.mean(), d_ndvi=d.dndvi.mean(), d_ndvi_within_division=d.dndvi_w.mean(), ci_lo=np.percentile(bs, 2.5), ci_hi=np.percentile(bs, 97.5), d_ndmi_within_division=d.dndmi_w.mean(), ndvi_2024_within_division=d.ndvi24_w.mean()))
R = pd.DataFrame(res); R.to_csv(OUT + 'n6_recovery.csv', index=False); print(R.round(4).to_string(index=False))
# same, holding the 2024 level: regression of dndvi on class + ndvi24 within division
import statsmodels.formula.api as smf
d = C[C.cls != 'part-burnt'].copy(); d['cls'] = pd.Categorical(d.cls, ['unburnt'] + [c for c in d.cls.unique() if c != 'unburnt'])
m = smf.ols('dndvi_w ~ cls + ndvi24_w', data=d).fit(cov_type='cluster', cov_kwds={'groups': d.key})
print(m.summary().tables[1])
