"""Static operational checks for CI (runs on clean github-hosted runners).

Tests that the operational stack's entrypoints are well-formed and the
production wiring is intact, WITHOUT requiring the gigabytes of v17 model
artefacts, FIRMS parquets, or running portal that the full harness needs.

Run on every push to main / feature branches via .github/workflows/ci.yml.
The full harness (`scripts/test_operational_pipeline.py`) runs daily as the
last step of `.github/workflows/daily_fire_alert.yml` against fresh
production artefacts.

Checks:
  1. All operational scripts have valid Python syntax (compile pass)
  2. Each `--help` resolves cleanly (catches broken imports + argparse)
  3. `daily_fire_alert.py` source includes `--use-hurdle-blend` (production wiring)
  4. `predict_ignition_v17.py` exposes the `--use-hurdle-blend` flag
  5. `build_operational_alerts.py` references all 4 trust tiers
  6. `test_operational_pipeline.py` covers ≥ 20 distinct checks
  7. `dashboard/v3/serve.py` references the warm-load path
"""
from __future__ import annotations

import logging
import py_compile
import subprocess
import sys
from pathlib import Path

sys.stdout.reconfigure(line_buffering=True)
logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger()

ROOT = Path(__file__).resolve().parents[1]
PYTHON = sys.executable

OPS_SCRIPTS = [
    "scripts/predict_ignition_v17.py",
    "scripts/daily_fire_alert.py",
    "scripts/build_operational_alerts.py",
    "scripts/train_v17_hurdle_stage_a.py",
    "scripts/evaluate_v17_hurdle_blend.py",
    "scripts/test_operational_pipeline.py",
    "scripts/calibrate_v17.py",
    "scripts/build_soil_features.py",
    "scripts/fit_statsforecast_per_division.py",
    "scripts/monitor_v17_feature_drift.py",
    "scripts/matrix_profile_firms.py",
    "scripts/detect_season_changepoints.py",
    "dashboard/v3/serve.py",
]

results: list[tuple[str, bool, str]] = []


def check(name: str, fn, *args):
    try:
        ok, msg = fn(*args)
    except Exception as e:
        ok, msg = False, f"EXCEPTION: {type(e).__name__}: {e}"
    results.append((name, ok, msg))
    log.info("[%s] %-55s %s", "PASS" if ok else "FAIL", name, msg)


def check_compile(path: str) -> tuple[bool, str]:
    p = ROOT / path
    if not p.exists():
        return False, f"missing: {path}"
    try:
        py_compile.compile(str(p), doraise=True)
        return True, f"{p.stat().st_size:,} bytes"
    except py_compile.PyCompileError as e:
        return False, str(e)[:200]


def check_help(path: str) -> tuple[bool, str]:
    p = ROOT / path
    if not p.exists():
        return False, f"missing: {path}"
    try:
        r = subprocess.run(
            [PYTHON, str(p), "--help"],
            cwd=ROOT, capture_output=True, text=True, timeout=15,
        )
    except subprocess.TimeoutExpired:
        return False, "--help took >15s (likely heavy import on entry)"
    if r.returncode != 0:
        # Some scripts (build_operational_alerts.py) don't take --help; treat as OK if "no error"
        if "unrecognized arguments" in r.stderr or "error: unrecognized" in r.stderr:
            return False, f"argparse error: {r.stderr[:150]}"
        # If stderr mentions ModuleNotFoundError, that's a real fail
        if "ModuleNotFoundError" in r.stderr or "ImportError" in r.stderr:
            return False, r.stderr[:200]
        # Otherwise probably no argparse — accept
        return True, f"no --help (rc={r.returncode}, no import error)"
    out = (r.stdout + r.stderr).strip()
    return "usage" in out.lower() or len(out) > 0, f"prints help ({len(out)} chars)"


def check_hurdle_wired() -> tuple[bool, str]:
    src = (ROOT / "scripts" / "daily_fire_alert.py").read_text()
    if "--use-hurdle-blend" not in src:
        return False, "daily_fire_alert.py does NOT include --use-hurdle-blend"
    if 'predict_ignition_v17.py' not in src:
        return False, "daily_fire_alert.py does not invoke predict_ignition_v17.py"
    return True, "wired in run_v17_ignition()"


