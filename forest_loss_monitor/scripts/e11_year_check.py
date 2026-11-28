"""Is the 2023 spike real? Mean forest tree cover by year per zone, and where and how the 2023 detections fall."""
import numpy as np
import pandas as pd
import rasterio

from common import *
from zones import zone as zone_of

t = pd.read_csv(WORK / "tiles.csv", keep_default_na=False)
b = pd.read_csv(OUT / "beat_lookup.csv")
zn = b.set_index("zone_id").Division.map(zone_of)
with rasterio.open(WORK / "zone_beat.tif") as s:
    full = s.read(1)
c = np.load(WORK / "classified.npz")
yod, cls = c["yod"], c["cls"]
rows, zm = [], []
for s in t.itertuples():
    with rasterio.open(WORK / "emb_v2" / f"{s.tile}.tif") as src:
        names = list(src.descriptions)
        tr = src.read([i + 1 for i, n in enumerate(names) if n.startswith("tree")])
        zz = src.read([i + 1 for i, n in enumerate(names) if n.startswith("z")])
    z = full[s.row:s.row + s.h, s.col:s.col + s.w]
    m = z > 0
    y = yod[s.row:s.row + s.h, s.col:s.col + s.w]
    rows.append(dict(tile=s.tile, px=int(m.sum()), det2023=int((y == 2023).sum()), det_other=int(((y > 0) & (y != 2023)).sum()),
                     **{f"tree{yy}": float(tr[i][m].mean()) / 1e4 for i, yy in enumerate(range(2017, 2026))},
                     **{f"z{yy}": float(zz[i][m].mean()) / 1e3 for i, yy in enumerate(range(2018, 2026))},
                     **{f"zp99_{yy}": float(np.percentile(zz[i][m], 99)) / 1e3 for i, yy in enumerate(range(2018, 2026))}))
r = pd.DataFrame(rows)
w = r.px / r.px.sum()
print("state mean tree by year", {yy: round(float((r[f"tree{yy}"] * w).sum()), 3) for yy in range(2017, 2026)})
print("state mean z by year", {yy: round(float((r[f"z{yy}"] * w).sum()), 3) for yy in range(2018, 2026)})
print("mean p99 z by year", {yy: round(float((r[f"zp99_{yy}"] * w).sum()), 2) for yy in range(2018, 2026)})
print(r.assign(ha23=r.det2023 * PX_HA, ha_other=r.det_other * PX_HA).sort_values("ha23", ascending=False)[["tile", "ha23", "ha_other"]].head(12).round(0).to_string(index=False))
# Patch size of 2023 vs other years, and Hansen overlap
from scipy import ndimage
lab, n = ndimage.label((cls == 1) | (cls == 2), structure=np.ones((3, 3), bool))
print("patches", n)
for yy in range(2018, 2026):
    m = ((cls == 1) | (cls == 2)) & (yod == yy)
    a = np.bincount(lab[m])
    a = a[a > 0]
    print(yy, "ha", round(m.sum() * PX_HA), "patches", len(a), "median ha", round(np.median(a) * PX_HA, 1), "p90", round(np.percentile(a, 90) * PX_HA, 1), "hansen overlap", round((c["hansen"] & m).sum() * PX_HA), "burned share", round(float(c["burned"][m].mean()), 2))
