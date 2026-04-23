"""Annual refresh of beat-level fire climatology for the coverage floor.

Slides the 5-year FIRMS window to end at (current_year - 1) and rewrites
`data_lake/fire_weather/beat_fire_climatology.parquet`.

Idempotent: if the parquet already covers the correct window
(`{current_year-5}–{current_year-1}`) the script logs a no-op and exits 0.

Usage:
    python scripts/refresh_climatology_history.py           # use current year
    python scripts/refresh_climatology_history.py --year 2027  # override year

How it calls the builder:
    Monkey-patches `HISTORY_YEARS` in `scripts.build_beat_fire_climatology` via
    an environment variable (`CLIM_HISTORY_YEARS`) read at import time, then
    invokes `build_beat_fire_climatology.main()` directly in the same process.
    This avoids subprocess spawning issues on Windows while remaining explicit
    about what changes.

Diff logging:
    After the new parquet is written, compares (Division, Beat, week_of_year)
    tuples between old and new; reports beats where `total_fires` changed by
    more than 10 %.
"""
from __future__ import annotations

import argparse
import logging
import os
import shutil
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd

# ── project root on sys.path ────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("refresh_climatology")

# ── paths ────────────────────────────────────────────────────────────────────
CLIM_PARQUET = ROOT / "data_lake" / "fire_weather" / "beat_fire_climatology.parquet"
METADATA_FILE = ROOT / "data_lake" / "fire_weather" / "beat_fire_climatology_metadata.json"

# Number of years in the sliding window (matches build_beat_fire_climatology.py)
WINDOW_SIZE = 5

# Fractional change threshold that is considered a "meaningful" drift
DRIFT_THRESHOLD = 0.10  # 10 %


# ── helpers ──────────────────────────────────────────────────────────────────

def _build_window(current_year: int) -> tuple[int, ...]:
    """Return the HISTORY_YEARS tuple for the given current year."""
    end = current_year - 1
    return tuple(range(end - WINDOW_SIZE + 1, end + 1))


def _window_label(years: tuple[int, ...]) -> str:
    return f"{min(years)}-{max(years)}"


