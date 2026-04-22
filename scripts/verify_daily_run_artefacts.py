"""Verify the daily pipeline produced + updated every expected artefact.

Run after `scripts/daily_fire_alert.py` completes. Reports PASS/FAIL per
artefact:
  - Freshness (mtime within last 60 min)
  - Content sanity (expected columns, row count, schema)

Usage:
  python scripts/verify_daily_run_artefacts.py --date 2026-04-22
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from pathlib import Path

import pandas as pd

sys.stdout.reconfigure(line_buffering=True)
logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger()

ROOT = Path(__file__).resolve().parents[1]

results: list[tuple[str, bool, str]] = []


def check(name: str, fn):
    try:
        ok, msg = fn()
    except Exception as e:
        ok, msg = False, f"EXCEPTION: {type(e).__name__}: {e}"
    log.info("[%s] %-50s %s", "PASS" if ok else "FAIL", name, msg)
    results.append((name, ok, msg))


def freshness(path: Path, max_age_min: int = 60) -> tuple[bool, str]:
    if not path.exists():
        return False, f"missing: {path.relative_to(ROOT)}"
    age_min = (time.time() - path.stat().st_mtime) / 60
    return age_min < max_age_min, f"age={age_min:.1f} min  size={path.stat().st_size:,} B"


def v17_json_schema(date: str):
    def _fn():
        p = ROOT / "outputs" / "dashboard_feed" / f"ignition_risk_v17_{date}.json"
        if not p.exists():
            return False, f"dated copy missing: {p.name}"
        d = json.loads(p.read_text())
        if d.get("model") != "v17_ba_pu":
            return False, f"unexpected model: {d.get('model')}"
        hb = d.get("hurdle_blend") or {}
        if not hb.get("applied"):
            return False, f"hurdle_blend not applied: {hb}"
        n = len(d.get("banded_alerts", []))
        if n < 100:
            return False, f"only {n} banded alerts (expected >100)"
        sample = d["banded_alerts"][0]
        if "stage_a_risk" not in sample:
            return False, "sample alert missing stage_a_risk"
        rc = d.get("rank_calibration", {})
        return True, (f"{n} alerts  CRIT={rc.get('n_critical')}  "
                      f"ALERT={rc.get('n_alert')}  WATCH={rc.get('n_watch')}")
    return _fn


def ops_alerts_schema():
    def _fn():
        p = ROOT / "outputs" / "dashboard_feed" / "operational_alerts_v17.json"
        d = json.loads(p.read_text())
        counts = d.get("counts", {})
        n = counts.get("final_critical", 0) + counts.get("final_alert", 0) + counts.get("final_watch", 0)
        if n == 0:
            return False, "no decorated alerts"
        cold = counts.get("cold_start", 0)
        return True, (f"raw={counts.get('raw_banded')} final="
                      f"{counts.get('final_critical')}/"
                      f"{counts.get('final_alert')}/"
                      f"{counts.get('final_watch')}  cold={cold}")
    return _fn


def parquet_rows(path_rel: str, min_rows: int = 1):
    def _fn():
        p = ROOT / path_rel
        if not p.exists():
            return False, f"missing: {path_rel}"
        df = pd.read_parquet(p)
        if len(df) < min_rows:
            return False, f"only {len(df)} rows (expected ≥ {min_rows})"
        return True, f"{len(df)} rows × {len(df.columns)} cols"
    return _fn


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=None, help="YYYY-MM-DD of the run")
    args = ap.parse_args()

    date = args.date or time.strftime("%Y-%m-%d")
    log.info("=" * 80)
    log.info("DAILY RUN ARTEFACT VERIFICATION — date=%s", date)
    log.info("=" * 80)

    log.info("\n--- v17.5 core ---")
    check("ignition_risk_v17.json freshness",
          lambda: freshness(ROOT / "outputs" / "dashboard_feed" / "ignition_risk_v17.json"))
    check(f"ignition_risk_v17_{date}.json schema", v17_json_schema(date))

    log.info("\n--- Operational alerts decoration ---")
    check("operational_alerts_v17.json freshness",
          lambda: freshness(ROOT / "outputs" / "dashboard_feed" / "operational_alerts_v17.json"))
    check("operational_alerts schema", ops_alerts_schema())
    check("division_briefings.json freshness",
          lambda: freshness(ROOT / "outputs" / "dashboard_feed" / "division_briefings.json"))

    log.info("\n--- Diagnostic stack (Step 4.7 + 4.8) ---")
    check("seasonal_pulse.json freshness",
          lambda: freshness(ROOT / "outputs" / "dashboard_feed" / "seasonal_pulse.json"))
    check("division_pulse.json freshness",
          lambda: freshness(ROOT / "outputs" / "dashboard_feed" / "division_pulse.json", max_age_min=120))
    check("feature_drift.json freshness",
          lambda: freshness(ROOT / "outputs" / "dashboard_feed" / "feature_drift.json", max_age_min=120))
    check("matrix_profile_firms.json freshness",
          lambda: freshness(ROOT / "outputs" / "dashboard_feed" / "matrix_profile_firms.json", max_age_min=120))
    check("season_onset.json freshness",
          lambda: freshness(ROOT / "outputs" / "dashboard_feed" / "season_onset.json", max_age_min=120))

    log.info("\n--- Step 4.9 soil features + v17 calibration ---")
    check("soil_daily.parquet freshness",
          lambda: freshness(ROOT / "data_lake" / "fire_weather" / "soil_daily.parquet", max_age_min=240))
    check("calibration.json freshness",
          lambda: freshness(ROOT / "outputs" / "predictive_fire_risk" / "predictive_v17_ba_pu" / "calibration.json", max_age_min=240))

    log.info("\n--- Alert parquets (rolling) ---")
    check("v17_drift_log has rows",
          parquet_rows("data_lake/alerts/v17_drift_log.parquet"))
    check("v17_validation_rolling has rows",
          parquet_rows("data_lake/alerts/v17_validation_rolling.parquet"))
    check("v17_feature_drift_log has rows",
          parquet_rows("data_lake/alerts/v17_feature_drift_log.parquet"))

    log.info("\n" + "=" * 80)
    n_pass = sum(1 for _, ok, _ in results if ok)
    n_fail = sum(1 for _, ok, _ in results if not ok)
    log.info("RESULTS: %d PASS, %d FAIL (of %d)", n_pass, n_fail, len(results))
    log.info("=" * 80)
    return 0 if not n_fail else 1


if __name__ == "__main__":
    raise SystemExit(main())
