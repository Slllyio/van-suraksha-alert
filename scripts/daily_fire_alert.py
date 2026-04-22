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

# Reconfigure stdout/stderr to UTF-8 so Unicode characters in log lines
# (e.g. 'λ', '→', '×') don't crash the script on Windows CMD's default cp1252.
# Same pattern as scripts/predict_ignition_v17.py and other ops scripts.
try:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    sys.stderr.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
except (AttributeError, Exception):
    pass

ROOT = Path(__file__).resolve().parent.parent
PYTHON = sys.executable
LOG_DIR = ROOT / "logs"
LOG_DIR.mkdir(exist_ok=True)
FEED_DIR = ROOT / "outputs" / "dashboard_feed"
FEED_DIR.mkdir(parents=True, exist_ok=True)

# Load .env if present
_env_file = ROOT / ".env"
if _env_file.exists():
    try:
        _env_text = _env_file.read_text(encoding="utf-8", errors="replace")
    except Exception:
        _env_text = _env_file.read_bytes().decode("utf-8", errors="replace")
    # Some installations have NULs embedded mid-file; filter them per-line
    for line in _env_text.replace("\x00", "").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, val = line.partition("=")
            key, val = key.strip(), val.strip()
            if key and val and "\x00" not in key and "\x00" not in val and key not in os.environ:
                try:
                    os.environ[key] = val
                except ValueError:
                    # Skip keys/values that still fail the NUL check in some Python versions
                    pass


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


def check_v17_feature_freshness(target_date: str) -> tuple[bool, list[str]]:
    """Check v17 feature parquets are fresh enough for prediction.

    Returns (ok_to_proceed, warnings). Hard-fail if dynamic feature >7 days stale.
    """
    warnings = []
    # Dynamic features — must be daily-fresh
    dynamic = [
        ("Hawkes λ (daily)", "data_lake/human_activity/hawkes/hawkes_lambda_per_cell_date.parquet", 48),
        ("v8 base dataset", "outputs/predictive_fire_risk/predictive_v8_ignition_dbscan/dataset.parquet", 168),  # weekly OK
    ]
    # Static features — just sanity-check they exist
    static = [
        ("GLCM texture", "data_lake/human_activity/glcm_texture_per_cell.parquet"),
        ("Hydro topology", "data_lake/human_activity/hydro_features_per_cell.parquet"),
    ]
    now = datetime.now()
    for label, rel_path, max_hours in dynamic:
        fp = ROOT / rel_path
        if not fp.exists():
            warnings.append(f"MISSING: {label} at {rel_path}")
            return False, warnings
        age_hours = (now.timestamp() - fp.stat().st_mtime) / 3600
        if age_hours > max_hours * 4:  # 4× buffer before hard-fail
            warnings.append(f"STALE (hard-fail): {label} is {age_hours:.0f}h old (limit {max_hours}h)")
            return False, warnings
        if age_hours > max_hours:
            warnings.append(f"STALE (warn): {label} is {age_hours:.0f}h old (soft-limit {max_hours}h)")
    for label, rel_path in static:
        fp = ROOT / rel_path
        if not fp.exists():
            warnings.append(f"MISSING: {label} at {rel_path}")
            return False, warnings
    return True, warnings


def run_v17_ignition(target_date: str) -> bool:
    """Step 4.5 — Run v17 ignition model + log metadata. Returns True on success."""
    print(f"\n{'='*60}")
    print(f"  STEP 4.5: v17 ignition prediction")
    print(f"{'='*60}")

    ok, warnings = check_v17_feature_freshness(target_date)
    for w in warnings:
        print(f"  [freshness] {w}")
    if not ok:
        print(f"  SKIP: feature freshness check failed")
        return False

    # Hurdle Stage A blend applied by default as of 2026-04-19 (Pivot A v2 T1).
    # Blend gives +1.77pp low-Hawkes / +0.89pp overall / +1.90pp cold-start
    # vs raw v17 on the 2025 honest hold-out. Pareto-better on every metric.
    # See docs/audits/pivot_a_v2_finding.md.
    return run_step("v17 Ignition Model (+ Hurdle blend)", [
        PYTHON, "scripts/predict_ignition_v17.py",
        "--date", target_date,
        "--rank-window-days", "7",
        "--use-hurdle-blend",
    ], timeout=300)


