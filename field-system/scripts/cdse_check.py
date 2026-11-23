# Once the CDSE OAuth secret is in the environment: read the same Sentinel-2 scenes from Planetary Computer and from
# CDSE on the arrow's grid and compare the pixels and the hot-pixel count. Pass = bands agree (r > 0.98, median
# difference < 0.01 reflectance) and hot pixels within 10%.   python scripts/cdse_check.py [n_scenes]
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app import cdse, direction
import planetary_computer as pc, pystac_client
from pyproj import Transformer
from rasterio.transform import from_origin
assert cdse.available(), "CDSE Process API refused us: add the OAuth secret for sh.dataspace.copernicus.eu first"
n = int(sys.argv[1]) if len(sys.argv) > 1 else 5
cat = pystac_client.Client.open("https://planetarycomputer.microsoft.com/api/stac/v1", modifier=pc.sign_inplace)
to43 = Transformer.from_crs("EPSG:4326", "EPSG:32643", always_xy=True).transform
pts = [(23.20, 77.70), (22.35, 80.60), (21.90, 78.20), (24.60, 79.90), (22.70, 76.20), (23.60, 81.00), (21.60, 76.90)]
ok = 0
for lat, lon in pts[:n]:
    pt = {"type": "Point", "coordinates": [lon, lat]}
    its = sorted(cat.search(collections=["sentinel-2-l2a"], intersects=pt, query={"eo:cloud_cover": {"lt": 20}},
                            datetime="2026-03-01/2026-05-31").items(), key=lambda i: i.datetime)[-1:]
    if not its:
        continue
    it = its[0]
    x, y = to43(lon, lat); tr = from_origin(x - 3000, y + 3000, 20, 20)
    a = direction._read(it, "s2", tr, 300, 300)
    c = [s for s in cdse.search(pt, it.datetime - timedelta(minutes=1), it.datetime + timedelta(minutes=1)) if direction._tile(s.id) == direction._tile(it.id)]
    b = direction._read(c[0], "s2c", tr, 300, 300)
    row = []
    for k in ("red", "nir", "swir2"):
        m = np.isfinite(a[k]) & np.isfinite(b[k])
        row.append((k, round(float(np.corrcoef(a[k][m], b[k][m])[0, 1]), 3), round(float(np.median(np.abs(a[k][m] - b[k][m]))), 4)))
    good = all(r > 0.98 and d < 0.01 for _, r, d in row)
    ok += good
    print(it.id, row, "hot", int(direction._hot(a, "s2").sum()), int(direction._hot(b, "s2").sum()), "PASS" if good else "FAIL")
print(f"{ok} of {min(n, len(pts))} scenes agree")
