"""End-to-end operational test for v17.5 production pipeline.

Exercises every component the daily cron + portal touch:

  Phase 1 — v17 JSON schema (raw + hurdle blend)
  Phase 2 — Operational alerts decoration consumes new schema
  Phase 3 — Portal endpoints serve new fields
  Phase 4 — Field-response POST + GET round-trip
  Phase 5 — Diagnostic stack endpoints (drift, season pulse, ...)
  Phase 6 — Validation backtest works with blended scores

Runs each check, reports PASS/FAIL with diagnostics. Non-zero exit if
anything fails.

Usage:
  python scripts/test_operational_pipeline.py
"""
from __future__ import annotations

import json
import logging
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import pandas as pd

sys.stdout.reconfigure(line_buffering=True)
logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger()

ROOT = Path(__file__).resolve().parents[1]
PYTHON = sys.executable
PORTAL_BASE = "http://localhost:8790"
V17_JSON = ROOT / "outputs" / "dashboard_feed" / "ignition_risk_v17.json"
OPS_JSON = ROOT / "outputs" / "dashboard_feed" / "operational_alerts_v17.json"
DIVISION_BRIEFINGS = ROOT / "outputs" / "dashboard_feed" / "division_briefings.json"
FIELD_RESPONSES = ROOT / "data_lake" / "alerts" / "field_responses.parquet"

results: list[tuple[str, bool, str]] = []


def check(name: str, fn, *args):
    """Run `fn(*args)`, capture (ok, message). Append to results."""
    try:
        ok, msg = fn(*args)
    except Exception as e:
        ok, msg = False, f"EXCEPTION: {type(e).__name__}: {e}"
    status = "PASS" if ok else "FAIL"
    log.info("[%s] %s — %s", status, name, msg)
    results.append((name, ok, msg))


def http_get(path: str) -> dict:
    with urllib.request.urlopen(f"{PORTAL_BASE}{path}", timeout=10) as r:
        return json.loads(r.read().decode())


def http_post(path: str, payload: dict) -> dict:
    body = json.dumps(payload).encode()
    req = urllib.request.Request(
        f"{PORTAL_BASE}{path}", data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read().decode())


# --- Phase 1: v17 JSON schema ----------------------------------------------

def test_v17_json_exists() -> tuple[bool, str]:
    if not V17_JSON.exists():
        return False, f"missing {V17_JSON}"
    data = json.loads(V17_JSON.read_text())
    n = len(data.get("banded_alerts", []))
    return n > 0, f"{n} banded alerts"


def test_v17_hurdle_metadata() -> tuple[bool, str]:
    data = json.loads(V17_JSON.read_text())
    meta = data.get("hurdle_blend")
    if meta is None:
        return False, "no hurdle_blend block — pipeline may not be using --use-hurdle-blend"
    if not meta.get("applied"):
        return False, f"hurdle_blend block present but applied=False: {meta}"
    variant = meta.get("variant", "?")
    return True, f"applied=True variant={variant}"


def test_v17_per_alert_stage_a() -> tuple[bool, str]:
    data = json.loads(V17_JSON.read_text())
    alerts = data.get("banded_alerts", [])
    if not alerts:
        return False, "no banded_alerts"
    sample = alerts[0]
    if "stage_a_risk" not in sample:
        return False, f"sample alert missing stage_a_risk: keys={list(sample)}"
    val = sample["stage_a_risk"]
    if not (0 <= val <= 1):
        return False, f"stage_a_risk out of range: {val}"
    return True, f"sample stage_a_risk={val:.4f} ignition_risk={sample['ignition_risk']:.4f}"


def test_v17_calibration_metadata() -> tuple[bool, str]:
    data = json.loads(V17_JSON.read_text())
    cal = data.get("probability_calibration")
    if cal is None:
        return False, "no probability_calibration block (expected isotonic)"
    method = cal.get("method", "?")
    if method != "isotonic":
        return False, f"unexpected method: {method}"
    brier = cal.get("brier", 1.0)
    return brier < 0.01, f"method={method} brier={brier:.4f}"


def test_v17_band_distribution() -> tuple[bool, str]:
    data = json.loads(V17_JSON.read_text())
    rc = data.get("rank_calibration", {})
    n_crit = rc.get("n_critical", 0)
    n_alert = rc.get("n_alert", 0)
    n_watch = rc.get("n_watch", 0)
    total = n_crit + n_alert + n_watch
    if total == 0:
        return False, "all band counts zero"
    if n_crit > n_alert or n_alert > n_watch:
        return False, f"band order wrong: CRITICAL={n_crit} ALERT={n_alert} WATCH={n_watch}"
    return True, f"CRITICAL={n_crit} ALERT={n_alert} WATCH={n_watch} (pyramid OK)"


# --- Phase 2: ops alerts decoration ----------------------------------------

def test_ops_alerts_exists() -> tuple[bool, str]:
    if not OPS_JSON.exists():
        return False, f"missing {OPS_JSON}"
    data = json.loads(OPS_JSON.read_text())
    n = len(data.get("alerts", []))
    return n > 0, f"{n} decorated alerts"


