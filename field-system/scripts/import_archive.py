"""Load past FIRMS points (CSV or parquet with FIRMS columns): history for persistent heat and the near-recent hints.
It opens no field tasks, and commits every 500 points so a running server stays responsive.

  python scripts/import_archive.py ../ratapani/viirs_snpp_2013_2024.parquet --since 2024-01-01
"""
import argparse, sys
from pathlib import Path
import pandas as pd
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app import db, firms
from app.geo import Beats

ap = argparse.ArgumentParser()
ap.add_argument("path")
ap.add_argument("--since")
ap.add_argument("--until")
a = ap.parse_args()
df = pd.read_parquet(a.path) if a.path.endswith(".parquet") else pd.read_csv(a.path)
df["acq_date"] = pd.to_datetime(df["acq_date"]).dt.strftime("%Y-%m-%d")
df = df[df["acq_time"].notna() & df["satellite"].notna()]   # Earth Engine (NRT-EE) rows carry no time or satellite
if a.since:
    df = df[df.acq_date >= a.since]
if a.until:
    df = df[df.acq_date <= a.until]
db.init()
rows, bad = [], 0
for r in df.to_dict("records"):
    inst = "MODIS" if str(r.get("instrument", "")).upper().startswith("MODIS") or "brightness" in r else "VIIRS"
    try:
        rows.append(firms.normalise(r, f"archive_{inst}", inst))
    except (KeyError, ValueError, TypeError):
        bad += 1
rows.sort(key=lambda d: d["acq_utc"])
B, new = Beats(), 0
for i in range(0, len(rows), 500):
    new += firms.store(rows[i:i + 500], B, "archive:" + Path(a.path).name, tasks=False)[0]
print("new detections:", new, "| rows skipped (bad time or position):", bad)
