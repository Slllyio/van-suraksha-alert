"""Area-weighted 2-day list (round 24): shared paths. Reuses the round-22 system_rebuild code (common, features, evalr)
read-only; its scratch r22 holds det_all, static.npz, grids and the saved score cubes. Big intermediates of this round go to
scratch r24 only."""
import os, sys
P = '/mnt/project-files/'
SR = P + 'ratapani/fsi/scouting/code/system_rebuild/'
sys.path.insert(0, SR)
import common as C, features as Fe, evalr as E   # noqa: E402
S24 = '/tmp/claude-0/-home-user/be9b8f54-cc26-52cb-bdbb-9c8008a24baf/scratchpad/r24/'
CODE = P + 'ratapani/fsi/scouting/code/area_weighted/'
OUT = CODE + 'out/'
os.makedirs(S24, exist_ok=True); os.makedirs(OUT, exist_ok=True)
KEPT = 'C_static_newhead'          # round-22 kept model: B0 + static GIS + brand-new head
TEST = {'held': (2022, 2023, 2024), 'fwd': (2025,)}   # forward 2025 only: no scars for 2026 yet
TRAIN = {'held': (2019, 2020, 2021), 'fwd': (2019, 2020, 2021, 2022, 2023, 2024)}
BIG = 200.0
