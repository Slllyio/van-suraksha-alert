"""System rebuild (round 22): shared constants, data loading and caches.
Grid: EPSG:32643 500 m MP grid (ratapani/mp_grid). Big intermediates go to scratch SC, never to the shared mount."""
import os, json, pickle
import numpy as np, pandas as pd
from pyproj import Transformer
P = '/mnt/project-files/'
SC = '/tmp/claude-0/-home-user/be9b8f54-cc26-52cb-bdbb-9c8008a24baf/scratchpad/r22/'
CODE = P + 'ratapani/fsi/scouting/code/system_rebuild/'
OUT = CODE + 'out/'
os.makedirs(SC, exist_ok=True); os.makedirs(OUT, exist_ok=True)
X0, Y1, S, W, H = 399000.0, 2996000.0, 500.0, 1829, 1332
TF = Transformer.from_crs(4326, 32643, always_xy=True)
SATS = {'snpp': 'S-NPP', 'jpss1': 'NOAA-20', 'noaa21': 'NOAA-21'}
PERIODS = {'held': ((2019, 2020, 2021), (2022, 2023, 2024)), 'fwd': ((2019, 2020, 2021, 2022, 2023, 2024), (2025, 2026))}


def load_det(years=range(2014, 2027)):
    """Every VIIRS SP detection (3 satellites, all types), with UTM x/y, grid row/col, UTC time, IST local date."""
    fn = SC + 'det_all.parquet'
    if not os.path.exists(fn):
        fs = []
        for y in range(2014, 2027):
            for sat in SATS:
                f = P + f'fire-alert-scars/alerts_mp/viirs-{sat}_{y}.csv'
                if not os.path.exists(f): continue
                d = pd.read_csv(f); d['sat'] = sat; fs.append(d)
        v = pd.concat(fs, ignore_index=True)
        x, y_ = TF.transform(v.longitude.values, v.latitude.values)
        v['x'] = x.astype(np.float32); v['y'] = y_.astype(np.float32)
        v['col'] = np.floor((x - X0) / S).astype(np.int32); v['row'] = np.floor((Y1 - y_) / S).astype(np.int32)
        v['utc'] = pd.to_datetime(v.acq_date) + pd.to_timedelta(v.acq_time // 100, 'h') + pd.to_timedelta(v.acq_time % 100, 'm')
        v['ld'] = (v.utc + pd.Timedelta(hours=5, minutes=30)).dt.normalize()
        v['season'] = v.ld.dt.year.astype(np.int16)
        v = v.drop(columns=['acq_date', 'satellite', 'instrument', 'version'])
        v['ctrl'] = ctrl_flag(v)
        v.to_parquet(fn)
    v = pd.read_parquet(fn)
    return v[v.season.isin(list(years))]


def ctrl_flag(v):
    """Likely control burns 15-28 Feb, exactly the mp_simple_rules.py MPV=season rule (type-0 points, any satellite):
    day-only cluster of <=2 points within 1 km on the day, max FRP <=5 MW, nothing else within 1 km on d-2..d+3."""
    from scipy.spatial import cKDTree
    ctrl = np.zeros(len(v), bool)
    t0 = np.where(v.type.values == 0)[0]
    q = v.iloc[t0]
    xy = np.c_[q.x.values.astype(float), q.y.values.astype(float)]; dn = (q.ld - pd.Timestamp('2000-01-01')).dt.days.values
    md = q.ld.dt.month.values * 100 + q.ld.dt.day.values; cand = np.where((md >= 215) & (md <= 228))[0]
    # mp_simple_rules drops duplicate rows only after the flag, and builds the tree on all type-0 rows of the loaded years
    tree = cKDTree(np.c_[xy, dn * 1e6]); dnv = q.daynight.values; frp = q.frp.values
    for i in cand:
        same = [j for j in tree.query_ball_point(np.r_[xy[i], dn[i] * 1e6], r=1000) if dn[j] == dn[i]]
        if len(same) > 2 or (dnv[same] != 'D').any() or frp[same].max() > 5: continue
        near = 0
        for dd in (-2, -1, 1, 2, 3):
            near += len(tree.query_ball_point(np.r_[xy[i], (dn[i] + dd) * 1e6], r=1000))
        if near == 0: ctrl[t0[i]] = True
    return ctrl


def grids():
    """Division grids exactly as the PC/mp_check scoring: 500 m cells with >=25% of area inside the division."""
    fn = SC + 'grids.pkl'
    if not os.path.exists(fn):
        import sys; sys.path.insert(0, P + 'ratapani/scoring/mp_check')
        import mp_simple_rules as M
        pickle.dump(M.grids(), open(fn, 'wb'))
    return pickle.load(open(fn, 'rb'))


# Ablation subset (coordinator scope change, 17 Oct): 10 divisions spanning MP types. Set R22_SUB=0 for all 87.
SUBSET = ['Obedullahganj', 'Raisen', 'Khandwa', 'South_Balaghat', 'Dindori', 'Kanha_Tiger_Reserve', 'Satpura_TR',
          'Shivpuri', 'Gwalior', 'Singrauli']
SUB = os.environ.get('R22_SUB', '1') == '1'
TAG = '_sub' if SUB else ''


def grids_active():
    G = grids()
    return {k: v for k, v in G.items() if k in SUBSET} if SUB else G


def union_cells():
    """All cells in any (active) division grid, as flat index row*W+col (sorted)."""
    G = grids_active(); fl = np.unique(np.concatenate([r * W + c for r, c in G.values()]))
    return fl


def issue_days(y):
    d = pd.date_range(f'{y}-02-13', f'{y}-05-30'); return d


def season_days(y):
    """Raster day axis used everywhere: 1 Oct (y-1) to 2 Jun y (data exist Jan-Jun only)."""
    return pd.date_range(f'{y - 1}-10-01', f'{y}-06-02')
