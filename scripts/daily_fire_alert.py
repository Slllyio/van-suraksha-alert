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
            # NRT pipeline stores fires in "fires" key (not GeoJSON "features")
            fires = alert_data.get("fires", [])
            for fire in fires:
                feat = {
                    "type": "Feature",
                    "geometry": {
                        "type": "Point",
                        "coordinates": [fire["fire_lon"], fire["fire_lat"]],
                    },
                    "properties": {
                        "severity": fire.get("severity", "LOW"),
                        "frp_mw": fire.get("frp_mw", 0),
                        "fire_date": fire.get("fire_date", target_date),
                        "fire_time_ist": fire.get("fire_time_ist", ""),
                        "land_cover": fire.get("land_cover", ""),
                        "in_forest": fire.get("in_forest"),
                        "fwi": alert_data.get("fwi", {}).get("value"),
                        "fwi_danger": alert_data.get("fwi", {}).get("danger_class"),
                        "message": fire.get("message", ""),
                        "source": "FIRMS_DETECTION",
                        "alert_type": "DETECTED",
                    },
                }
                features.append(feat)
            print(f"  Detection alerts: {len(fires)} fires from NRT pipeline")
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


def find_best_model(pred_dir: Path) -> tuple[Path, float] | None:
    """Return (model_path, test_auc) for the compatible model with the highest test AUC.

    Scans every ``predictive_*/results.json`` under *pred_dir*.  Models that
    lack a ``results.json`` or whose file cannot be parsed are silently skipped
    so a single corrupt directory never blocks the pipeline.

    Feature-count compatibility: models trained with a different number of
    features than the newest model are excluded, since ``predict_tomorrow()``
    always generates the current feature set.

    Returns None when no valid model directory is found.
    """
    import lightgbm as lgb

    # First pass: collect all candidates with their feature counts.
    candidates: list[tuple[Path, float, int]] = []
    for results_file in pred_dir.glob("predictive_*/results.json"):
        model_file = results_file.parent / "model.lgbm"
        if not model_file.exists():
            continue
        try:
            data = json.loads(results_file.read_text())
            auc = float(data["test"]["auc_roc"])
            n_feat = lgb.Booster(model_file=str(model_file)).num_feature()
        except Exception:
            continue
        candidates.append((model_file, auc, n_feat))

    if not candidates:
        return None

    # Use the feature count of the newest model (highest mtime) as the
    # reference — it was trained with the current feature generation code.
    ref_n_feat = max(candidates, key=lambda c: c[0].stat().st_mtime)[2]
    compatible = [(p, auc) for p, auc, nf in candidates if nf == ref_n_feat]

    if not compatible:
        return None

    best_path, best_auc = max(compatible, key=lambda c: c[1])
    return best_path, best_auc


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Daily Fire Alert Pipeline")
    parser.add_argument("--date", help="Specific date (YYYY-MM-DD)")
    parser.add_argument("--backfill", type=int, help="Process last N days")
    parser.add_argument("--skip-prediction", action="store_true",
                        help="Skip the predictive model step (faster)")
    parser.add_argument(
        "--model-tag",
        metavar="TAG",
        default=None,
        help=(
            "Use a specific predictive model directory by name "
            "(e.g. predictive_v3_no_leak).  Defaults to auto-selecting "
            "the model with the highest test AUC."
        ),
    )
    parser.add_argument(
        "--ensemble",
        action="store_true",
        help=(
            "Invoke ensemble_predict.py instead of a single model.  "
            "NOTE: ensemble_predict.py requires --models and --input to be "
            "configured separately; if the script is not ready this flag "
            "falls back to the best single model automatically."
        ),
    )
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
        pred_dir = ROOT / "outputs" / "predictive_fire_risk"

        # Resolve which model to use before launching the subprocess.
        if args.model_tag:
            tag_model = pred_dir / args.model_tag / "model.lgbm"
            if not tag_model.exists():
                print(f"\n  SKIP: --model-tag '{args.model_tag}' not found at {tag_model}")
                print(f"  Available tags: {[p.parent.name for p in pred_dir.glob('predictive_*/model.lgbm')]}")
                selected_model = None
            else:
                selected_model = tag_model
                print(f"\n  Model (--model-tag): {args.model_tag}")
        else:
            result = find_best_model(pred_dir)
            if result is None:
                selected_model = None
            else:
                selected_model, best_auc = result
                print(f"\n  Model (best AUC={best_auc:.4f}): {selected_model.parent.name}")

        if selected_model is not None:
            if args.ensemble:
                ensemble_script = ROOT / "scripts" / "ensemble_predict.py"
                if ensemble_script.exists():
                    # ensemble_predict.py requires --models and --input wired
                    # up externally; attempt it and fall back on failure.
                    ok = run_step("Ensemble Risk Map (Tomorrow)", [
                        PYTHON, str(ensemble_script),
                        "--predict", target_date,
                    ], timeout=300)
                    if not ok:
                        print(f"  FALLBACK: ensemble failed, running single best model")
                        run_step("Predictive Risk Map (Tomorrow) [fallback]", [
                            PYTHON, "scripts/train_predictive_fire_risk.py",
                            "--predict", target_date,
                        ], timeout=300)
                else:
                    print(f"  WARN: --ensemble requested but {ensemble_script} not found")
                    print(f"  Falling back to single best model: {selected_model.parent.name}")
                    run_step("Predictive Risk Map (Tomorrow)", [
                        PYTHON, "scripts/train_predictive_fire_risk.py",
                        "--predict", target_date,
                    ], timeout=300)
            else:
                run_step("Predictive Risk Map (Tomorrow)", [
                    PYTHON, "scripts/train_predictive_fire_risk.py",
                    "--predict", target_date,
                ], timeout=300)
        else:
            print(f"\n  SKIP: No valid predictive model found in {pred_dir}")
            print(f"  Train one first: python scripts/train_predictive_fire_risk.py --tag v2_improved")

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
