"""ROUGH state-wide range from the 4 calibration tiles only (LandTrendr rule). Tiles were chosen, not random: not a final figure.
lt_v2 has no Dynamic World band, so the crop filter is off and precision is taken from the labels for that same rule."""
import json
import importlib

import numpy as np
import pandas as pd
import rasterio

from common import *
from zones import zone as zone_of

clf = importlib.import_module("05_classify")
th = json.load(open(ROOT / "scripts" / "thresholds.json"))
th["crop_max"] = 1e9
b = pd.read_csv(OUT / "beat_lookup.csv")
b["z"] = b.Division.map(zone_of)
zmap = np.zeros(int(b.zone_id.max()) + 1, "uint8")
ZN = sorted(b.z.unique())
zmap[b.zone_id.values] = b.z.map({n: i + 1 for i, n in enumerate(ZN)}).values
with rasterio.open(WORK / "zone_beat.tif") as s:
    full = s.read(1)
state_ha = {n: float((zmap[full] == i + 1).sum() * PX_HA) for i, n in enumerate(ZN)}
t = pd.read_csv(WORK / "tiles.csv", keep_default_na=False)
rows, tile_rows = [], []
for s in t[t.cal != ""].itertuples():
    with rasterio.open(WORK / "lt_v2" / f"{s.tile}.tif") as src:
        A = {n: src.read(i + 1) for i, n in enumerate(src.descriptions)}
    A["dw_crops"] = np.zeros_like(A["yod"])
    z = full[s.row:s.row + s.h, s.col:s.col + s.w]
    yod, cls, _ = clf.classify(A, z, th)
    zz = zmap[z]
    tile_rows.append(dict(tile=s.cal, forest_ha=(z > 0).sum() * PX_HA, core_ha=(cls == 1).sum() * PX_HA + (cls == 2).sum() * PX_HA, small_ha=(cls == 3).sum() * PX_HA))
    for i, n in enumerate(ZN):
        m = zz == i + 1
        row = dict(z=n, forest=m.sum() * PX_HA)
        for y in REPORT_YEARS:
            row[f"core_{y}"] = ((yod == y) & m & (cls < 3)).sum() * PX_HA
            row[f"small_{y}"] = ((yod == y) & m & (cls == 3)).sum() * PX_HA
        rows.append(row)
r = pd.DataFrame(rows).groupby("z").sum()
tr = pd.DataFrame(tile_rows)
tr["core_pct_10yr"] = (100 * tr.core_ha / tr.forest_ha).round(2)
print(tr.round(0).to_string(index=False), "\n", tr.core_pct_10yr.tolist())
print("zone forest in tiles / state:", {n: (round(r.forest.get(n, 0)), round(state_ha[n])) for n in ZN})
# zones missing from the 4 tiles borrow the pooled rate
pool = r.drop(columns="forest").sum() / r.forest.sum()
est = pd.Series(0.0, index=pool.index)
for n in ZN:
    rate = r.loc[n].drop("forest") / r.loc[n, "forest"] if n in r.index and r.loc[n, "forest"] > 20000 else pool
    est += rate * state_ha[n]
cases = dict(low=(0.40, 0.85), central=(0.51, 0.69), high=(0.65, 0.45))  # (precision, recall); central measured on the labels
out = pd.DataFrame({"year": REPORT_YEARS, "mapped_ha": [est[f"core_{y}"] for y in REPORT_YEARS], "small_ha": [est[f"small_{y}"] for y in REPORT_YEARS]})
for k, (p, c) in cases.items():
    out[k] = out.mapped_ha * p / c
print(out.round(0).to_string(index=False))
y18 = out[out.year >= 2018]
print("2018-2025", y18.drop(columns="year").sum().round(0).to_dict())
print("all", out.drop(columns="year").sum().round(0).to_dict(), "state forest", sum(state_ha.values()))
out.round(0).to_csv(OUT / "provisional_estimate.csv", index=False)