def test_ops_alerts_carry_calibrated_risk() -> tuple[bool, str]:
    data = json.loads(OPS_JSON.read_text())
    alerts = data.get("alerts", [])
    if not alerts:
        return False, "no alerts"
    sample = alerts[0]
    has_cal = "calibrated_risk" in sample
    has_trust = "trust_level" in sample
    has_action = "action" in sample
    return all([has_cal, has_trust, has_action]), (
        f"calibrated_risk={sample.get('calibrated_risk')} "
        f"trust={sample.get('trust_level')} action={sample.get('action')}"
    )


def test_ops_alerts_budget_caps() -> tuple[bool, str]:
    data = json.loads(OPS_JSON.read_text())
    counts = data.get("counts", {})
    raw = counts.get("raw_banded", 0)
    final_crit = counts.get("final_critical", 0)
    if raw == 0:
        return False, "no raw_banded count"
    if final_crit > 130:  # statewide cap
        return False, f"final_critical={final_crit} exceeds statewide cap 130"
    return True, f"raw={raw} -> final CRIT={final_crit} (within cap)"


def test_division_briefings() -> tuple[bool, str]:
    if not DIVISION_BRIEFINGS.exists():
        return False, f"missing {DIVISION_BRIEFINGS}"
    data = json.loads(DIVISION_BRIEFINGS.read_text())
    n = data.get("n_divisions_with_alerts", 0)
    return n > 0, f"{n} division briefings"


# --- Phase 3: portal endpoints ---------------------------------------------

def test_portal_alive() -> tuple[bool, str]:
    try:
        d = http_get("/api/ignition-v17")
    except Exception as e:
        return False, f"portal not reachable: {e}"
    return "banded_alerts" in d, f"{len(d.get('banded_alerts', []))} alerts via API"


def test_portal_operational_alerts() -> tuple[bool, str]:
    d = http_get("/api/operational-alerts")
    if d.get("error"):
        return False, d["error"]
    sample = (d.get("alerts") or [{}])[0]
    return "calibrated_risk" in sample, (
        f"{len(d.get('alerts', []))} ops alerts, "
        f"sample has calibrated_risk={sample.get('calibrated_risk')}"
    )


def test_portal_division_pulse() -> tuple[bool, str]:
    d = http_get("/api/division-pulse")
    if d.get("error"):
        return False, d["error"]
    n = d.get("n_divisions_fit", 0)
    return n > 0, f"{n} divisions fit; summary={d.get('summary')}"


def test_portal_seasonal_pulse() -> tuple[bool, str]:
    d = http_get("/api/seasonal-pulse")
    if d.get("error"):
        return False, d["error"]
    return "drift" in d, f"latest={d.get('latest_actual_date')} drift={d.get('drift', {}).get('status')}"


def test_portal_matrix_profile() -> tuple[bool, str]:
    d = http_get("/api/matrix-profile")
    if d.get("error"):
        return False, d["error"]
    cw = d.get("current_window", {})
    return "status" in cw, f"current window status={cw.get('status')} pct={cw.get('percentile_in_history', 0):.1f}%"


def test_portal_season_onset() -> tuple[bool, str]:
    d = http_get("/api/season-onset")
    if d.get("error"):
        return False, d["error"]
    return "classification" in d, f"{d.get('current_year')} classification={d.get('classification')}"


def test_portal_feature_drift() -> tuple[bool, str]:
    d = http_get("/api/feature-drift")
    if d.get("error"):
        return False, d["error"]
    return "overall_status" in d, f"overall={d.get('overall_status')} counts={d.get('counts')}"


def test_portal_beats_geojson() -> tuple[bool, str]:
    d = http_get("/api/beats-boundary")
    if d.get("error"):
        return False, d["error"]
    n = len(d.get("features", []))
    return n > 0, f"{n} beat polygons"


def test_portal_viirs_fires() -> tuple[bool, str]:
    d = http_get("/api/viirs-fires?from=2026-04-01&to=2026-04-19")
    if d.get("error"):
        return False, d["error"]
    return "fires" in d, f"{d.get('n_fires', 0)} VIIRS fires (clipped to forest beats)"


# --- Phase 4: field-response loop ------------------------------------------

def test_field_response_post_get() -> tuple[bool, str]:
    payload = {
        "cell_id": "ops_test_cell_id",
        "outcome": "clear",
        "staff_id": "ops_test_runner",
        "band": "WATCH",
        "trust_level": "MEDIUM",
        "lat": 23.5,
        "lon": 78.5,
        "note": "ops_test_pipeline.py smoke test",
    }
    post_resp = http_post("/api/field-response", payload)
    if post_resp.get("status") != "ok":
        return False, f"POST failed: {post_resp}"
    summary = http_get("/api/field-responses")
    total = summary.get("total", 0)
    if total == 0:
        return False, "summary still 0 after POST"
    # Verify our test row is in the recent list
    recent = summary.get("recent", [])
    our_row = next((r for r in recent if r.get("staff_id") == "ops_test_runner"
                    and r.get("note", "").startswith("ops_test_pipeline.py")), None)
    if our_row is None:
        return False, f"test row not in recent ({len(recent)} rows). last: {recent[-1] if recent else None}"
    return True, f"POST→GET round-trip OK, total={total}"


