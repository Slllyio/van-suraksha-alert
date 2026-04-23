"""End-to-end smoke test for Cell2Fire engine integration.

Runs predict_spread() against a synthetic Madhya Pradesh fire detection
and reports horizon polygons / areas. Used to validate Task #9.
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s %(name)s: %(message)s",
)

from src.analysis.cell2fire.engine import (  # noqa: E402
    Cell2FireConfig,
    Cell2FireUnavailable,
    predict_spread,
)


def main() -> int:
    # A real-ish Guna forest pixel
    fire = {"fire_lat": 24.65, "fire_lon": 77.30, "frp_mw": 25.0}
    weather = {
        "wind_kmh": 12.0,
        "wind_dir_deg": 225.0,
        "temp_c": 36.0,
        "rh_pct": 28.0,
    }

    cfg = Cell2FireConfig(
        grid_size_px=64,
        cell_size_m=30.0,
        timeout_s=180,
        keep_workdir=True,  # keep so we can inspect the run if needed
    )

    try:
        result = predict_spread(fire, weather, config=cfg)
    except Cell2FireUnavailable as exc:
        print(f"CELL2FIRE_UNAVAILABLE: {exc}")
        return 1
    except Exception as exc:  # noqa: BLE001
        import traceback
        traceback.print_exc()
        print(f"OTHER_ERROR: {type(exc).__name__}: {exc}")
        return 2

    print("=== CELL2FIRE RESULT ===")
    for key, val in result.items():
        if isinstance(val, dict) and "polygon" in val:
            poly = val["polygon"]
            coords = poly.get("coordinates", [])
            n_pts = len(coords)
            print(
                f"  {key}: area={val['area_ha']} ha "
                f"max_ros={val['max_ros_m_min']} m/min "
                f"polygon={poly.get('type', 'none')}({n_pts} rings/parts)"
            )
        else:
            print(f"  {key}: {val}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
