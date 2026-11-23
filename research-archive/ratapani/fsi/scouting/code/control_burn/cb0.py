"""Shared settings for the control-burning study (scouting round 29, 19 Oct 2026).
Data: round-26 per-division fire rasters (scratch r26/fires_<div>.pkl: 60 m VTM lattice, every scar fire 2017-25 with per-cell burn day),
VIIRS points Jan-Jun 2014-26 (code/mp_types/out/viirs_vtm.parquet). Heat points are used to see re-burning because a second scar on
already-burnt ground is invisible to the scar method (no fresh dNBR change)."""
import os, sys, pickle, glob
import numpy as np, pandas as pd
sys.path.insert(0, '/mnt/project-files/ratapani/fsi/scouting/code/fire_lines/')
import common as C25  # noqa
SCR = '/tmp/claude-0/-home-user/be9b8f54-cc26-52cb-bdbb-9c8008a24baf/scratchpad/'
SC = SCR + 'cb/'; SC26 = SCR + 'r26/'
HERE = '/mnt/project-files/ratapani/fsi/scouting/code/control_burn/'; OUT = HERE + 'out/'
VIIRS = '/mnt/project-files/ratapani/fsi/scouting/code/mp_types/out/viirs_vtm.parquet'
RES = 60.0; CELL_HA = 0.36; SQ = 83          # 5 km squares = 83 cells
YEARS = range(2017, 2026)
D0, D1 = 46, 166                             # 15 Feb .. 15 Jun (doy, non-leap)
WEEKS = list(range(D0, D1, 7))               # 17 week starts
AGE_BINS = [7, 14, 28, 42, 56, 84, 400]      # days since the (deep) burn: 1-2 wk, 2-4, 4-6, 6-8, 8-12, 12+
AGE_LAB = ['1-2 wk', '2-4 wk', '4-6 wk', '6-8 wk', '8-12 wk', '12+ wk']
MON_LAB = ['15-28 Feb', 'Mar', 'Apr-Jun']   # month the old burn happened
KEYS = sorted(p.split('fires_')[1][:-4] for p in glob.glob(SC26 + 'fires_*.pkl') if 'table' not in p)
os.makedirs(SC, exist_ok=True); os.makedirs(OUT, exist_ok=True)
TF = C25.TF


def load_div(key):
    L = pickle.load(open(SC26 + f'fires_{key}.pkl', 'rb'))
    H, W = L['H'], L['W']; FOR = np.unpackbits(L['forest'])[:H * W].astype(bool).reshape(H, W)
    return L, FOR


def burn_day(L, year):
    """Day-of-year of the first scar burn per cell in a season (9999 = none)."""
    H, W = L['H'], L['W']; B = np.full((H, W), 9999, np.int16)
    for f in L['fires']:
        if f['year'] != year: continue
        h, w = f['shape']; M = np.unpackbits(f['M'])[:h * w].astype(bool).reshape(h, w)
        d = (f['t0'].dayofyear + f['day'].astype(np.int16))
        sub = B[f['r0']:f['r0'] + h, f['c0']:f['c0'] + w]
        D = np.full((h, w), 9999, np.int16); D[M] = d
        np.minimum(sub, D, out=sub)
    return B


def points(div, year):
    """VIIRS points of one division-season (Jan-Jun) with lattice row/col."""
    import pyarrow.parquet as pq, pyarrow.compute as pc, pyarrow as pa
    cols = ['latitude', 'longitude', 'season', 'doy', 'Division', 'type', 'daynight', 'frp']
    for name in (div, {'Obedullahganj': 'Obedullahganj (Ratapani)'}.get(div, div), div.replace('_', ' ')):   # 20 Oct: the VIIRS table names Ratapani 'Obedullahganj'
        t = pq.read_table(VIIRS, columns=cols, filters=[('Division', '=', name), ('season', '=', year), ('type', '=', 0)])
        if t.num_rows: break
    return t.to_pandas()


def rc(L, lat, lon):
    x, y = TF.transform(lon, lat)
    return np.floor((L['y1'] - y) / RES).astype(int), np.floor((x - L['x0']) / RES).astype(int)
