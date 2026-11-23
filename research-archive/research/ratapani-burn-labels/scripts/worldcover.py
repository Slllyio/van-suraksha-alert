"""ESA WorldCover 2021 on the 20 m AOI grid (AOI pixels only) -> worldcover.npy. Usage: python worldcover.py <out.npy>"""
import sys
import numpy as np, pystac_client, planetary_computer as pc
from rasterio.enums import Resampling
import fetch

cat = pystac_client.Client.open("https://planetarycomputer.microsoft.com/api/stac/v1")
its = list(cat.search(collections=["esa-worldcover"], bbox=[77.33, 22.81, 78.07, 23.11]).items())
its = [i for i in its if "2021" in i.id] or its
full = np.zeros((fetch.H, fetch.W), np.uint8)
for it in its:
    a = fetch.read(pc.sign(it).assets["map"].href, Resampling.nearest)
    full = np.where((full == 0) & (a > 0), a, full)
np.save(sys.argv[1], full[fetch.INSIDE])
print({int(k): int(v) for k, v in zip(*np.unique(full[fetch.INSIDE], return_counts=True))})