# --- Phase 6: validation backtest works with blended scores ---------------

def test_validation_log_readable() -> tuple[bool, str]:
    path = ROOT / "data_lake" / "alerts" / "v17_validation_rolling.parquet"
    if not path.exists():
        return False, f"missing {path}"
    df = pd.read_parquet(path)
    return len(df) > 0, f"{len(df)} validation rows"


def test_drift_log_readable() -> tuple[bool, str]:
    path = ROOT / "data_lake" / "alerts" / "v17_drift_log.parquet"
    if not path.exists():
        return False, f"missing {path}"
    df = pd.read_parquet(path)
    return len(df) > 0, f"{len(df)} drift log rows"


# --- Phase 5: daily_fire_alert.py end-to-end (smoke) ----------------------

def test_daily_pipeline_smoke() -> tuple[bool, str]:
    """Just checks that scripts/daily_fire_alert.py imports and parses --help.
    Full E2E run is heavy and externally-dependent (FIRMS NRT, FWI APIs)."""
    p = subprocess.run(
        [PYTHON, "scripts/daily_fire_alert.py", "--help"],
        cwd=ROOT, capture_output=True, text=True, timeout=30,
    )
    if p.returncode != 0:
        return False, f"--help failed: {p.stderr[-300:]}"
    return "--date" in (p.stdout + p.stderr), "daily_fire_alert.py --help OK"


def test_predict_v17_uses_hurdle_in_pipeline() -> tuple[bool, str]:
    """Read daily_fire_alert.py to confirm --use-hurdle-blend is wired."""
    src = (ROOT / "scripts" / "daily_fire_alert.py").read_text()
    if "--use-hurdle-blend" not in src:
        return False, "daily_fire_alert.py does NOT pass --use-hurdle-blend"
    return True, "daily_fire_alert.py invokes predict_ignition_v17 with --use-hurdle-blend"


def main() -> int:
    log.info("=" * 70)
    log.info("OPERATIONAL PIPELINE TEST")
    log.info("=" * 70)

    log.info("\n--- Phase 1: v17 JSON schema (raw + hurdle blend) ---")
    check("v17 JSON exists", test_v17_json_exists)
    check("v17 hurdle_blend metadata", test_v17_hurdle_metadata)
    check("v17 per-alert stage_a_risk", test_v17_per_alert_stage_a)
    check("v17 calibration metadata", test_v17_calibration_metadata)
    check("v17 band distribution", test_v17_band_distribution)

    log.info("\n--- Phase 2: operational alerts decoration ---")
    check("ops alerts JSON exists", test_ops_alerts_exists)
    check("ops alerts carry calibrated/trust/action", test_ops_alerts_carry_calibrated_risk)
    check("ops alerts budget caps", test_ops_alerts_budget_caps)
    check("division briefings", test_division_briefings)

    log.info("\n--- Phase 3: portal endpoints ---")
    check("portal /api/ignition-v17", test_portal_alive)
    check("portal /api/operational-alerts", test_portal_operational_alerts)
    check("portal /api/division-pulse", test_portal_division_pulse)
    check("portal /api/seasonal-pulse", test_portal_seasonal_pulse)
    check("portal /api/matrix-profile", test_portal_matrix_profile)
    check("portal /api/season-onset", test_portal_season_onset)
    check("portal /api/feature-drift", test_portal_feature_drift)
    check("portal /api/beats-boundary", test_portal_beats_geojson)
    check("portal /api/viirs-fires", test_portal_viirs_fires)

    log.info("\n--- Phase 4: field-response loop ---")
    check("POST /api/field-response → GET round-trip", test_field_response_post_get)

    log.info("\n--- Phase 5: daily pipeline smoke ---")
    check("daily_fire_alert.py --help", test_daily_pipeline_smoke)
    check("daily_fire_alert.py wires --use-hurdle-blend", test_predict_v17_uses_hurdle_in_pipeline)

    log.info("\n--- Phase 6: validation + drift logs ---")
    check("v17 validation rolling parquet", test_validation_log_readable)
    check("v17 drift log parquet", test_drift_log_readable)

    log.info("\n" + "=" * 70)
    n_pass = sum(1 for _, ok, _ in results if ok)
    n_fail = sum(1 for _, ok, _ in results if not ok)
    log.info("RESULTS: %d PASS, %d FAIL (of %d total)", n_pass, n_fail, len(results))
    log.info("=" * 70)

    if n_fail:
        log.info("\nFailed checks:")
        for name, ok, msg in results:
            if not ok:
                log.info("  [FAIL] %s — %s", name, msg)
        return 1
    log.info("\nAll operational checks PASSED.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
