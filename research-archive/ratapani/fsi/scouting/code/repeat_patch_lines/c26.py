"""Shared settings for round r26 (repeat-burn patches, entry direction, entry-side fire lines).
Reuses round-25 code (scouting/code/fire_lines/): event loading, fire chaining, start rule, 60 m VTM lattice, numba kernels.
Big intermediates in scratch r26 only."""
import sys, os
import numpy as np
FL = '/mnt/project-files/ratapani/fsi/scouting/code/fire_lines/'
sys.path.insert(0, FL)
import common as C25            # noqa: E402  (grid, paths, slug, CORE, TF/TB)
SC = '/tmp/claude-0/-home-user/be9b8f54-cc26-52cb-bdbb-9c8008a24baf/scratchpad/r26/'
SC25 = C25.SC
HERE = '/mnt/project-files/ratapani/fsi/scouting/code/repeat_patch_lines/'
OUT = HERE + 'out/'
RES = C25.RES; CELL_HA = C25.CELL_HA
TRAIN = (2017, 2018, 2019, 2020, 2021); TEST = (2022, 2023, 2024, 2025); ALL = TRAIN + TEST
P_STOP = 0.35
AGG = 2                         # repeat-burn grid = 2 x 2 VTM cells = 120 m
MIN_PATCH_HA = 10.0             # patches smaller than this are dropped
MIN_FIRE_IN_PATCH_HA = 1.0      # a fire 'burned into' a patch if it burned >= 1 ha of the patch's forest
SEG_KM = 1.0                    # edge segment length
os.makedirs(SC, exist_ok=True); os.makedirs(OUT, exist_ok=True)
CORE = C25.CORE; slug = C25.slug