def log_v17_drift(target_date: str) -> None:
    """Step 5.5 — append today's v17 rank thresholds + alert counts to drift log.
    Warn if today's thresholds drift >25% vs 7-day rolling mean.
    """
    drift_path = ROOT / "data_lake" / "alerts" / "v17_drift_log.parquet"
    v17_file = ROOT / "outputs" / "dashboard_feed" / "ignition_risk_v17.json"
    if not v17_file.exists():
        return
    try:
        payload = json.loads(v17_file.read_text())
    except Exception:
        return
    rank_cal = payload.get("rank_calibration", {})
    import pandas as pd

    today_row = {
        "date": target_date,
        "watch_threshold": rank_cal.get("watch_threshold"),
        "alert_threshold": rank_cal.get("alert_threshold"),
        "critical_threshold": rank_cal.get("critical_threshold"),
        "n_watch": rank_cal.get("n_watch"),
        "n_alert": rank_cal.get("n_alert"),
        "n_critical": rank_cal.get("n_critical"),
        "rank_mode": rank_cal.get("mode"),
        "reference_size": rank_cal.get("reference_size"),
        "generated_at": payload.get("generated_at"),
    }

    drift_path.parent.mkdir(parents=True, exist_ok=True)
    if drift_path.exists():
        hist = pd.read_parquet(drift_path)
        hist = hist[hist["date"] != target_date]
        hist = pd.concat([hist, pd.DataFrame([today_row])], ignore_index=True)
    else:
        hist = pd.DataFrame([today_row])
    hist.to_parquet(drift_path, index=False)

    # Drift check vs 7-day rolling mean (skip if insufficient history)
    hist["date_ts"] = pd.to_datetime(hist["date"])
    recent = hist[hist["date_ts"] < pd.Timestamp(target_date)].tail(7)
    if len(recent) >= 3:
        for col in ("watch_threshold", "alert_threshold", "critical_threshold"):
            rolling_mean = recent[col].mean()
            if rolling_mean and rolling_mean > 0:
                today_val = today_row[col]
                if today_val is not None:
                    drift_frac = abs(today_val - rolling_mean) / rolling_mean
                    if drift_frac > 0.25:
                        print(f"  [drift] WARN {col} drifted {drift_frac:.1%} vs 7-day mean "
                              f"(today={today_val:.4f}, mean={rolling_mean:.4f})")
        # Alert-count spike check
        n_crit_today = today_row["n_critical"] or 0
        n_crit_mean = recent["n_critical"].mean()
        if n_crit_mean > 0 and n_crit_today > 2 * n_crit_mean:
            print(f"  [drift] WARN n_critical={n_crit_today} is {n_crit_today/n_crit_mean:.1f}× "
                  f"7-day mean ({n_crit_mean:.0f}) — possible heatwave regime")

    print(f"  Drift log updated: {drift_path.relative_to(ROOT)} ({len(hist)} rows)")


def _confidence_flag(viirs_confidence: str | None) -> str:
    """Map FIRMS VIIRS confidence string to a unified confidence flag.

    FIRMS VIIRS encodes confidence as ``high``/``nominal``/``low`` (or
    single-letter ``h``/``n``/``l``).  We surface a normalised
    ``HIGH_CONFIDENCE``/``NOMINAL_CONFIDENCE``/``LOW_CONFIDENCE`` flag for
    downstream dashboard filters.
    """
    conf = (viirs_confidence or "").lower()
    if conf in ("high", "h"):
        return "HIGH_CONFIDENCE"
    if conf in ("low", "l"):
        return "LOW_CONFIDENCE"
    return "NOMINAL_CONFIDENCE"