def _load_metadata() -> dict:
    """Return persisted refresh metadata, or an empty dict if not found."""
    import json

    if not METADATA_FILE.exists():
        return {}
    try:
        return json.loads(METADATA_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_metadata(data: dict) -> None:
    import json

    METADATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    METADATA_FILE.write_text(
        json.dumps(data, indent=2, default=str), encoding="utf-8"
    )


def _is_already_current(target_window: tuple[int, ...]) -> bool:
    """Return True if the parquet already covers the target window exactly."""
    if not CLIM_PARQUET.exists():
        return False
    meta = _load_metadata()
    return meta.get("history_years") == list(target_window)


def _backup_existing(target_window: tuple[int, ...]) -> Path | None:
    """Copy existing parquet to a dated backup; return the backup path or None."""
    if not CLIM_PARQUET.exists():
        return None
    # Label the backup with the OLD window, derived from the current metadata
    meta = _load_metadata()
    old_years = meta.get("history_years")
    if old_years:
        old_label = f"{min(old_years)}-{max(old_years)}"
    else:
        old_label = "unknown"
    backup_path = CLIM_PARQUET.with_name(
        f"beat_fire_climatology_{old_label}.parquet"
    )
    shutil.copy2(CLIM_PARQUET, backup_path)
    log.info("Backed up existing parquet → %s", backup_path.name)
    return backup_path


def _compute_drift(
    old_path: Path | None,
    new_df: pd.DataFrame,
) -> None:
    """Log (Division, Beat, week_of_year) rows where total_fires changed > 10 %."""
    if old_path is None or not old_path.exists():
        log.info("No previous parquet to diff against — skipping drift report.")
        return

    try:
        old_df = pd.read_parquet(old_path)
    except Exception as exc:
        log.warning("Could not read backup for drift comparison: %s", exc)
        return

    key_cols = ["Division", "Beat", "week_of_year"]
    for col in key_cols:
        if col not in old_df.columns or col not in new_df.columns:
            log.warning("Drift comparison skipped — key column %r missing.", col)
            return

    # Merge on natural key; only common rows are compared
    merged = pd.merge(
        old_df[key_cols + ["total_fires"]].rename(columns={"total_fires": "fires_old"}),
        new_df[key_cols + ["total_fires"]].rename(columns={"total_fires": "fires_new"}),
        on=key_cols,
        how="inner",
    )
    if merged.empty:
        log.info("Drift: no overlapping (Beat, week) cells found between old and new.")
        return

    denom = merged["fires_old"].clip(lower=1)  # avoid division by zero
    merged["rel_change"] = (merged["fires_new"] - merged["fires_old"]).abs() / denom
    drifted = merged[merged["rel_change"] > DRIFT_THRESHOLD].sort_values(
        "rel_change", ascending=False
    )

    n_total = len(merged)
    n_drifted = len(drifted)
    log.info(
        "Drift report: %d / %d (Beat, week) cells changed > %.0f%% in total_fires.",
        n_drifted,
        n_total,
        DRIFT_THRESHOLD * 100,
    )
    if n_drifted == 0:
        return

    log.info("Top drifters (max 20 shown):")
    for _, row in drifted.head(20).iterrows():
        direction = "up" if row["fires_new"] > row["fires_old"] else "down"
        log.info(
            "  W%02d  %-30s / %-20s  %d → %d fires  (%+.0f%%, %s)",
            int(row["week_of_year"]),
            str(row["Division"]),
            str(row["Beat"]),
            int(row["fires_old"]),
            int(row["fires_new"]),
            row["rel_change"] * 100,
            direction,
        )


def _run_builder(target_years: tuple[int, ...]) -> int:
    """Inject HISTORY_YEARS into build_beat_fire_climatology and run main().

    Replaces the module-level constant before calling main() so no subprocess
    or file patching is required.  The module is reloaded if it was previously
    imported to ensure a clean state.
    """
    import importlib

    # Force reimport to pick up fresh constant values
    module_name = "scripts.build_beat_fire_climatology"
    if module_name in sys.modules:
        del sys.modules[module_name]

    # Temporarily expose the desired years via environment so the module reads
    # it at import time (belt-and-suspenders alongside the attribute patch below)
    os.environ["CLIM_HISTORY_YEARS"] = ",".join(str(y) for y in target_years)
    try:
        import scripts.build_beat_fire_climatology as builder
        # Patch the module-level tuple AFTER import (importlib does not re-exec
        # frozen compiled modules, so we patch the live attribute directly)
        builder.HISTORY_YEARS = target_years
        log.info(
            "Calling build_beat_fire_climatology.main() with HISTORY_YEARS=%s",
            target_years,
        )
        return builder.main()
    finally:
        os.environ.pop("CLIM_HISTORY_YEARS", None)


# ── main ─────────────────────────────────────────────────────────────────────

def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Annually refresh the beat-level fire climatology parquet."
    )
    ap.add_argument(
        "--year",
        type=int,
        default=datetime.now().year,
        help="Current year for window calculation (default: %(default)s).",
    )
    ap.add_argument(
        "--force",
        action="store_true",
        help="Re-run even if the parquet is already up to date.",
    )
    args = ap.parse_args(argv)

    current_year: int = args.year
    target_window = _build_window(current_year)
    window_label = _window_label(target_window)

    log.info("=" * 60)
    log.info("JwalaNetra climatology refresh — %s", datetime.now().strftime("%Y-%m-%d"))
    log.info("Current year : %d", current_year)
    log.info("Target window: %s  %s", target_window, window_label)
    log.info("=" * 60)

    # Idempotency check
    if not args.force and _is_already_current(target_window):
        log.info(
            "Parquet already covers window %s — nothing to do. "
            "Pass --force to re-run anyway.",
            window_label,
        )
        return 0

    # Back up existing parquet before overwriting
    backup_path = _backup_existing(target_window)

    # Run the builder with the new window
    rc = _run_builder(target_window)
    if rc != 0:
        log.error(
            "build_beat_fire_climatology.main() returned exit code %d — "
            "parquet NOT updated.",
            rc,
        )
        return rc

    # Load the freshly written parquet for drift comparison
    try:
        new_df = pd.read_parquet(CLIM_PARQUET)
    except Exception as exc:
        log.warning("Could not read new parquet for drift report: %s", exc)
        new_df = pd.DataFrame()

    # Report cells that changed materially
    _compute_drift(backup_path, new_df)

    # Persist metadata so future runs can detect idempotent state
    _save_metadata(
        {
            "history_years": list(target_window),
            "window_label": window_label,
            "refreshed_at": datetime.now().isoformat(),
            "n_rows": len(new_df),
            "parquet_path": str(CLIM_PARQUET),
        }
    )

    log.info(
        "Climatology refresh complete. New parquet has %d rows (window %s).",
        len(new_df),
        window_label,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
