"""Repair stored scrub-to-farm sidecars: sampleRectangle returned each 300-row sub-tile south-to-north (verified against computePixels on r02c03_02700_02700: flipped arrays equal 100%).
Flips each row band back, recomputes the 50 m majority, marks the file (key 'flipfix') so it is never flipped twice. Usage: e100_s2f_flipfix.py"""
import numpy as np
from scipy import ndimage

from common import *
from e62_s2f_chunks import MIN_MAJ, OUTD, TILE

n = 0
for f in sorted(OUTD.glob("*.npz")):
    if f.name.endswith(".tmp.npz"):
        continue
    with np.load(f) as z:
        if "flipfix" in z.files:
            continue
        fl, yr = z["f"].copy(), z["y"].copy()
    for ro in range(0, fl.shape[0], TILE):
        fl[ro:ro + TILE], yr[ro:ro + TILE] = fl[ro:ro + TILE][::-1], yr[ro:ro + TILE][::-1]
    k = ndimage.uniform_filter(fl.astype("float32"), 5, mode="constant") * 25
    tmp = f.with_suffix(".tmp.npz")
    np.savez_compressed(tmp, f=fl, y=yr, maj=(np.rint(k) >= MIN_MAJ) & (fl > 0), flipfix=True)
    tmp.replace(f)
    n += 1
print("repaired", n)
