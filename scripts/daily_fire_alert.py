"""
Daily Fire Alert Pipeline — Van Suraksha / JwalaNetra
=====================================================
Runs once daily (recommended: 06:00 AM IST) to generate fire alerts.

Steps:
  1. Update FWI (NASA POWER API -> fwi_daily.parquet)
  2. Fetch NRT FIRMS detections (last 24h)
  3. Run NRT alert pipeline -> alert JSON + CSV
  4. Run PREDICTIVE model -> tomorrow's risk map (25ha grid)
  5. Merge detection + prediction into unified dashboard feed

Usage:
  python scripts/daily_fire_alert.py
  python scripts/daily_fire_alert.py --date 2026-03-25    # specific date
  python scripts/daily_fire_alert.py --backfill 7         # last 7 days
  python scripts/daily_fire_alert.py --skip-prediction    # skip slow prediction step

Requirements:
  FIRMS_MAP_KEY in .env or environment variable
"""

import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PYTHON = sys.executable
LOG_DIR = ROOT / "logs"
LOG_DIR.mkdir(exist_ok=True)
FEED_DIR = ROOT / "outputs" / "dashboard_feed"
FEED_DIR.mkdir(parents=True, exist_ok=True)

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


def build_unified_feed(target_date: str):
    """Merge detection alerts + prediction risk map into unified GeoJSON feed."""
    import csv

    features = []

    # 1. Detection alerts (from NRT pipeline)
    alert_file = ROOT / "data_lake" / "alerts" / "latest_alert.json"
    if alert_file.exists():
        try:
            alert_data = json.loads(alert_file.read_text())
            det_features = alert_data.get("features", [])
            for f in det_features:
                f["properties"]["source"] = "FIRMS_DETECTION"
                f["properties"]["alert_type"] = "DETECTED"
            features.extend(det_features)
            print(f"  Detection alerts: {len(det_features)} features")
        except Exception as e:
            print(f"  WARN: Could not load detection alerts: {e}")

    # 2. Prediction risk map (from predictive model)
    risk_csv = ROOT / "outputs" / "predictive_fire_risk" / f"risk_map_{target_date}.csv"
    if risk_csv.exists():
        try:
            n_pred = 0
            with open(risk_csv, "r") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    risk_level = row.get("risk_level", "LOW")
                    if risk_level in ("MODERATE", "HIGH", "CRITICAL"):
                        features.append({
                            "type": "Feature",
                            "geometry": {
                                "type": "Point",
                                "coordinates": [float(row["lon"]), float(row["lat"])],
                            },
                            "properties": {
                                "cell_id": row["cell_id"],
                                "beat": row.get("beat", ""),
                                "range": row.get("range", ""),
                                "risk_score": round(float(row["risk_score"]), 4),
                                "risk_level": risk_level,
                                "source": "PREDICTIVE_MODEL",
                                "alert_type": "PREDICTED",
                                "prediction_date": target_date,
                            },
                        })
                        n_pred += 1
            print(f"  Prediction alerts: {n_pred} cells (MODERATE+)")
        except Exception as e:
            print(f"  WARN: Could not load prediction risk map: {e}")

    # Build unified GeoJSON
    geojson = {
        "type": "FeatureCollection",
        "metadata": {
            "generated": datetime.now().isoformat(),
            "target_date": target_date,
            "n_detections": sum(1 for f in features if f["properties"].get("source") == "FIRMS_DETECTION"),
            "n_predictions": sum(1 for f in features if f["properties"].get("source") == "PREDICTIVE_MODEL"),
        },
        "features": features,
    }

    out_path = FEED_DIR / "unified_alert.geojson"
    out_path.write_text(json.dumps(geojson, indent=2))
    print(f"  Unified feed: {out_path} ({len(features)} total features)")

    # Also copy detection-only feed for backward compat
    if alert_file.exists():
        shutil.copy2(alert_file, FEED_DIR / "latest_alert.json")

    return geojson


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Daily Fire Alert Pipeline")
    parser.add_argument("--date", help="Specific date (YYYY-MM-DD)")
    parser.add_argument("--backfill", type=int, help="Process last N days")
    parser.add_argument("--skip-prediction", action="store_true",
                        help="Skip the predictive model step (faster)")
    args = parser.parse_args()

    started = datetime.now()
    log_file = LOG_DIR / f"daily_{started.strftime('%Y%m%d_%H%M')}.log"
    firms_key = os.environ.get("FIRMS_MAP_KEY", "")

    # Determine target date for prediction (tomorrow)
    if args.date:
        target_date = args.date
    else:
        target_date = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")

    print(f"Van Suraksha Daily Fire Alert Pipeline")
    print(f"Started: {started.strftime('%Y-%m-%d %H:%M IST')}")
    print(f"FIRMS API Key: {'SET' if firms_key else 'MISSING'}")
    print(f"Prediction target: {target_date}")
    print(f"Log: {log_file}")

    # Step 1: Update FWI
    current_year = datetime.now().year
    run_step("Update FWI", [
        PYTHON, "scripts/compute_fwi.py",
        "--start", str(current_year - 1),
        "--end", str(current_year),
    ], timeout=120)

    # Step 2+3: Fetch NRT + Generate detection alerts
    alert_cmd = [PYTHON, "scripts/nrt_alert_pipeline.py"]

    if firms_key:
        alert_cmd.extend(["--fetch-nrt", "--api-key", firms_key])

    if args.date:
        alert_cmd.extend(["--date", args.date])
    elif args.backfill:
        alert_cmd.extend(["--days", str(args.backfill)])

    run_step("NRT Alert Pipeline (Detection)", alert_cmd, timeout=180)

    # Step 4: Run predictive model for tomorrow's risk
    if not args.skip_prediction:
        model_path = ROOT / "outputs" / "predictive_fire_risk" / "predictive_v2_improved" / "model.lgbm"
        if model_path.exists():
            run_step("Predictive Risk Map (Tomorrow)", [
                PYTHON, "scripts/train_predictive_fire_risk.py",
                "--predict", target_date,
            ], timeout=300)
        else:
            print(f"\n  SKIP: Predictive model not found at {model_path}")
            print(f"  Train it first: python scripts/train_predictive_fire_risk.py --tag v2_improved")

    # Step 5: Build unified feed (detection + prediction)
    print(f"\n{'='*60}")
    print(f"  STEP: Build Unified Alert Feed")
    print(f"{'='*60}")
    build_unified_feed(target_date)

    elapsed = (datetime.now() - started).total_seconds()
    print(f"\n{'='*60}")
    print(f"  PIPELINE COMPLETE -- {elapsed:.0f}s elapsed")
    print(f"{'='*60}")
    print(f"\n  Outputs:")
    print(f"    Detection:  outputs/dashboard_feed/latest_alert.json")
    print(f"    Prediction: outputs/predictive_fire_risk/risk_map_{target_date}.csv")
    print(f"    Unified:    outputs/dashboard_feed/unified_alert.geojson")


if __name__ == "__main__":
    main()