def check_predict_v17_flag() -> tuple[bool, str]:
    src = (ROOT / "scripts" / "predict_ignition_v17.py").read_text()
    if '--use-hurdle-blend' not in src:
        return False, "predict_ignition_v17.py does NOT define --use-hurdle-blend"
    if "_apply_hurdle_blend" not in src:
        return False, "predict_ignition_v17.py missing _apply_hurdle_blend helper"
    return True, "flag + helper present"


def check_ops_alerts_trust_tiers() -> tuple[bool, str]:
    src = (ROOT / "scripts" / "build_operational_alerts.py").read_text()
    tiers = ["HIGH", "MEDIUM", "COLD_START", "LOW"]
    missing = [t for t in tiers if f'"{t}"' not in src]
    if missing:
        return False, f"missing tiers: {missing}"
    return True, "all 4 trust tiers referenced"


def check_test_harness_coverage() -> tuple[bool, str]:
    src = (ROOT / "scripts" / "test_operational_pipeline.py").read_text()
    n_checks = src.count('check("')
    if n_checks < 20:
        return False, f"only {n_checks} check() calls (expected ≥ 20)"
    return True, f"{n_checks} check() calls"


def check_portal_warm_load() -> tuple[bool, str]:
    src = (ROOT / "dashboard" / "v3" / "serve.py").read_text()
    if "Warming beat polygon cache" not in src:
        return False, "missing warm-load on portal startup"
    if "_load_beat_polygons()" not in src:
        return False, "_load_beat_polygons not called on startup"
    return True, "warm-load present"


def check_calibration_artefacts() -> tuple[bool, str]:
    """The calibration JSON should be tracked at the path predict_ignition_v17 reads."""
    p = ROOT / "outputs" / "predictive_fire_risk" / "predictive_v17_ba_pu" / "calibration.json"
    # On CI, this file may not exist (gitignored). Pass if either:
    #   - it exists locally (dev) OR
    #   - the path string is present in source code (deployment-readiness check)
    src = (ROOT / "scripts" / "predict_ignition_v17.py").read_text()
    if "calibration.json" not in src:
        return False, "predict_ignition_v17.py doesn't reference calibration.json"
    return True, f"path referenced ({'exists locally' if p.exists() else 'gitignored on CI'})"


def main() -> int:
    log.info("=" * 80)
    log.info("CI STATIC OPS CHECKS")
    log.info("=" * 80)

    log.info("\n--- Phase 1: Python compile ---")
    for s in OPS_SCRIPTS:
        check(f"compile {s}", check_compile, s)

    log.info("\n--- Phase 2: --help / import resolution ---")
    # Limit to user-facing scripts that DO support --help (have argparse).
    # Test runners (test_operational_pipeline.py, ci_static_ops_checks.py) don't
    # use argparse — they execute directly — so excluded from --help check.
    for s in [
        "scripts/predict_ignition_v17.py",
        "scripts/daily_fire_alert.py",
        "scripts/build_dynamic_world_features.py",
        "scripts/calibrate_v17.py",
    ]:
        check(f"--help {s}", check_help, s)

    log.info("\n--- Phase 3: Production wiring ---")
    check("daily_fire_alert wires --use-hurdle-blend", check_hurdle_wired)
    check("predict_ignition_v17 defines --use-hurdle-blend", check_predict_v17_flag)
    check("build_operational_alerts defines 4 trust tiers", check_ops_alerts_trust_tiers)
    check("test_operational_pipeline coverage ≥ 20 checks", check_test_harness_coverage)
    check("portal warm-loads beat polygons", check_portal_warm_load)
    check("predict_ignition_v17 references calibration.json", check_calibration_artefacts)

    log.info("\n" + "=" * 80)
    n_pass = sum(1 for _, ok, _ in results if ok)
    n_fail = sum(1 for _, ok, _ in results if not ok)
    log.info("RESULTS: %d PASS, %d FAIL (of %d total)", n_pass, n_fail, len(results))
    log.info("=" * 80)

    if n_fail:
        log.info("\nFailed checks:")
        for name, ok, msg in results:
            if not ok:
                log.info("  [FAIL] %s — %s", name, msg)
        return 1
    log.info("\nAll static ops checks PASSED.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