def build_unified_feed(target_date: str):
    """Merge detection alerts + prediction risk map into unified GeoJSON feed."""
    import csv
    from collections import Counter

    features = []

    # Banded summary counters
    detection_severity_bands: Counter = Counter()
    detection_confidence_flags: Counter = Counter()
    detection_frp_categories: Counter = Counter()
    prediction_risk_bands: Counter = Counter()

    bulletin_severity = "WATCH"
    peak_frp_mw = 0.0
    n_forest_fires = 0
    n_agri_fires = 0
    fwi_value = None
    fwi_danger = None

    # 1. Detection alerts (from NRT pipeline)
    alert_file = ROOT / "data_lake" / "alerts" / "latest_alert.json"
    if alert_file.exists():
        try:
            alert_data = json.loads(alert_file.read_text())
            bulletin_severity = alert_data.get("bulletin_severity", "WATCH")
            peak_frp_mw = float(alert_data.get("peak_frp_mw", 0.0))
            n_forest_fires = int(alert_data.get("n_forest_fires", 0))
            n_agri_fires = int(alert_data.get("n_agri_fires", 0))
            fwi_value = alert_data.get("fwi", {}).get("value")
            fwi_danger = alert_data.get("fwi", {}).get("danger_class")

            # NRT pipeline stores fires in "fires" key (not GeoJSON "features")
            fires = alert_data.get("fires", [])
            for fire in fires:
                severity = fire.get("severity", "LOW")
                viirs_conf = fire.get("viirs_confidence")
                confidence_flag = _confidence_flag(viirs_conf)
                frp_category = fire.get("frp_category", "TRACE")

                detection_severity_bands[severity] += 1
                detection_confidence_flags[confidence_flag] += 1
                detection_frp_categories[frp_category] += 1

                feat = {
                    "type": "Feature",
                    "geometry": {
                        "type": "Point",
                        "coordinates": [fire["fire_lon"], fire["fire_lat"]],
                    },
                    "properties": {
                        "severity": severity,
                        "frp_mw": fire.get("frp_mw", 0),
                        "frp_category": frp_category,
                        "viirs_confidence": viirs_conf,
                        "confidence_flag": confidence_flag,
                        "daynight": fire.get("daynight", ""),
                        "fire_date": fire.get("fire_date", target_date),
                        "fire_time_ist": fire.get("fire_time_ist", ""),
                        "land_cover": fire.get("land_cover", ""),
                        "in_forest": fire.get("in_forest"),
                        "near_forest": fire.get("near_forest"),
                        "is_agricultural": fire.get("is_agricultural"),
                        "fwi": fwi_value,
                        "fwi_danger": fwi_danger,
                        "message": fire.get("message", ""),
                        "source": "FIRMS_DETECTION",
                        "alert_type": "DETECTED",
                        "predicted_spread": fire.get("predicted_spread"),
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
            with open(risk_csv, "r") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    risk_level = row.get("risk_level", "LOW")
                    if risk_level in ("MODERATE", "HIGH", "CRITICAL"):
                        prediction_risk_bands[risk_level] += 1
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
            n_pred = sum(prediction_risk_bands.values())
            print(f"  Prediction alerts: {n_pred} cells (MODERATE+)")
        except Exception as e:
            print(f"  WARN: Could not load prediction risk map: {e}")

    # 3. v17 ignition predictions (banded alerts at WATCH/ALERT/CRITICAL)
    ignition_v17_bands: Counter = Counter()
    v17_meta = None
    v17_file = ROOT / "outputs" / "dashboard_feed" / "ignition_risk_v17.json"
    if v17_file.exists():
        try:
            v17_data = json.loads(v17_file.read_text())
            v17_meta = {
                "model": v17_data.get("model"),
                "prediction_date": v17_data.get("prediction_date"),
                "generated_at": v17_data.get("generated_at"),
                "rank_calibration": v17_data.get("rank_calibration", {}),
                "metrics_on_validation": v17_data.get("metrics_on_validation", {}),
            }
            for a in v17_data.get("banded_alerts", []):
                band = a.get("band", "NONE")
                ignition_v17_bands[band] += 1
                features.append({
                    "type": "Feature",
                    "geometry": {
                        "type": "Point",
                        "coordinates": [a["lon"], a["lat"]],
                    },
                    "properties": {
                        "cell_id": a.get("cell_id"),
                        "ignition_risk": round(float(a.get("ignition_risk", 0)), 4),
                        "rank": round(float(a.get("rank", 0)), 4),
                        "band": band,
                        "hawkes_n_recent_10km_7d": a.get("hawkes_n_recent_10km_7d", 0),
                        "hawkes_lambda": round(float(a.get("hawkes_lambda", 0)), 4),
                        "source": "V17_IGNITION_MODEL",
                        "alert_type": "ignition_v17",
                        "prediction_date": v17_data.get("prediction_date"),
                    },
                })
            print(f"  v17 ignition alerts: {sum(ignition_v17_bands.values())} cells "
                  f"(CRITICAL={ignition_v17_bands.get('CRITICAL', 0)} "
                  f"ALERT={ignition_v17_bands.get('ALERT', 0)} "
                  f"WATCH={ignition_v17_bands.get('WATCH', 0)})")
        except Exception as e:
            print(f"  WARN: Could not load v17 ignition alerts: {e}")

    # Build unified GeoJSON
    n_detect = sum(detection_severity_bands.values())
    n_pred_total = sum(prediction_risk_bands.values())
    n_v17_total = sum(ignition_v17_bands.values())

    geojson = {
        "type": "FeatureCollection",
        "metadata": {
            "generated": datetime.now().isoformat(),
            "target_date": target_date,
            "n_detections": n_detect,
            "n_predictions": n_pred_total,
            "bulletin_severity": bulletin_severity,
            "peak_frp_mw": peak_frp_mw,
            "n_forest_fires": n_forest_fires,
            "n_agri_fires": n_agri_fires,
            "fwi": {"value": fwi_value, "danger_class": fwi_danger},
            "detection_severity_bands": {
                "critical": detection_severity_bands.get("CRITICAL", 0),
                "high": detection_severity_bands.get("HIGH", 0),
                "moderate": detection_severity_bands.get("MODERATE", 0),
                "low": detection_severity_bands.get("LOW", 0),
            },
            "detection_confidence_flags": {
                "high_confidence": detection_confidence_flags.get("HIGH_CONFIDENCE", 0),
                "nominal_confidence": detection_confidence_flags.get("NOMINAL_CONFIDENCE", 0),
                "low_confidence": detection_confidence_flags.get("LOW_CONFIDENCE", 0),
            },
            "detection_frp_categories": {
                "inferno": detection_frp_categories.get("INFERNO", 0),
                "intense": detection_frp_categories.get("INTENSE", 0),
                "active": detection_frp_categories.get("ACTIVE", 0),
                "minor": detection_frp_categories.get("MINOR", 0),
                "trace": detection_frp_categories.get("TRACE", 0),
            },
            "prediction_risk_bands": {
                "critical": prediction_risk_bands.get("CRITICAL", 0),
                "high": prediction_risk_bands.get("HIGH", 0),
                "moderate": prediction_risk_bands.get("MODERATE", 0),
            },
            "n_ignition_v17": n_v17_total,
            "ignition_v17_bands": {
                "critical": ignition_v17_bands.get("CRITICAL", 0),
                "alert": ignition_v17_bands.get("ALERT", 0),
                "watch": ignition_v17_bands.get("WATCH", 0),
            },
            "ignition_v17_meta": v17_meta,
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

    # Dead models excluded from auto-selection.  predictive_v3_no_leak is a
    # 1-tree stub (val AUC ~0.48) that shipped to production and has to stay
    # on disk for provenance, but must never be auto-selected.
    EXCLUDED = {"predictive_v3_no_leak"}

    # First pass: collect all candidates with their feature counts.
    candidates: list[tuple[Path, float, int]] = []
    for results_file in pred_dir.glob("predictive_*/results.json"):
        if results_file.parent.name in EXCLUDED:
            continue
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
            "(e.g. predictive_v6e_live).  Defaults to auto-selecting "
            "the model with the highest test AUC. Note: predictive_v3_no_leak "
            "is deprecated (1-tree stub, val AUC ~0.48)."
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

    # Step 1: Update FWI + fetch live weather from Open-Meteo API
    current_year = datetime.now().year
    run_step("Update FWI + Live Weather", [
        PYTHON, "scripts/compute_fwi.py",
        "--start", str(current_year - 1),
        "--end", str(current_year),
        "--update-nrt",
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

    # Step 4.5: Run v17 ignition model (new-ignition predictions at rank-banded alerts)
    if not args.skip_prediction:
        run_v17_ignition(target_date)

    # Step 4.6: Decorate raw v17 with trust tiers + actions + budget caps + weather/calendar
    if not args.skip_prediction:
        run_step("Build Operational Alerts", [
            PYTHON, "scripts/build_operational_alerts.py",
        ], timeout=60)

    # Step 4.7: Season Pulse (Prophet seasonal baseline + 28-day rolling FRP)
    if not args.skip_prediction:
        run_step("Fit Prophet Season Pulse", [
            PYTHON, "scripts/fit_prophet_firms_seasonality.py",
        ], timeout=120)

    # Step 4.8: Diagnostic stack — per-division baselines + drift + matrix profile + season onset
    if not args.skip_prediction:
        run_step("Per-division AutoARIMA (StatsForecast)", [
            PYTHON, "scripts/fit_statsforecast_per_division.py",
        ], timeout=600)
        run_step("v17 Feature Drift Monitor", [
            PYTHON, "scripts/monitor_v17_feature_drift.py",
        ], timeout=120)
        run_step("STUMPY Matrix Profile", [
            PYTHON, "scripts/matrix_profile_firms.py",
        ], timeout=300)
        run_step("Season Onset Change-points", [
            PYTHON, "scripts/detect_season_changepoints.py",
        ], timeout=120)

    # Step 4.9: Soil features (Open-Meteo Archive) + v17 calibration refit
    # These are slow/external so refit weekly is enough; if you want daily, just keep them on.
    if not args.skip_prediction:
        run_step("Soil Features (Open-Meteo Archive)", [
            PYTHON, "scripts/build_soil_features.py",
        ], timeout=300)
        run_step("v17 Probability Calibration", [
            PYTHON, "scripts/calibrate_v17.py",
        ], timeout=120)

    # Step 5: Build unified feed (detection + grid prediction + v17 ignition)
    print(f"\n{'='*60}")
    print(f"  STEP: Build Unified Alert Feed")
    print(f"{'='*60}")
    build_unified_feed(target_date)

    # Step 5.5: Update v17 drift log + warn if thresholds drift
    log_v17_drift(target_date)

    # Step 5.6: Field validation backtest (D-7 lookback — by now next-week FIRMS exists)
    if not args.skip_prediction:
        run_step("v17 Field Validation Backtest", [
            PYTHON, "scripts/validate_v17_daily.py",
            "--days", "30",
            "--end-date", target_date,
        ], timeout=180)

    # Step 6: 3-day fire danger forecast (GFS + forward FWI)
    forecast_script = ROOT / "scripts" / "forecast_fire_danger.py"
    if forecast_script.exists() and not args.skip_prediction:
        run_step("3-Day Fire Danger Forecast", [
            PYTHON, str(forecast_script),
            "--date", target_date,
            "--no-risk-maps",  # fast mode: FWI forecast only
        ], timeout=180)

    elapsed = (datetime.now() - started).total_seconds()
    print(f"\n{'='*60}")
    print(f"  PIPELINE COMPLETE -- {elapsed:.0f}s elapsed")
    print(f"{'='*60}")
    print(f"\n  Outputs:")
    print(f"    Detection:  outputs/dashboard_feed/latest_alert.json")
    print(f"    Prediction: outputs/predictive_fire_risk/risk_map_{target_date}.csv")
    print(f"    Unified:    outputs/dashboard_feed/unified_alert.geojson")
    print(f"    Forecast:   outputs/dashboard_feed/fire_danger_forecast.json")


if __name__ == "__main__":
    main()
