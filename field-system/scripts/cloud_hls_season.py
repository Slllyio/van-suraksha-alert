"""Statewide HLS dryness steps from the cloud (app/cloud_hls.step_fast) into an npz in the PC's mp_dry_<season>.npz layout
(cells, steps, X int16 [steps, cells, 4]: ndvi/ndmi/nbr x1e4, clear %; -32768 = none). Steps not listed are left -32768.
Usage: python cloud_hls_season.py <ref_npz> <out_npz> <step> [<step> ...]   (each step ~6.5 min statewide, 4 cores)"""
import sys, time
from pathlib import Path
import numpy as np
import pandas as pd
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app import cloud_hls as H

ref, out, want = sys.argv[1], Path(sys.argv[2]), [pd.Timestamp(s) for s in sys.argv[3:]]
z = np.load(ref); cells, steps = z["cells"], z["steps"]
X = np.load(out)["X"] if out.exists() else np.full((len(steps), len(cells), 4), -32768, np.int16)
part = out.with_suffix(".part.npy")
for d in want:
    k = int(np.flatnonzero(pd.to_datetime([str(s) for s in steps]) == d)[0])
    if (X[k, :, 3] != -32768).any():
        continue
    t = time.time(); o = H.step_fast(cells, d)
    v = np.where(np.isfinite(o), np.round(o * np.array([1e4, 1e4, 1e4, 1], np.float32)), -32768).astype(np.int16)
    X[k] = v
    np.savez(out, cells=cells, steps=steps, X=X); print(d.date(), f"{time.time() - t:.0f}s", flush=True)
