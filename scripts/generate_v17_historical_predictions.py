"""Generate v17 predictions for all Thursdays in a fire season window.

Used to expand the offset-correlation analysis to multi-year data.
"""
from __future__ import annotations

import logging
import subprocess
import sys
from datetime import date, timedelta
from pathlib import Path

sys.stdout.reconfigure(line_buffering=True)
logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger()

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "tmp" / "v17_historical"
OUT_DIR.mkdir(parents=True, exist_ok=True)

SEASONS: dict[int, tuple[date, date]] = {
    2024: (date(2024, 2, 1), date(2024, 5, 31)),
}


def thursdays_in(start: date, end: date) -> list[date]:
    """All Thursdays (weekday=3) between start and end inclusive."""
    d = start
    while d.weekday() != 3:
        d += timedelta(days=1)
    out = []
    while d <= end:
        out.append(d)
        d += timedelta(days=7)
    return out


def main() -> int:
    for year, (start, end) in SEASONS.items():
        thursdays = thursdays_in(start, end)
        log.info("Year %d: %d Thursdays from %s to %s",
                 year, len(thursdays), thursdays[0], thursdays[-1])
        for t in thursdays:
            out = OUT_DIR / f"ignition_risk_v17_{t}.json"
            if out.exists():
                log.info("  [SKIP] %s already exists", t)
                continue
            log.info("  Predicting %s...", t)
            r = subprocess.run(
                [sys.executable, "scripts/predict_ignition_v17.py",
                 "--date", str(t), "--output", str(out)],
                cwd=str(ROOT), capture_output=True, text=True, timeout=120,
            )
            if r.returncode != 0:
                log.error("  FAIL %s: %s", t, r.stderr[-200:])
                continue
            log.info("  OK %s", t)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
