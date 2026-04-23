"""Sweep wind speeds through Cell2Fire and record burn area + max ROS.

If ROS scales linearly with wind speed, the wind model is correct and the
underprediction comes from fuel/moisture or from the ROS magnitude floor.
If ROS stays flat, the wind input isn't reaching the Rothermel calculation.
"""
from __future__ import annotations

import json
import sys
import shutil
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import src.utils.proj_fix  # noqa: F401

from src.analysis.cell2fire.engine import (  # noqa: E402
    Cell2FireConfig,
    _make_workdir,
)
from src.analysis.cell2fire.grid_exporter import export_cell2fire_inputs  # noqa: E402
from src.analysis.cell2fire.output_parser import (  # noqa: E402
    burn_area_ha,
    burn_mask_at_horizon,
    parse_grids_directory,
)
from src.analysis.cell2fire.runner import run_cell2fire  # noqa: E402
from src.analysis.cell2fire.weather_writer import write_weather_csv  # noqa: E402


FIRE = {
    "fire_lat": 24.19155,
    "fire_lon": 76.97570,
    "frp_mw": 5.76,
}


def run_once(wind_kmh: float, wind_dir: float, rh: float, temp: float) -> dict:
    cfg = Cell2FireConfig(keep_workdir=False)
    workdir = _make_workdir(cfg.workdir_root)
    instance_dir = workdir / "instance"
    output_dir = workdir / "output"
    try:
        export = export_cell2fire_inputs(
            fire_lat=FIRE["fire_lat"], fire_lon=FIRE["fire_lon"],
            output_dir=instance_dir,
            grid_size_px=cfg.grid_size_px, cell_size_m=cfg.cell_size_m,
        )
        write_weather_csv(
            weather={"wind_kmh": wind_kmh, "wind_dir_deg": wind_dir,
                     "temp_c": temp, "rh_pct": rh},
            output_path=instance_dir / "Weather.csv",
            horizon_hours=24,
        )
        run_result = run_cell2fire(
            instance_dir=instance_dir, output_dir=output_dir,
            timeout_s=cfg.timeout_s, horizon_hours=24,
        )
        if not run_result.success:
            return {"wind_kmh": wind_kmh, "error": run_result.reason}

        parsed = parse_grids_directory(output_dir=output_dir, sim_index=1)
        mask_24 = burn_mask_at_horizon(parsed, 1440)
        area_24 = burn_area_ha(mask_24, 30.0)

        # Parse Messages file for max ROS
        msgs = (output_dir / "Messages" / "MessagesFile1.csv")
        if msgs.exists():
            text = msgs.read_text(encoding="ascii").splitlines()
            ros_vals = [float(line.split(",")[3]) for line in text if line]
            max_ros = max(ros_vals) if ros_vals else 0.0
            mean_ros = sum(ros_vals) / len(ros_vals) if ros_vals else 0.0
        else:
            max_ros = mean_ros = 0.0

        return {
            "wind_kmh": wind_kmh,
            "rh_pct": rh,
            "area_24h_ha": round(area_24, 2),
            "burned_cells": int(mask_24.sum()),
            "max_ros_m_min": round(max_ros, 3),
            "mean_ros_m_min": round(mean_ros, 3),
            "n_messages": len(ros_vals) if msgs.exists() else 0,
        }
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


def main() -> int:
    print("=== WIND SWEEP (rh=16%, T=33C, dir=259) ===")
    print(f"{'ws_kmh':>8} {'area_ha':>10} {'cells':>7} "
          f"{'max_ros':>9} {'mean_ros':>9}")
    results = []
    for ws in (1, 3, 7.06, 15, 30, 60):
        r = run_once(ws, 259.0, 16.03, 33.33)
        results.append(r)
        if "error" in r:
            print(f"{ws:>8.2f}  error={r['error']}")
        else:
            print(f"{ws:>8.2f} {r['area_24h_ha']:>10.2f} "
                  f"{r['burned_cells']:>7} {r['max_ros_m_min']:>9.3f} "
                  f"{r['mean_ros_m_min']:>9.3f}")

    print()
    print("=== RH SWEEP (ws=7 km/h) ===")
    print(f"{'rh_pct':>8} {'area_ha':>10} {'cells':>7} "
          f"{'max_ros':>9} {'mean_ros':>9}")
    for rh in (5, 10, 20, 40, 80):
        r = run_once(7.06, 259.0, rh, 33.33)
        results.append(r)
        if "error" in r:
            print(f"{rh:>8.2f}  error={r['error']}")
        else:
            print(f"{rh:>8.2f} {r['area_24h_ha']:>10.2f} "
                  f"{r['burned_cells']:>7} {r['max_ros_m_min']:>9.3f} "
                  f"{r['mean_ros_m_min']:>9.3f}")

    out = ROOT / "data_lake" / "outputs_sample" / "c2f_wind_sweep.json"
    out.write_text(json.dumps(results, indent=2))
    print(f"\nSaved: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
