"""Reproject beats, fetch districts, define the 90 km tile grid, rasterise zones to the 30 m grid."""
import json
import urllib.request

import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio
from rasterio.features import rasterize
from rasterio.transform import from_origin
from shapely import make_valid

from common import *

WORK.mkdir(exist_ok=True)
OUT.mkdir(exist_ok=True)
b = gpd.read_file(SHP)
b["geometry"] = b.geometry.map(make_valid)
b = b[~b.geometry.is_empty].reset_index(drop=True)
assert b.Division.notna().all()
b = b.to_crs(PROJ4)
b["zone_id"] = np.arange(1, len(b) + 1)
b["beat_ha"] = b.geometry.area / 1e4
for c in ("Division", "Range", "Beat"):
    b[c] = b[c].astype(str).str.strip()
b.to_parquet(WORK / "beats_albers.parquet")
b.drop(columns="geometry").to_csv(OUT / "beat_lookup.csv", index=False)

d = WORK / "districts.geojson"
if not d.exists():
    urllib.request.urlretrieve(DISTRICT_URL, d)
dist = gpd.read_file(d)
dist["geometry"] = dist.geometry.map(make_valid)
dist = dist.to_crs(PROJ4).reset_index(drop=True)
dist["dist_id"] = np.arange(1, len(dist) + 1)
dist.to_parquet(WORK / "districts_albers.parquet")

x0, y0, x1, y1 = b.total_bounds
x0, y0 = np.floor(x0 / RES) * RES - RES, np.floor(y0 / RES) * RES - RES
x1, y1 = np.ceil(x1 / RES) * RES + RES, np.ceil(y1 / RES) * RES + RES
W, H = int((x1 - x0) / RES), int((y1 - y0) / RES)
tr = from_origin(x0, y1, RES, RES)
json.dump(dict(x0=x0, y1=y1, width=W, height=H), open(WORK / "grid.json", "w"))
print("grid", W, H, W * H / 1e6, "Mpx; beats", len(b), "area Mha", b.beat_ha.sum() / 1e6)

prof = dict(driver="GTiff", width=W, height=H, count=1, crs=PROJ4, transform=tr, compress="deflate",
            tiled=True, blockxsize=512, blockysize=512, predictor=2, BIGTIFF="YES")
z = rasterize(zip(b.geometry, b.zone_id), out_shape=(H, W), transform=tr, fill=0, dtype="uint16")
with rasterio.open(WORK / "zone_beat.tif", "w", dtype="uint16", nodata=0, **prof) as o:
    o.write(z, 1)
print("rasterised forest Mha", (z > 0).sum() * PX_HA / 1e6, "(beat overlaps resolve to the later beat)")
zd = rasterize(zip(dist.geometry, dist.dist_id), out_shape=(H, W), transform=tr, fill=0, dtype="uint8")
with rasterio.open(WORK / "zone_district.tif", "w", dtype="uint8", nodata=0, **prof) as o:
    o.write(zd, 1)
print("forest ha with no district", ((z > 0) & (zd == 0)).sum() * PX_HA, "; districts", len(dist), dist.columns.tolist()[:8])

# Tile grid: only tiles holding forest pixels exist
rows = []
for r in range(0, H, TILE_PX):
    for c in range(0, W, TILE_PX):
        n = int((z[r:r + TILE_PX, c:c + TILE_PX] > 0).sum())
        if n:
            rows.append(dict(tile=f"r{r // TILE_PX:02d}c{c // TILE_PX:02d}", col=c, row=r, x0=x0 + c * RES, y1=y1 - r * RES,
                             w=min(TILE_PX, W - c), h=min(TILE_PX, H - r), forest_px=n))
t = pd.DataFrame(rows)
# Calibration tiles: the one holding the most forest of each named division
t["cal"] = ""
for name in ("Lamta_Proj_N_Balaghat", "Guna", "Sheopur", "Singrauli"):
    m = np.isin(z, b.loc[b.Division == name, "zone_id"].values)
    n = [int(m[s.row:s.row + s.h, s.col:s.col + s.w].sum()) for s in t.itertuples()]
    best = int(np.argmax(n))
    t.loc[best, "cal"] = (t.loc[best, "cal"] + " " + name).strip()
    print(name, t.loc[best, "tile"], n[best] * PX_HA, "ha")
t.to_csv(WORK / "tiles.csv", index=False)
print(len(t), "tiles; forest", t.forest_px.sum() * PX_HA / 1e6, "Mha")
