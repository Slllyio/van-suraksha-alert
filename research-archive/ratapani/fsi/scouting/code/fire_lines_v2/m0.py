"""Round r28: fire lines, serious redesign. Shared settings.
Reuses round-27 code (code/compartments/k0.py, k1_cuts.py) and round-26 fires/patches (scratch r26).
Variants tested, all with the k0 scoring rule (fire spreads again from its start inside its own outline; each line crossing stopped
with chance p; saved = 1 - (1-p)^k):
  patch sets  tr3 = cells burnt in >= 3 of 5 seasons 2017-21 (round 26), tr2 = >= 2 of 5 (new, larger candidate set)
  objectives  sum = mean over train years of patch forest saved (round 27);  med = median year;  lo = mean after dropping the best year
  stop chance p = 0.35 (round-25 value from 'road within 40 m' odds), 0.70 (OSM roads / railway / big streams, spread thread 4m), 1.0
Big intermediates in scratch r28 only."""
import sys, os
import numpy as np
sys.path.insert(0, '/mnt/project-files/ratapani/fsi/scouting/code/compartments/')
import k0 as K          # noqa: E402
SCR = K.SCR; SC = SCR + 'r28/'; SC26 = K.SC26; SC27 = K.SC
HERE = '/mnt/project-files/ratapani/fsi/scouting/code/fire_lines_v2/'
OUT = HERE + 'out/'
FIG = '/mnt/project-files/ratapani/fsi/scouting/figs_r28/'
for d in (SC, OUT, FIG): os.makedirs(d, exist_ok=True)
TRAIN, TEST, ALL = K.TRAIN, K.TEST, K.ALL
PS = (0.35, 0.70, 1.0)
OBJS = ('sum', 'med', 'lo')
PSETS = ('tr3', 'tr2')
BUDGETS = (100, 250, 500, 1000, 2000, 5000)
CELL_HA = K.CELL_HA; RES = K.RES; AGG = K.AGG
MIN_PATCH_HA = 10.0


def objective(sy, obj):
    """sy: per-train-year patch-forest ha saved (len 5)."""
    if obj == 'sum': return float(sy.mean())
    if obj == 'med': return float(np.median(sy))
    if obj == 'lo': return float((sy.sum() - sy.max()) / (len(sy) - 1))
    raise ValueError(obj)


def labels(Z, pset, H, W):
    """patch labels on the 60 m lattice. tr3 from round 26; tr2 built here (>= 2 of 5 seasons, 8-connected, >= 10 forest ha)."""
    from scipy import ndimage as ndi
    if pset in ('tr3', 'all5'):
        lab = Z['lab_' + pset]
    else:
        cnt = Z['cnt_tr']; fb = Z['fb']
        lab, n = ndi.label(cnt >= 2, structure=np.ones((3, 3), bool))
        if n:
            area = ndi.sum(fb, lab, np.arange(1, n + 1)) * CELL_HA
            keep = np.r_[False, area >= MIN_PATCH_HA]
            ren = np.zeros(n + 1, np.int32); ren[keep] = np.arange(1, keep.sum() + 1); lab = ren[lab]
    return np.kron(lab.astype(np.int32), np.ones((AGG, AGG), np.int32))[:H, :W]
