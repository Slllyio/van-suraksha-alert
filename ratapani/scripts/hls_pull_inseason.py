"""In-season variant: Jan-Apr monthly composites of season Y -> hls/inseason_<Y>.npy (4,6,H,W).
Based on: Pre-season HLS composites for Prithvi: for fire season Y, monthly medians of Oct, Nov, Dec of Y-1 (no in-season
information, so no burn-scar leakage). HLSL30 + HLSS30 merged, Fmask cloud/adjacent/shadow removed.
Bands (Prithvi order): blue, green, red, nir(narrow), swir1, swir2, as reflectance*10000 int16, nodata = -9999.
Output: ratapani/hls/season_<Y>.npy, shape (3 frames, 6 bands, H, W) on a 30 m EPSG:32643 grid + grid.json."""
import json, time
from pathlib import Path
import numpy as np
import geopandas as gpd
import ee

ee.Initialize(project="van-suraksha-alert")
R = Path(r"E:\FIRE\ratapani"); OUT = R / "hls"; OUT.mkdir(exist_ok=True)
aoi = gpd.read_file(R / "ratapani_aoi.geojson").to_crs(32643)
x0, y0, x1, y1 = aoi.buffer(1000).total_bounds
x0, y1 = np.floor(x0 / 30) * 30, np.ceil(y1 / 30) * 30
W, H = int(np.ceil((x1 - x0) / 30)), int(np.ceil((y1 - y0) / 30))
_ = (OUT / "grid.json").exists() or (OUT / "grid.json").write_text(json.dumps(dict(crs="EPSG:32643", x0=x0, y1=y1, res=30, W=W, H=H)))
print("grid", W, "x", H)
region = ee.Geometry.Rectangle([float(v) for v in aoi.to_crs(4326).buffer(0.02).total_bounds])
NAMES = ["blue", "green", "red", "nir", "swir1", "swir2"]


def clean(img):
    fm = img.select("Fmask")
    bad = fm.bitwiseAnd(0b1110).neq(0)  # bit1 cloud, bit2 adjacent, bit3 shadow
    return img.updateMask(bad.Not())


def month(y, m):
    s, e = ee.Date.fromYMD(y, m, 1), ee.Date.fromYMD(y, m, 1).advance(1, "month")
    l = ee.ImageCollection("NASA/HLS/HLSL30/v002").filterDate(s, e).filterBounds(region).map(clean) \
        .select(["B2", "B3", "B4", "B5", "B6", "B7"], NAMES)
    s2 = ee.ImageCollection("NASA/HLS/HLSS30/v002").filterDate(s, e).filterBounds(region).map(clean) \
        .select(["B2", "B3", "B4", "B8A", "B11", "B12"], NAMES)
    return l.merge(s2).median()


T = 512
for Y in range(2014, 2025):
    f = OUT / f"inseason_{Y}.npy"
    if f.exists():
        continue
    img = ee.Image.cat([month(Y, m) for m in (1, 2, 3, 4)]).multiply(10000).round().unmask(-9999).toInt16()
    arr = np.full((24, H, W), -9999, np.int16)
    t0 = time.time()
    for r0 in range(0, H, T):
        for c0 in range(0, W, T):
            h, w = min(T, H - r0), min(T, W - c0)
            for k in range(4):
                try:
                    a = ee.data.computePixels({"expression": img, "fileFormat": "NUMPY_NDARRAY",
                                               "grid": {"dimensions": {"width": w, "height": h},
                                                        "affineTransform": {"scaleX": 30, "shearX": 0, "translateX": x0 + c0 * 30,
                                                                            "shearY": 0, "scaleY": -30, "translateY": y1 - r0 * 30},
                                                        "crsCode": "EPSG:32643"}})
                    break
                except ee.EEException as e:
                    if k == 3: raise
                    print("retry", e); time.sleep(5 * 2 ** k)
            arr[:, r0:r0 + h, c0:c0 + w] = np.stack([a[n] for n in a.dtype.names])
    arr = arr.reshape(4, 6, H, W)
    np.save(f, arr)
    valid = (arr[:, 0] != -9999).mean(axis=(1, 2))
    print(Y, f"{time.time() - t0:.0f}s", "valid frac Jan-Apr:", valid.round(3),
          "median red/nir:", np.median(arr[1, 2][arr[1, 2] > -9999]), np.median(arr[1, 3][arr[1, 3] > -9999]), flush=True)
