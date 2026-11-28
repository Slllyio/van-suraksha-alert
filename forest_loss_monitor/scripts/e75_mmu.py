"""Cost of a 0.5 ha minimum on the old map at the Guna reference, area-weighted, by the patch at each point. Usage: e75_mmu.py"""
import numpy as np
import pandas as pd
from scipy import ndimage

from common import *
from e23_guna_labels import wpr
from e49_ts import guna_ref
from e48_tests import GT

g = pd.read_csv(GT / "guna_labels.csv").assign(pid=lambda d: d.gid + 500000)
r = guna_ref(set(g.pid))
t = pd.read_csv(WORK / "tiles.csv", keep_default_na=False)
ha = {}
for z in r.itertuples():
    s = t[(t.x0 <= z.x) & (t.x0 + t.w * RES > z.x) & (t.y1 >= z.y) & (t.y1 - t.h * RES < z.y)]
    if s.empty:
        continue
    s = s.iloc[0]
    rw, c = int((s.y1 - z.y) // 10), int((z.x - s.x0) // 10)
    p = WORK / "map10m" / f"{s.tile}_{rw // 900 * 900:05d}_{c // 900 * 900:05d}.npz"
    if not p.exists():
        continue
    lab, _ = ndimage.label(np.load(p)["cls"] > 0, structure=np.ones((3, 3), bool))
    rr, cc = rw % 900, c % 900
    b = lab[max(rr - 2, 0):rr + 3, max(cc - 2, 0):cc + 3]
    ids = np.unique(b[b > 0])
    ha[z.pid] = np.bincount(lab.ravel())[ids].max() * .01 if len(ids) else 0.0
d = r[r.pid.isin(ha)].assign(ha=lambda q: q.pid.map(ha))
for mn in (0, .1, .25, .5, 1):
    f = (d.ha >= mn) & (d.ha > 0)
    a, b = wpr(d.label.values, f.astype(int).values, d._w.values)
    print("min", mn, "flagged", int(f.sum()), "real", int((f & (d.label == 1)).sum()), "false", int((f & (d.label == 0)).sum()), "P", round(a, 3), "R", round(b, 3))
