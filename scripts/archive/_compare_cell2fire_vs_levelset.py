"""Side-by-side comparison: Cell2Fire vs level-set physics on identical input.

Runs both spread engines on the same Madhya Pradesh fire detection and prints
horizon areas + relative differences. Used to validate Task #9.
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

logging.basicConfig(
    level=logging.WARNING,
    format="%(levelname)s %(name)s: %(message)s",
)

from src.analysis.spread_predictor import SpreadPredictor  # noqa: E402


def _summarise(name: str, result: dict) -> dict[str, float]:
    out = {}
    for h in (6, 12, 24):
        key = f"spread_{h}h"
        sub = result.get(key, {})
        out[f"{h}h_ha"] = float(sub.get("area_ha", 0.0))
        out[f"{h}h_max_ros"] = float(sub.get("max_ros_m_min", 0.0))
    out["intensity_kw_m"] = float(result.get("byram_intensity_kw_m", 0.0))
    out["flame_m"] = float(result.get("flame_length_m", 0.0))
    out["mode"] = str(result.get("mode", "?"))
    print(
        f"  {name:>10}: 6h={out['6h_ha']:7.2f}ha  "
        f"12h={out['12h_ha']:7.2f}ha  "
        f"24h={out['24h_ha']:7.2f}ha  "
        f"max_ros={out['24h_max_ros']:.3f} m/min  "
        f"intensity={out['intensity_kw_m']:.0f} kW/m  "
        f"mode={out['mode']}"
    )
    return out


def main() -> int:
    fire = {"fire_lat": 24.65, "fire_lon": 77.30, "frp_mw": 25.0}
    weather = {
        "wind_kmh": 12.0,
        "wind_dir_deg": 225.0,
        "temp_c": 36.0,
        "rh_pct": 28.0,
    }

    print("=== INPUT ===")
    print(f"  fire   : {fire}")
    print(f"  weather: {weather}")
    print()

    # --- Level-set / Rothermel physics ---
    print("=== ENGINE OUTPUTS ===")
    physics_predictor = SpreadPredictor(engine="physics")
    physics_result = physics_predictor.predict(fire, weather)
    physics = _summarise("level-set", physics_result)

    # --- Cell2Fire ---
    c2f_predictor = SpreadPredictor(engine="cell2fire")
    c2f_result = c2f_predictor.predict(fire, weather)
    c2f = _summarise("cell2fire", c2f_result)

    # --- Comparison ---
    print()
    print("=== RELATIVE COMPARISON (cell2fire / level-set) ===")
    for h in (6, 12, 24):
        a_ls = physics[f"{h}h_ha"]
        a_c2 = c2f[f"{h}h_ha"]
        ratio = a_c2 / a_ls if a_ls > 0 else float("nan")
        delta = a_c2 - a_ls
        print(
            f"  {h:>2}h area : level-set={a_ls:7.2f}ha  "
            f"cell2fire={a_c2:7.2f}ha  "
            f"ratio={ratio:5.2f}  delta={delta:+7.2f} ha"
        )

    if c2f["mode"] != "cell2fire":
        print()
        print("WARNING: Cell2Fire engine fell back to physics — see logs above.")
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
