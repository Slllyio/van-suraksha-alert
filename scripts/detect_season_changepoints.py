"""ruptures PELT change-point detection for fire-season onset.

For each year, detect the first change-point in the Feb-May daily FRP series —
this is the data-driven fire-season onset date. Compare current year's onset
to the 5-year median to classify as EARLY / ON_TIME / LATE.

Output:
  outputs/dashboard_feed/season_onset.json
"""
from __future__ import annotations

import json
import logging
import sys
import warnings
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")
sys.stdout.reconfigure(line_buffering=True)
logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger()

ROOT = Path(__file__).resolve().parents[1]
FIRMS = ROOT / "data_lake" / "fire_detections" / "firms_mp_viirs" / "firms_mp_consolidated.parquet"
OUT = ROOT / "outputs" / "dashboard_feed" / "season_onset.json"

SEASON_WINDOW_START = (1, 15)   # (month, day) — Jan 15
SEASON_WINDOW_END = (6, 15)     # Jun 15
PELT_PENALTY = 8.0              # higher = fewer change-points
MIN_SEGMENT_SIZE = 7            # smallest segment in days


def detect_onset(daily_frp: pd.Series, year: int) -> dict | None:
    """Run PELT on one year's daily FRP series. First change-point = onset."""
    import ruptures as rpt

    start = pd.Timestamp(year, *SEASON_WINDOW_START)
    end = pd.Timestamp(year, *SEASON_WINDOW_END)
    year_series = daily_frp[(daily_frp.index >= start) & (daily_frp.index <= end)]
    if len(year_series) < 30:
        return None

    # Log-transform to stabilise variance
    signal = np.log1p(year_series.to_numpy()).reshape(-1, 1)
    algo = rpt.Pelt(model="rbf", min_size=MIN_SEGMENT_SIZE).fit(signal)
    try:
        bkps = algo.predict(pen=PELT_PENALTY)
    except Exception:
        return None
    # bkps is list of indices (last entry = len(signal))
    if len(bkps) <= 1:
        return None
    first_bkp = int(bkps[0])
    onset_date = year_series.index[first_bkp]

    # Onset confidence = log-mean AFTER onset / BEFORE onset
    before = year_series.iloc[:first_bkp]
    after = year_series.iloc[first_bkp:]
    conf = float(np.log1p(after.mean()) - np.log1p(max(before.mean(), 1)))

    return {
        "year": year,
        "onset_date": onset_date.strftime("%Y-%m-%d"),
        "onset_doy": int(onset_date.dayofyear),
        "n_change_points": len(bkps) - 1,
        "confidence": conf,
        "frp_mean_before": float(before.mean()),
        "frp_mean_after": float(after.mean()),
    }


def main() -> int:
    if not FIRMS.exists():
        log.error("FIRMS missing: %s", FIRMS); return 1

    log.info("Loading FIRMS daily...")
    f = pd.read_parquet(FIRMS, columns=["acq_date", "frp", "confidence"])
    f["acq_date"] = pd.to_datetime(f["acq_date"])
    f = f[f["confidence"].isin(["n", "h", "nominal", "high"])]
    daily = f.groupby("acq_date")["frp"].sum()
    full_range = pd.date_range(daily.index.min(), daily.index.max(), freq="D")
    daily = daily.reindex(full_range, fill_value=0)
    log.info("  %d days (%s to %s)", len(daily),
             daily.index.min().date(), daily.index.max().date())

    years = sorted(set(daily.index.year))
    records = []
    for y in years:
        r = detect_onset(daily, y)
        if r:
            records.append(r)

    df = pd.DataFrame(records).sort_values("year")
    log.info("\nDetected season onsets:")
    log.info(df[["year", "onset_date", "onset_doy", "confidence"]].to_string(index=False))

    # 5-year median onset DOY (excluding current year if it's partial)
    current_year = max(years)
    historical = df[df["year"] < current_year].tail(5)
    if len(historical) >= 3:
        median_doy = int(historical["onset_doy"].median())
        median_date = (pd.Timestamp(current_year, 1, 1)
                       + pd.Timedelta(days=median_doy - 1)).strftime("%Y-%m-%d")
    else:
        median_doy = None
        median_date = None

    # Classify current year
    current = df[df["year"] == current_year]
    classification = "UNKNOWN"
    days_diff = None
    current_onset = None
    if len(current) and median_doy is not None:
        current_onset_doy = int(current["onset_doy"].iloc[0])
        current_onset = str(current["onset_date"].iloc[0])
        days_diff = current_onset_doy - median_doy
        if days_diff <= -7:
            classification = "EARLY"
        elif days_diff >= 7:
            classification = "LATE"
        else:
            classification = "ON_TIME"
        log.info("\n%d season onset: %s (DOY %d)",
                 current_year, current_onset, current_onset_doy)
        log.info("5-year median: DOY %d (%s)", median_doy, median_date)
        log.info("Classification: %s (%+d days vs median)", classification, days_diff)

    payload = {
        "generated_at": datetime.utcnow().isoformat(),
        "method": "ruptures PELT change-point (RBF kernel)",
        "penalty": PELT_PENALTY,
        "per_year": df.to_dict(orient="records"),
        "current_year": current_year,
        "current_year_onset": current_onset,
        "historical_median_doy": median_doy,
        "historical_median_date": median_date,
        "days_vs_median": days_diff,
        "classification": classification,
    }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2, default=str))
    log.info("Wrote: %s", OUT.relative_to(ROOT))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
