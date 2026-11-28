"""Area per test division, class and year from the 10 m chunks, clipped to the 30 m beat raster."""
import numpy as np
import pandas as pd
import rasterio

from common import *
from e33_map10m import D, TEST_DIVS

t = pd.read_csv(WORK / "tiles.csv", keep_default_na=False).set_index("tile")
b = pd.read_csv(OUT / "beat_lookup.csv")
with rasterio.open(WORK / "zone_beat.tif") as s:
    z = s.read(1)
div = np.zeros(int(b.zone_id.max()) + 1, "uint8")
for i, n in enumerate(TEST_DIVS):
    div[b[b.Division == n].zone_id.values] = i + 1
rows = []
for f in D.glob("*.npz"):
    tile, r, c = f.stem.split("_")
    r, c = int(r), int(c)
    s = t.loc[tile]
    a = np.load(f)
    h, w = a["cls"].shape
    zz = np.repeat(np.repeat(z[s.row + r // 3:s.row + (r + h) // 3, s.col + c // 3:s.col + (c + w) // 3], 3, 0), 3, 1)
    k = div[zz]
    i = np.nonzero((a["cls"] > 0) & (k > 0))
    if len(i[0]):
        rows.append(pd.DataFrame(dict(div=k[i], cls=a["cls"][i], yr=a["yr"][i])))
d = pd.concat(rows)
g = d.groupby(["div", "cls", "yr"]).size().rename("px").reset_index()
g["ha"] = g.px * 0.01
g["Division"] = g["div"].map(lambda i: TEST_DIVS[i - 1])
g["cls"] = g.cls.map({1: "clearing", 2: "tree_to_shrub", 3: "shrub_to_crop"})
forest = {n: float(np.isin(z, b[b.Division == n].zone_id.values).sum() * PX_HA) for n in TEST_DIVS}
p = g.pivot_table(index="Division", columns="cls", values="ha", aggfunc="sum", fill_value=0)
p["total"] = p.sum(axis=1)
p["forest_ha"] = p.index.map(forest)
p["pct"] = (100 * p.total / p.forest_ha).round(2)
print(p.round(0).to_string())
print(g.pivot_table(index="yr", columns="Division", values="ha", aggfunc="sum", fill_value=0).round(0).to_string())
g.to_csv(OUT / "tables" / "test_divisions_10m.csv", index=False)
