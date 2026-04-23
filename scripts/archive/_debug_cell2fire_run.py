"""Debug trace: keep workdir after a Cell2Fire run and inspect every output.

Used to diagnose why batch validation shows Cell2Fire 24h areas clustering
around ~100 ha regardless of fire size/weather (fingerprint of the empirical
ROS fallback being always triggered).

Dumps:
  * Instance dir contents (fuels/elevation/slope/aspect ASC + Weather.csv)
  * Run stdout/stderr
  * output_dir/Grids/Grids1/ForestGrid*.csv counts and cell-state histograms
  * parsed.burn_time_minutes statistics
  * per-horizon burn area
  * Whether _empirical_max_ros fell back
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import src.utils.proj_fix  # noqa: F401  must precede rasterio

from src.analysis.cell2fire.engine import (  # noqa: E402
    Cell2FireConfig,
    _empirical_max_ros,
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
from src.analysis.fire_physics import FirePhysicsEngine  # noqa: E402


FIRE = {
    "fire_lat": 24.19155,
    "fire_lon": 76.97570,
    "frp_mw": 5.76,
    "fire_date": "2018-04-19",
}

WEATHER = {
    "wind_kmh": 7.06,
    "wind_dir_deg": 259.0,
    "temp_c": 33.33,
    "rh_pct": 16.03,
}


def main() -> int:
    print("=== CELL2FIRE DEBUG TRACE ===")
    print(f"Fire    : {FIRE}")
    print(f"Weather : {WEATHER}")
    print()

    cfg = Cell2FireConfig(
        keep_workdir=True,
        workdir_root=ROOT / "data_lake" / "outputs_sample" / "c2f_debug",
    )
    workdir = _make_workdir(cfg.workdir_root)
    instance_dir = workdir / "instance"
    output_dir = workdir / "output"

    print(f"WORKDIR : {workdir}")
    print()

    # 1. Export
    export = export_cell2fire_inputs(
        fire_lat=FIRE["fire_lat"],
        fire_lon=FIRE["fire_lon"],
        output_dir=instance_dir,
        grid_size_px=cfg.grid_size_px,
        cell_size_m=cfg.cell_size_m,
    )
    print("=== EXPORT ===")
    print(f"  burnable_fraction : {export.burnable_fraction:.3f}")
    print(f"  centre_in_burnable: {export.centre_in_burnable}")
    print(f"  centre_row/col    : {export.centre_row}/{export.centre_col}")
    print(f"  grid_size_px      : {export.grid_size_px}")

    # Show fuels histogram
    from src.analysis.cell2fire.grid_exporter import _write_asc  # noqa: F401
    fuels_text = export.fuels_asc.read_text(encoding="ascii").splitlines()
    header = fuels_text[:6]
    data_rows = fuels_text[6:]
    fuels = np.array(
        [[int(x) for x in row.split()] for row in data_rows if row.strip()],
        dtype=np.int32,
    )
    unique, counts = np.unique(fuels, return_counts=True)
    print(f"  fuels shape       : {fuels.shape}")
    print("  fuel histogram    :")
    for u, c in zip(unique, counts):
        print(f"    {u}: {c} ({c / fuels.size * 100:.1f}%)")
    print(f"  centre fuel       : {fuels[export.centre_row, export.centre_col]}")
    print()

    # 2. Weather
    write_weather_csv(
        weather=WEATHER,
        output_path=instance_dir / "Weather.csv",
        horizon_hours=24,
    )
    print("=== WEATHER.csv ===")
    print((instance_dir / "Weather.csv").read_text(encoding="ascii")[:1000])
    print()

    # 3. Run
    run_result = run_cell2fire(
        instance_dir=instance_dir,
        output_dir=output_dir,
        timeout_s=cfg.timeout_s,
        horizon_hours=24,
    )
    print("=== RUN RESULT ===")
    print(f"  success    : {run_result.success}")
    print(f"  reason     : {run_result.reason}")
    print(f"  return_code: {run_result.return_code}")
    print(f"  binary     : {run_result.binary}")
    print(f"  duration_s : {run_result.duration_s}")
    print(f"  stdout (last 2000):\n{run_result.stdout[-2000:]}")
    print(f"  stderr (last 2000):\n{run_result.stderr[-2000:]}")
    print()

    # 4. Grids directory
    grids_dir = output_dir / "Grids"
    print("=== OUTPUT DIR CONTENTS ===")
    if output_dir.exists():
        for p in sorted(output_dir.rglob("*")):
            if p.is_file():
                try:
                    size = p.stat().st_size
                except OSError:
                    size = -1
                print(f"  {p.relative_to(output_dir)}  ({size} bytes)")
    else:
        print("  (output dir does not exist)")
    print()

    if not grids_dir.exists():
        print("NO Grids DIR — Cell2Fire didn't write spread output")
        return 1

    # 5. Parse
    try:
        parsed = parse_grids_directory(output_dir=output_dir, sim_index=1)
    except FileNotFoundError as e:
        print(f"parse failed: {e}")
        return 1

    bt = parsed.burn_time_minutes
    print("=== PARSED burn_time_minutes ===")
    print(f"  shape    : {bt.shape}")
    print(f"  snapshots: {len(parsed.snapshots)}")
    print(f"  nonzero  : {int((bt > 0).sum())} cells "
          f"({(bt > 0).sum() / max(bt.size, 1) * 100:.4f}%)")
    if (bt > 0).any():
        vals = bt[bt > 0]
        print(f"  min time : {int(vals.min())} min")
        print(f"  max time : {int(vals.max())} min")
        unique_times, cnts = np.unique(vals, return_counts=True)
        print("  burn-time histogram (first 15):")
        for ut, cc in list(zip(unique_times, cnts))[:15]:
            print(f"    t={int(ut):>5}min  count={int(cc)}")
    print()

    # 6. Per-horizon areas
    print("=== HORIZON AREAS ===")
    for h in (6, 12, 24):
        mask = burn_mask_at_horizon(parsed, h * 60)
        area = burn_area_ha(mask, 30.0)
        print(f"  {h:>3}h: {int(mask.sum())} cells = {area:.2f} ha")
    print()

    # 7. Empirical ROS
    physics = FirePhysicsEngine()
    seed = physics.frp_to_ros(FIRE["frp_mw"])
    ros = _empirical_max_ros(parsed, cell_size_m=30.0, fallback_m_min=seed)
    print("=== EMPIRICAL ROS ===")
    print(f"  FRP-seed ROS : {seed:.3f} m/min")
    print(f"  empirical ROS: {ros:.3f} m/min")
    print(f"  fallback fired? {abs(ros - seed) < 1e-9}")
    print()

    # 8. Snapshot-by-snapshot
    print("=== SNAPSHOT burn counts ===")
    for snap in parsed.snapshots[:30]:
        n = int((snap.grid >= 1).sum())
        print(f"  period {snap.period_index:>3}  t={snap.minutes_since_ignition:>5}min  burned={n}")
    print()

    print(f"Workdir preserved at: {workdir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
