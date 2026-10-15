"""Download VIIRS NOAA-20 / NOAA-21 standard-processing fire detections over MP from the FIRMS area API.
Key from the FIRMS_MAP_KEY environment variable (never stored). 5-day windows, Dec 1 .. May 31 of each fire season.
Output: E:/FIRE/mp/firms_noaa/<source>/<YYYY-MM-DD>.csv (raw) and firms_noaa_mp.parquet (consolidated)."""
import io, os, time
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import urllib.request
import pandas as pd

KEY = os.environ["FIRMS_MAP_KEY"]
OUT = Path(r"E:\FIRE\mp\firms_noaa")
BBOX = "74.0,21.0,82.9,26.9"  # west,south,east,north - all of MP
SOURCES = {"VIIRS_NOAA20_SP": pd.Timestamp("2018-04-01"), "VIIRS_NOAA21_SP": pd.Timestamp("2023-03-01")}
SEASONS = range(2018, 2025)


def windows(first):
    for y in SEASONS:
        d, end = pd.Timestamp(f"{y - 1}-12-01"), pd.Timestamp(f"{y}-05-31")
        while d <= end:
            if d >= first:
                yield d
            d += pd.Timedelta(days=5)


def fetch(src, d):
    f = OUT / src / f"{d.date()}.csv"
    if f.exists():
        return 0
    url = f"https://firms.modaps.eosdis.nasa.gov/api/area/csv/{KEY}/{src}/{BBOX}/5/{d.date()}"
    for k in range(5):
        try:
            txt = urllib.request.urlopen(url, timeout=120).read().decode()
            if not txt.startswith("latitude"):
                raise RuntimeError(txt[:120])
            f.write_text(txt)
            return txt.count("\n") - 1
        except Exception as e:
            if k == 4:
                print("FAILED", src, d.date(), str(e)[:120], flush=True); return -1
            time.sleep(10 * (k + 1))


jobs = []
for src, first in SOURCES.items():
    (OUT / src).mkdir(parents=True, exist_ok=True)
    jobs += [(src, d) for d in windows(first)]
print(len(jobs), "requests", flush=True)
with ThreadPoolExecutor(4) as ex:
    res = list(ex.map(lambda j: fetch(*j), jobs))
print("rows fetched this run:", sum(r for r in res if r > 0), "failed:", sum(r < 0 for r in res), flush=True)
frames = []
for src in SOURCES:
    for f in sorted((OUT / src).glob("*.csv")):
        x = pd.read_csv(f)
        if len(x):
            frames.append(x.assign(source=src))
allx = pd.concat(frames, ignore_index=True).drop_duplicates(["latitude", "longitude", "acq_date", "acq_time", "source"])
allx["acq_date"] = pd.to_datetime(allx.acq_date)
allx.to_parquet(OUT / "firms_noaa_mp.parquet", index=False)
print(allx.groupby(["source", allx.acq_date.dt.year]).size().to_string())
