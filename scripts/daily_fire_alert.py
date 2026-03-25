"""
Daily Fire Alert Pipeline — Van Suraksha / JwalaNetra
=====================================================
Runs once daily (recommended: 06:00 AM IST) to generate fire alerts.

Steps:
  1. Update FWI (NASA POWER API → fwi_daily.parquet)
  2. Fetch NRT FIRMS detections (last 24h)
  3. Run NRT alert pipeline → alert JSON + CSV
  4. Copy latest alert to dashboard feed

Usage:
  python scripts/daily_fire_alert.py
  python scripts/daily_fire_alert.py --date 2026-03-25    # specific date
  python scripts/daily_fire_alert.py --backfill 7         # last 7 days

Requirements:
  FIRMS_MAP_KEY in .env or environment variable
"""

import os
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PYTHON = sys.executable
LOG_DIR = ROOT / "logs"
LOG_DIR.mkdir(exist_ok=True)

# Load .env if present
_env_file = ROOT / ".env"
if _env_file.exists():
    for line in _env_file.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, val = line.partition("=")
            key, val = key.strip(), val.strip()
            if key and val and key not in os.environ:
                os.environ[key] = val


def run_step(name: str, cmd: list[str], timeout: int = 300) -> bool:
    """Run a pipeline step, return True on success."""
    print(f"\n{'='*60}")
    print(f"  STEP: {name}")
    print(f"{'='*60}")
    try:
        result = subprocess.run(
            cmd, cwd=str(ROOT), timeout=timeout,
            capture_output=False, text=True,
        )
        if result.returncode != 0:
            print(f"  WARN: {name} exited with code {result.returncode}")
            return False
        return True
    except subprocess.TimeoutExpired:
        print(f"  WARN: {name} timed out after {timeout}s")
        return False
    except Exception as e:
        print(f"  ERROR: {name} failed: {e}")
        return False


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Daily Fire Alert Pipeline")
    parser.add_argument("--date", help="Specific date (YYYY-MM-DD)")
    parser.add_argument("--backfill", type=int, help="Process last N days")
    args = parser.parse_args()

    started = datetime.now()
    log_file = LOG_DIR / f"daily_{started.strftime('%Y%m%d_%H%M')}.log"
    firms_key = os.environ.get("FIRMS_MAP_KEY", "")

    print(f"Van Suraksha Daily Fire Alert Pipeline")
    print(f"Started: {started.strftime('%Y-%m-%d %H:%M IST')}")
    print(f"FIRMS API Key: {'SET' if firms_key else 'MISSING'}")
    print(f"Log: {log_file}")

    # Step 1: Update FWI
    current_year = datetime.now().year
    run_step("Update FWI", [
        PYTHON, "scripts/compute_fwi.py",
        "--start", str(current_year - 1),
        "--end", str(current_year),
    ], timeout=120)

    # Step 2+3: Fetch NRT + Generate alerts
    alert_cmd = [PYTHON, "scripts/nrt_alert_pipeline.py"]

    if firms_key:
        alert_cmd.extend(["--fetch-nrt", "--api-key", firms_key])

    if args.date:
        alert_cmd.extend(["--date", args.date])
    elif args.backfill:
        alert_cmd.extend(["--days", str(args.backfill)])

    run_step("NRT Alert Pipeline", alert_cmd, timeout=180)

    # Step 4: Copy latest alert to dashboard feed
    feed_dir = ROOT / "outputs" / "dashboard_feed"
    feed_dir.mkdir(parents=True, exist_ok=True)
    alert_dir = ROOT / "data_lake" / "alerts"
    latest = alert_dir / "latest_alert.json"
    if latest.exists():
        import shutil
        dest = feed_dir / "latest_alert.json"
        shutil.copy2(latest, dest)
        print(f"\n  Dashboard feed updated: {dest}")

    elapsed = (datetime.now() - started).total_seconds()
    print(f"\n{'='*60}")
    print(f"  PIPELINE COMPLETE — {elapsed:.0f}s elapsed")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
