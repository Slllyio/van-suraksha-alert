"""Top-layer soil moisture per division without Earth Engine (pc_models/CLOUD_PLAN.md). The live models use ERA5-Land
volumetric_soil_water_layer_1 (daily mean, division mean, value of 5 days before the issue day). ERA5-Land needs a
Copernicus key, so this reads ERA5 (ERA5T near-real-time, ~7 days behind) volumetric_soil_water_layer_1 from Google's
public ARCO-ERA5 Zarr (gs://gcp-public-data-arco-era5, no key): mean of 00/06/12/18 UTC, 0.25 deg cells weighted by
their share inside the division hull (app/cloud_gfs.weights). ERA5 and ERA5-Land differ; see the check in
pc_models/CLOUD_PLAN.md before relying on it."""
import urllib.error, urllib.request
import numpy as np
import pandas as pd

Z = "https://storage.googleapis.com/gcp-public-data-arco-era5/ar/full_37-1h-0p25deg-chunk-1.zarr-v3/volumetric_soil_water_layer_1"
LAT0, LAT1, LON0, LON1 = 20.0, 28.0, 73.0, 84.0


def _hour(t):
    import numcodecs
    i = int((pd.Timestamp(t) - pd.Timestamp("1900-01-01")) / pd.Timedelta(hours=1))
    for k in range(5):
        try:
            with urllib.request.urlopen(f"{Z}/{i}.0.0", timeout=120) as r:
                raw = r.read()
            break
        except urllib.error.HTTPError as e:
            if e.code == 404 or k == 4:                                  # not published yet (ERA5T ~6-7 days behind)
                raise
            import time; time.sleep(5 * (k + 1))
        except Exception:
            if k == 4:
                raise
            import time; time.sleep(5 * (k + 1))
    a = np.frombuffer(numcodecs.Blosc().decode(raw), "<f4").reshape(721, 1440)
    lat, lon = 90 - 0.25 * np.arange(721), 0.25 * np.arange(1440)
    return a[np.ix_((lat >= LAT0) & (lat <= LAT1), (lon >= LON0) & (lon <= LON1))]


def daily(day, W):
    """{division: daily mean swvl1} for UTC day `day`; W: {division: weights from cloud_gfs.weights}."""
    a = np.nanmean(np.stack([_hour(pd.Timestamp(day) + pd.Timedelta(hours=h)) for h in (0, 6, 12, 18)]), 0)
    return {dv: float(np.nansum(a * w) / w[np.isfinite(a)].sum()) for dv, w in W.items()}
