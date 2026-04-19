"""Pull soil temperature + moisture features from Open-Meteo Archive API.

Adds 4 new daily features to the diagnostic stack:
  - soil_temp_0_to_7cm    — surface soil temperature
  - soil_temp_7_to_28cm   — deeper soil temperature (lagged thermal storage)
  - soil_moisture_0_to_7cm — surface soil moisture (ignition-readiness proxy)
  - soil_moisture_7_to_28cm — root-zone moisture (vegetation stress)

Matches MP centroid used by compute_fwi.py. Output column-compatible with
fwi_daily.parquet for easy join.

NOT used in v17 inference (model is frozen). Added as a SUPPLEMENTARY feature
parquet for next-version retraining + as a diagnostic overlay on the portal.
"""
from __future__ import annotations

import json
import logging
import sys
import time
import urllib.request
import warnings
from datetime import date, datetime
from pathlib import Path

import pandas as pd

warnings.filterwarnings("ignore")
sys.stdout.reconfigure(line_buffering=True)
logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger()

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data_lake" / "fire_weather" / "soil_daily.parquet"

# Match compute_fwi.py centroid
LAT = 24.38
LON = 77.15

ARCHIVE_URL = (
    "https://archive-api.open-meteo.com/v1/archive"
    "?latitude={lat}&longitude={lon}"
    "&start_date={start}&end_date={end}"
    "&hourly=soil_temperature_0_to_7cm,soil_temperature_7_to_28cm,"
    "soil_moisture_0_to_7cm,soil_moisture_7_to_28cm"
    "&timezone=UTC"
)

START_DATE = date(2020, 1, 1)
END_DATE = date.today()


def fetch_chunk(start: date, end: date) -> pd.DataFrame:
    """Pull soil hourly for a date range, aggregate to daily."""
    url = ARCHIVE_URL.format(lat=LAT, lon=LON, start=start, end=end)
    log.info("  GET %s..%s", start, end)
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "VanSuraksha/1.0"})
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read().decode())
    except Exception as e:
        log.error("  archive API failed: %s", e)
        return pd.DataFrame()

    h = data.get("hourly", {})
    times = h.get("time", [])
    if not times:
        log.warning("  empty hourly array")
        return pd.DataFrame()

    df = pd.DataFrame({
        "datetime": pd.to_datetime(times),
        "soil_temp_0_to_7cm": h.get("soil_temperature_0_to_7cm", []),
        "soil_temp_7_to_28cm": h.get("soil_temperature_7_to_28cm", []),
        "soil_moisture_0_to_7cm": h.get("soil_moisture_0_to_7cm", []),
        "soil_moisture_7_to_28cm": h.get("soil_moisture_7_to_28cm", []),
    })
    df["date"] = df["datetime"].dt.date
    daily = df.groupby("date").agg(
        soil_temp_0_to_7cm_mean=("soil_temp_0_to_7cm", "mean"),
        soil_temp_0_to_7cm_max=("soil_temp_0_to_7cm", "max"),
        soil_temp_7_to_28cm_mean=("soil_temp_7_to_28cm", "mean"),
        soil_moisture_0_to_7cm_mean=("soil_moisture_0_to_7cm", "mean"),
        soil_moisture_0_to_7cm_min=("soil_moisture_0_to_7cm", "min"),
        soil_moisture_7_to_28cm_mean=("soil_moisture_7_to_28cm", "mean"),
    ).reset_index()
    return daily


def main() -> int:
    log.info("Pulling soil features from Open-Meteo Archive %s -> %s",
             START_DATE, END_DATE)

    # Open-Meteo archive limits ~10 years per call; chunk by 2 years
    chunks = []
    cur = START_DATE
    while cur < END_DATE:
        nxt = date(min(cur.year + 2, END_DATE.year + 1), 1, 1)
        if nxt > END_DATE:
            nxt = END_DATE
        chunks.append((cur, nxt))
        cur = nxt + pd.Timedelta(days=1).to_pytimedelta()
    log.info("Will fetch in %d chunks", len(chunks))

    frames = []
    for s, e in chunks:
        df = fetch_chunk(s, e)
        if not df.empty:
            frames.append(df)
        time.sleep(1.0)  # be polite

    if not frames:
        log.error("No data fetched."); return 1
    soil = pd.concat(frames, ignore_index=True).drop_duplicates("date").sort_values("date")
    soil["date"] = pd.to_datetime(soil["date"])

    # Anomalies vs DOY climatology (from this dataset)
    soil["doy"] = soil["date"].dt.dayofyear
    clim = soil.groupby("doy")[["soil_temp_0_to_7cm_mean", "soil_moisture_0_to_7cm_mean"]].mean()
    clim.columns = ["soil_temp_climatology", "soil_moisture_climatology"]
    soil = soil.merge(clim, left_on="doy", right_index=True, how="left")
    soil["soil_temp_anomaly"] = soil["soil_temp_0_to_7cm_mean"] - soil["soil_temp_climatology"]
    soil["soil_moisture_anomaly"] = soil["soil_moisture_0_to_7cm_mean"] - soil["soil_moisture_climatology"]
    soil = soil.drop(columns=["doy"])

    OUT.parent.mkdir(parents=True, exist_ok=True)
    soil.to_parquet(OUT, index=False)
    log.info("Wrote %s (%d days, %s -> %s)",
             OUT.relative_to(ROOT), len(soil),
             soil["date"].min().date(), soil["date"].max().date())

    # Sanity print latest row
    latest = soil.tail(1).to_dict(orient="records")[0]
    log.info("Latest day: temp_0_7=%.1f°C  moist_0_7=%.3f m³/m³  temp_anom=%+.1f°C  moist_anom=%+.3f",
             latest["soil_temp_0_to_7cm_mean"], latest["soil_moisture_0_to_7cm_mean"],
             latest["soil_temp_anomaly"], latest["soil_moisture_anomaly"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
