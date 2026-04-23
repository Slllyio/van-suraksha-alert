"""Backfill v17.5 predictions + operational alerts for the 2026 fire season.

For every date D in the configured window where:
  - FWI (weather) is available, AND
  - `outputs/dashboard_feed/ignition_risk_v17_{D}.json` does not already exist

this script runs:
  1. predict_ignition_v17.py --date D --use-hurdle-blend --output <dated_json>
  2. build_operational_alerts.py --input-v17 <dated_json> --output-alerts <dated_ops_json> --output-briefings <dated_briefings_json>

The two dated JSON stashes are what `validate_2026_season.py` consumes.

HAWKES date-safety:
  `compute_hawkes_for_date(target_date, ign_df, ...)` at
  scripts/predict_ignition_v17.py:107 filters `ign_df` strictly
  `acq_date < target_date`. No future FIRMS leak.

Non-Hawkes feature staleness:
  Base features come from the most-recent row in the v8 dataset
  (2025-05-29) because the training pipeline was frozen there. This is
  how v17 runs in production today — the backfill reproduces production
  behaviour rather than idealising it.

Usage:
  python scripts/run_2026_backfill.py              # dry-run: list what would be done
  python scripts/run_2026_backfill.py --execute    # actually run
  python scripts/run_2026_backfill.py --execute --workers 4 --start 2026-02-16 --end 2026-04-22
"""
from __future__ import annotations

import argparse
import logging
import subprocess
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import date, datetime, timedelta
from pathlib import Path

import pandas as pd

sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)
logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger()

ROOT = Path(__file__).resolve().parents[1]
FEED_DIR = ROOT / "outputs" / "dashboard_feed"
FWI_PARQUET = ROOT / "data_lake" / "fire_weather" / "fwi_daily.parquet"

PYTHON = sys.executable


def available_weather_dates() -> set[date]:
    df = pd.read_parquet(FWI_PARQUET, columns=["date"])
    df["date"] = pd.to_datetime(df["date"]).dt.date
    return set(df["date"].unique())


def dated_predict_path(d: date) -> Path:
    return FEED_DIR / f"ignition_risk_v17_{d.strftime('%Y-%m-%d')}.json"


def dated_ops_path(d: date) -> Path:
    return FEED_DIR / f"operational_alerts_v17_{d.strftime('%Y-%m-%d')}.json"


def dated_briefings_path(d: date) -> Path:
    return FEED_DIR / f"division_briefings_{d.strftime('%Y-%m-%d')}.json"


def run_one(d_str: str) -> tuple[str, bool, str]:
    """Run the predict + ops-alerts pipeline for one date. Returns (date, ok, msg)."""
    d = datetime.strptime(d_str, "%Y-%m-%d").date()
    pred_json = dated_predict_path(d)
    ops_json = dated_ops_path(d)
    brf_json = dated_briefings_path(d)
    t0 = time.time()

    try:
        # Phase A: predict
        if not pred_json.exists():
            r = subprocess.run(
                [PYTHON, "scripts/predict_ignition_v17.py",
                 "--date", d_str, "--use-hurdle-blend",
                 "--use-live-weather", "--use-beat-history",
                 "--output", str(pred_json)],
                cwd=ROOT, capture_output=True, text=True, timeout=600,
            )
            if r.returncode != 0:
                return (d_str, False, f"predict FAILED: {r.stderr[-400:]}")

        # Phase B: ops alerts
        if not ops_json.exists():
            r = subprocess.run(
                [PYTHON, "scripts/build_operational_alerts.py",
                 "--input-v17", str(pred_json),
                 "--output-alerts", str(ops_json),
                 "--output-briefings", str(brf_json)],
                cwd=ROOT, capture_output=True, text=True, timeout=300,
            )
            if r.returncode != 0:
                return (d_str, False, f"ops FAILED: {r.stderr[-400:]}")

        elapsed = time.time() - t0
        return (d_str, True, f"ok in {elapsed:.1f}s")
    except subprocess.TimeoutExpired:
        return (d_str, False, "TIMEOUT")
    except Exception as e:
        return (d_str, False, f"EXCEPTION: {type(e).__name__}: {e}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default="2026-02-16",
                    help="First date inclusive (YYYY-MM-DD)")
    ap.add_argument("--end", default="2026-04-22",
                    help="Last date inclusive (YYYY-MM-DD)")
    ap.add_argument("--workers", type=int, default=4,
                    help="Parallel worker processes. Predict is CPU-bound; pick < physical cores.")
    ap.add_argument("--execute", action="store_true",
                    help="Actually run. Without this flag, only lists the work that would be done.")
    ap.add_argument("--force", action="store_true",
                    help="Re-run even if dated JSONs already exist.")
    args = ap.parse_args()

    start = datetime.strptime(args.start, "%Y-%m-%d").date()
    end = datetime.strptime(args.end, "%Y-%m-%d").date()
    window = [start + timedelta(days=i) for i in range((end - start).days + 1)]

    log.info("Window: %s -> %s (%d calendar days)", start, end, len(window))

    # Every date is eligible: predict_ignition_v17 reads weather features from
    # the FROZEN v8 dataset (2025-05-29), not from the live FWI parquet. The
    # FWI parquet only feeds the operational decoration's "extreme weather"
    # banner and load_weather_context() already falls back to the latest
    # pre-target date when an exact match is missing.
    weather_dates = available_weather_dates()
    eligible = list(window)
    no_wx_in_window = [d for d in window if d not in weather_dates]
    if no_wx_in_window:
        log.warning("FWI missing for %d days (will use most-recent prior FWI for ops banner): %s .. %s",
                    len(no_wx_in_window), no_wx_in_window[0], no_wx_in_window[-1])

    if args.force:
        todo = eligible
    else:
        todo = [d for d in eligible
                if not (dated_predict_path(d).exists() and dated_ops_path(d).exists())]
    already_done = [d for d in eligible
                    if dated_predict_path(d).exists() and dated_ops_path(d).exists()]
    log.info("Already done: %d days", len(already_done))
    log.info("To run: %d days", len(todo))

    if not args.execute:
        log.info("Dry-run. Pass --execute to actually run.")
        for d in todo[:10]:
            log.info("  would run: %s", d)
        if len(todo) > 10:
            log.info("  ... and %d more", len(todo) - 10)
        return 0

    if not todo:
        log.info("Nothing to do. Exiting.")
        return 0

    log.info("Starting %d-worker pool...", args.workers)
    n_ok = 0
    n_fail = 0
    t_start = time.time()
    with ProcessPoolExecutor(max_workers=args.workers) as ex:
        futures = {ex.submit(run_one, d.strftime("%Y-%m-%d")): d for d in todo}
        for i, fut in enumerate(as_completed(futures), 1):
            d_str, ok, msg = fut.result()
            if ok:
                n_ok += 1
                log.info("[%3d/%3d] PASS %s %s", i, len(todo), d_str, msg)
            else:
                n_fail += 1
                log.error("[%3d/%3d] FAIL %s %s", i, len(todo), d_str, msg)

    elapsed = time.time() - t_start
    log.info("=" * 60)
    log.info("Backfill done: %d PASS, %d FAIL (of %d) in %.1f min",
             n_ok, n_fail, len(todo), elapsed / 60)
    return 0 if n_fail == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
