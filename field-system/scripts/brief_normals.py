# Normal for the date, per division, for the officials' daily brief: average S-NPP VIIRS dots a day inside the division's
# beats, 2014-2025 (one satellite, so every year is counted the same way), smoothed over 15 days around each day of year.
#   python scripts/brief_normals.py  ->  data/brief/normal_snpp.json
import json, sys
from pathlib import Path
import numpy as np, pandas as pd
from shapely import points
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.geo import Beats
B = Beats()
A = Path("/mnt/project-files/fire-alert-scars/alerts_mp")
YEARS = range(2014, 2026)
div_of = np.array([p.get("division") or "" for p in B.props])
divs = sorted(set(div_of) - {""})
ix = {d: i for i, d in enumerate(divs)}
C = np.zeros((len(divs), 366))
for y in YEARS:
    df = pd.read_csv(A / f"viirs-snpp_{y}.csv", usecols=["latitude", "longitude", "acq_date"])
    pi, gi = B.tree.query(points(df.longitude.values, df.latitude.values), predicate="intersects")
    pi, first = np.unique(pi, return_index=True)          # a dot on a shared edge counts once
    d = div_of[gi[first]]
    doy = pd.to_datetime(df.acq_date.values[pi]).dayofyear.values - 1
    for dv, dd in zip(d, doy):
        if dv:
            C[ix[dv], dd] += 1
    print(y, len(df), len(pi), flush=True)
C /= len(YEARS)
k = np.ones(15) / 15
S = np.array([np.convolve(np.r_[c[-7:], c, c[:7]], k, "valid") for c in C])
out = {"source": "S-NPP VIIRS dots inside beats, 2014-2025 average per day, 15-day smoothing", "years": [YEARS[0], YEARS[-1]],
       "daily": {d: [round(float(v), 3) for v in S[ix[d]]] for d in divs}}
json.dump(out, open(Path(__file__).resolve().parent.parent / "data/brief/normal_snpp.json", "w"))
print("divisions", len(divs))
