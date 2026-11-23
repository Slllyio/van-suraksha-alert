"""Shared paths and grid for the fire-line study (round r25).
Grid: EPSG:32643 (UTM 43N), 60 m cells aligned exactly to the VTM land-cover raster, cropped per landscape (one per division).
Coverage (coordinator note, 18 Oct): only complete scar sets are used -
  * 8 tiger-reserve divisions, all forest fire events 2017-25 (fire-alert-scars/mp/out tiger_reserve_scars.geojson, 12,586 events;
    drawn on 3 km chips before the v2 edge fix, so big single-day outlines can be cut at the chip edge);
  * Ratapani / Obedullahganj, scar outlines v2 (2026-10-16) FIRMS events 2017-25.
The rest-of-MP history (half built) is NOT used. Big intermediates go to scratch SC only."""
import os
import numpy as np
from pyproj import Transformer

P = '/mnt/project-files/'
SC = '/tmp/claude-0/-home-user/be9b8f54-cc26-52cb-bdbb-9c8008a24baf/scratchpad/r25/'
HERE = P + 'ratapani/fsi/scouting/code/fire_lines/'
OUT = HERE + 'out/'
VTM = SC + '../r14_types_data/vtm.tif'
DEM = SC + '../r19_pool/dem_mp.npz'
ROADS = SC + '../r15_firms_nd/roads_mp.parquet'
BEATS = P + 'ratapani/beats/mp_beats.geojson'
RES = 60.0
VX0, VY1 = -196215.0, 3932351.0   # VTM origin (top-left)
TF = Transformer.from_crs(4326, 32643, always_xy=True)
TB = Transformer.from_crs(32643, 4326, always_xy=True)
CELL_HA = RES * RES / 1e4
TRAIN = (2017, 2018, 2019, 2020, 2021)
TEST = (2022, 2023, 2024, 2025)
P_STOP = 0.35      # central chance a cleared line stops a front that reaches it (see f3 / plan for derivation)
P_RANGE = (0.20, 0.50)
os.makedirs(SC, exist_ok=True)
os.makedirs(OUT, exist_ok=True)


def snap_box(xmin, ymin, xmax, ymax):
    """Landscape window snapped to the VTM 60 m lattice: returns (x0, y1, ncols, nrows)."""
    c0 = int(np.floor((xmin - VX0) / RES)); c1 = int(np.ceil((xmax - VX0) / RES))
    r0 = int(np.floor((VY1 - ymax) / RES)); r1 = int(np.ceil((VY1 - ymin) / RES))
    return VX0 + c0 * RES, VY1 - r0 * RES, c1 - c0, r1 - r0


def slug(div):
    import re
    return re.sub(r'[^A-Za-z0-9]+', '_', div.split(' (')[0]).strip('_')


CORE = {'BTR', 'Kanha_Tiger_Reserve', 'Madhav_National_Park', 'Noradehi', 'Obedullahganj', 'PTR_MP', 'Panna_TR', 'SANJAY_DUBRI', 'Satpura_TR'}


def years(key):
    """Training (2017-21) and test (2022-25) seasons used for a division. Core divisions: all. Rest of MP: only seasons whose
    scar run is >= 95% finished (coverage_rest.csv), so a rerun on the finished history widens this automatically."""
    if key in CORE: return list(TRAIN), list(TEST)
    import pandas as pd
    cv = pd.read_csv(SC + 'coverage_rest.csv'); cv['k'] = cv.Division.map(slug)
    ok = set(cv[(cv.k == key) & (cv.share >= 0.95)].year)
    return [y for y in TRAIN if y in ok], [y for y in TEST if y in ok]
