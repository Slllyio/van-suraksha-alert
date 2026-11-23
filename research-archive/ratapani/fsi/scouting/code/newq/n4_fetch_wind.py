"""Q4 input: ERA5 10 m wind over MP, 15 Feb - 15 Mar 2017-25, 06/09/12 UTC (11:30-17:30 IST, the spread hours), from Google's
public ARCO-ERA5 Zarr (same reader as field-system/app/cloud_soil.py, no key). Writes scratch era5wind/wind_<year>.npz with
u, v (day, hour, lat, lon) float32 on the 0.25 deg MP window lat 28..20, lon 73..84."""
import os, sys, urllib.request, numpy as np, numcodecs, pandas as pd
from concurrent.futures import ThreadPoolExecutor
Z = "https://storage.googleapis.com/gcp-public-data-arco-era5/ar/full_37-1h-0p25deg-chunk-1.zarr-v3"
OUT = sys.argv[1]; LAT0, LAT1, LON0, LON1 = 20.0, 28.0, 73.0, 84.0
lat, lon = 90 - 0.25 * np.arange(721), 0.25 * np.arange(1440); LI = (lat >= LAT0) & (lat <= LAT1); LJ = (lon >= LON0) & (lon <= LON1)
def chunk(var, t):
    i = int((t - pd.Timestamp("1900-01-01")) / pd.Timedelta(hours=1))
    for k in range(5):
        try:
            with urllib.request.urlopen(f"{Z}/{var}/{i}.0.0", timeout=120) as r: raw = r.read()
            break
        except Exception as e:
            if k == 4: raise
    a = np.frombuffer(numcodecs.Blosc().decode(raw), "<f4").reshape(721, 1440)
    return a[np.ix_(LI, LJ)]
HOURS = (6, 9, 12)
for y in range(2017, 2026):
    f = f"{OUT}/wind_{y}.npz"
    if os.path.exists(f): continue
    days = pd.date_range(f"{y}-02-15", f"{y}-03-15")
    times = [(d, h) for d in days for h in HOURS]
    with ThreadPoolExecutor(6) as ex:
        U = list(ex.map(lambda dh: chunk("10m_u_component_of_wind", dh[0] + pd.Timedelta(hours=dh[1])), times))
        V = list(ex.map(lambda dh: chunk("10m_v_component_of_wind", dh[0] + pd.Timedelta(hours=dh[1])), times))
    U = np.array(U).reshape(len(days), len(HOURS), LI.sum(), LJ.sum()); V = np.array(V).reshape(U.shape)
    np.savez_compressed(f, u=U, v=V, days=days.strftime("%Y-%m-%d").values, hours=np.array(HOURS), lat=lat[LI], lon=lon[LJ])
    print(y, U.shape, "mean speed", np.hypot(U, V).mean().round(2), flush=True)
print("done")
