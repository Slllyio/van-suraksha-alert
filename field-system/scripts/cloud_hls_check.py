# Cloud HLS dryness (app/cloud_hls.py, Planetary Computer) vs the PC's Earth Engine pull (mp_dry_<season>.npz) on one
# 128 x 128-cell tile and step.   python scripts/cloud_hls_check.py 2025 2025-03-21 6 5
import sys, time
from pathlib import Path
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app import cloud_hls as H
season, day, tr, tc = sys.argv[1], sys.argv[2], int(sys.argv[3]), int(sys.argv[4])
z = np.load(f"/mnt/project-files/ratapani/mp_grid/dryness/mp_dry_{season}.npz")
steps = [str(s) for s in z["steps"]]; print("steps", steps[:3], "...")
k = [i for i, s in enumerate(steps) if s.replace("-", "").endswith(day[5:].replace("-", ""))][0]
cells = z["cells"]; r, c = cells // 1829, cells % 1829
m = (r // 128 == tr) & (c // 128 == tc)
t = time.time(); got = H.step(cells[m], day); print("cells", m.sum(), f"{time.time() - t:.0f}s")
ref = z["X"][k, m].astype(np.float32); ref[ref == -9999] = np.nan; ref[:, :3] /= 1e4
for j, n in enumerate(["ndvi", "ndmi", "nbr", "clear"]):
    a, b = got[:, j], ref[:, j]
    ok = np.isfinite(a) & np.isfinite(b)
    print(n, "both", ok.sum(), "r", round(float(np.corrcoef(a[ok], b[ok])[0, 1]), 3), "median |diff|", round(float(np.median(np.abs(a[ok] - b[ok]))), 4),
          "ref mean", round(float(np.nanmean(b)), 3), "cloud mean", round(float(np.nanmean(a)), 3))
