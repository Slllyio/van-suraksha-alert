"""FILDA-2 night pixels vs FIRMS (operational VIIRS 375 m) night points, same satellite and overpass, MP forest
(cells in a beat), 15 Feb - 31 May. Usage: python3 compare_filda.py YEAR -> compare_YEAR.json, extra_YEAR.csv"""
import sys, json, numpy as np, pandas as pd
from scipy.spatial import cKDTree
from pyproj import Transformer
sys.path.insert(0, '/mnt/project-files/ratapani/scoring/mp_check'); import mp_simple_rules as M
Y = int(sys.argv[1]); D = '/mnt/project-files/research/ceiling/filda/'
TO = Transformer.from_crs('EPSG:4326', 'EPSG:32643', always_xy=True)
cells = pd.read_parquet(M.P + 'ratapani/mp_grid/mp_cells.parquet')[['row', 'col', 'beat_uid']]
FOREST = set(zip(cells.row, cells.col))
def rc(lon, lat):
    x, y = M.TF.transform(lon, lat); return np.floor((M.Y1 - y) / M.S).astype(int), np.floor((x - M.X0) / M.S).astype(int)
F = pd.read_csv(D + f'filda_{Y}.csv', parse_dates=['utc']); F = F[F.FP_Gas_Flaring == 0]
F['sat'] = F.sat.map({'VNP47IMG': 'snpp', 'VJ147IMG': 'jpss1'})
F['row'], F['col'] = rc(F.FP_Longitude.values, F.FP_Latitude.values)
F['ld'] = (F.utc + pd.Timedelta(hours=5, minutes=30)).dt.normalize()
A = []
for s in ('snpp', 'jpss1', 'noaa21'):
    a = pd.read_csv(M.P + f'fire-alert-scars/alerts_mp/viirs-{s}_{Y}.csv'); a['sat'] = s; A.append(a)
A = pd.concat(A, ignore_index=True)
A['utc'] = pd.to_datetime(A.acq_date) + pd.to_timedelta(A.acq_time // 100, 'h') + pd.to_timedelta(A.acq_time % 100, 'm')
A['ld'] = (A.utc + pd.Timedelta(hours=5, minutes=30)).dt.normalize()
A['row'], A['col'] = rc(A.longitude.values, A.latitude.values)
for X, lo, la in ((F, 'FP_Longitude', 'FP_Latitude'), (A, 'longitude', 'latitude')):
    X['x'], X['y'] = TO.transform(X[lo].values, X[la].values)
    X['forest'] = [(r, c) in FOREST for r, c in zip(X.row, X.col)]
    md = X.ld.dt.month * 100 + X.ld.dt.day; X['season'] = (md >= 215) & (md <= 531)
# same-overpass match: FIRMS point of the same satellite within 20 min
F['d_firms'] = np.inf; A['d_filda'] = np.inf
for s in ('snpp', 'jpss1'):
    f = F[F.sat == s]; a = A[(A.sat == s) & (A.daynight == 'N')]
    for g, fg in f.groupby(f.utc.dt.floor('h')):
        ag = a[(a.utc >= fg.utc.min() - pd.Timedelta('20min')) & (a.utc <= fg.utc.max() + pd.Timedelta('26min'))]
        if len(ag):
            F.loc[fg.index, 'd_firms'] = cKDTree(ag[['x', 'y']].values).query(fg[['x', 'y']].values)[0]
            A.loc[ag.index, 'd_filda'] = np.minimum(A.loc[ag.index, 'd_filda'], cKDTree(fg[['x', 'y']].values).query(ag[['x', 'y']].values)[0])
F['extra'] = F.d_firms > 750
# context from FIRMS (any satellite, day or night)
dn = lambda t: (t - pd.Timestamp('2000-01-01')).dt.days.values
tree = cKDTree(np.c_[A.x.values, A.y.values]); adn = dn(A.ld)
def ctx(r):
    idx = tree.query_ball_point([r.x, r.y], 1500); d = adn[idx] - dn(pd.Series([r.ld]))[0]
    return pd.Series({'firms_before': int(((d >= -3) & (d < 0)).sum()), 'firms_same': int((d == 0).sum()), 'firms_after': int(((d > 0) & (d <= 3)).sum())})
E = F[F.extra & F.forest & F.season].copy()
E = pd.concat([E, E.apply(ctx, axis=1)], axis=1)
E['kind'] = np.select([(E.firms_before > 0) & (E.firms_after > 0), (E.firms_before == 0) & (E.firms_same + E.firms_after > 0), E.firms_before > 0],
                      ['gap_fill (FIRMS before and after)', 'earlier (FIRMS only same day or after)', 'tail (FIRMS only before)'], 'isolated (no FIRMS within 1.5 km, +-3 d)')
E.to_csv(D + f'extra_{Y}.csv', index=False)
fs = F[F.forest & F.season]; an = A[(A.daynight == 'N') & A.forest & A.season & A.sat.isin(['snpp', 'jpss1'])]
R = {'year': Y, 'filda_forest_night_px': len(fs), 'filda_extra_px': int(fs.extra.sum()),
     'firms_forest_night_px_snpp_jpss1': len(an), 'firms_matched_by_filda_pct': round(100 * (an.d_filda <= 750).mean(), 1),
     'extra_vs_firms_pct': round(100 * fs.extra.sum() / max(1, len(an)), 1),
     'extra_kind': E.kind.value_counts().to_dict(),
     'extra_conf': E.FP_confidence.value_counts().to_dict(), 'extra_power_median_MW': float(E.FP_Power.median()),
     'matched_power_median_MW': float(fs[~fs.extra].FP_Power.median()), 'extra_dnb_pos': E.FP_DNB_POS.describe().round(2).to_dict()}
json.dump(R, open(D + f'compare_{Y}.json', 'w'), indent=1, default=str); print(json.dumps(R, indent=1, default=str))
